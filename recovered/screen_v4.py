"""Production screen using the validated v4 rank-normalised score (price factors),
with point-in-time fundamentals attached for CONTEXT -- they did not improve selection,
so they are reported, not scored."""
import numpy as np, pandas as pd
import factors as F, precomp as PC, algo_v4 as A4

GATE=(0.80,1.00); TOPN=25

def main():
    close, vol = F.load_panel()
    ctx = PC.build(close, vol)
    asof = close.index[-1]
    f = PC.factors_at(ctx, asof); f["ticker"]=f.index; f=f.reset_index(drop=True)

    fu = pd.read_parquet("data/fundamentals_lag90.parquet")
    fu["avail_date"]=pd.to_datetime(fu["avail_date"])
    fu = fu[fu.avail_date <= asof].sort_values("avail_date")
    latest = fu.groupby("ticker").tail(1)
    f = f.merge(latest[["ticker","end","rule40","rev_stability","net_margin","op_margin",
                        "rev_yoy_ttm","profitable"]], on="ticker", how="left")
    age = (asof - pd.to_datetime(f["end"])).dt.days
    for c in ["rule40","rev_stability","net_margin","op_margin","rev_yoy_ttm","profitable"]:
        f.loc[age>460, c]=np.nan

    sc = pd.read_csv("data/nasdaq_screener.csv").rename(columns={"symbol":"ticker"})
    sc["marketCap"]=pd.to_numeric(sc["marketCap"],errors="coerce")
    d = A4.score(f, GATE, "price")
    d = d.merge(sc[["ticker","industry","marketCap"]], on="ticker", how="left")

    im = d.groupby("industry")["mom_12_1"].agg(["median","size"])
    im = im[im["size"]>=5]; im["pct"]=im["median"].rank(pct=True)
    d = d.merge(im[["pct"]].rename(columns={"pct":"ind_pct"}), left_on="industry", right_index=True, how="left")
    d["final_score"] = d["score"] + (d["ind_pct"].fillna(0.5)-0.5)*1.0
    d = d.sort_values("final_score", ascending=False).reset_index(drop=True)
    d.index = d.index+1
    d.to_csv("out/screen_v4_full.csv")

    print("Screen as of %s | universe after gates: %d | with fundamentals: %d" % (
        asof.date(), len(d), d.rule40.notna().sum()), flush=True)
    cols=["ticker","final_score","price","marketCap","industry","pct_of_52w_high","max_dd_12m",
          "mom_36","vol_12m","rule40","rev_yoy_ttm","op_margin","rev_stability"]
    t=d.head(TOPN)[cols].copy()
    t["marketCap"]=(t.marketCap/1e9).round(1)
    t=t.rename(columns={"marketCap":"mcap$B","pct_of_52w_high":"pct52w","max_dd_12m":"maxDD",
                        "mom_36":"mom3y","vol_12m":"vol","rev_yoy_ttm":"revYoY",
                        "op_margin":"opMgn","rev_stability":"revStab"})
    print("", flush=True)
    print(t.round(2).to_string(), flush=True)
    t.to_csv("out/screen_v4_top.csv")
    print("", flush=True)
    print("industry mix:", flush=True)
    print(d.head(TOPN)["industry"].value_counts().head(8).to_string(), flush=True)
    print("", flush=True)
    print("fundamental profile of the top %d vs the gated universe:" % TOPN, flush=True)
    for c,lab in [("rule40","rule40"),("op_margin","op margin"),("rev_yoy_ttm","rev growth YoY"),
                  ("rev_stability","rev instability"),("profitable","share profitable")]:
        print("   %-16s top %+7.3f   universe %+7.3f" % (lab, d.head(TOPN)[c].median(), d[c].median()), flush=True)
    print("SCREEN4_COMPLETE", flush=True)

if __name__=="__main__":
    main()
