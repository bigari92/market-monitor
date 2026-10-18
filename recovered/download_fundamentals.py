"""Download quarterly income-statement fundamentals for the whole market via SEC XBRL frames.

One request per (concept, calendar quarter) rather than per company: ~430 requests total.
"""
import os, json, itertools
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from sec_common import get_json

CONCEPTS = ["Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "GrossProfit",
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "OperatingIncomeLoss",
            "NetIncomeLoss"]

QUARTERS = [f"CY{y}Q{q}" for y in range(2012, 2027) for q in (1, 2, 3, 4)]
OUT = "data/sec_frames"


def fetch(concept, per):
    f = f"{OUT}/{concept}__{per}.json"
    if os.path.exists(f):
        return None
    url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{per}.json"
    try:
        d = get_json(url)
    except Exception:
        return (concept, per, "ERR")
    if not d:
        return (concept, per, "404")
    rows = [{"cik": r["cik"], "val": r["val"], "start": r.get("start"),
             "end": r.get("end"), "accn": r.get("accn")} for r in d.get("data", [])]
    pd.DataFrame(rows).to_json(f, orient="records")
    return (concept, per, len(rows))


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = list(itertools.product(CONCEPTS, QUARTERS))
    print("%d (concept, quarter) frames to fetch" % len(jobs), flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(fetch, c, p) for c, p in jobs]
        for fu in as_completed(futs):
            r = fu.result(); done += 1
            if done % 50 == 0:
                print("  %d/%d" % (done, len(jobs)), flush=True)
    got = len(os.listdir(OUT))
    print("frame files on disk: %d" % got, flush=True)
    print("FRAMES_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
