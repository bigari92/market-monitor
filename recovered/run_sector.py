"""Do industry-level trends persist? If the winners clustered in themes, the practical
question is whether a theme can be identified EARLY enough to act on."""
import numpy as np, pandas as pd
from scipy import stats

def main():
    p = pd.read_parquet("data/panel.parquet"); p["date"]=pd.to_datetime(p["date"])
    sc = pd.read_csv("data/nasdaq_screener.csv").rename(columns={"symbol":"ticker"})
    p = p.merge(sc[["ticker","sector","industry"]], on="ticker", how="left")
    p = p[p.industry.notna()]
    print("panel with industry: %d rows, %d industries" % (len(p), p.industry.nunique()), flush=True)

    # industry aggregate: trailing 12-1 momentum (median across members) vs forward 12m median
    g = p.groupby(["date","industry"]).agg(mom=("mom_12_1","median"), fwd=("fwd_ret","median"),
                                           n=("ticker","size")).reset_index()
    g = g[g.n >= 5]
    print("industry-date cells with >=5 members: %d" % len(g), flush=True)

    ics = g.groupby("date").apply(
        lambda d: stats.spearmanr(d["mom"], d["fwd"])[0] if len(d) > 10 else np.nan,
        include_groups=False).dropna()
    print("", flush=True)
    print("=== INDUSTRY MOMENTUM -> INDUSTRY FORWARD 12M RETURN ===", flush=True)
    print("mean rank IC %.4f | t %.2f | %% months positive %.1f%% | n months %d" % (
        ics.mean(), ics.mean()/(ics.std()/np.sqrt(len(ics))), 100*(ics>0).mean(), len(ics)), flush=True)

    g["mq"] = g.groupby("date")["mom"].transform(lambda x: pd.qcut(x.rank(method="first"),5,labels=False,duplicates="drop"))
    t = g.groupby("mq")["fwd"].agg(["mean","median","size"])
    t[["mean","median"]] *= 100
    print("", flush=True)
    print("forward 12m median return by industry-momentum quintile (Q4=hottest):", flush=True)
    print(t.round(2).to_string(), flush=True)

    # Does adding industry momentum to the stock score help?
    p = p.merge(g[["date","industry","mom","mq"]].rename(columns={"mom":"ind_mom"}),
                on=["date","industry"], how="left")
    p["stk_q"] = p.groupby("date")["mom_12_1"].transform(lambda x: pd.qcut(x.rank(method="first"),5,labels=False,duplicates="drop"))
    x = p.dropna(subset=["mq","stk_q"])
    piv_m = x.pivot_table(index="stk_q", columns="mq", values="fwd_ret", aggfunc="mean")*100
    piv_w = x.pivot_table(index="stk_q", columns="mq", values="fwd_ret",
                          aggfunc=lambda s:(s>0.5).mean())*100
    print("", flush=True)
    print("=== MEAN fwd12m: stock momentum (rows) x industry momentum (cols) ===", flush=True)
    print(piv_m.round(2).to_string(), flush=True)
    print("", flush=True)
    print("=== P(fwd12m > +50%%): stock momentum x industry momentum ===", flush=True)
    print(piv_w.round(2).to_string(), flush=True)

    # which industries were hottest most recently?
    last = g[g.date == g.date.max()].sort_values("mom", ascending=False)
    print("", flush=True)
    print("=== hottest industries as of %s (trailing 12-1 momentum, median member) ===" % g.date.max().date(), flush=True)
    print(last.head(15)[["industry","mom","n"]].round(3).to_string(index=False), flush=True)
    print("SECTOR_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
