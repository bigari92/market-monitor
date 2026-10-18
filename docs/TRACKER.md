# The tracker — what it emits, and what it refuses to

Built 2026-10-18. This is the market-wide candidate tracker: it scans US-listed equities, ranks
them, and keeps a record of what it said. It is not an analysis of anyone's holdings, and it
reads no personal file (CLOUD-RULES.md §3).

**One thing to confirm before the cadence is set — see §6.** Everything else below is built,
tested and running.

---

## 1. What a run produces

Three outputs, from `python -m market_monitor.cloud.run track`:

**(1) BUY candidates** — the top 25 of the gated cross-section, each with its factor values and
the reason it ranks there. The reason is attribution, never a forecast: "near its 52-week high
(+0.87); shallow 12m drawdown (+0.83)" is a statement about the past. Each name's row carries the
per-term rank contributions, so the ranking is readable off the record without the panel that
produced it.

**(2) SELL / EXIT signals** — for anything previously listed, under one of six reasons:

| reason | trigger |
|---|---|
| `TREND_BREAK` | was at or above its 200-day average last run, is below it now |
| `RANK_DECAY` | rank fell past the carry buffer (2 × top N = 50) |
| `LEFT_VOL_GATE` | still priced and liquid, but out of the volatility cohort |
| `GATE_FAIL_PRICE` | price below 5.00 |
| `GATE_FAIL_LIQUIDITY` | 3-month average dollar volume below 5,000,000 |
| `NO_LONGER_PRICED` | absent from the panel entirely — delisted, renamed, or a feed gap |

**(3) TRACKING STATE** — the real product. Three append-only CSVs in `results/tracking/`:

- `runs.csv` — one row per run: `data_as_of`, `signal_version`, the universe funnel, counts.
- `listings.csv` — one row per listed name per run: rank, score, rank change, runs held,
  first-listed date, twelve factor values, and the reason.
- `events.csv` — every ENTER and EXIT with its reason, detail, and rank before/after.

A run never rewrites a past row; `test_a_past_row_is_never_rewritten` checks the new file starts
with the old one byte-for-byte.

## 2. The three properties that make the record worth keeping

**Append-only.** A call made in March is readable in September exactly as it was made, with the
`signal_version` that made it and the `data_as_of` it saw.

**Point-in-time, therefore survivorship-bias-free going forward.** RECOVERY.md defect 1 — a
survivor-only universe — is fatal to the recovered backtest and unfixable there, because the
delisted names are simply absent. It does not apply to what this accumulates: a name that is
listed and then collapses stays in `events.csv` with an exit reason. **The forward record is the
one unbiased dataset this project will own.** It is also, today, one run long.

**Reproducible.** `data_as_of` is the panel's last completed session, discovered from the data and
never `today()`. On 2026-10-18 (a Sunday) that was 2026-10-16. The signal definition is hashed
into `signal_version`, so two runs that disagree are either a market change or a definition
change, and the hash says which.

## 3. What it will never emit

**No probability.** Not configurable. `signal.assert_no_probability_columns` runs on every emitted
frame and rejects any column reading as a likelihood or expected return. The measured reason: an
isotonic calibrator fitted on one regime carried a Brier score of 0.120 into another where it
scored 0.189 — worse than not calibrating at all. A displayed probability would be precise and
wrong, and the precision is what would make it persuasive.

**No performance figure.** The published +37.8%/yr against +14.6% rests on roughly **7 effective
annual observations** (t ≈ 2.64) over a survivor-only universe. It is not an expected return and
nothing in the tool reports it as one.

**What the signal actually is: a loser-filter.** Conditional on the volatility cohort, trend
quality barely moves the up-tail (18.7% → 21.9%) and roughly halves the down-tail
(48.3% → 23.4%). The edge is in declining to rank names that are falling apart. It ranks and it
refuses; the owner decides.

## 4. The pipeline, and where each defect is handled

```
SEC company_tickers_exchange.json      10,444 rows
  → universe.build_universe             7,161 plain US-listed symbols (+ CIK, for the SEC join)
  → feeds.yahoo_chart                   7,161 fetched, 5y daily, 149s, zero 429s
  → universe.refine_universe            6,941 after dropping 209 ETFs and non-USD
  → factors.compute_factors             5,941 with 273+ sessions
  → signal.apply_gates                  2,697 past price/liquidity → 540 past the volatility gate
  → signal.score                        ranked, with per-term attribution
  → tracker.run                         diffed against the record, appended
```

| RECOVERY.md defect | status |
|---|---|
| 1. Survivor-only universe | **Structural for backtests; void forward.** The tracker records point-in-time and keeps exits, so its own history is unbiased. Sharadar is priced in `feeds/sharadar.py` for the backtest case. |
| 2. `auto_adjust=True` hides corporate actions | **Fixed at the source.** The raw endpoint returns `close`, `adjclose` and the split/dividend tables; 60,889 actions captured. Trend reads `close`, momentum reads `adjclose`. |
| 3. 12× overlapping forward returns | **Not applicable.** The tracker computes no forward return. It is also why §3 reports no performance. |
| 4. No cost model | **Closed** — `results/cost_model.md`. Spread estimated by two published estimators (converging at 96–99 bps on the top 25), commission from a published rate card, impact scaled by the cohort's own volatility, and turnover **measured** at 3.25×/yr from the replay record. Execution cost is 1.0–1.9pp a year for a 12-month hold and 3.2–6.1pp as configured, against 2.7–13× break-even headroom. Tax stays out of scope by design (CLOUD-RULES.md §3). |

## 5. Running it

```bash
python -m market_monitor.cloud.run track              # the run that writes the record
python -m market_monitor.cloud.run track --dry-run    # score and report, write nothing
python -m market_monitor.cloud.run universe           # the universe funnel alone
python -m market_monitor.cloud.run probe              # re-measure the feed
python -m market_monitor.cloud.run replay --months 24 # past dates into results/replay/
python -m market_monitor.cloud.run --years 20 horizon  # rank IC and tails at 3m vs 12m
```

`replay` is mechanical validation and **not a backtest**: no forward return, no performance. It
exists to exercise the exit paths on real prices, and it found two bugs that the synthetic tests
could not (see the commit log). It writes to `results/replay/` and never touches the live record.

First run takes ~150s to fetch; afterwards the panel is cached in `data/panels/` (gitignored,
~2s to read). `data/` is never committed; the ranking is what gets committed, and it is small.

## 6. Cadence: monthly — measured, not assumed

This was the one open question. It is now settled by measurement:
**`results/horizon_test.md`**, 190 monthly rebalance dates over 2010–2025.

The signal carries genuine information at 3 months (rank IC 0.096, positive in 74% of months,
t = 5.4 on 63 independent observations), so a monthly-refreshed ranking is reading signal rather
than reshuffling. More importantly, **the one thing the tracker does on review — detect
deterioration — works better at the short horizon than the long one:** the top 25 cuts the
frequency of a −30% move by **1.92× at 3 months against 1.58× at 12**, better identified
(t 5.65 vs 3.52), and positive in 15 of 16 calendar years.

The 12-month horizon has the larger IC (0.148) and the weaker evidence: 20 years of monthly dates
contain only ~15 independent 12-month observations against 63 at 3 months. Identification, not
magnitude, is the binding constraint — and it is the reason the published t-statistics in the
recovered research were inflated 3.4×.

**Monthly review is not monthly trading**, and that distinction is what makes the cadence safe.
The exit rules fire on structural breaks rather than rank drift, so a listing stays a
long-horizon thesis that gets *checked* often. The 24-month replay confirms the shape: 4–13 exits
a month from a watchlist of 28–38, not wholesale rotation.

**The cost model now closes this loop, and it sharpens the point.** Measured turnover is
**3.25×/yr** — an average holding period of 3.7 months, not 12 — and that costs 3× what a
12-month hold costs: 21–40% of the gross excess against 8–16%. Net of costs the two cadences are
a wash, so the 3-month horizon's higher gross excess buys nothing once paid for. Monthly review
remains right; **the conservative exit rules are load-bearing, and loosening them would trade
real money for noise.** See `results/cost_model.md` §5.

Weekly is not supported: nothing measured speaks to horizons under 63 trading days, and the exit
rules are built to ignore the rank noise a weekly cadence would surface.

Cadence is not hashed into `signal_version`, so changing it later does not invalidate the record —
but it changes what the record means, so it is recorded per run in `runs.csv`.

## 7. What to do next, in order of value

1. **Let the record accumulate.** It is one run long. Its entire value is in the second run and
   after, and nothing substitutes for elapsed time.
2. ~~**Fundamentals from the SEC Financial Statement Data Sets.**~~ **Done** —
   `results/fundamentals_build.md` and `results/fundamentals_modes.md`. 413,516 point-in-time
   rows over 14,995 CIKs, as-filed with real filing dates, joined on CIK. The measured answer:
   **the fundamentals do not improve selection and the signal stays price-only**, confirming
   `screen_v4.py`'s decision on a strictly harder dataset (no restated values, no 90-day
   lookahead). They are carried as **context** in the run report — `rule40`, margins, revenue
   growth and instability beside each name — plus the SIC sector mix, none of it scored.
3. **Read `results/factor_redundancy.md` and decide nothing in a hurry.** It answers
   RECOVERY.md's open question and finds a tighter redundancy that no review had looked at. Any
   change to the weight vector is a new configuration and belongs in the trials ledger that the
   block bootstrap (C2) is meant to score against.
4. ~~**Sector/industry data.**~~ **Done** — SIC comes free in the SEC filings and the run
   report now states the watchlist's industry mix. It confirms the concentration: **6 of the
   top 25 share SIC 3674 (semiconductors)**, and on a broader reading 13 of 25 are
   semiconductors or the equipment serving them. Reported, not scored —
   `screen_v4.py`'s industry-momentum *overlay* stays omitted and `signal_version` still
   hashes `industry_overlay: false`, because turning it on would change the signal.

5. ~~**A cost model.**~~ **Done** — `results/cost_model.md`. The answer changed a conclusion:
   net of costs, the faster cadence wins nothing. The tracker's measured 3.25× turnover gives up
   21–40% of its gross excess against 8–16% for a 12-month hold, and the 3-month horizon's
   higher gross excess is almost exactly consumed by it. **Monthly review stays right, and the
   conservative exit rules turn out to be load-bearing rather than merely defensible.**

6. **Survivorship is now the binding defect.** It is the only one of the four still structural,
   it cannot be fixed by being careful, and every net figure in `results/cost_model.md` inherits
   it. `feeds/sharadar.py` is priced and ready; this is the one place money would buy a real
   answer rather than a convenience.
