"""Are the fundamentals redundant, or did I just weight them badly?

Test: regress forward return on the PRICE factors within each date, then measure the IC
of each fundamental factor against the RESIDUAL. Residual IC near zero => the price
factors already carry the information. Residual IC intact => the information is real and
additive, and the score construction is at fault.
"""
import numpy as np, pandas as pd
from scipy import stats

PRICE = ["pct_of_52w_high","max_dd_12m","mom_36","adv_3m_usd","mom_12_1","skew_12m",
         "vol_12m","days_above_ma200"]
FUND  = ["rule40","rev_stability","net_margin","op_margin","profitable","rev_yoy_ttm"]

def zc(s):
    m,sd = s.mean(), s.std()
    return (s-m)/sd if np.isfinite(sd) and sd>0 else s*0

def main():
    p = pd.read_parquet("data/panel_fund90.parquet"); p["date"]=pd.to_datetime(p["date"])
    p["vdec"]=p.groupby("date")["vol_12m"].transform(
        lambda x: pd.qcut(x.rank(method="first"),10,labels=False,duplicates="drop"))
    hi = p[p.vdec>=8].copy()
    hi["rev_stability"] = np.log1p(hi["rev_stability"].clip(lower=0))

    print("=== 1. CORRELATION of fundamental factors with price factors (high-vol cohort) ===", flush=True)
    sub = hi[PRICE+FUND].dropna()
    print("   n = %d complete rows" % len(sub), flush=True)
    cm = sub.corr(method="spearman").loc[FUND, PRICE]
    print(cm.round(2).to_string(), flush=True)
    print("", flush=True)
    print("   max |corr| with any price factor:", flush=True)
    for f in FUND:
        j = cm.loc[f].abs().idxmax()
        print("     %-14s %+.2f  (vs %s)" % (f, cm.loc[f,j], j), flush=True)

    print("", flush=True)
    print("=== 2. RESIDUAL IC: fundamental vs forward return, price factors removed ===", flush=True)
    recs=[]
    for c in FUND:
        raws, resids = [], []
        for d,g in hi.groupby("date"):
            s = g[[c,"fwd_ret"]+PRICE].dropna()
            if len(s) < 60: continue
            X = np.column_stack([zc(s[k]).values for k in PRICE] + [np.ones(len(s))])
            y = s["fwd_ret"].values
            try:
                beta,_,_,_ = np.linalg.lstsq(X, y, rcond=None)
            except Exception:
                continue
            res = y - X@beta
            raws.append(stats.spearmanr(s[c], y)[0])
            resids.append(stats.spearmanr(s[c], res)[0])
        raws, resids = np.array(raws), np.array(resids)
        if len(resids) < 20: continue
        recs.append({"factor":c, "raw_IC":raws.mean(),
                     "residual_IC":resids.mean(),
                     "resid_t":resids.mean()/(resids.std()/np.sqrt(len(resids))),
                     "retained":resids.mean()/raws.mean() if raws.mean()!=0 else np.nan,
                     "months":len(resids)})
    r = pd.DataFrame(recs).sort_values("residual_IC", key=abs, ascending=False)
    print(r.round(3).to_string(index=False), flush=True)
    r.to_csv("out/residual_ic.csv", index=False)
    print("", flush=True)
    print("   'retained' = residual IC / raw IC. Near 0 => redundant. Near 1 => additive.", flush=True)
    print("ORTHO_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
