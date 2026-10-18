"""Production screener: run the algorithm on the most recent data and rank candidates.

Outputs an EMPIRICAL outcome distribution for each score bucket, taken from the
backtest -- not a model probability, because the model was shown to be overconfident.
"""
import sys
import numpy as np, pandas as pd
import factors as F, precomp as PC, algo as A

VOL_GATE = (0.60, 1.00)     # variant B: names capable of a big move
TOPN = 40


def industry_momentum(panel_today, sc):
    d = panel_today.merge(sc[["ticker","sector","industry"]], on="ticker", how="left")
    im = d.groupby("industry").agg(ind_mom=("mom_12_1","median"), ind_n=("ticker","size"))
    im = im[im.ind_n >= 5]
    im["ind_mom_pct"] = im["ind_mom"].rank(pct=True)
    return d, im


def main():
    close, vol = F.load_panel()
    ctx = PC.build(close, vol)
    asof = close.index[-1]
    print("Screening as of %s" % asof.date(), flush=True)

    f = PC.factors_at(ctx, asof)
    f["ticker"] = f.index
    f = f.reset_index(drop=True)

    sc = pd.read_csv("data/nasdaq_screener.csv").rename(columns={"symbol":"ticker"})
    sc["marketCap"] = pd.to_numeric(sc["marketCap"], errors="coerce")

    scored = A.score(f, VOL_GATE)
    print("universe after liquidity + volatility gate: %d" % len(scored), flush=True)

    d, im = industry_momentum(scored, sc)
    d = d.merge(im[["ind_mom","ind_mom_pct"]], left_on="industry", right_index=True, how="left")
    # modest industry tilt: +0.5 z-equivalent for a top-quintile industry, -0.5 for bottom
    d["ind_tilt"] = (d["ind_mom_pct"].fillna(0.5) - 0.5) * 1.0
    d["final_score"] = d["score"] + d["ind_tilt"]
    d = d.merge(sc[["ticker","marketCap","country","ipoyear"]], on="ticker", how="left")
    d = d.sort_values("final_score", ascending=False)
    d["rank"] = range(1, len(d) + 1)
    d.to_csv("out/screen_full.csv", index=False)

    cols = ["rank","ticker","final_score","price","marketCap","industry",
            "pct_of_52w_high","max_dd_12m","mom_12_1","mom_36","vol_12m","skew_12m",
            "adv_3m_usd","ind_mom"]
    top = d.head(TOPN)[cols].copy()
    top["marketCap"] = (top["marketCap"]/1e9).round(2)
    top["adv_3m_usd"] = (top["adv_3m_usd"]/1e6).round(1)
    top = top.rename(columns={"marketCap":"mcap_$B","adv_3m_usd":"adv_$M"})
    print("", flush=True)
    print("=== TOP %d CANDIDATES (as of %s) ===" % (TOPN, asof.date()), flush=True)
    print(top.round(3).to_string(index=False), flush=True)
    top.to_csv("out/screen_top.csv", index=False)

    print("", flush=True)
    print("industry mix of top %d:" % TOPN, flush=True)
    print(d.head(TOPN)["industry"].value_counts().head(12).to_string(), flush=True)
    print("SCREEN_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
