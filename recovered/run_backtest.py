"""Rank-IC + decile analysis on the point-in-time panel."""
import numpy as np, pandas as pd
import backtest as B

def main():
    p = pd.read_parquet("data/panel.parquet")
    p["date"] = pd.to_datetime(p["date"])
    print("panel %s | dates %d | %s .. %s" % (p.shape, p["date"].nunique(),
          p["date"].min().date(), p["date"].max().date()), flush=True)
    print("median obs/date: %d" % p.groupby("date").size().median(), flush=True)
    print("unconditional mean fwd 12m: %+.2f%%  median: %+.2f%%" %
          (100*p["fwd_ret"].mean(), 100*p["fwd_ret"].median()), flush=True)
    print("unconditional P(fwd>+50%%): %.2f%%   P(fwd>+100%%): %.2f%%" %
          (100*(p["fwd_ret"]>0.5).mean(), 100*(p["fwd_ret"]>1.0).mean()), flush=True)

    ics, summ = B.rank_ic(p)
    ics.to_csv("out/ic_by_date.csv", index=False)
    summ.to_csv("out/ic_summary.csv")
    print("", flush=True)
    print("=== RANK IC vs FORWARD 12M RETURN (127 monthly cross-sections, 2015-2025) ===", flush=True)
    print("mean = average Spearman corr | t_stat = significance | hit_rate = %% of months IC>0", flush=True)
    print(summ[["mean","std","t_stat","ic_ir","hit_rate","count"]].round(4).to_string(), flush=True)

    print("", flush=True)
    for c in ["mom_12_1","vol_12m","pct_of_52w_high","px_vs_ma200","mom_accel","price","vol_surge","max_dd_12m"]:
        d = B.decile_table(p, c)
        print("--- deciles of %s (D0=lowest, D9=highest) ---" % c, flush=True)
        print((d*100).round(2).assign(n=d["n"]).to_string(), flush=True)
        d.to_csv("out/decile_%s.csv" % c)
        print("", flush=True)
    print("BACKTEST_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
