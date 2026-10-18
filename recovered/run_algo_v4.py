import numpy as np, pandas as pd
import algo as A2, algo_v4 as A4

GATE=(0.80,1.00); TOPN=25

def ev(panel, fn, label, deciles=False):
    rows=[]; picks=[]; alld=[]
    for d,g in panel.groupby("date"):
        s=fn(g)
        if s is None or len(s)<TOPN: continue
        s=s.sort_values("score",ascending=False)
        t=s.head(TOPN)
        rows.append({"date":d,"n":len(s),"top_mean":t.fwd_ret.mean(),"top_med":t.fwd_ret.median(),
                     "up50":(t.fwd_ret>.5).mean(),"dn30":(t.fwd_ret<-.3).mean(),
                     "uni_mean":s.fwd_ret.mean(),"uni_up50":(s.fwd_ret>.5).mean(),
                     "uni_dn30":(s.fwd_ret<-.3).mean()})
        picks.append(t[["ticker","date","fwd_ret"]])
        if deciles:
            s2=s.copy(); s2["dec"]=pd.qcut(s2.score.rank(method="first"),5,labels=False,duplicates="drop")
            alld.append(s2[["dec","fwd_ret"]])
    r=pd.DataFrame(rows); p=pd.concat(picks,ignore_index=True)
    print("  %-42s mean %+6.2f%%  med %+6.2f%%  up50 %5.2f%%  dn30 %5.2f%%  uni %d" % (
        label,100*r.top_mean.mean(),100*r.top_med.mean(),100*r.up50.mean(),100*r.dn30.mean(),r.n.median()), flush=True)
    if deciles and alld:
        a=pd.concat(alld,ignore_index=True); g=a.groupby("dec")["fwd_ret"]
        q=pd.DataFrame({"mean":100*g.mean(),"med":100*g.median(),
                        "up50":100*g.apply(lambda x:(x>.5).mean()),
                        "dn30":100*g.apply(lambda x:(x<-.3).mean())})
        print("      quintiles of the score (Q4 = best):", flush=True)
        print("      "+q.round(2).to_string().replace("\n","\n      "), flush=True)
    return r,p

def main():
    p=pd.read_parquet("data/panel_fund90.parquet"); p["date"]=pd.to_datetime(p["date"])
    oos=p[p["date"]>="2019-01-01"]
    print("OOS %s .. %s   (top %d/month, 12m hold)" % (oos.date.min().date(),oos.date.max().date(),TOPN), flush=True)
    print("", flush=True)
    print("BASELINE", flush=True)
    ev(oos, lambda g: A2.score(g,GATE), "v2  z-scored, price only", deciles=True)
    print("", flush=True)
    print("RANK-NORMALISED VARIANTS", flush=True)
    r_p,_ = ev(oos, lambda g: A4.score(g,GATE,"price"),     "v4  rank-norm, price only", deciles=True)
    r_f,_ = ev(oos, lambda g: A4.score(g,GATE,"rank_fund"), "v4  rank-norm + fundamental tilt", deciles=True)
    r_x,pf= ev(oos, lambda g: A4.score(g,GATE,"filter"),    "v4  price score + fundamental EXCLUSION", deciles=True)
    r_b,pb= ev(oos, lambda g: A4.score(g,GATE,"both"),      "v4  exclusion + tilt", deciles=True)
    for n,rr in [("p",r_p),("f",r_f),("x",r_x),("b",r_b)]: rr.to_csv("out/v4_%s.csv"%n,index=False)
    pb.to_csv("out/v4_both_picks.csv",index=False)
    print("", flush=True)
    for nm,rr in [("v4 price",r_p),("v4 tilt",r_f),("v4 exclusion",r_x),("v4 both",r_b)]:
        rr["year"]=pd.to_datetime(rr.date).dt.year
        y=rr.groupby("year")["top_mean"].mean()*100
        print("  %-14s by year: %s" % (nm, " ".join("%d:%+.0f"%(k,v) for k,v in y.items())), flush=True)
    print("", flush=True); print("V4_COMPLETE", flush=True)

if __name__=="__main__":
    main()
