"""Point-in-time factor construction from daily price/volume panels.

Every factor at date T uses ONLY data with index <= T. No lookahead.
"""
import numpy as np
import pandas as pd

TD_M = 21          # trading days per month
TD_Y = 252         # trading days per year


def load_panel(close_glob="data/px_batches/close_*.parquet",
               vol_glob="data/px_batches/vol_*.parquet"):
    import glob
    cs, vs = [], []
    for f in sorted(glob.glob(close_glob)):
        try:
            cs.append(pd.read_parquet(f))
        except Exception:
            pass
    for f in sorted(glob.glob(vol_glob)):
        try:
            v = pd.read_parquet(f)
            if v.shape[1] > 0:
                vs.append(v)
        except Exception:
            pass
    close = pd.concat(cs, axis=1)
    close = close.loc[:, ~close.columns.duplicated()].sort_index()
    vol = pd.concat(vs, axis=1) if vs else pd.DataFrame(index=close.index)
    vol = vol.loc[:, ~vol.columns.duplicated()].sort_index()
    vol = vol.reindex(columns=close.columns)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    vol.index = pd.to_datetime(vol.index).tz_localize(None)
    return close, vol


def ret(close, lo, hi):
    """Return over window [t-hi, t-lo] in trading days, as a DataFrame aligned to close."""
    return close.shift(lo) / close.shift(hi) - 1.0


def compute_factors(close, vol, date):
    """Factor cross-section as of `date` (uses data <= date only)."""
    c = close.loc[:date]
    v = vol.loc[:date] if vol.shape[1] else None
    if len(c) < TD_Y + TD_M:
        return None

    px = c.iloc[-1]
    f = pd.DataFrame(index=c.columns)
    f["price"] = px

    # --- Momentum family -------------------------------------------------
    f["mom_12_1"] = c.iloc[-1 - TD_M] / c.iloc[-TD_Y - TD_M] - 1.0   # 12m skip last month
    f["mom_6_1"]  = c.iloc[-1 - TD_M] / c.iloc[-6 * TD_M - TD_M] - 1.0
    f["mom_3"]    = c.iloc[-1] / c.iloc[-3 * TD_M] - 1.0
    f["mom_1"]    = c.iloc[-1] / c.iloc[-TD_M] - 1.0                  # short-term reversal
    if len(c) >= 3 * TD_Y:
        f["mom_36"] = c.iloc[-1] / c.iloc[-3 * TD_Y] - 1.0            # long-term reversal
    else:
        f["mom_36"] = np.nan

    # Momentum acceleration: recent 6m vs prior 6m
    r_recent = c.iloc[-1] / c.iloc[-6 * TD_M] - 1.0
    r_prior  = c.iloc[-6 * TD_M] / c.iloc[-12 * TD_M] - 1.0
    f["mom_accel"] = r_recent - r_prior

    # --- Trend / structure -----------------------------------------------
    ma50  = c.iloc[-50:].mean()
    ma200 = c.iloc[-200:].mean()
    f["px_vs_ma200"] = px / ma200 - 1.0
    f["ma50_vs_ma200"] = ma50 / ma200 - 1.0
    hi52 = c.iloc[-TD_Y:].max()
    lo52 = c.iloc[-TD_Y:].min()
    f["pct_of_52w_high"] = px / hi52
    f["off_52w_low"] = px / lo52 - 1.0
    # fraction of last 12m spent above the 200d moving average
    ma200_series = c.rolling(200).mean()
    above = (c > ma200_series).iloc[-TD_Y:]
    f["days_above_ma200"] = above.mean()

    # --- Risk ------------------------------------------------------------
    r = c.pct_change(fill_method=None)
    f["vol_6m"] = r.iloc[-6 * TD_M:].std() * np.sqrt(TD_Y)
    f["vol_12m"] = r.iloc[-TD_Y:].std() * np.sqrt(TD_Y)
    roll_max = c.iloc[-TD_Y:].cummax()
    f["max_dd_12m"] = (c.iloc[-TD_Y:] / roll_max - 1.0).min()
    # upside/downside return asymmetry
    r12 = r.iloc[-TD_Y:]
    f["skew_12m"] = r12.skew()

    # --- Liquidity / participation ---------------------------------------
    if v is not None and v.shape[1]:
        dv = (c * v)
        adv_3m = dv.iloc[-3 * TD_M:].mean()
        adv_12m = dv.iloc[-TD_Y:].mean()
        f["adv_3m_usd"] = adv_3m
        f["vol_surge"] = adv_3m / adv_12m          # volume expansion
    else:
        f["adv_3m_usd"] = np.nan
        f["vol_surge"] = np.nan

    f["date"] = date
    return f


def forward_return(close, date, horizon_days=TD_Y):
    """Realized forward return from `date` over horizon. Uses future data — ONLY for scoring."""
    idx = close.index
    pos = idx.searchsorted(pd.Timestamp(date))
    if pos >= len(idx):
        return None
    fpos = pos + horizon_days
    if fpos >= len(idx):
        return None
    p0 = close.iloc[pos]
    p1 = close.iloc[fpos]
    return p1 / p0 - 1.0
