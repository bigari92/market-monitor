"""Point-in-time backtest: do any factors actually predict forward 12m returns?

Method
------
At each rebalance date T (month-ends, 2015..2025):
  1. Build the investable cross-section (liquidity + price filters) using data <= T
  2. Compute factors using data <= T
  3. Compute REALIZED forward 12m return (T -> T+252 trading days)
  4. Score: rank IC, decile spreads, and P(big winner) by decile

Nothing at step 1-2 touches data after T. Step 3 is the label only.
"""
import numpy as np
import pandas as pd
from scipy import stats
import factors as F

MIN_PRICE = 3.0
MIN_ADV   = 2_000_000    # $2M/day - keeps it realistically tradeable
HORIZON   = F.TD_Y

FACTOR_COLS = ["mom_12_1", "mom_6_1", "mom_3", "mom_1", "mom_36", "mom_accel",
               "px_vs_ma200", "ma50_vs_ma200", "pct_of_52w_high", "off_52w_low",
               "days_above_ma200", "vol_6m", "vol_12m", "max_dd_12m", "skew_12m",
               "vol_surge", "adv_3m_usd", "price"]


def rebalance_dates(close, start="2015-01-31", end="2025-09-30", freq="ME"):
    idx = close.index
    want = pd.date_range(start, end, freq=freq)
    out = []
    for d in want:
        pos = idx.searchsorted(d, side="right") - 1
        if 0 <= pos < len(idx):
            out.append(idx[pos])
    return sorted(set(out))


def build_dataset(close, vol, dates, horizon=HORIZON):
    """Assemble the panel of (factors at T, forward return T->T+h)."""
    rows = []
    for d in dates:
        f = F.compute_factors(close, vol, d)
        if f is None:
            continue
        fwd = F.forward_return(close, d, horizon)
        if fwd is None:
            continue
        f = f.copy()
        f["fwd_ret"] = fwd
        # investable filter
        m = (f["price"] >= MIN_PRICE) & (f["adv_3m_usd"] >= MIN_ADV) & f["fwd_ret"].notna()
        f = f[m]
        if len(f) < 100:
            continue
        f["ticker"] = f.index
        rows.append(f)
        print(f"  {d.date()}  n={len(f)}", flush=True)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def rank_ic(panel, cols=FACTOR_COLS):
    """Spearman rank IC of each factor vs forward return, computed per date."""
    recs = []
    for d, g in panel.groupby("date"):
        for c in cols:
            s = g[[c, "fwd_ret"]].dropna()
            if len(s) < 50:
                continue
            ic, _ = stats.spearmanr(s[c], s["fwd_ret"])
            recs.append({"date": d, "factor": c, "ic": ic, "n": len(s)})
    ics = pd.DataFrame(recs)
    if ics.empty:
        return ics, pd.DataFrame()
    summ = ics.groupby("factor")["ic"].agg(["mean", "std", "count"])
    summ["t_stat"] = summ["mean"] / (summ["std"] / np.sqrt(summ["count"]))
    summ["ic_ir"] = summ["mean"] / summ["std"]
    summ["hit_rate"] = ics.groupby("factor")["ic"].apply(lambda x: (x > 0).mean())
    return ics, summ.sort_values("mean", ascending=False)


def decile_table(panel, col, n=10):
    """Forward-return distribution by within-date decile of `col`."""
    p = panel[[col, "fwd_ret", "date"]].dropna().copy()
    if p.empty:
        return pd.DataFrame()
    p["dec"] = p.groupby("date")[col].transform(
        lambda x: pd.qcut(x.rank(method="first"), n, labels=False, duplicates="drop"))
    g = p.groupby("dec")["fwd_ret"]
    out = pd.DataFrame({
        "mean": g.mean(),
        "median": g.median(),
        "p_gt_50": g.apply(lambda x: (x > 0.50).mean()),
        "p_gt_100": g.apply(lambda x: (x > 1.00).mean()),
        "p_lt_-30": g.apply(lambda x: (x < -0.30).mean()),
        "n": g.size(),
    })
    return out
