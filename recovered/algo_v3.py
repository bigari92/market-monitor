"""ALGORITHM v3 -- v2 (price/trend) plus point-in-time fundamentals.

What the fundamental retest changed:
  * Revenue GROWTH was dropped as a standalone signal. Its IC is indistinguishable from
    zero on the full panel (rev_yoy_ttm -0.004, t = -0.50; rev_yoy_q -0.002, t = -0.19;
    rev_accel +0.003, t = 0.71). The most intuitive growth metric predicts nothing.
    Growth enters only inside rule40, i.e. conditional on profitability.
  * Gross margin was also dropped (IC +0.010, t = 0.73). Operating and net margin work;
    gross margin does not.
  * rule40 and revenue stability are the two strongest additions, and inside the
    high-volatility cohort they are the strongest factors in the whole study
    (rule40 +0.131 t=17.4; rev_stability -0.150 t=-20.9, positive in 2% of months).
  * rule40 is hump-shaped like 3y momentum: healthy from -50% to +60%, deteriorating
    beyond. Same capped-plus-penalty treatment.
  * rev_stability is the only factor found that improves BOTH tails rather than just
    the downside, so it carries a full weight.
"""
import numpy as np, pandas as pd

PRICE_W = {
    "pct_of_52w_high":  1.0,
    "max_dd_12m":       1.0,
    "mom36_healthy":    0.75,
    "mom36_overext":   -0.75,
    "adv_3m_usd_log":   0.75,
    "days_above_ma200": 0.5,
    "mom_12_1":         0.5,
    "skew_12m":        -0.75,
}
FUND_W = {
    "r40_healthy":      1.0,
    "r40_excess":      -0.5,
    "rev_instability": -1.0,   # log1p(std of quarterly YoY revenue growth)
    "net_margin_c":     0.5,
    "profitable":       0.35,
}

MIN_PRICE, MIN_ADV = 5.0, 5_000_000
HEALTHY_CAP, OVEREXT_FROM = 2.0, 3.0
R40_LO, R40_HI = -0.5, 0.6


def zs(s):
    m, sd = s.mean(), s.std()
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - m) / sd).clip(-3, 3)


def _derive(d):
    d = d.copy()
    d["adv_3m_usd_log"] = np.log(d["adv_3m_usd"].clip(lower=1))
    m36 = d["mom_36"].fillna(0.0)
    d["mom36_healthy"] = m36.clip(lower=-0.5, upper=HEALTHY_CAP)
    d["mom36_overext"] = np.log1p(m36.clip(lower=OVEREXT_FROM)) - np.log1p(OVEREXT_FROM)
    if "rule40" in d.columns:
        r = d["rule40"]
        d["r40_healthy"] = r.clip(lower=R40_LO, upper=R40_HI)
        d["r40_excess"] = (r - R40_HI).clip(lower=0)
        d["rev_instability"] = np.log1p(d["rev_stability"].clip(lower=0))
        d["net_margin_c"] = d["net_margin"].clip(-2, 0.5)
    return d


def score(df, vol_gate=None, use_fundamentals=True, require_fundamentals=False):
    d = df[(df["price"] >= MIN_PRICE) & (df["adv_3m_usd"] >= MIN_ADV)].copy()
    if len(d) < 50:
        return None
    if vol_gate is not None:
        vp = d["vol_12m"].rank(pct=True)
        d = d[(vp >= vol_gate[0]) & (vp <= vol_gate[1])]
    if require_fundamentals and use_fundamentals:
        d = d.dropna(subset=["rule40", "rev_stability"])
    if len(d) < 30:
        return None

    d = _derive(d)
    weights = dict(PRICE_W)
    if use_fundamentals:
        weights.update(FUND_W)

    tot = pd.Series(0.0, index=d.index)
    for f, w in weights.items():
        if f not in d.columns:
            continue
        col = d[f]
        z = zs(col.dropna())
        # missing fundamentals score neutrally (z = 0) rather than being excluded
        zf = pd.Series(0.0, index=d.index)
        zf.loc[z.index] = z
        d["z_" + f] = zf
        tot = tot + w * zf
    d["score"] = tot
    d["score_pct"] = d["score"].rank(pct=True)
    return d
