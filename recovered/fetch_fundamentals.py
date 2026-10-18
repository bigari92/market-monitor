"""Fetch fundamental snapshots + annual/quarterly income statements for a ticker list.

NOTE: yfinance `info` is a CURRENT snapshot (as of today), not point-in-time. It is used
here for DESCRIPTIVE characterisation only, never as a backtest feature.
Annual statements go back ~4 years and ARE usable point-in-time with a reporting lag.
"""
import json, os, sys, time
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

INFO_KEYS = ["sector", "industry", "marketCap", "enterpriseValue", "trailingPE", "forwardPE",
             "priceToBook", "priceToSalesTrailing12Months", "enterpriseToRevenue",
             "enterpriseToEbitda", "profitMargins", "grossMargins", "operatingMargins",
             "ebitdaMargins", "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
             "returnOnEquity", "returnOnAssets", "debtToEquity", "totalCash", "totalDebt",
             "totalRevenue", "freeCashflow", "operatingCashflow", "sharesOutstanding",
             "floatShares", "heldPercentInsiders", "heldPercentInstitutions",
             "shortPercentOfFloat", "beta", "fullTimeEmployees", "country"]


def one(sym):
    out = {"ticker": sym}
    try:
        t = yf.Ticker(sym)
        try:
            info = t.info or {}
        except Exception:
            info = {}
        for k in INFO_KEYS:
            out[k] = info.get(k)
        # annual income statement -> revenue history
        try:
            fin = t.income_stmt
            if fin is not None and not fin.empty:
                cols = sorted(fin.columns)          # oldest -> newest
                for i, c in enumerate(cols[-5:]):
                    yr = pd.Timestamp(c).year
                    for src, dst in [("Total Revenue", "rev"), ("Gross Profit", "gp"),
                                     ("Operating Income", "oi"), ("Net Income", "ni")]:
                        if src in fin.index:
                            out[f"{dst}_{yr}"] = fin.loc[src, c]
        except Exception:
            pass
        # quarterly revenue (recent, for acceleration)
        try:
            q = t.quarterly_income_stmt
            if q is not None and not q.empty and "Total Revenue" in q.index:
                cols = sorted(q.columns)
                for i, c in enumerate(cols[-6:]):
                    out[f"qrev_{pd.Timestamp(c).strftime('%Y%m')}"] = q.loc["Total Revenue", c]
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
    return out


def main():
    listfile, outfile = sys.argv[1], sys.argv[2]
    syms = [l.strip() for l in open(listfile) if l.strip()]
    print(f"fetching {len(syms)} tickers", flush=True)
    res, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(one, s): s for s in syms}
        for fu in as_completed(futs):
            res.append(fu.result())
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(syms)}", flush=True)
    df = pd.DataFrame(res)
    df.to_csv(outfile, index=False)
    print(f"saved {outfile}  shape={df.shape}", flush=True)
    print("FUNDAMENTALS_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
