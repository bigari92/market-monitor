"""Point-in-time factors, ported from `recovered/factors.py`.

`recovered/` is evidence and is never imported or edited (docs/RECOVERY.md), so this is a
deliberate port rather than a re-export. Every factor definition below is the recovered one,
arithmetic unchanged, because changing a definition while porting would quietly invalidate the
only validation work that exists.

What the port *does* change, and why each is a fix rather than a tweak:

1. **The 273-session floor is returned, not hidden.** The recovered `compute_factors` answers
   `None` for a cross-section with fewer than `TD_Y + TD_M` sessions. Here the floor applies
   per ticker: a name with 200 sessions is dropped from the cross-section and *counted*, rather
   than poisoning the whole date or being scored on short history.
2. **`close` vs `adjclose` is now a decision.** The recovered code received one price series from
   `auto_adjust=True` and could not tell a dividend from a drawdown. Trend and drawdown factors
   read `close` (split-adjusted, dividends intact) because a 4% dividend is not a 4% drawdown;
   the momentum family reads `adjclose`, because a total-return series is the honest answer to
   "how much did a holder make". The recovered code could not express that distinction at all.
3. **No `date` column.** The recovered frame carried one so many dates could be concatenated for
   a backtest panel. This scores one cross-section per run; the as-of date belongs to the run,
   not to every row of it.

Nothing is added. No factor is re-weighted, no threshold is moved, and no new factor is
introduced — CLOUD-RULES.md §5. The list is the recovered list.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TD_M = 21   # trading days per month
TD_Y = 252  # trading days per year

# The recovered floor: TD_Y + TD_M sessions before a name is scored at all.
MIN_SESSIONS = TD_Y + TD_M

# Every factor the recovered code produced, in its order. Used to assert the port stays complete.
FACTOR_NAMES = (
    "price",
    "mom_12_1", "mom_6_1", "mom_3", "mom_1", "mom_36", "mom_accel",
    "px_vs_ma200", "ma50_vs_ma200", "pct_of_52w_high", "off_52w_low", "days_above_ma200",
    "vol_6m", "vol_12m", "max_dd_12m", "skew_12m",
    "adv_3m_usd", "vol_surge",
)


def _tail(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    return frame.iloc[-n:] if len(frame) >= n else frame


def compute_factors(close: pd.DataFrame, volume: pd.DataFrame, as_of,
                    adjclose: pd.DataFrame | None = None,
                    min_sessions: int = MIN_SESSIONS) -> pd.DataFrame:
    """The factor cross-section as of `as_of`, using data with index <= as_of only.

    `close` is split-adjusted with dividends intact; `adjclose` is total return. Passing only
    `close` reproduces the recovered single-series behaviour exactly, which is what the port test
    checks against.

    Returns one row per ticker that cleared `min_sessions`, indexed by ticker.
    """
    as_of = pd.Timestamp(as_of)
    c_all = close.loc[:as_of]
    if c_all.empty:
        raise ValueError(f"no price history at or before {as_of:%Y-%m-%d}")
    a_all = (adjclose if adjclose is not None else close).loc[:as_of]
    v_all = volume.loc[:as_of] if volume is not None and volume.shape[1] else None

    # Per-ticker history, counted on the series the trend factors use.
    history = c_all.notna().sum()
    keep = history.index[history >= min_sessions]
    if len(keep) == 0:
        raise ValueError(
            f"no ticker has {min_sessions} sessions at {as_of:%Y-%m-%d}; the panel is too short "
            "to score, which is a data problem and not an empty market"
        )

    c = c_all[keep]
    a = a_all.reindex(columns=keep)
    v = v_all.reindex(columns=keep) if v_all is not None else None

    px = c.ffill().iloc[-1]
    f = pd.DataFrame(index=keep)
    f.index.name = "ticker"
    f["price"] = px

    # --- Momentum family, on total return ---------------------------------
    # Positional offsets, exactly as recovered: iloc[-1 - TD_M] / iloc[-TD_Y - TD_M] - 1.
    af = a.ffill()

    def at(n: int) -> pd.Series:
        """The session n positions back from the end, forward-filled."""
        return af.iloc[-n] if len(af) >= n else pd.Series(np.nan, index=keep)

    f["mom_12_1"] = at(1 + TD_M) / at(TD_Y + TD_M) - 1.0   # 12m, skipping the last month
    f["mom_6_1"] = at(1 + TD_M) / at(6 * TD_M + TD_M) - 1.0
    f["mom_3"] = at(1) / at(3 * TD_M) - 1.0
    f["mom_1"] = at(1) / at(TD_M) - 1.0                    # short-term reversal
    # The recovered code sets mom_36 to NaN when the panel is shorter than 3 years, and
    # algo_v4._derive fills it with 0.0. Per ticker: NaN where that name lacks 3 years.
    f["mom_36"] = (at(1) / at(3 * TD_Y) - 1.0) if len(af) >= 3 * TD_Y \
        else pd.Series(np.nan, index=keep)

    # Momentum acceleration: recent 6m against the prior 6m.
    recent = at(1) / at(6 * TD_M) - 1.0
    prior = at(6 * TD_M) / at(12 * TD_M) - 1.0
    f["mom_accel"] = recent - prior

    # --- Trend and structure, on split-adjusted close ---------------------
    # On `close`, not `adjclose`: "is the price above its 200-day average" is a question about
    # the price a holder sees, and a dividend-adjusted series answers a different question.
    cf = c.ffill()
    ma50 = _tail(cf, 50).mean()
    ma200 = _tail(cf, 200).mean()
    f["px_vs_ma200"] = px / ma200 - 1.0
    f["ma50_vs_ma200"] = ma50 / ma200 - 1.0

    last_year = _tail(cf, TD_Y)
    f["pct_of_52w_high"] = px / last_year.max()
    f["off_52w_low"] = px / last_year.min() - 1.0
    # Fraction of the last 12m spent above the 200d average. `min_periods=200` keeps a name's
    # early sessions out of the count rather than comparing against a partial average.
    ma200_series = cf.rolling(200, min_periods=200).mean()
    f["days_above_ma200"] = (cf > ma200_series).iloc[-TD_Y:].mean()

    # --- Risk -------------------------------------------------------------
    r = cf.pct_change(fill_method=None)
    f["vol_6m"] = r.iloc[-6 * TD_M:].std() * np.sqrt(TD_Y)
    f["vol_12m"] = r.iloc[-TD_Y:].std() * np.sqrt(TD_Y)
    # Deepest trough against its own running maximum anywhere in the window. RECOVERY.md's
    # fifth item asks whether this is the same quantity as pct_of_52w_high; it is not, and
    # `signal.factor_diagnostics` measures their correlation rather than assuming either way.
    running_max = last_year.cummax()
    f["max_dd_12m"] = (last_year / running_max - 1.0).min()
    f["skew_12m"] = r.iloc[-TD_Y:].skew()

    # --- Liquidity --------------------------------------------------------
    if v is not None:
        dollar_volume = cf * v.ffill()
        adv_3m = dollar_volume.iloc[-3 * TD_M:].mean()
        adv_12m = dollar_volume.iloc[-TD_Y:].mean()
        f["adv_3m_usd"] = adv_3m
        f["vol_surge"] = adv_3m / adv_12m
    else:
        f["adv_3m_usd"] = np.nan
        f["vol_surge"] = np.nan

    missing = [name for name in FACTOR_NAMES if name not in f.columns]
    if missing:
        raise AssertionError(f"port is incomplete; missing factors: {missing}")
    return f[list(FACTOR_NAMES)]


def coverage(close: pd.DataFrame, as_of, min_sessions: int = MIN_SESSIONS) -> dict:
    """How many names the session floor admits and excludes. Reported, never silent."""
    history = close.loc[:pd.Timestamp(as_of)].notna().sum()
    return {
        "tickers_in_panel": int(len(history)),
        "scorable": int((history >= min_sessions).sum()),
        "short_history": int((history < min_sessions).sum()),
        "min_sessions": int(min_sessions),
        "have_3y_for_mom36": int((history >= 3 * TD_Y).sum()),
    }
