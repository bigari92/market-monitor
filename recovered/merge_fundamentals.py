"""As-of join fundamentals onto the price panel: at each rebalance date, use only the
most recent fiscal period whose availability date has already passed."""
import sys
import numpy as np, pandas as pd

LAG = int(sys.argv[1]) if len(sys.argv) > 1 else 90

FUND_COLS = ["rev_yoy_ttm","rev_yoy_q","rev_accel","gross_margin","op_margin","net_margin",
             "gross_margin_delta","op_margin_delta","net_margin_delta","rule40",
             "rev_stability","profitable","rev_ttm"]

def main():
    p = pd.read_parquet("data/panel.parquet"); p["date"] = pd.to_datetime(p["date"])
    f = pd.read_parquet(f"data/fundamentals_lag{LAG}.parquet")
    f["avail_date"] = pd.to_datetime(f["avail_date"])
    f = f.sort_values("avail_date")
    p = p.sort_values("date")

    merged = pd.merge_asof(p, f[["ticker","avail_date","end"]+FUND_COLS],
                           left_on="date", right_on="avail_date", by="ticker",
                           direction="backward", allow_exact_matches=True)
    # staleness guard: drop fundamentals older than 15 months
    age = (merged["date"] - merged["end"]).dt.days
    stale = age > 460
    for c in FUND_COLS:
        merged.loc[stale, c] = np.nan
    merged["fund_age_days"] = age

    print("panel rows: %d" % len(merged), flush=True)
    print("with any fundamentals: %.1f%%" % (100*merged.rev_yoy_ttm.notna().mean()), flush=True)
    print("median staleness of joined data: %.0f days" % merged.loc[merged.rev_yoy_ttm.notna(),"fund_age_days"].median(), flush=True)
    print("", flush=True)
    print("coverage by factor:", flush=True)
    for c in FUND_COLS:
        print("   %-22s %5.1f%%" % (c, 100*merged[c].notna().mean()), flush=True)
    print("", flush=True)
    print("coverage by year:", flush=True)
    cy = merged.assign(y=merged.date.dt.year).groupby("y")["rev_yoy_ttm"].agg(
        n="size", cov=lambda s: 100*s.notna().mean())
    print(cy.round(1).to_string(), flush=True)
    merged.to_parquet(f"data/panel_fund{LAG}.parquet")
    print("", flush=True); print("MERGE_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
