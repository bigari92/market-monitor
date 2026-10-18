"""Precompute causal rolling series ONCE over the full panel.

Safety note: every series here is causal (value at row T uses only rows <= T), so
computing them on the full history and slicing later introduces no lookahead.
"""
import numpy as np
import pandas as pd

TD_M, TD_Y = 21, 252


def build(close, vol):
    ctx = {}
    ctx["close"] = close
    r = close.pct_change(fill_method=None)
    ctx["ret"] = r
    ctx["ma50"] = close.rolling(50, min_periods=40).mean()
    ctx["ma200"] = close.rolling(200, min_periods=160).mean()
    ctx["above200"] = (close > ctx["ma200"]).astype(float)
    ctx["frac_above200_12m"] = ctx["above200"].rolling(TD_Y, min_periods=200).mean()
    ctx["hi52"] = close.rolling(TD_Y, min_periods=200).max()
    ctx["lo52"] = close.rolling(TD_Y, min_periods=200).min()
    ctx["vol6m"] = r.rolling(6 * TD_M, min_periods=100).std() * np.sqrt(TD_Y)
    ctx["vol12m"] = r.rolling(TD_Y, min_periods=200).std() * np.sqrt(TD_Y)
    ctx["skew12m"] = r.rolling(TD_Y, min_periods=200).skew()
    # rolling 12m max drawdown
    roll_max = close.rolling(TD_Y, min_periods=200).max()
    ctx["dd12m"] = (close / roll_max - 1.0).rolling(TD_Y, min_periods=200).min()
    if vol is not None and vol.shape[1]:
        dv = close * vol
        ctx["adv3m"] = dv.rolling(3 * TD_M, min_periods=40).mean()
        ctx["adv12m"] = dv.rolling(TD_Y, min_periods=200).mean()
    else:
        ctx["adv3m"] = None
        ctx["adv12m"] = None
    return ctx


def factors_at(ctx, date):
    """Cross-section of factors as of `date`, sliced from precomputed causal series."""
    close = ctx["close"]
    idx = close.index
    pos = idx.searchsorted(pd.Timestamp(date), side="right") - 1
    if pos < TD_Y + TD_M:
        return None
    c = close

    def at(k):
        return ctx[k].iloc[pos]

    px = c.iloc[pos]
    f = pd.DataFrame(index=c.columns)
    f["price"] = px
    f["mom_12_1"] = c.iloc[pos - TD_M] / c.iloc[pos - TD_Y - TD_M] - 1.0
    f["mom_6_1"] = c.iloc[pos - TD_M] / c.iloc[pos - 7 * TD_M] - 1.0
    f["mom_3"] = px / c.iloc[pos - 3 * TD_M] - 1.0
    f["mom_1"] = px / c.iloc[pos - TD_M] - 1.0
    f["mom_36"] = (px / c.iloc[pos - 3 * TD_Y] - 1.0) if pos >= 3 * TD_Y else np.nan
    r6 = px / c.iloc[pos - 6 * TD_M] - 1.0
    r6p = c.iloc[pos - 6 * TD_M] / c.iloc[pos - 12 * TD_M] - 1.0
    f["mom_accel"] = r6 - r6p
    f["px_vs_ma200"] = px / at("ma200") - 1.0
    f["ma50_vs_ma200"] = at("ma50") / at("ma200") - 1.0
    f["pct_of_52w_high"] = px / at("hi52")
    f["off_52w_low"] = px / at("lo52") - 1.0
    f["days_above_ma200"] = at("frac_above200_12m")
    f["vol_6m"] = at("vol6m")
    f["vol_12m"] = at("vol12m")
    f["max_dd_12m"] = at("dd12m")
    f["skew_12m"] = at("skew12m")
    if ctx["adv3m"] is not None:
        f["adv_3m_usd"] = at("adv3m")
        f["vol_surge"] = at("adv3m") / at("adv12m")
    else:
        f["adv_3m_usd"] = np.nan
        f["vol_surge"] = np.nan
    f["date"] = idx[pos]
    return f


def fwd_return(close, date, horizon=TD_Y):
    idx = close.index
    pos = idx.searchsorted(pd.Timestamp(date), side="right") - 1
    fpos = pos + horizon
    if pos < 0 or fpos >= len(idx):
        return None
    return close.iloc[fpos] / close.iloc[pos] - 1.0
