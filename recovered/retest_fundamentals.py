"""Do point-in-time fundamentals predict forward 12m returns, and do they add anything
on top of the price/trend factors already in the model?"""
import numpy as np, pandas as pd
from scipy import stats

FUND = ["rev_yoy_ttm","rev_yoy_q","rev_accel","gross_margin","op_margin","net_margin",
        "gross_margin_delta","op_margin_delta","net_margin_delta","rule40",
        "rev_stability","profitable"]
PRICE = ["pct_of_52w_high","max_dd_12m","mom_36","adv_3m_usd","mom_12_1","skew_12m","vol_12m"]

def ic_table(p, cols, label):
    recs=[]
    for c in cols:
        s = p[[c,"fwd_ret","date"]].dropna()
        if len(s) < 5000: 
            pass
        ics = s.groupby("date").apply(
            lambda g: stats.spearmanr(g[c], g["fwd_ret"])[0] if len(g) > 50 else np.nan,
            include_groups=False).dropna()
        if len(ics) < 20: continue
        recs.append({"factor": c, "mean_IC": ics.mean(), "t_stat": ics.mean()/(ics.std()/np.sqrt(len(ics))),
                     "pct_pos": 100*(ics>0).mean(), "months": len(ics), "obs": len(s)})
    t = pd.DataFrame(recs).sort_values("mean_IC", ascending=False)
    print("", flush=True); print("=== %s ===" % label, flush=True)
    print(t.round(3).to_string(index=False), flush=True)
    return t

def dec(p, c, n=5):
    d = p[[c,"fwd_ret","date"]].dropna().copy()
    d["q"] = d.groupby("date")[c].transform(lambda x: pd.qcut(x.rank(method="first"), n, labels=False, duplicates="drop"))
    g = d.groupby("q")["fwd_ret"]
    t = pd.DataFrame({"mean":100*g.mean(),"median":100*g.median(),
                      "P_up50":100*g.apply(lambda x:(x>.5).mean()),
                      "P_dn30":100*g.apply(lambda x:(x<-.3).mean()),"n":g.size()})
    return t

def main():
    p = pd.read_parquet("data/panel_fund90.parquet")
    p["date"] = pd.to_datetime(p["date"])
    print("panel %s | rows with fundamentals %d" % (p.shape, p.rev_yoy_ttm.notna().sum()), flush=True)

    t1 = ic_table(p, FUND, "FUNDAMENTAL FACTORS vs FORWARD 12M RETURN (full panel)")
    t1.to_csv("out/ic_fundamentals.csv", index=False)

    # restrict to rows WITH fundamentals so price factors are measured on the same sample
    q = p[p.rev_yoy_ttm.notna()]
    t2 = ic_table(q, PRICE, "PRICE FACTORS on the SAME covered sample (for comparison)")
    t2.to_csv("out/ic_price_on_fund_sample.csv", index=False)

    print("", flush=True)
    for c in ["rev_yoy_ttm","op_margin","gross_margin","rule40","op_margin_delta","rev_accel"]:
        print("--- quintiles of %s (Q0 low -> Q4 high) ---" % c, flush=True)
        print(dec(p, c).round(2).to_string(), flush=True)
        print("", flush=True)

    # the key question: inside the algorithm's universe (high volatility), do they help?
    p["vdec"] = p.groupby("date")["vol_12m"].transform(
        lambda x: pd.qcut(x.rank(method="first"),10,labels=False,duplicates="drop"))
    hi = p[p.vdec >= 8]
    print("=== INSIDE THE HIGH-VOLATILITY COHORT (top 20%% vol, n=%d) ===" % len(hi), flush=True)
    t3 = ic_table(hi, FUND, "fundamental ICs within high-vol cohort")
    t3.to_csv("out/ic_fund_hivol.csv", index=False)
    print("", flush=True)
    for c in ["rev_yoy_ttm","op_margin","profitable","rule40"]:
        print("--- %s quintiles WITHIN high-vol cohort ---" % c, flush=True)
        print(dec(hi, c).round(2).to_string(), flush=True)
        print("", flush=True)
    print("RETEST_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
