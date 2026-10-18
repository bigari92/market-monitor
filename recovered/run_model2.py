"""Three-way purged time split + isotonic recalibration + permutation importance.

train   <= 2018-12   |  purge 12m  |  calib 2020-01..2020-12  | purge 12m |  test 2022-01..
Calibration is fitted on data the model never trained on, and evaluated on data neither
the model nor the calibrator has seen.
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.inspection import permutation_importance
import model as M

FE = [c + "_r" for c in M.FEATURES]

def split(p):
    d = p["date"]
    tr = p[d <= "2018-12-31"]
    ca = p[(d >= "2020-01-31") & (d <= "2020-12-31")]
    ts = p[d >= "2022-01-31"]
    return tr, ca, ts

def go(p, thr, name):
    p = p.copy(); p["y"] = (p["fwd_ret"] > thr).astype(int)
    tr, ca, ts = split(p)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_depth=5,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    clf.fit(tr[FE].values, tr["y"].values)
    raw_ca = clf.predict_proba(ca[FE].values)[:,1]
    raw_ts = clf.predict_proba(ts[FE].values)[:,1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_ca, ca["y"].values)
    cal_ts = iso.predict(raw_ts)
    y = ts["y"].values
    print("", flush=True)
    print("######## %s : P(fwd12m > %+.0f%%) ########" % (name, thr*100), flush=True)
    print("train n=%d (%s..%s) base=%.2f%% | calib n=%d | test n=%d (%s..%s) base=%.2f%%" % (
        len(tr), tr.date.min().date(), tr.date.max().date(), 100*tr.y.mean(), len(ca),
        len(ts), ts.date.min().date(), ts.date.max().date(), 100*y.mean()), flush=True)
    print("OOS AUC %.4f | Brier raw %.4f -> calibrated %.4f | base-rate Brier %.4f" % (
        roc_auc_score(y, raw_ts), brier_score_loss(y, raw_ts),
        brier_score_loss(y, cal_ts), brier_score_loss(y, np.full(len(y), y.mean()))), flush=True)
    d = pd.DataFrame({"y": y, "p": cal_ts})
    d["bin"] = pd.qcut(d.p.rank(method="first"), 10, labels=False, duplicates="drop")
    g = d.groupby("bin")
    cal = pd.DataFrame({"predicted_%": 100*g.p.mean(), "actual_%": 100*g.y.mean(), "n": g.size()})
    print("--- CALIBRATED out-of-sample reliability ---", flush=True)
    print(cal.round(2).to_string(), flush=True)
    return clf, iso, ts, cal_ts

def main():
    p = pd.read_parquet("data/panel.parquet"); p["date"] = pd.to_datetime(p["date"])
    p = M.add_ranks(p)
    for thr, nm in [(0.50, "MOONSHOT"), (0.20, "COMPOUNDER")]:
        clf, iso, ts, pr = go(p, thr, nm)
        if thr == 0.50:
            sub = ts.sample(30000, random_state=0)
            r = permutation_importance(clf, sub[FE].values, sub["y"].values,
                                       n_repeats=5, random_state=0, scoring="roc_auc", n_jobs=1)
            imp = pd.Series(r.importances_mean, index=[f[:-2] for f in FE]).sort_values(ascending=False)
            print("", flush=True)
            print("--- PERMUTATION IMPORTANCE (drop in OOS AUC when feature is shuffled) ---", flush=True)
            print((imp*1000).round(2).to_string(), flush=True)
            imp.to_csv("out/feature_importance.csv")
    print("", flush=True); print("MODEL2_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
