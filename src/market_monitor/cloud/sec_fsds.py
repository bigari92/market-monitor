"""SEC Financial Statement Data Sets: download, stream-filter, and keep the real filing date.

## Why this and not the route the recovered pipeline used

`recovered/download_fundamentals.py` pulls the EDGAR **frames** API. CLOUD-RULES.md §4 bans that
for historical panels, and the reason is specific: a frames fact comes from the entity's *last
filed* submission, so values silently mix originally-filed and restated numbers — concentrated
in exactly the companies that restate, which are exactly the companies a quality signal is
trying to judge. Nothing in the output marks which is which.

The Financial Statement Data Sets are the documented alternative: one zip per quarter, as filed,
"presented without change", and every row traceable to a submission with a real `filed` date.
That last column is what removes `build_fundamentals.py`'s `LAG_DAYS = 90` approximation —
availability stops being an assumption and becomes an observation.

## What this module does NOT extract, and why each exclusion is load-bearing

Measured on 2026q2 before any of this was written, because each of these is a silent
corruption rather than an error:

- **`segments` must be empty.** Of 42,139 consolidated-looking `NetIncomeLoss` rows, **28,205
  (67%) carry a non-empty `segments`** — a per-segment or per-product breakdown, not the
  company total. Summing or max-ing across them produces a number that belongs to no entity.
  This is the single most dangerous column in the dataset.
- **`coreg` must be empty.** A co-registrant is a subsidiary filing under the parent's
  accession; its revenue is not the parent's revenue.
- **`uom` must be USD.** Share counts, per-share amounts and foreign-currency duplicates all
  share the tag namespace.
- **The form must be a 10-K or 10-Q.** 11-K (employee benefit plans) and 6-K carry unrelated
  figures under the same tags. **20-F is excluded too**, which is a real coverage cost rather
  than a clean win: foreign private issuers report annually on 20-F, so US-listed ADRs get no
  fundamentals here. `results/fundamentals_build.md` reports which names that loses.

## Quarterly flows: Q4 does not exist in the data and has to be derived

`qtrs` gives the period length in quarters: 0 instant, 1 one quarter, 4 a full year. For
`NetIncomeLoss` on 2026q2's 10-K filings the split is **1,387 rows at `qtrs=4` against 119 at
`qtrs=1`** — annual reports state the year, not its fourth quarter.

So a pipeline that keeps only one-quarter durations has a systematic **hole at every Q4**, and a
trailing-twelve-month sum built with `min_periods=4` goes NaN or silently shifts there.
`recovered/build_fundamentals.py` filters frames to durations of 80–100 days, which is that same
filter by another name, so the recovered fundamental panel probably carried this hole.
`results/fundamentals_build.md` measures whether it did rather than asserting it.

Here Q4 is derived: `Q4 = FY - (Q1 + Q2 + Q3)`, only where all three quarters and the year are
present for the same fiscal year.
"""
from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

FSDS_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip"

# CLOUD-RULES.md §4: a declared User-Agent of the form `Name email@domain`. A missing or generic
# one returns an "Undeclared Automated Tool" page rather than data.
SEC_UA = "market-monitor research valer.vladislav@gmail.com"

# §4 again: at most 10 requests/second. These are 60-95 MB files fetched a handful at a time, so
# the rate is nowhere near the ceiling; the floor is here so a retry loop cannot drift into it.
MIN_REQUEST_INTERVAL = 0.15

# The income-statement tags `recovered/build_fundamentals.py` used, unchanged. Revenue is
# coalesced across the first four by priority, because the tag a company uses moved with
# ASC 606 and a single tag covers only part of the history.
REVENUE_TAGS = ("Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueNet")
OTHER_TAGS = ("GrossProfit", "CostOfRevenue", "CostOfGoodsAndServicesSold",
              "OperatingIncomeLoss", "NetIncomeLoss")
WANTED_TAGS = frozenset(REVENUE_TAGS + OTHER_TAGS)

KEEP_FORMS = ("10-K", "10-Q")
KEEP_QTRS = frozenset({"1", "4"})

FIRST_QUARTER = (2009, 1)


def quarters(start: tuple[int, int] = FIRST_QUARTER,
             end: tuple[int, int] | None = None) -> list[str]:
    """Quarter labels from `start` to `end` inclusive, e.g. '2009q1'.

    The dataset begins at 2009q1, but the early files are nearly empty — 2009q1 is 13 KB
    against 60-95 MB for a recent quarter — because the XBRL mandate phased in by filer size
    through 2011. They are fetched anyway and the thinness is reported, not assumed.
    """
    if end is None:
        today = pd.Timestamp.utcnow()
        end = (today.year, (today.month - 1) // 3 + 1)
    out = []
    year, quarter = start
    while (year, quarter) <= end:
        out.append(f"{year}q{quarter}")
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    return out


_last_request = [0.0]


def _throttle() -> None:
    gap = time.time() - _last_request[0]
    if gap < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - gap)
    _last_request[0] = time.time()


def download_quarter(quarter: str, dest_dir: Path, retries: int = 3) -> Path | None:
    """Fetch one quarter's zip. Returns None if that quarter is not published yet (404).

    A 404 is the ordinary way to discover the end of the series — the current quarter's file
    does not exist until weeks after it closes — so it is a None, not an error.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{quarter}.zip"
    if target.exists() and target.stat().st_size > 1000:
        return target

    url = FSDS_URL.format(quarter=quarter)
    for attempt in range(retries):
        _throttle()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
            if len(body) < 1000:
                return None
            target.write_bytes(body)
            return target
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def read_submissions(archive: zipfile.ZipFile) -> dict[str, dict]:
    """adsh -> {cik, sic, form, filed, period, fy, fp, prevrpt} for 10-K/10-Q submissions only."""
    out: dict[str, dict] = {}
    with archive.open("sub.txt") as handle:
        reader = csv.DictReader(io.TextIOWrapper(handle, "utf-8", errors="replace"),
                                delimiter="\t")
        for row in reader:
            form = (row.get("form") or "").strip()
            if not form.startswith(KEEP_FORMS):
                continue
            out[row["adsh"]] = {
                "cik": row.get("cik"), "sic": row.get("sic"), "form": form,
                "filed": row.get("filed"), "fy": row.get("fy"), "fp": row.get("fp"),
                "prevrpt": row.get("prevrpt"),
            }
    return out


def filter_numbers(archive: zipfile.ZipFile, submissions: dict[str, dict]) -> pd.DataFrame:
    """Stream num.txt and keep only consolidated USD rows for the wanted tags.

    Streamed line by line rather than parsed with pandas: num.txt is ~600 MB uncompressed per
    quarter and ~70 quarters exist, so extracting or fully parsing them is 42 GB of work to
    reach the 7% of rows that matter. The scan takes ~6s per quarter.
    """
    rows = []
    with archive.open("num.txt") as handle:
        handle.readline()  # header
        for raw in handle:
            parts = raw.split(b"\t")
            if len(parts) < 9:
                continue
            # Cheapest discriminators first: tag, then the two emptiness checks.
            tag = parts[1].decode("utf-8", "replace")
            if tag not in WANTED_TAGS:
                continue
            if parts[6] or parts[7]:        # segments / coreg must both be empty
                continue
            if parts[4].decode() not in KEEP_QTRS:
                continue
            if parts[5] != b"USD":
                continue
            submission = submissions.get(parts[0].decode("utf-8", "replace"))
            if submission is None:
                continue
            value = parts[8].strip()
            if not value:
                continue
            try:
                number = float(value)
            except ValueError:
                continue
            rows.append((submission["cik"], parts[3].decode(), int(parts[4]), tag, number,
                         submission["filed"], submission["form"], submission["sic"],
                         submission["fy"], submission["fp"]))

    frame = pd.DataFrame(rows, columns=["cik", "ddate", "qtrs", "tag", "value", "filed",
                                        "form", "sic", "fy", "fp"])
    if frame.empty:
        return frame
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce").astype("Int64")
    frame["ddate"] = pd.to_datetime(frame["ddate"], format="%Y%m%d", errors="coerce")
    frame["filed"] = pd.to_datetime(frame["filed"], format="%Y%m%d", errors="coerce")
    frame["sic"] = pd.to_numeric(frame["sic"], errors="coerce").astype("Int64")
    return frame.dropna(subset=["cik", "ddate", "filed"])


def harvest(dest_dir: Path, quarter_labels: list[str] | None = None,
            keep_zips: bool = False, progress: bool = True) -> pd.DataFrame:
    """Download and filter every quarter, returning one long frame of facts.

    Each zip is deleted after filtering unless `keep_zips`, so peak disk stays at one quarter
    rather than the ~5 GB the full series would occupy.
    """
    labels = quarter_labels or quarters()
    collected: list[pd.DataFrame] = []
    missing: list[str] = []
    sizes: dict[str, int] = {}

    for label in labels:
        path = download_quarter(label, dest_dir)
        if path is None:
            missing.append(label)
            if progress:
                print(f"  {label}: not published", flush=True)
            continue
        sizes[label] = path.stat().st_size
        with zipfile.ZipFile(path) as archive:
            submissions = read_submissions(archive)
            frame = filter_numbers(archive, submissions)
        if not keep_zips:
            path.unlink()
        collected.append(frame)
        if progress:
            print(f"  {label}: {len(submissions):5d} submissions, {len(frame):7d} facts",
                  flush=True)

    if not collected:
        raise RuntimeError("no quarter yielded any facts; the dataset or its URL changed")
    # Empty frames are dropped before concat: 2009q1 contains zero 10-K/10-Q submissions (the
    # XBRL mandate had not begun), and concatenating an all-NA frame makes pandas warn about
    # future dtype behaviour rather than simply ignoring it.
    non_empty = [frame for frame in collected if not frame.empty]
    if not non_empty:
        raise RuntimeError("every quarter filtered to zero rows; check the exclusion filters")
    facts = pd.concat(non_empty, ignore_index=True)
    facts.attrs["missing_quarters"] = missing
    facts.attrs["zip_sizes"] = sizes
    return facts


def as_originally_filed(facts: pd.DataFrame) -> pd.DataFrame:
    """Collapse to one value per (cik, period end, qtrs, tag): the EARLIEST filing that said it.

    This is the point of using this dataset. A later 10-K may restate an earlier quarter, and
    taking the latest value — which is what the frames API does — means a backtest at 2014 can
    see a number first published in 2017. Taking the earliest filing gives what was actually
    knowable, and carries the date on which it became knowable.

    The alternative reading is defensible and is not what is implemented: at rebalance date T the
    market also knew any restatement filed before T. That version answers "best information
    available at T"; this one answers "information as originally reported", which is the harsher
    and more reproducible of the two. The choice is recorded here rather than left implicit.
    """
    ordered = facts.sort_values(["cik", "ddate", "qtrs", "tag", "filed"])
    return ordered.drop_duplicates(subset=["cik", "ddate", "qtrs", "tag"], keep="first")


def restatement_rate(facts: pd.DataFrame) -> dict:
    """How often a (cik, period, tag) was reported more than once, and how much the value moved.

    Reported because it is the size of the problem CLOUD-RULES.md §4 is about. If it were
    negligible the frames ban would be pedantry; it is not.
    """
    keys = ["cik", "ddate", "qtrs", "tag"]
    counts = facts.groupby(keys)["value"].agg(["count", "first", "last", "nunique"])
    repeated = counts[counts["count"] > 1]
    if repeated.empty:
        return {"groups": int(len(counts)), "restated_groups": 0}
    changed = repeated[repeated["nunique"] > 1]
    relative = ((changed["last"] - changed["first"]).abs()
                / changed["first"].abs().replace(0, pd.NA)).dropna()
    return {
        "groups": int(len(counts)),
        "reported_more_than_once": int(len(repeated)),
        "value_actually_changed": int(len(changed)),
        "share_of_groups_restated_%": round(100 * len(changed) / len(counts), 3),
        "median_relative_change": round(float(relative.median()), 4) if len(relative) else None,
        "p90_relative_change": round(float(relative.quantile(0.9)), 4) if len(relative) else None,
        "changes_over_10pct": int((relative > 0.10).sum()) if len(relative) else 0,
    }
