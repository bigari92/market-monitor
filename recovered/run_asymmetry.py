"""THE key question: conditional on a stock being CAPABLE of a big move (high volatility),
what separates the ones that go up from the ones that go down?

Selecting on volatility alone raises both tails equally -- that is not an edge.
An edge requires a factor whose up-tail gain exceeds its down-tail cost.
"""
import numpy as np, pandas as pd
from scipy import stats
import model as M

def asym_table(p, col, label):
    d = p[[col, "fwd_ret", "date"]].dropna().copy()
    d["dec"] = d.groupby("date")[col].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False, duplicates="drop"))
    g = d.groupby("dec")["fwd_ret"]
    t = pd.DataFrame({"mean": 100*g.mean(), "median": 100*g.median(),
                      "P_up50": 100*g.apply(lambda x:(x>.5).mean()),
                      "P_dn30": 100*g.apply(lambda x:(x<-.3).mean())})
    t["up_dn_ratio"] = t["P_up50"]/t["P_dn30"].replace(0,np.nan)
    return t

def main():
    p = pd.read_parquet("data/panel.parquet"); p["date"] = pd.to_datetime(p["date"])
    p["vdec"] = p.groupby("date")["vol_12m"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 10, labels=False, duplicates="drop"))

    print("=== STEP 1: volatility alone raises BOTH tails (no edge) ===", flush=True)
    g = p.groupby("vdec")["fwd_ret"]
    t0 = pd.DataFrame({"mean":100*g.mean(),"median":100*g.median(),
                       "P_up50":100*g.apply(lambda x:(x>.5).mean()),
                       "P_dn30":100*g.apply(lambda x:(x<-.3).mean())})
    t0["up_dn_ratio"]=t0.P_up50/t0.P_dn30
    print(t0.round(2).to_string(), flush=True)

    hi = p[p.vdec >= 7].copy()          # the "capable of a big move" cohort
    print("", flush=True)
    print("=== STEP 2: WITHIN the high-volatility cohort (top 3 vol deciles, n=%d) ===" % len(hi), flush=True)
    print("cohort base: mean %+.2f%% | median %+.2f%% | P(up50) %.2f%% | P(dn30) %.2f%%" % (
        100*hi.fwd_ret.mean(), 100*hi.fwd_ret.median(),
        100*(hi.fwd_ret>.5).mean(), 100*(hi.fwd_ret<-.3).mean()), flush=True)

    recs=[]
    for c in ["mom_12_1","mom_6_1","mom_3","mom_1","mom_36","mom_accel","px_vs_ma200",
              "ma50_vs_ma200","pct_of_52w_high","off_52w_low","days_above_ma200",
              "max_dd_12m","skew_12m","vol_surge","adv_3m_usd","price"]:
        s = hi[[c,"fwd_ret","date"]].dropna()
        ic = s.groupby("date").apply(lambda g: stats.spearmanr(g[c],g["fwd_ret"])[0] if len(g)>30 else np.nan,
                                     include_groups=False).dropna()
        t = asym_table(hi, c, c)
        recs.append({"factor":c, "mean_IC":ic.mean(), "t":ic.mean()/(ic.std()/np.sqrt(len(ic))),
                     "Q5_mean":t["mean"].iloc[-1], "Q1_mean":t["mean"].iloc[0],
                     "Q5_up50":t["P_up50"].iloc[-1], "Q5_dn30":t["P_dn30"].iloc[-1],
                     "Q5_ratio":t["up_dn_ratio"].iloc[-1], "Q1_ratio":t["up_dn_ratio"].iloc[0]})
    r = pd.DataFrame(recs).sort_values("mean_IC", ascending=False)
    print("", flush=True)
    print("--- factor performance INSIDE the high-vol cohort (Q5=highest quintile of factor) ---", flush=True)
    print(r.round(3).to_string(index=False), flush=True)
    r.to_csv("out/asymmetry_hivol.csv", index=False)

    print("", flush=True)
    for c in ["pct_of_52w_high","max_dd_12m","adv_3m_usd","mom_36"]:
        print("--- %s quintiles within high-vol cohort ---" % c, flush=True)
        print(asym_table(hi,c,c).round(2).to_string(), flush=True)
        print("", flush=True)
    print("ASYM_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
