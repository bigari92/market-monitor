# Price feed probe — what actually returns data from a cloud session

**Run:** 2026-10-18, from the cloud session's datacentre IP (`market-monitor`, env `Default`).
**Question:** can a market-wide daily price panel for ~5,000+ US names be built from this
environment at all, and if so from what? The answer decides the architecture, so it was measured
before anything was built on top of it.

**Verdict: YES, from the Yahoo chart endpoint. 7,161 of 7,161 tickers, 100% success, zero
rate-limit responses, 149 seconds.** No paid feed is required for the forward tracker. Sharadar
remains the right purchase for a *backtest*, for one reason that money cannot be worked around —
delisted tickers — and that reason is recorded in `src/market_monitor/cloud/feeds/sharadar.py`.

---

## 1. The claim under test

`docs/CLOUD-RULES.md` §2 bans `yfinance` on every cloud path, because a datacentre IP was
reported rate-limited across every yfinance endpoint with no recovery in 48 hours. That is one
observation from Sept 2026, so it was re-measured rather than assumed.

## 2. Every source tried, with the real response

| Source | Result | Detail |
|---|---|---|
| **Yahoo chart** `query1.finance.yahoo.com/v8/finance/chart/{t}` | **WORKS** | 7,161/7,161 at 48 req/s sustained. Zero 429s. See §3. |
| **SEC** `company_tickers_exchange.json` | **WORKS** | 524 KB, 10,444 rows, cik + name + ticker + exchange. Needs the declared `Name email` User-Agent. |
| **SEC** `company_tickers.json` | **WORKS** | 799 KB, 9,909 plain-symbol tickers. |
| **SEC** Financial Statement Data Sets `2026q2.zip` | **WORKS** | 60.4 MB in **1.2 s**. The as-filed fundamentals route (§4 of the rules) is wide open. |
| **NASDAQ Trader** `nasdaqlisted.txt` / `otherlisted.txt` | **BLOCKED** | Imperva. See §4 — this is the dangerous one. |
| **Stooq** `stooq.com`, `stooq.pl` | **DEAD** | Connection failure (curl exit, `http=000`) after 7 s and 12 s. Not reachable from here at all. |
| **api.nasdaq.com** screener | **PARTIAL** | Small queries return JSON; `download=true&limit=10000` returns `rows: null`. Not needed — SEC replaced it. |

### A correction to the brief's expectation about Stooq

The brief warned that Stooq's documented failure mode is *empty bodies, not errors*. From this
environment Stooq does not get far enough to return an empty body — the connection itself fails.
The warning was still the right one to carry, and it is now enforced in code regardless of which
feed is in use: `feeds.FeedEmptyError` is raised by `Bars.__post_init__` on a panel with no
columns, and by `YahooChartFeed.fetch` when every ticker comes back dataless. A feed that answers
without data can never be mistaken for a feed that answered.

## 3. The Yahoo measurement, in full

Two stages. The first was a 300-request burst at three concurrency levels; the second was the
real thing — every ticker in the universe, once.

**Stage 1 — burst, 300 requests** (sample drawn deterministically, seed 20261018):

| phase | n | workers | wall | req/s | ≥250 bars | HTTP codes | p50 lat | p95 lat |
|---|---|---|---|---|---|---|---|---|
| A | 60 | 1 | 6.7 s | 8.9 | 52 | 200×58, 404×2 | 0.096 s | 0.155 s |
| B | 120 | 8 | 2.1 s | 56.1 | 97 | 200×118, 404×2 | 0.098 s | 0.601 s |
| C | 120 | 16 | 1.6 s | 74.3 | 93 | 200×113, 404×7 | 0.111 s | 0.829 s |

Every 404 was a genuine `"No data found, symbol may be delisted"`. **No 429 at any concurrency.**

**Stage 2 — the whole universe, 7,161 tickers, 5 years of daily bars:**

```
requested          7161
attempted          7161
status_counts      {"ok": 7161}      <- no failures of any kind
wall_seconds       149.0
requests_per_second 48.1
stopped_early      false
```

Resulting panel: **7,161 tickers x 1,255 sessions, 2021-10-18 .. 2026-10-16**, and
**60,889 corporate actions** (2,069 splits, 58,820 dividends) captured as data.

Coverage against the 273-session minimum that `factors.compute_factors` requires:

| bar-count percentile | p01 | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| sessions | 1 | 95 | 562 | 1,255 | 1,255 | 1,255 |

**5,941 names clear 273 bars and are scorable.** The short-history tail is recent IPOs, which the
factor code already declines to score rather than scoring badly.

Universe funnel: 10,444 SEC rows → 7,161 after exchange and plain-symbol filters → 6,941 after
dropping 209 ETFs and non-USD lines by instrument type → 5,941 with enough history.

### What the endpoint gives that `yfinance` hid

`auto_adjust=True` is RECOVERY.md defect 2 — after it, a price move and a split cannot be told
apart. The raw endpoint returns **three series and the action tables**: `close` (split-adjusted,
dividends intact), `adjclose` (total return), `volume`, plus `events.splits` and
`events.dividends`. Verified on NVDA's 10:1 split of 2024-06-10, which appears as an explicit
`{"splitRatio": "10:1"}` record rather than as an invisible rescaling.

**Defect 2 is therefore fixed at the source, not worked around.** `feeds.Bars` carries all three
series and the event table precisely so the distinction stays auditable.

## 4. The failure that mattered most — and it was silent

`nasdaqtrader.com` answered **HTTP 200** to every User-Agent tried, including a full Chrome one.
The body was 212 bytes of Imperva JavaScript challenge:

```
http=200 bytes=212 ct=text/html
<html><head><META NAME="robots" CONTENT="noindex,nofollow">
<script src="/_Incapsula_Resource?SWJIYLWA=..."></script>
```

A naive `pd.read_csv` on that gets a parse error if lucky and a one-row frame if not. Nothing
about the status code says the universe source is gone. `recovered/build_universe.py` depends on
exactly this URL, which is one concrete reason the recovered pipeline cannot simply be re-run.

**Replaced by `https://www.sec.gov/files/company_tickers_exchange.json`, which is better on every
axis:** official, documented, bulk, already covered by the §4 User-Agent convention, and it
carries the **CIK** — so the join to the SEC fundamentals datasets needs no ticker matching.
`src/market_monitor/cloud/universe.py` raises rather than returning a small frame if that source
ever parses to zero rows.

## 5. What this does and does not settle

**Settled:** the free feed runs the forward tracker. No purchase is needed to start, and the
USD 90 is not spent on data.

**Not settled, and stated rather than glossed:**

1. **The endpoint is unlicensed and undocumented.** It worked perfectly today from this IP; it
   carries no uptime promise and can change or close without notice. It is *measured-viable*,
   not *dependable*. This is why the feed sits behind a protocol in `feeds/__init__.py` and why
   `sharadar.py` is priced and ready rather than absent.
2. **One IP, one day.** 7,161 clean requests is strong evidence and not a guarantee. The
   §2 failure *mechanism* is therefore handled in code and not by optimism:
   `YahooChartFeed` makes **one attempt per ticker, never retries through a throttle**, and
   raises `FeedThrottledError` the moment five 429s arrive — so a throttled session stops
   quickly instead of spending the budget discovering it is throttled.
3. **Survivorship is untouched by any of this.** The universe is today's registrants, so it is
   survivor-only exactly as RECOVERY.md defect 1 says. It is harmless *forward* — the tracker
   records each run point-in-time and keeps delisted names with an exit reason, so the history it
   accumulates is bias-free by construction — and still fatal to any backtest run on it. No
   number in `recovered/` is rehabilitated by this probe.

## 6. Cost

**USD 0.00 of the USD 90 was spent on data.** Everything in this report came from free endpoints.
The session cost itself is recorded in `docs/CREDIT-LEDGER.md`.

## 7. Reproducing it

```bash
.venv/bin/python -m market_monitor.cloud.run probe     # the feed probe
.venv/bin/python -m market_monitor.cloud.universe      # the universe funnel alone
```

The panel caches to `data/panels/yahoo_chart_<as_of>/` (gitignored, ~150 s to rebuild from
scratch, ~2 s to read). Nothing in `data/` is ever committed; the committed artefact is the
ranking, which is small.
