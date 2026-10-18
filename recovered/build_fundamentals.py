"""Turn raw SEC frames into a point-in-time fundamental factor panel.

Each row is (ticker, fiscal period end, availability date, factors). The availability
date is period_end + LAG_DAYS; downstream joins may only use rows whose availability
date is on or before the rebalance date. LAG_DAYS is set from the measured filing-lag
distribution (see validate_lag.py): 90 days covers 96% of genuine first filings.
"""
import os, glob, json, sys
import numpy as np, pandas as pd
from sec_common import get_json

LAG_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 90
REV_PRIORITY = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]


def load_concept(c):
    rows = []
    for f in glob.glob(f"data/sec_frames/{c}__*.json"):
        try:
            d = pd.read_json(f)
        except Exception:
            continue
        if len(d) == 0:
            continue
        d["concept"] = c
        rows.append(d)
    if not rows:
        return pd.DataFrame()
    d = pd.concat(rows, ignore_index=True)
    d["start"] = pd.to_datetime(d["start"], errors="coerce")
    d["end"] = pd.to_datetime(d["end"], errors="coerce")
    d = d.dropna(subset=["start", "end"])
    dur = (d["end"] - d["start"]).dt.days
    d = d[(dur >= 80) & (dur <= 100)]                  # true quarterly periods only
    return d[["cik", "end", "val", "concept"]]


def main():
    print("loading frames...", flush=True)
    parts = {}
    for c in REV_PRIORITY + ["GrossProfit", "CostOfRevenue", "CostOfGoodsAndServicesSold",
                             "OperatingIncomeLoss", "NetIncomeLoss"]:
        parts[c] = load_concept(c)
        print("  %-52s %7d rows" % (c, len(parts[c])), flush=True)

    # --- revenue: coalesce across tags by priority ---
    rev = None
    for c in REV_PRIORITY:
        p = parts[c]
        if len(p) == 0:
            continue
        p = p.groupby(["cik", "end"], as_index=False)["val"].max().rename(columns={"val": "rev"})
        rev = p if rev is None else rev.merge(p, on=["cik", "end"], how="outer",
                                              suffixes=("", "_n")).assign(
            rev=lambda x: x["rev"].fillna(x["rev_n"])).drop(columns=["rev_n"])
    print("revenue observations: %d  (%d companies)" % (len(rev), rev.cik.nunique()), flush=True)

    def agg(c, name):
        p = parts[c]
        if len(p) == 0:
            return pd.DataFrame(columns=["cik", "end", name])
        return p.groupby(["cik", "end"], as_index=False)["val"].max().rename(columns={"val": name})

    df = rev
    for c, n in [("GrossProfit", "gp"), ("CostOfRevenue", "cor"),
                 ("CostOfGoodsAndServicesSold", "cogs"),
                 ("OperatingIncomeLoss", "oi"), ("NetIncomeLoss", "ni")]:
        df = df.merge(agg(c, n), on=["cik", "end"], how="left")

    # derive gross profit where the tag is absent
    df["gp"] = df["gp"].fillna(df["rev"] - df["cor"]).fillna(df["rev"] - df["cogs"])
    df = df.drop(columns=["cor", "cogs"])
    df = df.sort_values(["cik", "end"]).reset_index(drop=True)

    # --- TTM aggregates and growth, computed per company on its own quarter sequence ---
    g = df.groupby("cik")
    for col in ["rev", "gp", "oi", "ni"]:
        df[col + "_ttm"] = g[col].transform(lambda s: s.rolling(4, min_periods=4).sum())
    df["rev_ttm_prev"] = g["rev_ttm"].shift(4)
    df["rev_q_prev"] = g["rev"].shift(4)

    df["rev_yoy_ttm"] = df["rev_ttm"] / df["rev_ttm_prev"].replace(0, np.nan) - 1
    df["rev_yoy_q"] = df["rev"] / df["rev_q_prev"].replace(0, np.nan) - 1
    df["rev_accel"] = df["rev_yoy_q"] - df.groupby("cik")["rev_yoy_q"].shift(1)

    rt = df["rev_ttm"].replace(0, np.nan)
    df["gross_margin"] = df["gp_ttm"] / rt
    df["op_margin"] = df["oi_ttm"] / rt
    df["net_margin"] = df["ni_ttm"] / rt
    for m in ["gross_margin", "op_margin", "net_margin"]:
        df[m + "_delta"] = df[m] - df.groupby("cik")[m].shift(4)
    df["rule40"] = df["rev_yoy_ttm"] + df["op_margin"]
    df["rev_stability"] = df.groupby("cik")["rev_yoy_q"].transform(
        lambda s: s.rolling(8, min_periods=5).std())
    df["profitable"] = (df["ni_ttm"] > 0).astype(float)

    # sanity clipping: XBRL has occasional scale errors
    for c in ["rev_yoy_ttm", "rev_yoy_q", "rev_accel"]:
        df.loc[df[c].abs() > 10, c] = np.nan
    for c in ["gross_margin", "op_margin", "net_margin"]:
        df.loc[(df[c] > 5) | (df[c] < -10), c] = np.nan

    # --- map CIK -> ticker ---
    m = get_json("https://www.sec.gov/files/company_tickers.json")
    tk = pd.DataFrame([{"cik": v["cik_str"], "ticker": v["ticker"]} for v in m.values()])
    tk = tk.drop_duplicates("cik")
    df = df.merge(tk, on="cik", how="inner")

    df["avail_date"] = df["end"] + pd.Timedelta(days=LAG_DAYS)
    keep = ["ticker", "cik", "end", "avail_date", "rev_ttm", "rev_yoy_ttm", "rev_yoy_q",
            "rev_accel", "gross_margin", "op_margin", "net_margin", "gross_margin_delta",
            "op_margin_delta", "net_margin_delta", "rule40", "rev_stability", "profitable"]
    out = df[keep].dropna(subset=["ticker"])
    out.to_parquet(f"data/fundamentals_lag{LAG_DAYS}.parquet")
    print("", flush=True)
    print("PANEL: %d rows | %d tickers | %s .. %s" % (
        len(out), out.ticker.nunique(), out["end"].min().date(), out["end"].max().date()), flush=True)
    print("non-null: rev_yoy_ttm %.0f%% | gross_margin %.0f%% | op_margin %.0f%%" % (
        100*out.rev_yoy_ttm.notna().mean(), 100*out.gross_margin.notna().mean(),
        100*out.op_margin.notna().mean()), flush=True)
    print("FUNDAMENTALS_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
