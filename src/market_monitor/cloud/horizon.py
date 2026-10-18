"""Does the signal say anything at 3 months? It was built and validated on 12.

A port of `recovered/horizon_test.py`'s logic (`recovered/` is evidence: never imported, never
edited). It exists to settle one decision — the tracker's review cadence — with a measurement
instead of a judgement call. The recovered script's *results* were never recovered, only the
script, so the question was open.

## Four things this adds to the recovered logic, and why each is a correction

1. **Honest standard errors.** The recovered script computes `ics.mean()/(ics.std()/sqrt(n))` on
   a monthly grid of 12-month forward returns. Consecutive observations share 11/12ths of their
   window, so that t-statistic is inflated — RECOVERY.md defect 3, and the reason the published
   result rests on ~7 effective annual observations rather than 127. Three figures are reported
   here: the naive t, a Newey-West t with the overlap as its lag length, and a t from
   non-overlapping windows only. Where they disagree, the naive one is the wrong one.

2. **The down-tail at both horizons.** The recovered script reports `t3_dn30` but no 12-month
   equivalent, so it cannot compare the thing that actually matters. The owner's own research
   says the edge is a loser-filter: trend quality barely moves the up-tail (18.7% -> 21.9%) and
   roughly halves the down-tail (48.3% -> 23.4%). Whether *that* survives at 3 months is the
   cadence question, so both tails are measured at both horizons.

3. **One common sample.** Forward returns at 3 and 12 months are available over different date
   ranges. Measuring each over all the dates it has would mean comparing two different samples
   and reading the difference as a horizon effect. Both horizons use only dates where both are
   defined.

4. **Spearman without scipy.** `stats.spearmanr` is unavailable here (scipy arrives at Stage 3).
   A Pearson correlation of ranks is the same quantity, so it is computed that way.

## What this is NOT

It is not a backtest and it does not validate the strategy. The universe is today's registrants,
so across 20 years the survivorship bias is severe and every absolute figure below is inflated —
the names that went to zero are simply absent (RECOVERY.md defect 1). What it can do is compare
two horizons on the same biased sample, where the bias applies to both. That is a relative
question, and it is the only question being asked.

No probability here is a forecast. These are historical frequencies on a biased sample, reported
in a research file. Nothing in this module reaches the tracker's output, which still displays no
probability at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import factors as F
from . import signal as sig

H3, H12 = 63, 252          # trading days: ~3 months, ~12 months

# Sessions of history handed to compute_factors per rebalance date. The deepest lookback is
# 3*252 = 756 positions (mom_36); days_above_ma200 needs 252 + 199 for its rolling warmup. 820
# covers both, and slicing rather than passing the whole panel is what makes ~190 dates feasible.
FACTOR_WINDOW = 820


def rebalance_dates(sessions: pd.DatetimeIndex, horizon: int = H12,
                    window: int = FACTOR_WINDOW) -> list[pd.Timestamp]:
    """Month-end sessions that have enough history behind them and enough future ahead.

    The forward-looking bound is what keeps this honest: a date is only usable if the realized
    return is already in the panel. Nothing is scored against a future that has not happened.
    """
    if len(sessions) <= window + horizon:
        return []
    usable = sessions[window:len(sessions) - horizon]
    frame = pd.Series(usable, index=usable)
    return list(frame.groupby([usable.year, usable.month]).last().values)


def forward_return(adjclose: pd.DataFrame, sessions: pd.DatetimeIndex,
                   as_of: pd.Timestamp, horizon: int) -> pd.Series | None:
    """Realized total return from `as_of` over `horizon` trading days.

    On `adjclose`, because "what did a holder make" is a total-return question. Uses future data
    by definition and is only ever joined onto factors computed strictly before `as_of`.
    """
    position = sessions.searchsorted(pd.Timestamp(as_of), side="right") - 1
    future = position + horizon
    if position < 0 or future >= len(sessions):
        return None
    start = adjclose.iloc[position]
    end = adjclose.iloc[future]
    return (end / start - 1.0).replace([np.inf, -np.inf], np.nan)


def build_panel(close: pd.DataFrame, adjclose: pd.DataFrame, volume: pd.DataFrame,
                dates: list[pd.Timestamp], progress: bool = True) -> pd.DataFrame:
    """Score every rebalance date and attach both realized forward returns.

    Returns a long frame: one row per (date, ticker) that cleared the gates, carrying the score,
    the factors the score needs, and `fwd3m` / `fwd12m`.
    """
    sessions = close.index
    rows: list[pd.DataFrame] = []
    refused = 0

    for i, as_of in enumerate(dates):
        as_of = pd.Timestamp(as_of)
        stop = sessions.searchsorted(as_of, side="right")
        start = max(0, stop - FACTOR_WINDOW)
        c = close.iloc[start:stop]
        a = adjclose.iloc[start:stop]
        v = volume.iloc[start:stop]

        try:
            factor_frame = F.compute_factors(c, v, as_of, adjclose=a)
            scored = sig.score(factor_frame)
        except (ValueError, sig.RefusedToRank):
            refused += 1
            continue

        r3 = forward_return(adjclose, sessions, as_of, H3)
        r12 = forward_return(adjclose, sessions, as_of, H12)
        if r3 is None or r12 is None:
            continue

        block = scored[["score", "rank", "vol_12m", "pct_of_52w_high", "max_dd_12m"]].copy()
        block["date"] = as_of
        block["ticker"] = block.index
        block["fwd3m"] = r3.reindex(block.index)
        block["fwd12m"] = r12.reindex(block.index)
        rows.append(block.reset_index(drop=True))

        if progress and (i + 1) % 24 == 0:
            print(f"  {i + 1}/{len(dates)} dates scored", flush=True)

    if not rows:
        raise RuntimeError("no rebalance date produced a scoreable cross-section")
    panel = pd.concat(rows, ignore_index=True)
    panel = panel[panel["fwd3m"].notna() & panel["fwd12m"].notna()]
    panel.attrs["refused_dates"] = refused
    return panel


# --- statistics -----------------------------------------------------------


def spearman(x: pd.Series, y: pd.Series) -> float:
    """Spearman's rho as the Pearson correlation of ranks. Identical quantity, no scipy."""
    if len(x) < 10:
        return np.nan
    return float(x.rank().corr(y.rank()))


def newey_west_t(series: pd.Series, lags: int) -> float:
    """t-statistic for the mean of an autocorrelated series (Newey-West, Bartlett kernel).

    Overlapping forward returns make consecutive observations share most of their window. The
    naive standard error assumes independence and is therefore too small; this corrects it with
    the overlap as the lag length.
    """
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 3:
        return np.nan
    centred = values - values.mean()
    variance = float(centred @ centred) / n
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        covariance = float(centred[lag:] @ centred[:-lag]) / n
        variance += 2.0 * weight * covariance
    if variance <= 0:
        return np.nan
    return float(values.mean() / np.sqrt(variance / n))


def nonoverlapping_t(series: pd.Series, step: int) -> tuple[float, int]:
    """t-statistic using only every `step`-th observation, so no two windows overlap.

    Blunt and assumption-free: it throws away most of the data rather than modelling the
    dependence. Reported beside Newey-West because when the two agree the conclusion is not an
    artefact of either correction. Takes the best of the `step` possible offsets' sample sizes
    by averaging their t-statistics, so the answer does not depend on where the grid starts.
    """
    clean = series.dropna()
    if len(clean) < step * 3:
        return np.nan, 0
    ts, counts = [], []
    for offset in range(step):
        subset = clean.iloc[offset::step]
        if len(subset) < 3 or subset.std(ddof=1) == 0:
            continue
        ts.append(subset.mean() / (subset.std(ddof=1) / np.sqrt(len(subset))))
        counts.append(len(subset))
    if not ts:
        return np.nan, 0
    return float(np.mean(ts)), int(np.mean(counts))


def ic_series(panel: pd.DataFrame, return_column: str) -> pd.Series:
    """Per-date rank IC between the score and the realized return."""
    return (panel.groupby("date")
            .apply(lambda g: spearman(g["score"], g[return_column]), include_groups=False)
            .dropna())


def ic_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Rank IC at both horizons, with all three standard errors."""
    rows = []
    for label, column, overlap in (("3-month", "fwd3m", 3), ("12-month", "fwd12m", 12)):
        ics = ic_series(panel, column)
        naive = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics))) if len(ics) > 2 else np.nan
        nw = newey_west_t(ics, lags=overlap)
        no_t, no_n = nonoverlapping_t(ics, step=overlap)
        rows.append({
            "horizon": label, "mean_ic": ics.mean(), "median_ic": ics.median(),
            "months_positive": 100 * (ics > 0).mean(), "n_dates": len(ics),
            "t_naive": naive, "t_newey_west": nw,
            "t_nonoverlapping": no_t, "n_independent": no_n,
        })
    return pd.DataFrame(rows)


def selection_table(panel: pd.DataFrame, top_n: int = sig.TOP_N) -> pd.DataFrame:
    """What the top N actually did, against the cohort it was drawn from, at both horizons.

    The down-tail columns are the point: the signal is a loser-filter, so `dn30` is where its
    claimed edge lives, and `up50` is where it is claimed NOT to live.
    """
    rows = []
    for as_of, group in panel.groupby("date"):
        top = group.sort_values("score", ascending=False).head(top_n)
        if len(top) < top_n:
            continue
        row = {"date": as_of, "cohort_n": len(group)}
        for label, column in (("3m", "fwd3m"), ("12m", "fwd12m")):
            row[f"top_mean_{label}"] = top[column].mean()
            row[f"top_median_{label}"] = top[column].median()
            row[f"top_up50_{label}"] = (top[column] > 0.5).mean()
            row[f"top_dn30_{label}"] = (top[column] < -0.3).mean()
            row[f"cohort_up50_{label}"] = (group[column] > 0.5).mean()
            row[f"cohort_dn30_{label}"] = (group[column] < -0.3).mean()
            row[f"cohort_mean_{label}"] = group[column].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def base_rates(panel: pd.DataFrame) -> pd.DataFrame:
    """Unconditional frequency of a large move, cohort-wide, at both horizons."""
    rows = []
    for label, column in (("3m", "fwd3m"), ("12m", "fwd12m")):
        rows.append({
            "horizon": label,
            "p_up50": 100 * (panel[column] > 0.5).mean(),
            "p_dn30": 100 * (panel[column] < -0.3).mean(),
            "mean": 100 * panel[column].mean(),
            "median": 100 * panel[column].median(),
            "n_obs": len(panel),
        })
    return pd.DataFrame(rows)


def run(close: pd.DataFrame, adjclose: pd.DataFrame, volume: pd.DataFrame,
        top_n: int = sig.TOP_N) -> dict:
    """The whole test. Returns every table, for rendering and for writing down."""
    dates = rebalance_dates(close.index)
    if not dates:
        raise RuntimeError(
            f"the panel has {len(close)} sessions, which cannot support "
            f"{FACTOR_WINDOW} of history plus {H12} of future. Fetch a longer panel."
        )
    print(f"scoring {len(dates)} monthly rebalance dates "
          f"({pd.Timestamp(dates[0]):%Y-%m} .. {pd.Timestamp(dates[-1]):%Y-%m})", flush=True)
    panel = build_panel(close, adjclose, volume, dates)
    selection = selection_table(panel, top_n)
    return {
        "panel_rows": len(panel),
        "n_dates": panel["date"].nunique(),
        "first_date": str(pd.Timestamp(panel["date"].min()).date()),
        "last_date": str(pd.Timestamp(panel["date"].max()).date()),
        "refused_dates": panel.attrs.get("refused_dates", 0),
        "base_rates": base_rates(panel),
        "ic": ic_table(panel),
        "selection": selection,
        "top_n": top_n,
    }
