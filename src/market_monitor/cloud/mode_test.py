"""Do the fundamentals improve selection? The four configurations, re-measured out of sample.

## Why this is not a search

`recovered/run_algo_v4.py` compared exactly four configurations — `price`, `rank_fund`,
`filter`, `both` — and `recovered/screen_v4.py`, written afterwards, shipped `price` with the
note that fundamentals "did not improve selection, so they are reported, not scored".

Those four trials were spent in Sept 2026. Re-measuring **the same four, pre-specified, with no
new variants** on a differently-built panel does not add to the multiple-testing count that
package C2 is meant to score against; it is an out-of-sample test of a choice already made.
What would add to the count is inventing a fifth configuration, re-weighting `FUND_W`, or moving
`EXCL_R40`. None of that happens here, and CLOUD-RULES.md §5 forbids it.

The live tracker stays on `price` whatever this measures. Switching it is the owner's call, and
`signal_version` gives each mode a different hash so the record can never blur the two.

## What differs from the recovered comparison, and why it matters

The fundamentals are built from the Financial Statement Data Sets with **real filing dates**,
not `period_end + 90 days`. The recovered comparison therefore gave the fundamental modes a
quarter of lookahead on every late filer — and a late filer is a distressed filer, which is
precisely the population an exclusion rule is trying to catch. If the fundamental block looked
better in Sept 2026 than it does here, that gap is the first place to look.

A fair comparison also needs care about the cohort: `filter` and `both` remove names, so their
top 25 is drawn from a smaller pool. Every mode's top 25 is therefore scored against **one
common reference cohort** (the price-mode gated cross-section) as well as against its own.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import factors as F
from . import fundamentals as FU
from . import horizon as H
from . import signal as sig

FUND_COLUMNS = ("rule40", "rev_stability", "net_margin", "op_margin", "rev_yoy_ttm",
                "profitable", "gross_margin")


def attach_fundamentals(factor_frame: pd.DataFrame, panel: pd.DataFrame,
                        cik_by_ticker: dict[str, int], as_of_date) -> pd.DataFrame:
    """Join the fundamentals knowable at `as_of_date` onto a factor cross-section, by CIK.

    Joined on CIK, never on ticker: `universe.py` carries the CIK from SEC's own exchange map,
    so there is no name-matching step that could mis-associate a company with a symbol.
    """
    visible = FU.as_of(panel, as_of_date)
    out = factor_frame.copy()
    out["cik"] = out.index.map(cik_by_ticker)
    if visible.empty:
        for column in FUND_COLUMNS:
            out[column] = np.nan
        return out
    keep = ["cik", *[c for c in FUND_COLUMNS if c in visible.columns]]
    merged = out.reset_index().merge(visible[keep], on="cik", how="left")
    return merged.set_index(factor_frame.index.name or "ticker")


def run(close: pd.DataFrame, adjclose: pd.DataFrame, volume: pd.DataFrame,
        fundamentals: pd.DataFrame, cik_by_ticker: dict[str, int],
        modes: tuple[str, ...] = sig.MODES, top_n: int = sig.TOP_N,
        progress: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score every rebalance date under every mode. Returns (per-date rows, join coverage)."""
    dates = H.rebalance_dates(close.index)
    if not dates:
        raise RuntimeError("panel too short for a 12-month forward return")
    sessions = close.index
    rows: list[dict] = []
    coverage: list[dict] = []

    for index, as_of in enumerate(dates):
        as_of = pd.Timestamp(as_of)
        stop = sessions.searchsorted(as_of, side="right")
        start = max(0, stop - H.FACTOR_WINDOW)
        try:
            factor_frame = F.compute_factors(close.iloc[start:stop], volume.iloc[start:stop],
                                             as_of, adjclose=adjclose.iloc[start:stop])
        except ValueError:
            continue

        with_fundamentals = attach_fundamentals(factor_frame, fundamentals, cik_by_ticker, as_of)
        r3 = H.forward_return(adjclose, sessions, as_of, H.H3)
        r12 = H.forward_return(adjclose, sessions, as_of, H.H12)
        if r3 is None or r12 is None:
            continue

        # The common reference cohort: the price-mode gated cross-section.
        try:
            reference = sig.score(with_fundamentals, mode="price")
        except sig.RefusedToRank:
            continue
        reference_tickers = reference.index
        coverage.append({
            "date": as_of, "gated": len(reference),
            "with_rule40": int(reference["rule40"].notna().sum())
            if "rule40" in reference.columns else 0,
        })

        cohort3 = r3.reindex(reference_tickers)
        cohort12 = r12.reindex(reference_tickers)

        for mode in modes:
            try:
                scored = sig.score(with_fundamentals, mode=mode)
            except sig.RefusedToRank:
                continue
            top = scored.sort_values("score", ascending=False).head(top_n)
            if len(top) < top_n:
                continue
            top3 = r3.reindex(top.index)
            top12 = r12.reindex(top.index)
            rows.append({
                "date": as_of, "mode": mode,
                "own_cohort_n": len(scored),
                "top_mean_3m": top3.mean(), "top_mean_12m": top12.mean(),
                "top_median_12m": top12.median(),
                "top_up50_3m": (top3 > 0.5).mean(), "top_up50_12m": (top12 > 0.5).mean(),
                "top_dn30_3m": (top3 < -0.3).mean(), "top_dn30_12m": (top12 < -0.3).mean(),
                "ref_mean_3m": cohort3.mean(), "ref_mean_12m": cohort12.mean(),
                "ref_up50_12m": (cohort12 > 0.5).mean(),
                "ref_dn30_12m": (cohort12 < -0.3).mean(),
            })

        if progress and (index + 1) % 24 == 0:
            print(f"  {index + 1}/{len(dates)} dates", flush=True)

    if not rows:
        raise RuntimeError("no date produced a scoreable cross-section in any mode")
    return pd.DataFrame(rows), pd.DataFrame(coverage)


def summarise(per_date: pd.DataFrame) -> pd.DataFrame:
    """One row per mode, with honest standard errors on the two quantities that matter."""
    out = []
    for mode, group in per_date.groupby("mode"):
        group = group.sort_values("date")
        row: dict = {"mode": mode, "n_dates": len(group),
                     "median_cohort": int(group["own_cohort_n"].median())}
        for label, overlap in (("3m", 3), ("12m", 12)):
            excess = group[f"top_mean_{label}"] - group[f"ref_mean_{label}"]
            row[f"top_mean_{label}_%"] = 100 * group[f"top_mean_{label}"].mean()
            row[f"excess_{label}_pp"] = 100 * excess.mean()
            t_nw = H.newey_west_t(excess.reset_index(drop=True), lags=overlap)
            t_no, n_ind = H.nonoverlapping_t(excess.reset_index(drop=True), step=overlap)
            row[f"excess_{label}_t_NW"] = t_nw
            row[f"excess_{label}_t_nonoverlap"] = t_no
            row[f"n_independent_{label}"] = n_ind
        # The loser-filter quantity, at the validated horizon.
        cut = group["ref_dn30_12m"] - group["top_dn30_12m"]
        row["dn30_12m_%"] = 100 * group["top_dn30_12m"].mean()
        row["ref_dn30_12m_%"] = 100 * group["ref_dn30_12m"].mean()
        row["dn_tail_cut_pp"] = 100 * cut.mean()
        row["dn_tail_cut_t_nonoverlap"] = H.nonoverlapping_t(
            cut.reset_index(drop=True), step=12)[0]
        row["up50_12m_%"] = 100 * group["top_up50_12m"].mean()
        out.append(row)
    frame = pd.DataFrame(out).set_index("mode")
    order = [m for m in sig.MODES if m in frame.index]
    return frame.loc[order]


def paired_difference(per_date: pd.DataFrame, mode: str, baseline: str = "price") -> dict:
    """Is `mode` different from `baseline` on the SAME dates? A paired test, not two separate ones.

    Comparing two mode-level averages ignores that both saw the same market. The paired
    difference removes the common regime, which is where nearly all the variance lives, and is
    the only version of this comparison that can distinguish the configurations.
    """
    wide = per_date.pivot(index="date", columns="mode")
    results: dict = {"mode": mode, "baseline": baseline}
    for label, overlap in (("3m", 3), ("12m", 12)):
        column = f"top_mean_{label}"
        if (column, mode) not in wide.columns or (column, baseline) not in wide.columns:
            continue
        pair = wide[column][[mode, baseline]].dropna()
        if len(pair) < overlap * 3:
            continue
        difference = (pair[mode] - pair[baseline]).reset_index(drop=True)
        t_no, n_ind = H.nonoverlapping_t(difference, step=overlap)
        results[f"diff_{label}_pp"] = round(100 * float(difference.mean()), 3)
        results[f"diff_{label}_t_NW"] = round(float(H.newey_west_t(difference, overlap)), 3)
        results[f"diff_{label}_t_nonoverlap"] = round(float(t_no), 3) if t_no == t_no else None
        results[f"n_paired_{label}"] = int(len(pair))
        results[f"n_independent_{label}"] = n_ind
        results[f"dates_better_{label}_%"] = round(100 * float((difference > 0).mean()), 1)
    return results
