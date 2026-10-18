"""Assemble the point-in-time backtest panel: factors at T + realized forward 12m return."""
import numpy as np
import pandas as pd
import factors as F
import precomp as PC

MIN_PRICE, MIN_ADV = 3.0, 2_000_000
HORIZON = 252


def main():
    close, vol = F.load_panel()
    print("panel: %d days x %d tickers" % close.shape, flush=True)
    print("building causal rolling series...", flush=True)
    ctx = PC.build(close, vol)
    print("done", flush=True)

    idx = close.index
    want = pd.date_range("2015-01-31", "2025-09-30", freq="ME")
    dates = sorted({idx[idx.searchsorted(d, side="right") - 1] for d in want
                    if 0 <= idx.searchsorted(d, side="right") - 1 < len(idx)})
    print("%d rebalance dates: %s .. %s" % (len(dates), dates[0].date(), dates[-1].date()), flush=True)

    rows = []
    for d in dates:
        f = PC.factors_at(ctx, d)
        if f is None:
            continue
        fwd = PC.fwd_return(close, d, HORIZON)
        if fwd is None:
            print("  %s  no forward window - stop" % d.date(), flush=True)
            continue
        f = f.copy()
        f["fwd_ret"] = fwd
        m = ((f["price"] >= MIN_PRICE) & (f["adv_3m_usd"] >= MIN_ADV)
             & f["fwd_ret"].notna() & f["mom_12_1"].notna())
        f = f[m]
        if len(f) < 100:
            continue
        f["ticker"] = f.index
        rows.append(f.reset_index(drop=True))
        print("  %s  n=%d  fwd_med=%+.1f%%" % (d.date(), len(f), 100 * f["fwd_ret"].median()), flush=True)

    panel = pd.concat(rows, ignore_index=True)
    panel.to_parquet("data/panel.parquet")
    print("PANEL shape %s  dates %d" % (panel.shape, panel["date"].nunique()), flush=True)
    print("DATASET_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
