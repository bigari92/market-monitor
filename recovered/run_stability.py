"""Is the signal a stable LIFT over a regime-dependent BASE RATE?

If base rate swings by year but lift is stable, then the model can rank reliably but
cannot state an absolute probability -- which is exactly what 'degree of confidence' needs.
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
import model as M

FE = [c + "_r" for c in M.FEATURES]

def main():
    p = pd.read_parquet("data/panel.parquet"); p["date"] = pd.to_datetime(p["date"])
    p = M.add_ranks(p); p["y"] = (p["fwd_ret"] > 0.50).astype(int)
    tr = p[p["date"] <= "2018-12-31"]
    ts = p[p["date"] >= "2020-01-31"].copy()
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_depth=5,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    clf.fit(tr[FE].values, tr["y"].values)
    ts["p"] = clf.predict_proba(ts[FE].values)[:,1]
    ts["sel"] = ts.groupby("date")["p"].rank(pct=True)
    ts["year"] = ts["date"].dt.year

    rows = []
    for yr, g in ts.groupby("year"):
        base = g.y.mean()
        top = g[g.sel >= 0.90]
        bot = g[g.sel <= 0.10]
        rows.append({"year": yr, "n": len(g),
                     "base_P>50%": 100*base,
                     "top10%_P>50%": 100*top.y.mean(),
                     "lift": top.y.mean()/max(base,1e-9),
                     "top10%_mean": 100*top.fwd_ret.mean(),
                     "top10%_median": 100*top.fwd_ret.median(),
                     "top10%_P<-30%": 100*(top.fwd_ret<-.3).mean(),
                     "all_mean": 100*g.fwd_ret.mean(),
                     "all_median": 100*g.fwd_ret.median()})
    df = pd.DataFrame(rows)
    print("=== YEAR BY YEAR: signal-formation year -> realised over NEXT 12 months ===", flush=True)
    print(df.round(2).to_string(index=False), flush=True)
    print("", flush=True)
    print("base rate range: %.1f%% - %.1f%%  (ratio %.1fx)" % (
        df["base_P>50%"].min(), df["base_P>50%"].max(), df["base_P>50%"].max()/df["base_P>50%"].min()), flush=True)
    print("lift range:      %.2fx - %.2fx  (mean %.2fx, sd %.2f)" % (
        df["lift"].min(), df["lift"].max(), df["lift"].mean(), df["lift"].std()), flush=True)
    df.to_csv("out/stability_by_year.csv", index=False)
    print("STABILITY_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
