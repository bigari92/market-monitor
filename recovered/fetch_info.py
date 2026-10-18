"""Light fetch: yfinance .info snapshot only (sector/industry/current fundamentals)."""
import sys
import pandas as pd, yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

KEYS = ["sector","industry","marketCap","trailingPE","forwardPE","priceToBook",
        "priceToSalesTrailing12Months","enterpriseToRevenue","enterpriseToEbitda",
        "profitMargins","grossMargins","operatingMargins","revenueGrowth","earningsGrowth",
        "returnOnEquity","debtToEquity","totalRevenue","freeCashflow","sharesOutstanding",
        "heldPercentInstitutions","shortPercentOfFloat","beta","fullTimeEmployees","country"]

def one(s):
    o = {"ticker": s}
    try:
        i = yf.Ticker(s).info or {}
        for k in KEYS: o[k] = i.get(k)
    except Exception as e:
        o["error"] = type(e).__name__
    return o

def main():
    syms = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    print("fetching info for %d" % len(syms), flush=True)
    res, n = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for fu in as_completed([ex.submit(one, s) for s in syms]):
            res.append(fu.result()); n += 1
            if n % 200 == 0: print("  %d/%d" % (n, len(syms)), flush=True)
    pd.DataFrame(res).to_csv(sys.argv[2], index=False)
    print("INFO_COMPLETE %s" % sys.argv[2], flush=True)

if __name__ == "__main__":
    main()
