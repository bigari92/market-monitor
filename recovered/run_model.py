"""Train + validate two models with a strict TIME split and a 12-month purge gap.

Model A ("compounder"):  predicts P(fwd 12m return > +20%)  -> expected-return maximiser
Model B ("moonshot"):    predicts P(fwd 12m return > +50%)  -> big-move hunter
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
import model as M

def run(p, thr, name, train_end="2020-12-31", purge=12):
    p = p.copy()
    p["y"] = (p["fwd_ret"] > thr).astype(int)
    te = pd.Timestamp(train_end); ts_start = te + pd.DateOffset(months=purge)
    tr = p[p["date"] <= te]; ts = p[p["date"] >= ts_start]
    feats = [c + "_r" for c in M.FEATURES]
    Xtr, ytr = tr[feats].values, tr["y"].values
    Xts, yts = ts[feats].values, ts["y"].values
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_depth=5,
                                         min_samples_leaf=200, l2_regularization=1.0,
                                         random_state=0)
    clf.fit(Xtr, ytr)
    ptr, pts = clf.predict_proba(Xtr)[:,1], clf.predict_proba(Xts)[:,1]
    print("", flush=True)
    print("################ MODEL %s : P(fwd 12m > %+.0f%%) ################" % (name, thr*100), flush=True)
    print("train %s..%s  n=%d  base=%.2f%%" % (tr.date.min().date(), tr.date.max().date(), len(tr), 100*ytr.mean()), flush=True)
    print("test  %s..%s  n=%d  base=%.2f%%" % (ts.date.min().date(), ts.date.max().date(), len(ts), 100*yts.mean()), flush=True)
    print("AUC   in-sample %.4f | OUT-OF-SAMPLE %.4f" % (roc_auc_score(ytr,ptr), roc_auc_score(yts,pts)), flush=True)
    print("Brier out-of-sample %.4f (base-rate-only model: %.4f)" % (
        brier_score_loss(yts,pts), brier_score_loss(yts, np.full(len(yts), yts.mean()))), flush=True)

    ts = ts.copy(); ts["p"] = pts
    ts["sel"] = ts.groupby("date")["p"].rank(pct=True)
    print("", flush=True)
    print("--- OUT-OF-SAMPLE outcomes by model-score decile ---", flush=True)
    ts["dec"] = ts.groupby("date")["p"].transform(lambda x: pd.qcut(x.rank(method="first"),10,labels=False,duplicates="drop"))
    g = ts.groupby("dec")
    tab = pd.DataFrame({"mean_fwd": 100*g.fwd_ret.mean(), "median_fwd": 100*g.fwd_ret.median(),
                        "P_gt50": 100*g.fwd_ret.apply(lambda x:(x>.5).mean()),
                        "P_gt100": 100*g.fwd_ret.apply(lambda x:(x>1).mean()),
                        "P_lt-30": 100*g.fwd_ret.apply(lambda x:(x<-.3).mean()),
                        "n": g.size()})
    print(tab.round(2).to_string(), flush=True)

    print("", flush=True)
    print("--- CALIBRATION (out-of-sample): does a predicted p%% actually happen p%% of the time? ---", flush=True)
    cal = M.calibration_table(yts, pts, bins=10)
    cal["pred_mean"]*=100; cal["actual_rate"]*=100
    print(cal.round(2).to_string(), flush=True)
    return ts, tab, cal

def main():
    p = pd.read_parquet("data/panel.parquet")
    p["date"] = pd.to_datetime(p["date"])
    p = M.add_ranks(p)
    a_ts, a_tab, a_cal = run(p, 0.20, "A-COMPOUNDER")
    b_ts, b_tab, b_cal = run(p, 0.50, "B-MOONSHOT")
    a_tab.to_csv("out/model_A_deciles.csv"); a_cal.to_csv("out/model_A_calib.csv")
    b_tab.to_csv("out/model_B_deciles.csv"); b_cal.to_csv("out/model_B_calib.csv")
    print("", flush=True); print("MODEL_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
