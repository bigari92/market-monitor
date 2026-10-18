"""Head-to-head: v2 (price only) vs v3 (price + fundamentals), same out-of-sample window."""
import numpy as np, pandas as pd
import algo as A2, algo_v3 as A3

GATE = (0.80, 1.00)
TOPN = 25

def ev(panel, fn, label):
    rows, picks = [], []
    for d, g in panel.groupby("date"):
        s = fn(g)
        if s is None or len(s) < TOPN: continue
        t = s.sort_values("score", ascending=False).head(TOPN)
        rows.append({"date": d, "n": len(s),
                     "top_mean": t.fwd_ret.mean(), "top_med": t.fwd_ret.median(),
                     "up50": (t.fwd_ret>.5).mean(), "dn30": (t.fwd_ret<-.3).mean(),
                     "uni_mean": s.fwd_ret.mean(), "uni_med": s.fwd_ret.median(),
                     "uni_up50": (s.fwd_ret>.5).mean(), "uni_dn30": (s.fwd_ret<-.3).mean()})
        picks.append(t[["ticker","date","fwd_ret"]])
    r = pd.DataFrame(rows); p = pd.concat(picks, ignore_index=True)
    print("", flush=True)
    print("======== %s ========" % label, flush=True)
    print("months %d | median universe %.0f | picks %d" % (len(r), r.n.median(), len(p)), flush=True)
    print("  mean fwd12m   %+7.2f%%   (universe %+6.2f%%)" % (100*r.top_mean.mean(), 100*r.uni_mean.mean()), flush=True)
    print("  median fwd12m %+7.2f%%   (universe %+6.2f%%)" % (100*r.top_med.mean(), 100*r.uni_med.mean()), flush=True)
    print("  P(up>50%%)      %6.2f%%    (universe %6.2f%%)  %.2fx" % (100*r.up50.mean(), 100*r.uni_up50.mean(), r.up50.mean()/r.uni_up50.mean()), flush=True)
    print("  P(dn<-30%%)     %6.2f%%    (universe %6.2f%%)  %.2fx" % (100*r.dn30.mean(), 100*r.uni_dn30.mean(), r.dn30.mean()/r.uni_dn30.mean()), flush=True)
    pr = p.fwd_ret
    print("  pick distribution: p10 %+.0f%% | p25 %+.0f%% | median %+.0f%% | p75 %+.0f%% | p90 %+.0f%%" % (
        100*pr.quantile(.1),100*pr.quantile(.25),100*pr.median(),100*pr.quantile(.75),100*pr.quantile(.9)), flush=True)
    print("  P(profitable) %.1f%% | P(>+100%%) %.1f%%" % (100*(pr>0).mean(), 100*(pr>1).mean()), flush=True)
    r["year"]=pd.to_datetime(r.date).dt.year
    yr=r.groupby("year").agg(algo=("top_mean","mean"),uni=("uni_mean","mean"),
                             up50=("up50","mean"),dn30=("dn30","mean"))
    yr*=100; yr["excess"]=yr.algo-yr.uni
    print("  by signal year:", flush=True)
    print(yr.round(1).to_string(), flush=True)
    return r, p

def main():
    p = pd.read_parquet("data/panel_fund90.parquet"); p["date"]=pd.to_datetime(p["date"])
    oos = p[p["date"]>="2019-01-01"]
    print("OOS window %s .. %s" % (oos.date.min().date(), oos.date.max().date()), flush=True)
    r2,p2 = ev(oos, lambda g: A2.score(g, GATE), "v2  PRICE ONLY")
    r3,p3 = ev(oos, lambda g: A3.score(g, GATE, True, False), "v3  + FUNDAMENTALS (neutral if missing)")
    r4,p4 = ev(oos, lambda g: A3.score(g, GATE, True, True), "v3s + FUNDAMENTALS (required)")
    for n,rr in [("v2",r2),("v3",r3),("v3s",r4)]: rr.to_csv("out/cmp_%s.csv"%n, index=False)
    p3.to_csv("out/v3_picks.csv", index=False)
    print("", flush=True); print("V3_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
