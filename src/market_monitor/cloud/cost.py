"""The cost model — RECOVERY.md defect 4, the last of the four.

> **4. No cost model.** Nothing deducts commission, spread or tax anywhere.

Every return figure this project has produced is gross. That matters more here than it would for
a slower strategy, for two measured reasons:

- **The volatility gate selects the wide-spread end of the market on purpose.** Costs are not a
  uniform haircut; they fall hardest on exactly the cohort the signal ranks.
- **The tracker's measured turnover is 3.12x a year**, not the 1x a 12-month hold implies — 26%
  of the watchlist exits per month across the 24-run replay, an average holding period of about
  four months. Cost scales with turnover, so this multiplies the haircut threefold.

## What this module does and does not claim

It computes **execution cost**: commission, spread, and market impact. It does **not** compute
tax — see `TAX_IS_OUT_OF_SCOPE` below for why that is a boundary rather than an omission.

Spread is **estimated, not observed.** No free feed carries quotes, so it is reconstructed from
the daily range by two independent published estimators, both reported:

- **Corwin & Schultz (2012)**, from consecutive daily high-low ranges. Well known, and known to
  be noisy for individual names; negative estimates are floored at zero, which biases it upward.
- **Abdi & Ranaldo (2017)**, from close against the log midrange. Less prone to the
  overnight-return contamination that inflates Corwin-Schultz, but its estimator is a variance
  that can come out negative in a short sample, and the convention floors those at zero.

Two estimators rather than one for the same reason the horizon test reports three standard
errors: when they agree the conclusion is not an artefact of either. **Measured, they disagree
at short windows and converge at long ones**, and the window is what decides it:

| window | Corwin-Schultz | Abdi-Ranaldo | names where AR floored to zero |
|---|---|---|---|
| 21d | 107 bps | 22 bps | 48% |
| 252d | 116 bps | 35 bps | 36% |
| **504d** | **99 bps** | **96 bps** | **12%** |

So the ~100 bps figure is the one both estimators support, and anything computed from a short
window is Corwin-Schultz alone wearing a second name. `DEFAULT_WINDOW` is 504 for that reason.
Where they still disagree the wider is used, because the cost of underestimating cost is a
strategy that looks profitable and is not.

## The conclusion does not rest on the estimate

`break_even_cost_bps` inverts the question: rather than asking "what is the spread", it asks
"how wide would the round trip have to be to erase the measured gross excess". That number is
independent of any estimator, so the verdict survives even if both estimators are wrong.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

K_CS = 3.0 - 2.0 * np.sqrt(2.0)      # Corwin-Schultz constant, ~0.17157

# Two trading years. Short windows make Abdi-Ranaldo floor to zero on up to half the names
# (its estimator is a variance that goes negative in small samples), which silently collapses
# the two-estimator check into one. At 504 days the two agree to within 3 bps on this cohort.
# A spread used for a cost model wants to be a stable average anyway, not a responsive one.
DEFAULT_WINDOW = 504

TAX_IS_OUT_OF_SCOPE = """\
Tax is deliberately not modelled here, and that is a scope boundary rather than an oversight.

A realised-gain tax depends on the owner's jurisdiction, account type, other income, holding
periods and loss carry-forwards. None of that is public data, none of it belongs in this
repository (CLOUD-RULES.md §3: no personal financial data, ever), and a cloud session cannot see
it. A number invented here would be worse than a blank, because it would be carried forward as
fact.

What this module provides instead is `after_tax_drag`, which takes a rate the owner supplies and
applies it to the gross excess. The rate has no default on purpose: the function requires one.
Note also that a 4-month average holding period is short-term in most jurisdictions, so a higher
rate than a buy-and-hold investor would pay. That interacts with turnover, which is the thing
this module measures."""


# --- commission ------------------------------------------------------------


@dataclass(frozen=True)
class CommissionSchedule:
    """A published per-share commission schedule.

    Defaults are Interactive Brokers' advertised US-stock **fixed** tier: USD 0.005 per share,
    USD 1.00 minimum per order, capped at 1% of trade value. They are a documented rate card,
    **not** a claim about which plan the owner is on or what he actually pays — this repository
    has no access to his account and must not (CLOUD-RULES.md §3). Substitute real numbers to get
    real answers.
    """

    per_share: float = 0.005
    min_per_order: float = 1.00
    max_pct_of_value: float = 0.01
    name: str = "IBKR fixed tier (advertised)"

    def per_order(self, price: float, position_value: float) -> float:
        """Commission in currency for one order."""
        if price <= 0 or position_value <= 0:
            return 0.0
        shares = position_value / price
        fee = max(self.per_share * shares, self.min_per_order)
        return min(fee, self.max_pct_of_value * position_value)

    def bps(self, price: float, position_value: float) -> float:
        """Commission for one order, in basis points of position value."""
        if position_value <= 0:
            return 0.0
        return 1e4 * self.per_order(price, position_value) / position_value


def commission_bps_for_portfolio(prices: pd.Series, portfolio_value: float,
                                 positions: int,
                                 schedule: CommissionSchedule | None = None) -> float:
    """Average one-way commission in bps for an equal-weighted book of `positions` names.

    Position size is what decides this, and it is why portfolio value is a parameter. At USD
    1.00 per order minimum, a small position pays the minimum rather than the per-share rate:
    a USD 400 position is 25 bps of commission, a USD 40,000 position is under 1 bp. The
    per-share rate only binds once positions are large.
    """
    schedule = schedule or CommissionSchedule()
    if positions <= 0 or portfolio_value <= 0:
        return 0.0
    position_value = portfolio_value / positions
    valid = prices.dropna()
    valid = valid[valid > 0]
    if valid.empty:
        return 0.0
    return float(np.mean([schedule.bps(price, position_value) for price in valid]))


# --- spread, estimated from the daily range --------------------------------


def corwin_schultz_spread(high: pd.DataFrame, low: pd.DataFrame,
                          window: int = DEFAULT_WINDOW) -> pd.Series:
    """Corwin-Schultz (2012) effective spread, as a fraction of price, averaged over `window`.

    Uses consecutive two-day high-low ranges to separate the spread from volatility. Per-pair
    negative estimates are floored at zero, which is the convention in the original paper and
    which biases the result **upward** — stated because that direction flatters cost, not the
    strategy.
    """
    high = high.replace(0, np.nan)
    low = low.replace(0, np.nan)
    log_range = np.log(high / low) ** 2

    # beta: the two single-day squared log ranges summed over days t and t+1.
    beta = log_range + log_range.shift(-1)
    # gamma: the squared log range of the two days treated as one period.
    high_2 = pd.concat([high, high.shift(-1)]).groupby(level=0).max()
    low_2 = pd.concat([low, low.shift(-1)]).groupby(level=0).min()
    gamma = np.log(high_2 / low_2) ** 2

    alpha = ((np.sqrt(2.0 * beta) - np.sqrt(beta)) / K_CS
             - np.sqrt(gamma.clip(lower=0) / K_CS))
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    spread = spread.clip(lower=0.0)            # the paper's convention
    return spread.iloc[-window:].mean()


def abdi_ranaldo_spread(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                        window: int = DEFAULT_WINDOW) -> pd.Series:
    """Abdi-Ranaldo (2017) effective spread, as a fraction of price, over `window`.

    s^2 = 4 * E[(c_t - eta_t) * (c_t - eta_{t+1})], where eta is the log midrange. It compares
    a close against the midranges either side of it, so a large overnight move does not
    masquerade as a spread.

    The expectation can come out negative in a short sample, and the convention floors it at
    zero — which on a 21-day window happens for ~48% of this cohort and makes the estimator
    useless. See `DEFAULT_WINDOW`.
    """
    close = close.replace(0, np.nan)
    high = high.replace(0, np.nan)
    low = low.replace(0, np.nan)

    log_close = np.log(close)
    eta = (np.log(high) + np.log(low)) / 2.0
    product = 4.0 * (log_close - eta) * (log_close - eta.shift(-1))
    mean_sq = product.iloc[-window:].mean()
    return np.sqrt(mean_sq.clip(lower=0.0))


def spread_estimates(bars, as_of, tickers: list[str] | None = None,
                     window: int = DEFAULT_WINDOW) -> pd.DataFrame:
    """Both estimators for every ticker, in basis points, as of `as_of`.

    Returns [cs_bps, ar_bps, used_bps], where `used_bps` is the larger of the two: the cost of
    underestimating cost is a strategy that looks profitable and is not. `ar_floored` flags the
    names where Abdi-Ranaldo hit zero, so a reader can see when the pair has collapsed to one.
    """
    require_high_low(bars)
    as_of = pd.Timestamp(as_of)
    close = bars.close.loc[:as_of]
    high = bars.high.loc[:as_of]
    low = bars.low.loc[:as_of]
    if tickers is not None:
        keep = [t for t in tickers if t in close.columns]
        close, high, low = close[keep], high[keep], low[keep]

    cs = corwin_schultz_spread(high, low, window) * 1e4
    ar = abdi_ranaldo_spread(close, high, low, window) * 1e4
    frame = pd.DataFrame({"cs_bps": cs, "ar_bps": ar})
    frame["used_bps"] = frame[["cs_bps", "ar_bps"]].max(axis=1)
    frame["ar_floored"] = frame["ar_bps"] <= 0
    return frame


def require_high_low(bars) -> None:
    """Refuse to estimate a spread from a panel that has no range data.

    A panel cached before the cost model existed carries no high/low. Silently returning zero
    would make every strategy look costless, which is the failure this whole file exists to
    prevent.
    """
    if getattr(bars, "high", None) is None or getattr(bars, "low", None) is None:
        raise ValueError(
            "this panel has no high/low, so no spread can be estimated. Re-fetch with a feed "
            "that supplies them (`run --refresh`) rather than treating the spread as zero."
        )


# --- market impact ---------------------------------------------------------


def impact_bps(position_value: float, adv_usd: pd.Series, daily_vol: float = 0.03,
               coefficient: float = 1.0) -> float:
    """One-way square-root market impact in bps: coefficient * sigma_daily * sqrt(Q / ADV).

    The conventional functional form (Almgren et al., Kyle), and it is **scaled by volatility
    on purpose**: impact is paid in units of the stock's own variability, so the same
    participation rate costs more in a volatile name than a quiet one. That matters here
    specifically, because the volatility gate selects the volatile end of the market — an impact
    model that ignored volatility would understate cost for exactly this cohort.

    `coefficient` is order-one by convention. This is an order-of-magnitude device, not a
    calibrated model; `daily_vol` should be the cohort's own, not a market average.

    It is included to show impact is *small relative to spread* here rather than to assume so:
    the liquidity gate requires ADV >= USD 5m, so a sane position is a small slice of a day's
    volume. If it ever stops being small, the portfolio has outgrown the gate.
    """
    adv = adv_usd.dropna()
    adv = adv[adv > 0]
    if adv.empty or position_value <= 0 or daily_vol <= 0:
        return 0.0
    participation = position_value / adv
    return float(coefficient * daily_vol * np.sqrt(participation).mean() * 1e4)


# --- putting it together ---------------------------------------------------


@dataclass(frozen=True)
class CostAssumptions:
    """Everything the drag calculation needs, stated in one place so it can be printed."""
    portfolio_value: float
    positions: int
    annual_turnover: float
    commission: CommissionSchedule
    spread_source: str = "max(Corwin-Schultz, Abdi-Ranaldo), 21-day window"


def round_trip_bps(commission_one_way_bps: float, spread_bps: float,
                   impact_one_way_bps: float = 0.0) -> float:
    """Cost of one full round trip, in bps of position value.

    Commission and impact are paid twice (in and out). The spread is paid **once** per round
    trip, not twice: buying at the ask and selling at the bid costs the full quoted spread
    between them, and `spread_bps` already is the full effective spread rather than a half.
    """
    return 2.0 * commission_one_way_bps + spread_bps + 2.0 * impact_one_way_bps


def annual_drag_bps(round_trip: float, annual_turnover: float) -> float:
    """Annual cost drag in bps: one round trip per unit of turnover."""
    return round_trip * annual_turnover


def break_even_cost_bps(gross_excess_pp: float, annual_turnover: float) -> float:
    """The round-trip cost that would exactly erase a gross annual excess.

    The number that makes the verdict independent of the spread estimate. `gross_excess_pp` is
    in percentage points per year; the result is bps per round trip.
    """
    if annual_turnover <= 0:
        return float("inf")
    return (gross_excess_pp * 100.0) / annual_turnover


def after_tax_drag(gross_excess_pp: float, drag_pp: float, tax_rate: float) -> float:
    """Net excess after execution cost and a tax rate the OWNER supplies.

    `tax_rate` is required and has no default: see `TAX_IS_OUT_OF_SCOPE`. Applied to the
    post-cost excess, which assumes the whole excess is realised as a taxable gain in the year —
    a simplification that is conservative for a ~4-month holding period and wrong for anyone
    holding in a sheltered account.
    """
    if not 0.0 <= tax_rate < 1.0:
        raise ValueError(f"tax_rate must be in [0, 1), got {tax_rate}")
    return (gross_excess_pp - drag_pp) * (1.0 - tax_rate)


def measure_turnover(runs: pd.DataFrame) -> dict:
    """Annualised turnover from a tracking or replay record's own runs.csv.

    Measured, not assumed, and it is the input the whole drag calculation scales with. Exits per
    run over watchlist size gives the monthly replacement rate; the first run is excluded
    because nothing can exit on it.
    """
    usable = runs[~runs["is_first_run"].astype(str).str.lower().isin(["true", "1"])] \
        if "is_first_run" in runs.columns else runs
    usable = usable[usable["watchlist_size"] > 0]
    if usable.empty:
        return {"runs": 0}
    monthly = (usable["exited"] / usable["watchlist_size"])
    return {
        "runs": int(len(usable)),
        "mean_watchlist": round(float(usable["watchlist_size"].mean()), 1),
        "mean_exits_per_run": round(float(usable["exited"].mean()), 2),
        "monthly_exit_rate": round(float(monthly.mean()), 4),
        "annual_turnover": round(float(12 * monthly.mean()), 3),
        "implied_holding_months": round(float(1 / monthly.mean()), 1) if monthly.mean() else None,
    }
