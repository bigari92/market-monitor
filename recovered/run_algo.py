"""Out-of-sample backtest of the composite algorithm, including a strategy P&L."""
import numpy as np, pandas as pd
import algo as A

def evaluate(panel, vol_gate, label, topn=25):
    rows, picks = [], []
    for d, g in panel.groupby("date"):
        s = A.score(g, vol_gate)
        if s is None: continue
        s = s.sort_values("score", ascending=False)
        t = s.head(topn)
        rows.append({"date": d, "n_universe": len(s),
                     "top_mean": t.fwd_ret.mean(), "top_median": t.fwd_ret.median(),
                     "top_up50": (t.fwd_ret>.5).mean(), "top_dn30": (t.fwd_ret<-.3).mean(),
                     "uni_mean": s.fwd_ret.mean(), "uni_median": s.fwd_ret.median(),
                     "uni_up50": (s.fwd_ret>.5).mean(), "uni_dn30": (s.fwd_ret<-.3).mean()})
        tt = t[["ticker","date","score","fwd_ret"]].copy(); picks.append(tt)
    r = pd.DataFrame(rows)
    p = pd.concat(picks, ignore_index=True) if picks else pd.DataFrame()
    print("", flush=True)
    print("======== %s  (top %d each month) ========" % (label, topn), flush=True)
    print("months: %d  |  median universe size: %.0f" % (len(r), r.n_universe.median()), flush=True)
    print("               TOP-%d      UNIVERSE   edge" % topn, flush=True)
    print("mean fwd12m   %+7.2f%%   %+7.2f%%   %+.2f pp" % (100*r.top_mean.mean(), 100*r.uni_mean.mean(), 100*(r.top_mean.mean()-r.uni_mean.mean())), flush=True)
    print("median fwd12m %+7.2f%%   %+7.2f%%   %+.2f pp" % (100*r.top_median.mean(), 100*r.uni_median.mean(), 100*(r.top_median.mean()-r.uni_median.mean())), flush=True)
    print("P(up >50%%)     %6.2f%%    %6.2f%%   %.2fx" % (100*r.top_up50.mean(), 100*r.uni_up50.mean(), r.top_up50.mean()/max(r.uni_up50.mean(),1e-9)), flush=True)
    print("P(dn <-30%%)    %6.2f%%    %6.2f%%   %.2fx" % (100*r.top_dn30.mean(), 100*r.uni_dn30.mean(), r.top_dn30.mean()/max(r.uni_dn30.mean(),1e-9)), flush=True)
    r["year"] = pd.to_datetime(r.date).dt.year
    yr = r.groupby("year").agg(top_mean=("top_mean","mean"), uni_mean=("uni_mean","mean"),
                               top_up50=("top_up50","mean"), top_dn30=("top_dn30","mean"))
    yr[["top_mean","uni_mean","top_up50","top_dn30"]] *= 100
    yr["excess_pp"] = yr.top_mean - yr.uni_mean
    print("", flush=True); print("by signal year (realised over next 12m):", flush=True)
    print(yr.round(2).to_string(), flush=True)
    return r, p

def main():
    panel = pd.read_parquet("data/panel.parquet"); panel["date"] = pd.to_datetime(panel["date"])
    oos = panel[panel["date"] >= "2019-01-01"]     # nothing here informed the weight choice
    print("OUT-OF-SAMPLE WINDOW: %s .. %s" % (oos.date.min().date(), oos.date.max().date()), flush=True)
    r1,p1 = evaluate(oos, None,          "A. QUALITY-TREND  (all liquid names)")
    r2,p2 = evaluate(oos, (0.60, 1.00),  "B. ASYMMETRIC GROWTH (top 40% volatility only)")
    r3,p3 = evaluate(oos, (0.80, 1.00),  "C. AGGRESSIVE (top 20% volatility only)")
    for nm, rr in [("A",r1),("B",r2),("C",r3)]:
        rr.to_csv("out/algo_%s_months.csv" % nm, index=False)
    p2.to_csv("out/algo_B_picks.csv", index=False)
    print("", flush=True); print("ALGO_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
