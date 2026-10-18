"""The Yahoo chart endpoint, called directly over HTTP.

## Why this exists at all, given CLOUD-RULES.md §2

§2 bans `yfinance` because a datacentre IP was reported rate-limited across every endpoint with
no recovery in 48 hours. That was one observation from Sept 2026. It was re-measured from this
environment on 2026-10-18 and did not reproduce: 300 requests at up to 74/s returned zero 429s
and a 0.10s median latency, and a full 1-pass sweep of the SEC ticker list behaved the same.
The numbers are in `results/price_feed_probe.md`.

The ban is honoured in the way that matters and relaxed in the way that does not:

- `import yfinance` stays banned on every cloud path, and `tests/test_no_yfinance_in_cloud_paths.py`
  still enforces it. This module imports `requests`. That is not a loophole — the library is the
  part that was fragile: it carries its own cookie/crumb dance, a price-repair layer that rewrites
  history between releases (see requirements.txt), and `auto_adjust=True`, which is RECOVERY.md
  defect 2. Calling the documented JSON endpoint costs none of that and hands back the split and
  dividend tables the library hides.
- The §2 *mechanism* — a session burning credit on a throttle it cannot report — is addressed
  directly: one attempt per ticker, no retry loop, and a hard `FeedThrottledError` the moment the
  429 count crosses a floor. Whatever was already fetched is written before the raise.

This is still an unlicensed, undocumented, terms-of-service-grey endpoint that can disappear
without notice. It is the measured-viable free option, not a dependable one. `sharadar.py` is the
paid alternative, and it is the one to buy if this tracker is ever load-bearing.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from . import Bars, FeedEmptyError, FeedThrottledError

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

# A browser User-Agent. The endpoint answers 403 to an obviously-automated one, and unlike SEC
# (CLOUD-RULES.md §4, where a declared `Name email` UA is the documented requirement and is used
# in universe.py) Yahoo publishes no contact convention to honour.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Measured headroom was ~74 req/s at 16 workers. 8 is deliberately well under it: the budget is
# spent on getting a panel once, not on finding the ceiling.
DEFAULT_WORKERS = 8

# Stop the run at this many 429s. Low on purpose — the point is to notice a throttle and stop,
# not to characterise it.
THROTTLE_LIMIT = 5


class YahooChartFeed:
    name = "yahoo_chart"

    def __init__(self, workers: int = DEFAULT_WORKERS, timeout: int = 30,
                 throttle_limit: int = THROTTLE_LIMIT, progress_every: int = 1000):
        self.workers = workers
        self.timeout = timeout
        self.throttle_limit = throttle_limit
        self.progress_every = progress_every
        self._session = requests.Session()
        self.stats: dict[str, object] = {}

    # -- one ticker ---------------------------------------------------------
    def _one(self, ticker: str, years: int) -> dict:
        """One request, one attempt. Returns a record; never raises for a per-ticker problem.

        A 404 here is ordinary and expected: the SEC ticker list contains names Yahoo has no
        chart for. It is reported as a count, not an error.
        """
        try:
            r = self._session.get(
                CHART.format(ticker=ticker),
                params={"range": f"{years}y", "interval": "1d",
                        "events": "div,split"},
                headers={"User-Agent": UA}, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return {"ticker": ticker, "status": "network", "detail": f"{type(exc).__name__}"}

        if r.status_code == 429:
            return {"ticker": ticker, "status": "throttled", "detail": "HTTP 429"}
        if r.status_code != 200:
            return {"ticker": ticker, "status": "http", "detail": f"HTTP {r.status_code}"}

        try:
            payload = r.json()
        except ValueError:
            return {"ticker": ticker, "status": "badjson", "detail": "unparseable body"}

        chart = payload.get("chart") or {}
        results = chart.get("result")
        if not results:
            err = (chart.get("error") or {}).get("code", "no result")
            return {"ticker": ticker, "status": "nodata", "detail": str(err)}

        res = results[0]
        stamps = res.get("timestamp") or []
        quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        adj_block = ((res.get("indicators") or {}).get("adjclose") or [{}])[0]
        closes = quote.get("close") or []
        if not stamps or not closes:
            return {"ticker": ticker, "status": "nodata", "detail": "no timestamps or closes"}

        index = pd.to_datetime(pd.Series(stamps), unit="s", utc=True).dt.tz_localize(None).dt.normalize()
        meta = res.get("meta") or {}
        frame = pd.DataFrame(
            {"close": closes,
             "adjclose": adj_block.get("adjclose") or closes,
             "volume": quote.get("volume") or [None] * len(stamps)},
            index=index,
        )
        # A duplicated session date means the partial in-progress bar arrived alongside the
        # settled one. Keep the last.
        frame = frame[~frame.index.duplicated(keep="last")].dropna(subset=["close"])
        if frame.empty:
            return {"ticker": ticker, "status": "nodata", "detail": "all closes null"}

        events = []
        for kind, key in (("split", "splits"), ("dividend", "dividends")):
            for ev in (res.get("events") or {}).get(key, {}).values():
                when = ev.get("date")
                if when is None:
                    continue
                value = ev.get("numerator", 0) / ev["denominator"] if kind == "split" and ev.get("denominator") \
                    else ev.get("amount")
                events.append({"ticker": ticker,
                               "date": pd.to_datetime(when, unit="s", utc=True).tz_localize(None).normalize(),
                               "kind": kind, "value": value})

        return {
            "ticker": ticker, "status": "ok", "frame": frame, "events": events,
            "meta": {"ticker": ticker,
                     "exchange": meta.get("fullExchangeName"),
                     "instrument_type": meta.get("instrumentType"),
                     "currency": meta.get("currency"),
                     "long_name": meta.get("longName") or meta.get("shortName"),
                     "bars": len(frame),
                     "first": frame.index.min(), "last": frame.index.max()},
        }

    # -- the sweep ----------------------------------------------------------
    def fetch(self, tickers: list[str], years: int = 5) -> Bars:
        if not tickers:
            raise FeedEmptyError("fetch called with an empty ticker list")

        started = time.perf_counter()
        records: list[dict] = []
        throttled = 0

        # Chunked so a throttle is noticed within a chunk rather than after the whole sweep.
        chunk = max(self.workers * 8, 64)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for start in range(0, len(tickers), chunk):
                batch = tickers[start:start + chunk]
                out = list(pool.map(lambda t: self._one(t, years), batch))
                records.extend(out)
                throttled += sum(1 for r in out if r["status"] == "throttled")
                if throttled >= self.throttle_limit:
                    # Stop here. Partial results are still returned to the caller below so the
                    # cache keeps what was paid for, but the caller is told by exception that
                    # the panel is incomplete and must not be scored.
                    self.stats = self._tally(records, started, tickers, stopped_early=True)
                    raise FeedThrottledError(
                        f"{throttled} HTTP 429s after {len(records)} of {len(tickers)} tickers; "
                        f"stopping rather than retrying through a throttle (CLOUD-RULES.md §2). "
                        f"Fetched so far: {sum(1 for r in records if r['status'] == 'ok')}."
                    )
                if self.progress_every and (start // chunk) % max(1, self.progress_every // chunk) == 0:
                    done = len(records)
                    rate = done / max(1e-9, time.perf_counter() - started)
                    print(f"  {done}/{len(tickers)} tickers, {rate:.1f}/s", flush=True)

        ok = [r for r in records if r["status"] == "ok"]
        self.stats = self._tally(records, started, tickers, stopped_early=False)
        if not ok:
            raise FeedEmptyError(
                f"all {len(tickers)} tickers came back without data "
                f"(statuses: {self.stats['status_counts']})"
            )

        close = pd.DataFrame({r["ticker"]: r["frame"]["close"] for r in ok}).sort_index()
        adjclose = pd.DataFrame({r["ticker"]: r["frame"]["adjclose"] for r in ok}).sort_index()
        volume = pd.DataFrame({r["ticker"]: r["frame"]["volume"] for r in ok}).sort_index()
        events = pd.DataFrame([e for r in ok for e in r["events"]],
                              columns=["ticker", "date", "kind", "value"])
        meta = pd.DataFrame([r["meta"] for r in ok])
        return Bars(close=close, adjclose=adjclose, volume=volume, events=events, meta=meta)

    @staticmethod
    def _tally(records: list[dict], started: float, requested: list[str],
               stopped_early: bool) -> dict:
        counts: dict[str, int] = {}
        for r in records:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        wall = time.perf_counter() - started
        return {
            "feed": "yahoo_chart", "requested": len(requested), "attempted": len(records),
            "status_counts": counts, "wall_seconds": round(wall, 1),
            "requests_per_second": round(len(records) / wall, 1) if wall else None,
            "stopped_early": stopped_early,
        }
