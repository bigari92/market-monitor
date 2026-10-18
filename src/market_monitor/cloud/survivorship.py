"""RECOVERY.md defect 1 — the survivor-only universe — bounded rather than fixed.

> **1. Survivorship.** `build_universe.py` fetches the NASDAQ Trader symbol directory **live**,
> so the universe is today's listings only. Delisted companies are absent, which is exactly
> where a cheapness signal's apparent edge hides. This is structural.

"Structural" is right, and this module does not pretend otherwise. It cannot recover the missing
returns, because the data to recover them is not available free at any effort — see
`results/survivorship.md` §2 for the measurement that establishes that. What it *can* do is put
a bound on how wrong the survivor-only numbers are, which is the whole of package C3:

> **C3.** Survivorship **bound** at three imputation severities, reported beside the
> survivor-only baseline.

## The bound, and why it needs no prices

Let `f` be the fraction of a cross-section that delists inside the forward window, and `r` the
return attributed to a delisted name. Two cases bracket the truth, and both are closed-form:

**Pessimistic — the signal has no ability to avoid delistings.** They enter the top N at the
same rate as everything else:

    top_adj    = (1 - f) * top_mean    + f * r
    cohort_adj = (1 - f) * cohort_mean + f * r
    excess_adj = top_adj - cohort_adj  = (1 - f) * excess

The imputed return **cancels**. The measured excess is simply overstated by `1 / (1 - f)`,
whatever `r` is. This is the case that matters and it is strikingly simple: at `f = 0.10` the
measured edge is 11% too high, and no assumption about how badly delisted names did changes it.

**Optimistic — the signal excludes every delisting.** The top N is untouched while the cohort
it is measured against gets worse:

    excess_adj = top_mean - [(1 - f) * cohort_mean + f * r] = excess + f * (cohort_mean - r)

Since `r < cohort_mean`, this *raises* the excess. A perfect loser-filter is flattered by
survivorship bias being removed, not hurt by it.

**So the sign of the bias depends entirely on how good the filter is at avoiding deaths**, and
the project's own thesis is that the filter is good at exactly that (`results/horizon_test.md`:
the edge is a 1.9x cut in the down-tail and no up-tail lift at all). That makes the optimistic
end less absurd than it first sounds — but it is still an assumption, and the pessimistic end
is the one to plan against.

## What `f` is, and why the estimate here is a floor

`f` is measured from Form 25 filings — the SEC notification that a security has been removed
from an exchange — against the size of the listed universe. Two reasons it is a **floor** for
this strategy rather than a central estimate:

1. Form 25 is filed per *security*, not per company, and some are warrants, units or preferred
   lines whose common stock stays listed, so the raw count must be filtered to companies that
   actually left (see `delisting_rate`).
2. The volatility gate selects the fragile end of the market on purpose. A cohort chosen for
   being capable of large moves delists more often than the average listed name, and that
   cohort-specific rate **cannot be measured here** — it would need the delisted tickers, which
   is the thing that is unavailable. So `f` understates the cohort's true rate by an unknown
   margin.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# The three severities C3 asks for. A delisted name is not automatically a total loss — most
# delistings are acquisitions, which are often at a premium — so a single assumption would be
# wrong in either direction and three are reported.
SEVERITIES = {
    "total_loss": -1.00,        # the name went to zero
    "severe": -0.50,            # halved, the shape of a distressed delisting
    "neutral": None,            # the cohort's own median: delisting carries no return signal
}


@dataclass(frozen=True)
class Bound:
    """A measured excess with its survivorship bracket. Both ends, never one number."""
    measured_excess_pp: float
    delisting_rate: float
    severity: str
    imputed_return: float
    pessimistic_pp: float       # the signal cannot avoid delistings
    optimistic_pp: float        # the signal avoids all of them
    overstatement_factor: float  # measured / pessimistic

    def as_row(self) -> dict:
        return {
            "severity": self.severity,
            "imputed_return": self.imputed_return,
            "delisting_rate_f": self.delisting_rate,
            "measured_excess_pp": round(self.measured_excess_pp, 3),
            "pessimistic_pp": round(self.pessimistic_pp, 3),
            "optimistic_pp": round(self.optimistic_pp, 3),
            "overstatement_x": round(self.overstatement_factor, 3),
        }


def bound_excess(measured_excess_pp: float, cohort_mean_pp: float, delisting_rate: float,
                 severity: str = "severe") -> Bound:
    """Bracket a measured excess return for survivorship, at one severity.

    `measured_excess_pp` and `cohort_mean_pp` are in percentage points over the same horizon as
    `delisting_rate` (both annual, or both per-quarter — not mixed).
    """
    if not 0.0 <= delisting_rate < 1.0:
        raise ValueError(f"delisting_rate must be in [0, 1), got {delisting_rate}")
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(SEVERITIES)}, got {severity!r}")

    imputed = SEVERITIES[severity]
    imputed_pp = cohort_mean_pp if imputed is None else 100.0 * imputed

    pessimistic = (1.0 - delisting_rate) * measured_excess_pp
    optimistic = measured_excess_pp + delisting_rate * (cohort_mean_pp - imputed_pp)
    factor = measured_excess_pp / pessimistic if pessimistic else float("inf")

    return Bound(measured_excess_pp=measured_excess_pp, delisting_rate=delisting_rate,
                 severity=severity, imputed_return=imputed_pp / 100.0,
                 pessimistic_pp=pessimistic, optimistic_pp=optimistic,
                 overstatement_factor=factor)


def bound_table(measured_excess_pp: float, cohort_mean_pp: float,
                delisting_rate: float) -> pd.DataFrame:
    """All three severities beside the survivor-only baseline. C3's deliverable."""
    rows = [bound_excess(measured_excess_pp, cohort_mean_pp, delisting_rate, s).as_row()
            for s in ("total_loss", "severe", "neutral")]
    return pd.DataFrame(rows)


def delisting_rate(form25: pd.DataFrame, live_ciks: set[int],
                   ticker_present: dict[int, bool] | None = None,
                   universe_size: int = 6939) -> pd.DataFrame:
    """Annual delisting rate from Form 25 filings, filtered to companies that actually left.

    A raw Form 25 count overstates company deaths: the form is filed per security, so a
    delisted warrant, unit or preferred line counts even when the common stock stays listed,
    and it is also filed when a company moves between exchanges.

    Two filters, in increasing strictness:
      * `raw` — every Form 25 filing.
      * `distinct_cik` — one per company per year.
      * `gone` — the company is not in today's listed universe, and (where
        `ticker_present` is supplied from the SEC submissions bulk) SEC has cleared its ticker,
        which it does on deregistration. This is the closest free proxy for "the company left
        and did not come back".
    """
    frame = form25.copy()
    frame["is_live"] = frame["cik"].isin(live_ciks)
    if ticker_present is not None:
        mapped = frame["cik"].map(ticker_present).astype("boolean").fillna(False)
        frame["ticker_cleared"] = ~mapped.astype(bool)
    else:
        frame["ticker_cleared"] = ~frame["is_live"]

    rows = []
    for year, group in frame.groupby("year"):
        distinct = group["cik"].nunique()
        gone = group.loc[~group["is_live"] & group["ticker_cleared"], "cik"].nunique()
        rows.append({
            "year": int(year),
            "form25_filings": len(group),
            "distinct_ciks": distinct,
            "gone_and_ticker_cleared": gone,
            "rate_distinct_%": round(100 * distinct / universe_size, 2),
            "rate_gone_%": round(100 * gone / universe_size, 2),
        })
    return pd.DataFrame(rows)
