"""Phase 3: build and HONESTLY validate a scoring model.

Design decisions that matter:
  * Features are cross-sectional PERCENTILE RANKS within each rebalance date. This makes the
    model learn relative positioning rather than absolute levels, which drift across regimes.
  * Train/test split is by TIME, never random. A random split would leak: the same date's
    cross-section would appear in both halves, and overlapping 12m forward windows would
    share outcome periods.
  * A purge gap is applied between train and test so the training set's 12m forward windows
    cannot overlap the test period.
  * We report CALIBRATION, not just ranking quality -- 'degree of confidence' requires that
    a predicted 20% probability actually happens ~20% of the time out of sample.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

FEATURES = ["mom_12_1", "mom_6_1", "mom_3", "mom_1", "mom_36", "mom_accel",
            "px_vs_ma200", "ma50_vs_ma200", "pct_of_52w_high", "off_52w_low",
            "days_above_ma200", "vol_6m", "vol_12m", "max_dd_12m", "skew_12m",
            "vol_surge", "adv_3m_usd", "price"]

WIN_THRESHOLD = 0.50     # "high growth" = +50% or more over the next 12 months


def add_ranks(panel, feats=FEATURES):
    """Cross-sectional percentile rank of each feature within each date."""
    p = panel.copy()
    for c in feats:
        p[c + "_r"] = p.groupby("date")[c].rank(pct=True)
    return p


def make_label(panel, thr=WIN_THRESHOLD):
    p = panel.copy()
    p["y"] = (p["fwd_ret"] > thr).astype(int)
    return p


def time_split(panel, train_end="2020-12-31", purge_months=12):
    """Split by date with a purge gap so train labels can't overlap test period."""
    te = pd.Timestamp(train_end)
    test_start = te + pd.DateOffset(months=purge_months)
    tr = panel[panel["date"] <= te]
    ts = panel[panel["date"] >= test_start]
    return tr, ts, test_start


def calibration_table(y_true, y_prob, bins=10):
    df = pd.DataFrame({"y": y_true, "p": y_prob})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), bins, labels=False, duplicates="drop")
    g = df.groupby("bin")
    return pd.DataFrame({
        "pred_mean": g["p"].mean(),
        "actual_rate": g["y"].mean(),
        "n": g.size(),
    })


def evaluate(name, y, p, panel_slice=None):
    out = {"model": name,
           "auc": roc_auc_score(y, p) if len(np.unique(y)) > 1 else np.nan,
           "brier": brier_score_loss(y, p),
           "base_rate": y.mean()}
    if panel_slice is not None:
        d = panel_slice.copy()
        d["p"] = p
        # top-decile-by-date selection performance
        d["sel"] = d.groupby("date")["p"].rank(pct=True)
        top = d[d["sel"] >= 0.90]
        out["top10pct_hit_rate"] = top["y"].mean()
        out["top10pct_mean_fwd"] = top["fwd_ret"].mean()
        out["top10pct_median_fwd"] = top["fwd_ret"].median()
        out["all_mean_fwd"] = d["fwd_ret"].mean()
        out["all_median_fwd"] = d["fwd_ret"].median()
        out["lift"] = out["top10pct_hit_rate"] / max(out["base_rate"], 1e-9)
    return out
