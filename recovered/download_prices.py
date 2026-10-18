"""Bulk-download daily adjusted Close + Volume for the universe. Resumable, batched."""
import os, sys, time, glob
import pandas as pd
import yfinance as yf

START = "2014-01-01"
END   = "2026-09-06"
BATCH = 120
OUT   = "data/px_batches"

def main():
    os.makedirs(OUT, exist_ok=True)
    u = pd.read_csv("data/universe_raw.csv")
    syms = sorted(u["Symbol"].astype(str).unique().tolist())
    batches = [syms[i:i+BATCH] for i in range(0, len(syms), BATCH)]
    print(f"{len(syms)} symbols in {len(batches)} batches", flush=True)

    for bi, b in enumerate(batches):
        cf = f"{OUT}/close_{bi:04d}.parquet"
        vf = f"{OUT}/vol_{bi:04d}.parquet"
        if os.path.exists(cf) and os.path.exists(vf):
            continue
        for attempt in range(3):
            try:
                d = yf.download(b, start=START, end=END, progress=False,
                                auto_adjust=True, threads=True, group_by="column")
                if d is None or len(d) == 0:
                    print(f"batch {bi}: EMPTY", flush=True); break
                close = d["Close"] if "Close" in d.columns.get_level_values(0) else None
                vol   = d["Volume"] if "Volume" in d.columns.get_level_values(0) else None
                if close is None:
                    print(f"batch {bi}: no Close", flush=True); break
                close = close.dropna(axis=1, how="all")
                close.to_parquet(cf)
                if vol is not None:
                    vol[close.columns].to_parquet(vf)
                else:
                    pd.DataFrame(index=close.index).to_parquet(vf)
                print(f"batch {bi}/{len(batches)}: {close.shape[1]} tickers, {close.shape[0]} days", flush=True)
                break
            except Exception as e:
                print(f"batch {bi} attempt {attempt} failed: {type(e).__name__} {e}", flush=True)
                time.sleep(5 * (attempt + 1))
        time.sleep(0.6)
    print("DOWNLOAD_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
