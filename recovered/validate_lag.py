"""Measure the ACTUAL gap between fiscal period end and SEC filing date.

The frames API gives no filing date, so the panel must assume a reporting lag. Rather
than asserting one, this samples companyconcept (which does carry `filed`) and measures
the real distribution, so the lag used downstream is chosen from evidence.
"""
import random, json
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from sec_common import get_json

def one(cik):
    for tag in ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]:
        d = get_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json")
        if not d:
            continue
        rows = []
        for unit, facts in d.get("units", {}).items():
            if unit != "USD":
                continue
            for f in facts:
                if not f.get("start") or not f.get("end") or not f.get("filed"):
                    continue
                e, fl = pd.Timestamp(f["end"]), pd.Timestamp(f["filed"])
                dur = (e - pd.Timestamp(f["start"])).days
                rows.append({"cik": cik, "form": f.get("form"), "dur": dur,
                             "lag_days": (fl - e).days})
        if rows:
            return rows
    return []

def main():
    m = get_json("https://www.sec.gov/files/company_tickers.json")
    ciks = sorted({v["cik_str"] for v in m.values()})
    random.seed(7)
    sample = random.sample(ciks, 220)
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for fu in as_completed([ex.submit(one, c) for c in sample]):
            try:
                out += fu.result()
            except Exception:
                pass
    df = pd.DataFrame(out)
    df = df[(df.lag_days >= 0) & (df.lag_days < 400)]
    q = df[(df.dur > 80) & (df.dur < 100)]          # quarterly periods
    a = df[(df.dur > 350) & (df.dur < 380)]         # annual periods
    print("sampled companies: %d | facts: %d" % (df.cik.nunique(), len(df)), flush=True)
    for nm, s in [("QUARTERLY (10-Q)", q), ("ANNUAL (10-K)", a), ("ALL", df)]:
        if len(s) == 0:
            continue
        print("", flush=True)
        print("--- %s : days from period end to SEC filing (n=%d) ---" % (nm, len(s)), flush=True)
        for p in [50, 75, 90, 95, 97, 99]:
            print("   p%-3d %5.0f days" % (p, np.percentile(s.lag_days, p)), flush=True)
        for L in [60, 75, 90, 100, 120, 150]:
            print("   covered by a %3d-day lag: %5.1f%%" % (L, 100*(s.lag_days <= L).mean()), flush=True)
    df.to_csv("data/lag_sample.csv", index=False)
    print("", flush=True); print("LAG_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
