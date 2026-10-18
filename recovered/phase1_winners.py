"""Phase 1 (descriptive): who were the 3-year winners, and what did they look like
AT THE START of the window?

This answers 'what unites them' -- but the analysis is inherently ex-post, so we also
compute the BASE RATE of winning by starting-decile of each trait. A trait only counts
as a real signal if the winner rate actually rises with it.
"""
import numpy as np
import pandas as pd
import factors as F

START = "2023-09-05"
END = "2026-09-04"


def main():
    close, vol = F.load_panel()
    print("panel: %d days x %d tickers" % (close.shape[0], close.shape[1]), flush=True)
    idx = close.index
    s = idx[idx.searchsorted(pd.Timestamp(START), side="right") - 1]
    e = idx[idx.searchsorted(pd.Timestamp(END), side="right") - 1]
    print("window %s -> %s" % (s.date(), e.date()), flush=True)

    p0, p1 = close.loc[s], close.loc[e]
    tr = (p1 / p0 - 1.0).dropna()

    f0 = F.compute_factors(close, vol, s).reindex(tr.index)
    inv = ((f0["price"] >= 3.0) & (f0["adv_3m_usd"] >= 2_000_000)).fillna(False)
    tr = tr[inv]
    f0 = f0.loc[tr.index]
    print("investable at start: %d" % len(tr), flush=True)

    bm = pd.read_parquet("data/benchmarks.parquet")
    bm.index = pd.to_datetime(bm.index).tz_localize(None)
    spy = bm.loc[:e, "SPY"].iloc[-1] / bm.loc[:s, "SPY"].iloc[-1] - 1.0
    print("SPY over window: %+.1f%%" % (spy * 100), flush=True)

    df = f0.copy()
    df["ret_3y"] = tr
    df["cagr"] = (1 + tr) ** (1 / 3) - 1
    df["excess_vs_spy"] = tr - spy
    df["ticker"] = df.index
    u = pd.read_csv("data/universe_raw.csv").set_index("Symbol")
    df["name"] = u["name"].reindex(df.index)
    df = df.sort_values("ret_3y", ascending=False)
    df.to_csv("out/phase1_all_investable.csv", index=False)

    win = df[df["ret_3y"] >= 2.0]
    elite = df[df["ret_3y"] >= 5.0]
    win.to_csv("out/phase1_winners.csv", index=False)
    elite.to_csv("out/phase1_elite.csv", index=False)
    print("", flush=True)
    print("WINNERS (>=+200%%, tripled):   %d of %d = %.1f%%" % (len(win), len(df), 100*len(win)/len(df)), flush=True)
    print("ELITE   (>=+500%%, 6-bagger):  %d of %d = %.1f%%" % (len(elite), len(df), 100*len(elite)/len(df)), flush=True)
    print("Beat SPY at all:              %.1f%% of investable names" % (100*(df["ret_3y"] > spy).mean()), flush=True)
    print("Median investable stock:      %+.1f%%" % (100*df["ret_3y"].median()), flush=True)
    print("Mean investable stock:        %+.1f%%" % (100*df["ret_3y"].mean()), flush=True)
    print("", flush=True)
    print("Top 40 performers:", flush=True)
    print(win.head(40)[["ticker", "name", "ret_3y", "cagr"]].to_string(index=False, max_colwidth=42), flush=True)

    df["is_winner"] = df.index.isin(win.index)
    cols = ["price", "mom_12_1", "mom_6_1", "mom_3", "mom_36", "mom_accel",
            "px_vs_ma200", "ma50_vs_ma200", "pct_of_52w_high", "off_52w_low",
            "days_above_ma200", "vol_6m", "vol_12m", "max_dd_12m", "skew_12m",
            "vol_surge", "adv_3m_usd"]
    comp = df.groupby("is_winner")[cols].median().T
    comp.columns = ["rest", "winners"]
    print("", flush=True)
    print("--- MEDIAN CHARACTERISTICS AT START OF WINDOW (Sep 2023) ---", flush=True)
    print(comp.round(3).to_string(), flush=True)
    comp.to_csv("out/phase1_winner_vs_rest.csv")

    print("", flush=True)
    print("--- P(tripling over next 3y) BY STARTING DECILE OF EACH TRAIT ---", flush=True)
    recs = []
    for c in cols:
        s2 = df[[c, "is_winner"]].dropna().copy()
        if len(s2) < 200:
            continue
        s2["dec"] = pd.qcut(s2[c].rank(method="first"), 10, labels=False, duplicates="drop")
        r = s2.groupby("dec")["is_winner"].mean()
        recs.append({"factor": c, "D1_low": r.iloc[0], "D5": r.iloc[4],
                     "D10_high": r.iloc[-1], "spread": r.iloc[-1] - r.iloc[0]})
    bd = pd.DataFrame(recs).sort_values("spread", ascending=False)
    print(bd.round(4).to_string(index=False), flush=True)
    bd.to_csv("out/phase1_base_rates.csv", index=False)
    print("", flush=True)
    print("PHASE1_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
