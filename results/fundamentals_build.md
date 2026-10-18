# As-filed fundamentals from the SEC Financial Statement Data Sets

**Run:** 2026-10-18. 70 quarterly zips, **2009q1 .. 2026q3** (2026q4 not yet published).
**3,374,331 raw facts → 1,551,147 as-originally-filed → a 413,516-row point-in-time panel over
14,995 CIKs.** USD 0.00 spent; every byte is free and public.

This replaces the EDGAR **frames** route that `recovered/download_fundamentals.py` uses and that
`docs/CLOUD-RULES.md` §4 bans. The ban existed as a reasoned rule; §1 below measures it.

---

## 1. The frames ban was right, and here is its size

§4's argument: a frames fact comes from the entity's *last filed* submission, so values silently
mix originally-filed and restated numbers. Measured across all 1,551,147 (cik, period, tag)
groups:

| | |
|---|---|
| groups reported more than once | 1,127,464 |
| **groups where the value actually changed** | **148,819** |
| **share of all groups restated** | **9.59%** |
| median relative change, where it changed | **5.0%** |
| **p90 relative change** | **104.0%** |
| changes larger than 10% | 60,716 |

**Roughly one figure in ten is later restated, and the top decile of those changes more than
doubles.** This is not a rounding concern. Had the frames route been used, about 9.6% of the
panel would carry a number that did not exist at the time it is dated, and the affected rows
would not be a random sample — they are concentrated in the companies that restate, which is
exactly the population a quality signal is trying to judge.

## 2. The 90-day lag assumption — a correction in the recovered work's favour

`recovered/build_fundamentals.py` sets `avail_date = period_end + 90 days`, with the comment
that 90 days "covers 96% of genuine first filings". The real `filed` date is now in hand, so
that claim is checkable.

The lag distribution is **bimodal**, and reading it without noticing that would produce a wrong
verdict:

| lag bucket (days) | share of rows |
|---|---|
| ≤ 30 | 8.00% |
| 30–45 | **53.10%** |
| 45–60 | 14.01% |
| 60–75 | 4.39% |
| 75–90 | 3.70% |
| 90–120 | 2.15% |
| 120–180 | 1.06% |
| 180–300 | 0.83% |
| 300–400 | 2.10% |
| **400–500** | **9.22%** |
| > 500 | 1.43% |

Two populations, not one:

- **Genuine first filings** — 86.5% of rows, lag ≤ 200 days, median **41**, p95 **89**.
  **Within this population 96.11% fall inside 90 days.** The recovered claim of 96% was
  accurate, and the naive whole-sample figure (83.35%) would have falsely contradicted it.
- **Comparative-only periods** — 12.8% of rows at lag > 300 days, median **410**. These are not
  late filings. A fiscal period whose original filing predates this dataset, or arrived on a form
  not collected here, first *appears* as a prior-year comparative inside a later filing. A
  ~410-day lag is exactly what a prior-year column looks like.

**So the improvement from using `filed` is not that 90 days was badly calibrated — it was well
calibrated. It is twofold and narrower:**

1. The 3.89% of genuine filings that land beyond 90 days are no longer mis-dated. That is a small
   share and the worst possible one to get wrong: a company filing late is a company in trouble,
   and a signal built to avoid trouble must not see its numbers early.
2. **For the 12.8% comparative-only rows, `period_end + 90 days` introduces real lookahead** — it
   would date a figure as knowable roughly ten months before any filing in this dataset reported
   it. Using `filed` is conservative there (availability later than the truth), which is the
   safe direction to err.

## 3. Q4 does not exist in the source and had to be derived

`qtrs` gives the period length in quarters. A 10-K states the fiscal year (`qtrs=4`), not its
fourth quarter. Counting reported one-quarter rows by the calendar month their period ends:

| month | Mar | Jun | Sep | **Dec** |
|---|---|---|---|---|
| reported quarterly rows | 95,697 | 99,983 | 94,815 | **44,372** |

December is the dominant fiscal year end, and it carries **fewer than half** the quarterly rows of
any other quarter-end month. The missing ones are Q4s that only ever appear folded into the
annual figure.

Deriving `Q4 = FY − (Q1 + Q2 + Q3)` added **66,717 rows**, a 17.8% increase over the 374,783
reported quarterly rows. Without it, `rolling(4).sum()` with `min_periods=4` cannot step across
Q4 and the TTM series breaks once a year for most companies.

**`recovered/build_fundamentals.py` filters frames to durations of 80–100 days**, which is the
same filter by another name, so the recovered fundamental panel very likely carried this hole.
That is an inference about code this session may not edit or run, not a measurement of its
output — but the magnitude above is measured, and it is large.

## 4. Coverage: the panel effectively starts in 2012, not 2009

The XBRL mandate phased in by filer size, and the files show it — 2009q1 contains **zero**
10-K/10-Q submissions, 2009q2 twenty. Non-null share by fiscal year:

| year | rows | CIKs | rev_ttm | rev_yoy_ttm | op_margin | rule40 | rev_stability |
|---|---|---|---|---|---|---|---|
| 2010 | 18,336 | 7,796 | 20.8% | 6.0% | 13.2% | 3.3% | 3.9% |
| 2011 | 29,131 | 8,441 | 47.7% | 12.3% | 29.5% | 6.7% | 9.6% |
| 2012 | 29,465 | 8,343 | 59.4% | 40.1% | 33.0% | 24.8% | 31.8% |
| 2013 | 28,767 | 8,069 | 59.4% | 49.9% | 32.9% | 31.2% | 50.8% |
| 2016 | 25,103 | 7,014 | 61.0% | 53.3% | 34.3% | 33.4% | 55.6% |
| 2020 | 23,615 | 6,677 | 68.6% | 60.5% | 41.7% | 40.3% | 65.5% |
| 2025 | 20,961 | 5,971 | 74.1% | 68.1% | 56.1% | 56.6% | 69.3% |

`rule40` — the variable both fundamental modes lean on — is under 7% before 2012 and only
reaches a third by 2013. **Any comparison of the fundamental modes before ~2013 is measuring
missing data, not a strategy**, which is why `results/fundamentals_modes.md` reports the
coverage per date alongside the result.

`op_margin` never exceeds 56% even recently, because a large minority of filers (banks, REITs,
insurers, trusts) do not report the income-statement tags this panel is built from. That is a
property of the tag set the recovered code chose, carried over unchanged.

A handful of rows carry period ends back to 1987 — single comparatives buried in later filings.
They are harmless (one row in 1987) and left in rather than trimmed by a rule that would need
justifying.

## 5. The join onto the tradable universe

Joined on **CIK**, taken from SEC's own exchange map in `universe.py`, so a ticker is never a
join key and cannot mis-associate a company with a symbol.

| | |
|---|---|
| universe names (post instrument filter) | 6,936 — 5,924 distinct CIKs |
| with fundamentals knowable at 2026-10-16 | 4,254 (**71.8%**) |
| **of the 540-name gated cohort** | **471 (87.2%)** |
| of the live top 25 | **23 / 25** |

Coverage is far better where it matters: the price and liquidity floors already exclude most of
the shells and micro-caps that lack usable filings, so the cohort the signal actually ranks is
87% covered against 72% for the raw universe.

### The two misses are the documented cost, and they are real

**UMC** (rank 5) and **TGB** (rank 22) have no fundamentals, and both have no SIC code here
either. Both are foreign issuers — a foreign private issuer files **20-F** or **40-F**, forms
this module deliberately excludes because they are annual and carry different tags. §2 of
`src/market_monitor/cloud/sec_fsds.py` names that exclusion as "a real coverage cost rather than
a clean win"; these are the names it costs. Any fundamental exclusion rule would silently treat
both as unknown rather than as passing.

## 6. Sector, for the first time

SIC arrives free in `sub.txt`, so the concentration that has been visible to the eye is now
reportable. `recovered/screen_v4.py` read industry from a Nasdaq screener download this
environment cannot reach (`results/price_feed_probe.md` §2), which is why the tracker has been
shipping a conspicuously semiconductor-heavy list with no way to say so in its own output.

The live top 25, by SIC:

| SIC | industry | names |
|---|---|---|
| 3674 | Semiconductors & related devices | **AMD, MTSI, SMTC, INTC, MU, FORM** (6) |
| 7372 | Services — prepackaged software | NET, ZETA, TWLO (3) |
| 2836 | Biological products | IOVA, MRNA, RLAY (3) |
| 3825/3826/3559/3572/3669/3672/7374 | other instruments, equipment, computing | TER, TXG, LRCX, P, LITE, SANM, RNG (7) |
| 2834 | Pharmaceutical preparations | SYRE (1) |
| 2911 | Petroleum refining | PBF (1) |
| 6795 | Mineral royalty traders | SSRM (1) |
| 4899 | Communication services | VSAT (1) |
| — | no SIC (foreign filers) | UMC, TGB (2) |

**Six of 25 are the same SIC code, and on a broader reading 13 of 25 sit in semiconductors or
the equipment and instruments that serve them.** That is the volatility gate doing what it is
built to do — it selects names capable of large moves, and in this market those cluster — but it
is concentration the owner should see stated rather than infer. The 444-code SEC SIC list is
committed as package reference data (`reference/sic_codes.csv`) rather than fetched at runtime,
because a ranking run should not depend on a web page being up.

**SIC is reported and not scored.** `screen_v4.py`'s industry-momentum overlay stays omitted and
`signal_version` still hashes `industry_overlay: false`; turning it on would change the signal,
which §5 does not permit a session to do.

## 7. Reproducing it

```bash
python -m market_monitor.cloud.run fundamentals              # harvest + build (cached after)
python -m market_monitor.cloud.run fundamentals --refetch    # re-download all 70 quarters
```

~40 minutes for a cold harvest, dominated by downloading ~5 GB of zips. Each zip is
stream-filtered to the ~7% of rows that matter (~6s per quarter) and then **deleted**, so peak
disk is one quarter rather than 5 GB; `num.txt` alone is ~600 MB uncompressed per quarter, so
extracting the series would be 42 GB. The filtered facts and the built panel live in
`data/sec/` (gitignored); what gets committed is this report and the code.

Three exclusions are applied at parse time and each is a silent corruption rather than an error:
`segments` must be empty (**67%** of consolidated-looking `NetIncomeLoss` rows carry a segment
breakdown), `coreg` must be empty, and `uom` must be USD. The tests in
`tests/test_fundamentals.py` pin the Q4 derivation, the as-originally-filed rule, and the
point-in-time cutoff against arithmetic.
