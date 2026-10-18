"""Does the fundamental information pay off at lower concentration?

The quintile tables showed the exclusion improving every quintile, but top-25 selection
showed nothing. If the benefit is real but diluted by concentration, it should appear as
portfolio size grows.
"""
import numpy as np, pandas as pd
from scipy import stats
import algo as A2, algo_v4 as A4

GATE=(0.80,1.00)

def run(panel, fn, topn):
    rows=[]
    for d,g in panel.groupby("date"):
        s=fn(g)
        if s is None or len(s)<topn: continue
        t=s.sort_values("score",ascending=False).head(topn)
        rows.append({"date":d,"mean":t.fwd_ret.mean(),"med":t.fwd_ret.median(),
                     "up50":(t.fwd_ret>.5).mean(),"dn30":(t.fwd_ret<-.3).mean()})
    return pd.DataFrame(rows).set_index("date")

def main():
    p=pd.read_parquet("data/panel_fund90.parquet"); p["date"]=pd.to_datetime(p["date"])
    oos=p[p["date"]>="2019-01-01"]
    print("=== v2 z-score vs v4 rank-normalisation (price factors only) ===", flush=True)
    a=run(oos, lambda g: A2.score(g,GATE), 25)
    b=run(oos, lambda g: A4.score(g,GATE,"price"), 25)
    j=a.join(b,lsuffix="_z",rsuffix="_r",how="inner")
    diff=j["mean_r"]-j["mean_z"]; t,pv=stats.ttest_1samp(diff.dropna(),0)
    print("  rank-norm minus z-score: %+.2f pp   t=%+.2f  p=%.3f  months better %.0f%%" % (
        100*diff.mean(),t,pv,100*(diff>0).mean()), flush=True)
    print("", flush=True)

    print("=== fundamentals at increasing portfolio size ===", flush=True)
    print("  %-6s %-22s %8s %8s %7s %7s" % ("N","variant","mean","median","up50","dn30"), flush=True)
    for topn in [25, 50, 100, 200]:
        base = run(oos, lambda g: A4.score(g,GATE,"price"), topn)
        print("  %-6d %-22s %+7.2f%% %+7.2f%% %6.2f%% %6.2f%%" % (
            topn,"price only",100*base["mean"].mean(),100*base["med"].mean(),
            100*base.up50.mean(),100*base.dn30.mean()), flush=True)
        for mode,lab in [("filter","+ exclusion"),("rank_fund","+ tilt")]:
            o = run(oos, lambda g: A4.score(g,GATE,mode), topn)
            j = base.join(o,lsuffix="_b",rsuffix="_o",how="inner")
            d = j["mean_o"]-j["mean_b"]; t,pv = stats.ttest_1samp(d.dropna(),0)
            print("  %-6s %-22s %+7.2f%% %+7.2f%% %6.2f%% %6.2f%%   delta %+5.2f pp (p=%.3f)" % (
                "", lab, 100*o["mean"].mean(),100*o["med"].mean(),
                100*o.up50.mean(),100*o.dn30.mean(), 100*d.mean(), pv), flush=True)
        print("", flush=True)
    print("CONC_COMPLETE", flush=True)

if __name__=="__main__":
    main()
