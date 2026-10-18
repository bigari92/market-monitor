"""The point-in-time fundamental panel: one row per (cik, fiscal quarter), with a real
availability date.

The factor arithmetic is `recovered/build_fundamentals.py`'s, unchanged — TTM sums, year-on-year
growth, margins and their four-quarter deltas, `rule40`, `rev_stability`, `profitable`, and the
same sanity clips. CLOUD-RULES.md §5 forbids changing a definition, so none is changed.

Three things are different, and each is a defect fixed rather than a preference:

1. **`avail_date` is observed, not assumed.** The recovered code set
   `avail_date = period_end + 90 days`, chosen because 90 days covered 96% of genuine first
   filings. The Financial Statement Data Sets carry the actual `filed` date per submission, so
   the approximation is gone — along with the 4% of filings it mis-dated, which are not a random
   4%: a late filer is a distressed filer, exactly the population a quality signal must not see
   early. `filing_lag_profile` measures the distribution that assumption was standing in for.

2. **Q4 exists.** 10-K filings state the fiscal year, not its fourth quarter — on 2026q2 the
   split was 1,387 annual rows against 119 quarterly ones. Keeping only one-quarter durations
   therefore leaves a hole at every Q4, and `rolling(4).sum()` with `min_periods=4` cannot step
   over it. Q4 is derived here as `FY - (Q1 + Q2 + Q3)`.

3. **The join is on CIK.** `build_fundamentals.py` mapped CIK to ticker through
   `company_tickers.json` and then joined on the ticker. `universe.py` already carries the CIK
   from SEC's own exchange map, so the ticker never becomes a join key and cannot mis-match.

Nothing here is scored by default. `recovered/screen_v4.py` — the production screen — ran the
price-only composite with fundamentals attached "for CONTEXT ... they did not improve selection,
so they are reported, not scored". That decision stands until a measurement overturns it, and
this module's job is to make the measurement possible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .sec_fsds import OTHER_TAGS, REVENUE_TAGS

# The metric names `build_fundamentals.py` used internally, and the tags behind each.
METRIC_TAGS = {
    "gp": ("GrossProfit",),
    "cor": ("CostOfRevenue",),
    "cogs": ("CostOfGoodsAndServicesSold",),
    "oi": ("OperatingIncomeLoss",),
    "ni": ("NetIncomeLoss",),
}

# Window, in days before a fiscal year end, in which the three reported quarters of that year
# must fall for Q4 to be derivable. Generous at the near end (a quarter end is ~91 days back)
# and bounded at the far end so a prior year's quarter cannot be swept in.
Q4_WINDOW_MIN_DAYS = 20
Q4_WINDOW_MAX_DAYS = 330

FACTOR_COLUMNS = ("rev_ttm", "rev_yoy_ttm", "rev_yoy_q", "rev_accel", "gross_margin",
                  "op_margin", "net_margin", "gross_margin_delta", "op_margin_delta",
                  "net_margin_delta", "rule40", "rev_stability", "profitable")


def _pivot(facts: pd.DataFrame, qtrs: int) -> pd.DataFrame:
    """One row per (cik, ddate) for the given period length, one column per tag."""
    subset = facts[facts["qtrs"] == qtrs]
    if subset.empty:
        return pd.DataFrame()
    # `max` where a tag repeats within a key, matching build_fundamentals.py's groupby().max().
    wide = (subset.pivot_table(index=["cik", "ddate"], columns="tag", values="value",
                               aggfunc="max")
            .reset_index())
    filed = (subset.groupby(["cik", "ddate"])["filed"].min().reset_index())
    return wide.merge(filed, on=["cik", "ddate"], how="left")


def _coalesce_revenue(frame: pd.DataFrame) -> pd.Series:
    """Revenue across the four tags, by priority.

    Needed because the tag a company reports under moved with ASC 606: `Revenues` and
    `SalesRevenueNet` dominate the early years, the
    `RevenueFromContractWithCustomer*` pair the later ones. A single tag covers only part of
    any long history, and a gap in revenue silently voids every margin and growth factor.
    """
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    for tag in REVENUE_TAGS:
        if tag in frame.columns:
            out = out.fillna(frame[tag])
    return out


def _standardise(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce a tag-wide frame to the metric columns build_fundamentals.py worked with."""
    if frame.empty:
        return pd.DataFrame(columns=["cik", "ddate", "filed", "rev", "gp", "oi", "ni"])
    out = frame[["cik", "ddate", "filed"]].copy()
    out["rev"] = _coalesce_revenue(frame)
    for metric, tags in METRIC_TAGS.items():
        values = pd.Series(np.nan, index=frame.index, dtype=float)
        for tag in tags:
            if tag in frame.columns:
                values = values.fillna(frame[tag])
        out[metric] = values
    # Gross profit where the tag is absent, from either cost tag. As recovered.
    out["gp"] = out["gp"].fillna(out["rev"] - out["cor"]).fillna(out["rev"] - out["cogs"])
    return out.drop(columns=["cor", "cogs"])


def derive_q4(quarterly: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    """Q4 = FY - (Q1 + Q2 + Q3), where all three quarters of that fiscal year are present.

    Returned rows carry the 10-K's `filed` date, because the fourth quarter only becomes
    knowable when the annual report lands — never earlier.
    """
    if annual.empty or quarterly.empty:
        return pd.DataFrame(columns=quarterly.columns)

    metrics = ["rev", "gp", "oi", "ni"]
    by_cik: dict[int, pd.DataFrame] = {cik: group.sort_values("ddate")
                                       for cik, group in quarterly.groupby("cik")}
    rows = []
    for cik, group in annual.groupby("cik"):
        quarters_for_cik = by_cik.get(cik)
        if quarters_for_cik is None:
            continue
        dates = quarters_for_cik["ddate"]
        for _, year in group.iterrows():
            year_end = year["ddate"]
            gap = (year_end - dates).dt.days
            window = quarters_for_cik[(gap >= Q4_WINDOW_MIN_DAYS) & (gap <= Q4_WINDOW_MAX_DAYS)]
            if len(window) != 3:
                # Fewer than three means a gap in the year; more means an ambiguous fiscal
                # calendar (a changed year end). Neither is guessed at.
                continue
            row = {"cik": cik, "ddate": year_end, "filed": year["filed"]}
            usable = True
            for metric in metrics:
                annual_value = year.get(metric)
                parts = window[metric]
                if pd.isna(annual_value) or parts.isna().any():
                    row[metric] = np.nan
                    if metric == "rev":
                        usable = False
                else:
                    row[metric] = float(annual_value) - float(parts.sum())
            if usable:
                rows.append(row)
    return pd.DataFrame(rows)


def build_panel(facts: pd.DataFrame) -> pd.DataFrame:
    """Facts -> the point-in-time fundamental factor panel, one row per (cik, fiscal quarter).

    `facts` is `sec_fsds.as_originally_filed`'s output. Returns the factor columns plus
    `avail_date`, the date from which the row could have been known.
    """
    quarterly = _standardise(_pivot(facts, qtrs=1))
    annual = _standardise(_pivot(facts, qtrs=4))
    q4 = derive_q4(quarterly, annual)

    combined = pd.concat([quarterly, q4], ignore_index=True)
    # A reported Q4 (rare, but it happens) beats a derived one: keep the first occurrence, with
    # reported rows ordered ahead of derived.
    combined["_derived"] = [0] * len(quarterly) + [1] * len(q4)
    combined = (combined.sort_values(["cik", "ddate", "_derived"])
                .drop_duplicates(subset=["cik", "ddate"], keep="first")
                .drop(columns="_derived")
                .reset_index(drop=True))

    frame = combined.sort_values(["cik", "ddate"]).reset_index(drop=True)
    grouped = frame.groupby("cik")

    # --- TTM aggregates and growth, per company on its own quarter sequence (as recovered) ---
    for column in ("rev", "gp", "oi", "ni"):
        frame[column + "_ttm"] = grouped[column].transform(
            lambda s: s.rolling(4, min_periods=4).sum())

    frame["rev_ttm_prev"] = grouped["rev_ttm"].shift(4)
    frame["rev_q_prev"] = grouped["rev"].shift(4)
    frame["rev_yoy_ttm"] = frame["rev_ttm"] / frame["rev_ttm_prev"].replace(0, np.nan) - 1
    frame["rev_yoy_q"] = frame["rev"] / frame["rev_q_prev"].replace(0, np.nan) - 1
    frame["rev_accel"] = frame["rev_yoy_q"] - frame.groupby("cik")["rev_yoy_q"].shift(1)

    revenue_ttm = frame["rev_ttm"].replace(0, np.nan)
    frame["gross_margin"] = frame["gp_ttm"] / revenue_ttm
    frame["op_margin"] = frame["oi_ttm"] / revenue_ttm
    frame["net_margin"] = frame["ni_ttm"] / revenue_ttm
    for margin in ("gross_margin", "op_margin", "net_margin"):
        frame[margin + "_delta"] = frame[margin] - frame.groupby("cik")[margin].shift(4)

    frame["rule40"] = frame["rev_yoy_ttm"] + frame["op_margin"]
    frame["rev_stability"] = frame.groupby("cik")["rev_yoy_q"].transform(
        lambda s: s.rolling(8, min_periods=5).std())
    frame["profitable"] = (frame["ni_ttm"] > 0).astype(float)

    # Sanity clipping: XBRL carries occasional scale errors. Thresholds as recovered.
    for column in ("rev_yoy_ttm", "rev_yoy_q", "rev_accel"):
        frame.loc[frame[column].abs() > 10, column] = np.nan
    for column in ("gross_margin", "op_margin", "net_margin"):
        frame.loc[(frame[column] > 5) | (frame[column] < -10), column] = np.nan

    # A TTM figure is knowable only once its LAST constituent quarter has been filed.
    #
    # Computed on int64 nanoseconds because `rolling(...).max()` refuses a datetime64 column
    # ("No numeric types to aggregate"). The round-trip is exact — int64 ns is the storage
    # representation — and the result is re-floored against each row's own `filed` date so a
    # quarter can never appear before the filing that reported it.
    filed_ns = frame.groupby("cik")["filed"].transform(
        lambda s: s.astype("int64").rolling(4, min_periods=1).max())
    frame["avail_date"] = pd.to_datetime(filed_ns, unit="ns")
    frame["avail_date"] = frame[["avail_date", "filed"]].max(axis=1)

    keep = ["cik", "ddate", "filed", "avail_date", *FACTOR_COLUMNS]
    return frame[keep].rename(columns={"ddate": "period_end"})


def attach_sic(panel: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    """Add each company's most recent SIC code. The sector dimension the cloud had no source for.

    `screen_v4.py`'s industry-momentum overlay needed an industry column and took it from a
    Nasdaq screener download that this environment cannot reach. SIC arrives free in `sub.txt`,
    so sector becomes reportable — as context, not as a score (the overlay stays omitted and
    `signal_version` still hashes `industry_overlay: false`).
    """
    sic = (facts.dropna(subset=["sic"]).sort_values("filed")
           .groupby("cik")["sic"].last().rename("sic"))
    return panel.merge(sic, on="cik", how="left")


def as_of(panel: pd.DataFrame, when, max_age_days: int = 460) -> pd.DataFrame:
    """The latest row per company that was already knowable at `when`.

    Two rules, both from `recovered/screen_v4.py`:
      * only rows with `avail_date <= when` — the point-in-time constraint;
      * a row whose fiscal period ended more than `max_age_days` ago is dropped, because a
        company that has not reported in 15 months is not described by its last report.
    """
    when = pd.Timestamp(when)
    visible = panel[panel["avail_date"] <= when]
    if visible.empty:
        return visible
    latest = (visible.sort_values("avail_date").groupby("cik").tail(1).copy())
    age = (when - latest["period_end"]).dt.days
    return latest[age <= max_age_days].reset_index(drop=True)


# --- measurement ----------------------------------------------------------


def filing_lag_profile(panel: pd.DataFrame) -> dict:
    """The distribution the recovered `LAG_DAYS = 90` was standing in for.

    `recovered/validate_lag.py` set out to measure this and its results were never recovered.
    The question it answers: how wrong is a flat 90-day assumption, and in which direction?
    """
    lag = (panel["filed"] - panel["period_end"]).dt.days
    lag = lag[(lag >= 0) & (lag <= 1000)]
    if lag.empty:
        return {"n": 0}
    return {
        "n": int(len(lag)),
        "mean_days": round(float(lag.mean()), 1),
        "median_days": int(lag.median()),
        "p05": int(lag.quantile(0.05)), "p25": int(lag.quantile(0.25)),
        "p75": int(lag.quantile(0.75)), "p90": int(lag.quantile(0.90)),
        "p95": int(lag.quantile(0.95)), "p99": int(lag.quantile(0.99)),
        "share_within_90d_%": round(100 * float((lag <= 90).mean()), 2),
        "share_beyond_90d_%": round(100 * float((lag > 90).mean()), 2),
        "max_days": int(lag.max()),
    }


def coverage_profile(panel: pd.DataFrame) -> pd.DataFrame:
    """Non-null share of each factor by year, so a thin early history is visible not assumed."""
    frame = panel.copy()
    frame["year"] = frame["period_end"].dt.year
    rows = frame.groupby("year").apply(
        lambda g: pd.Series({"rows": len(g), "ciks": g["cik"].nunique(),
                             **{c: round(100 * g[c].notna().mean(), 1)
                                for c in ("rev_ttm", "rev_yoy_ttm", "op_margin", "rule40",
                                          "rev_stability")}}),
        include_groups=False)
    return rows
