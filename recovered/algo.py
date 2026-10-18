"""THE ALGORITHM (v2).

Core empirical findings this encodes:
  1. Within the 'capable of a big move' cohort, quality-of-trend factors barely raise the
     up-tail but roughly HALVE the down-tail. The edge is loss avoidance, not winner-finding.
  2. Long-term momentum is HUMP-SHAPED, not linear. Moderate 3y gains (0-200%) are healthy;
     beyond ~300% forward returns deteriorate sharply and past +800% they are outright
     negative (mean -7.5%, median -27.9%, 48% fall >30%). v1 used a linear weight here and
     got the extremes exactly backwards.
  3. `price` is EXCLUDED despite a strong backtest IC: the universe holds only currently
     listed stocks, so the cheap bucket is precisely where delisted zeroes are missing.
     That measured edge is survivorship bias. A hard price FLOOR is used instead.

Weights are round numbers from IC sign and rough magnitude -- not optimised. Optimising
weights over 127 overlapping cross-sections would overfit.
"""
import numpy as np, pandas as pd

WEIGHTS = {
    "pct_of_52w_high":  1.0,
    "max_dd_12m":       1.0,     # less negative = shallower drawdown = better
    "mom36_healthy":    0.75,    # hump-shaped, see mom36_transform
    "mom36_overext":   -0.75,    # explicit parabolic-extension penalty
    "adv_3m_usd_log":   0.75,
    "days_above_ma200": 0.5,
    "mom_12_1":         0.5,
    "skew_12m":        -0.75,    # low skew (no lottery jumps) is better
}

MIN_PRICE = 5.0
MIN_ADV = 5_000_000
HEALTHY_CAP = 2.0      # +200% over 3y: top of the healthy band
OVEREXT_FROM = 3.0     # +300% over 3y: deterioration starts


def mom36_transform(m):
    """Split 3y momentum into a healthy component and an over-extension penalty."""
    healthy = m.clip(lower=-0.5, upper=HEALTHY_CAP)
    overext = np.log1p(m.clip(lower=OVEREXT_FROM)) - np.log1p(OVEREXT_FROM)
    return healthy, overext


def zs(s):
    m, sd = s.mean(), s.std()
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - m) / sd).clip(-3, 3)


def score(df, vol_gate=None):
    d = df.copy()
    d = d[(d["price"] >= MIN_PRICE) & (d["adv_3m_usd"] >= MIN_ADV)]
    if len(d) < 50:
        return None
    if vol_gate is not None:
        vp = d["vol_12m"].rank(pct=True)
        d = d[(vp >= vol_gate[0]) & (vp <= vol_gate[1])]
        if len(d) < 30:
            return None
    d["adv_3m_usd_log"] = np.log(d["adv_3m_usd"].clip(lower=1))
    h, o = mom36_transform(d["mom_36"].fillna(0.0))
    d["mom36_healthy"], d["mom36_overext"] = h, o
    tot = 0.0
    for f, w in WEIGHTS.items():
        if f in d.columns:
            z = zs(d[f])
            d["z_" + f] = z
            tot = tot + w * z
    d["score"] = tot
    d["score_pct"] = d["score"].rank(pct=True)
    return d
