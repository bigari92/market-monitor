"""ALGORITHM v4 -- fundamentals folded in two different ways, to find which one works.

v3 hand-weighted z-scores of fundamentals and FAILED to beat v2. The orthogonality test
showed the information is additive (rev_stability retains 69% of its IC after removing
every price factor), so the fault was construction:
  * fundamental variables are violently skewed (op_margin p5 = -4.7, rule40 p5 = -23),
    so a z-score is dominated by outliers even after clipping. v4 ranks instead.
  * their payoff is concentrated in avoiding a bad tail, not in ranking the good end,
    which argues for an exclusion rather than a tilt.
Weights on the fundamental block are proportional to measured RESIDUAL IC, not chosen.
"""
import numpy as np, pandas as pd

PRICE_W = {"pct_of_52w_high":1.0, "max_dd_12m":1.0, "mom36_healthy":0.75,
           "mom36_overext":-0.75, "adv_3m_usd_log":0.75, "days_above_ma200":0.5,
           "mom_12_1":0.5, "skew_12m":-0.75}
# weights ∝ residual IC from orthogonality.py (0.099 / 0.065 / 0.057 / 0.038)
FUND_W = {"rev_instability":-1.0, "r40_healthy":0.65, "net_margin_c":0.55, "profitable":0.40}

MIN_PRICE, MIN_ADV = 5.0, 5_000_000
R40_LO, R40_HI = -0.5, 0.6
# exclusion thresholds from the bucket tables: these are the buckets where P(-30%) > 45%
EXCL_R40 = -1.0
EXCL_INSTAB = 0.80


def cs_rank(s):
    """Cross-sectional percentile rank centred on zero. Robust to skew and outliers."""
    r = s.rank(pct=True)
    return (r - 0.5) * 2.0


def _derive(d):
    d = d.copy()
    d["adv_3m_usd_log"] = np.log(d["adv_3m_usd"].clip(lower=1))
    m36 = d["mom_36"].fillna(0.0)
    d["mom36_healthy"] = m36.clip(lower=-0.5, upper=2.0)
    d["mom36_overext"] = np.log1p(m36.clip(lower=3.0)) - np.log1p(3.0)
    if "rule40" in d.columns:
        d["r40_healthy"] = d["rule40"].clip(lower=R40_LO, upper=R40_HI)
        d["rev_instability"] = np.log1p(d["rev_stability"].clip(lower=0))
        d["net_margin_c"] = d["net_margin"]
    return d


def score(df, vol_gate=None, mode="rank_fund"):
    """mode: 'price' (v2 equivalent, rank-normalised) | 'rank_fund' | 'filter' | 'both'"""
    d = df[(df["price"] >= MIN_PRICE) & (df["adv_3m_usd"] >= MIN_ADV)].copy()
    if len(d) < 50:
        return None
    if vol_gate is not None:
        vp = d["vol_12m"].rank(pct=True)
        d = d[(vp >= vol_gate[0]) & (vp <= vol_gate[1])]
    if len(d) < 40:
        return None
    d = _derive(d)

    if mode in ("filter", "both") and "rule40" in d.columns:
        bad = ((d["rule40"] < EXCL_R40) |
               (np.log1p(d["rev_stability"].clip(lower=0)) > np.log1p(EXCL_INSTAB)))
        d = d[~bad.fillna(False)]
        if len(d) < 30:
            return None

    weights = dict(PRICE_W)
    if mode in ("rank_fund", "both"):
        weights.update(FUND_W)

    tot = pd.Series(0.0, index=d.index)
    for f, w in weights.items():
        if f not in d.columns:
            continue
        col = d[f]
        rk = cs_rank(col.dropna())
        z = pd.Series(0.0, index=d.index)
        z.loc[rk.index] = rk
        tot = tot + w * z
    d["score"] = tot
    return d
