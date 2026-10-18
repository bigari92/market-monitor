"""The tradable universe, from SEC's own ticker-to-exchange map.

`recovered/build_universe.py` fetched NASDAQ Trader's symbol directory. That route is gone from
this environment: `nasdaqtrader.com` sits behind an Imperva challenge and answers every
User-Agent tried with a 212-byte interstitial under an HTTP 200 — a silent failure, which is the
worst kind, and the one `feeds.FeedEmptyError` exists to catch.

`https://www.sec.gov/files/company_tickers_exchange.json` replaces it and is strictly better:
official, documented, bulk, and already governed by the User-Agent convention in CLOUD-RULES.md
§4. It carries cik, name, ticker and exchange, so the CIK is in hand for the fundamentals join
that the SEC Financial Statement Data Sets will need later, with no ticker-matching step.

## The survivorship question, stated honestly

This is a *current* registrant list, so it is survivor-only, exactly as RECOVERY.md defect 1
describes. That defect is fatal to a backtest and harmless to this tracker, for one reason: the
tracker never scores the past. It scores today, writes the ranking down, and compares the next
run against the record. Every observation it accumulates is point-in-time by construction, and a
name that delists stays in the history with its last rank and an exit reason. Going forward the
tracking state is survivorship-bias-free; the recovered backtest numbers it inherited are not,
and nothing here should be read as validating them.
"""
from __future__ import annotations

import io
import json
import urllib.request

import pandas as pd

SEC_TICKERS_EXCHANGE = "https://www.sec.gov/files/company_tickers_exchange.json"

# CLOUD-RULES.md §4: SEC requires a declared User-Agent of the form `Name email@domain`.
# A missing or generic one returns an "Undeclared Automated Tool" page.
SEC_UA = "market-monitor research valer.vladislav@gmail.com"

# The exchanges a listed US common stock trades on. OTC is excluded deliberately: the liquidity
# gate (MIN_ADV) would reject nearly all of it anyway, and quote quality there is poor enough
# that a factor computed on it is measuring the spread, not the company.
KEEP_EXCHANGES = {"Nasdaq", "NYSE", "NYSE American", "NYSEAmerican", "NYSE Arca", "CBOE"}

# Instrument types Yahoo reports that are not operating companies. Applied after the price fetch,
# since the exchange map does not distinguish a fund from a company.
DROP_INSTRUMENT_TYPES = {"ETF", "MUTUALFUND", "INDEX", "CURRENCY", "CRYPTOCURRENCY", "FUTURE"}

# Share-class suffixes and non-common instruments arrive as symbols with punctuation
# (BRK.B, warrants as ...W, units as ...U). `recovered/build_universe.py` kept 1-5 plain letters
# and that rule is kept here, with its consequence named: it drops legitimate dual-class B shares.
# For a ranking tool that is the right trade — the A line is in the universe and the two move
# together — but it is a choice, not a cleanup.
SYMBOL_RE = r"[A-Z]{1,5}"


def fetch_sec_exchange_map(url: str = SEC_TICKERS_EXCHANGE, timeout: int = 60) -> pd.DataFrame:
    """The raw SEC map as a frame [cik, name, ticker, exchange]. No filtering."""
    request = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    payload = json.loads(body.decode("utf-8"))
    frame = pd.DataFrame(payload["data"], columns=payload["fields"])
    if frame.empty:
        raise RuntimeError(
            f"{url} parsed to zero rows. Treat this as a failure, not an empty market: "
            "the SEC map is never empty, so an empty parse means the response changed shape."
        )
    return frame


def build_universe(url: str = SEC_TICKERS_EXCHANGE) -> pd.DataFrame:
    """Candidate tickers: US-listed, plain common-stock symbols, one row per ticker.

    Returns [ticker, cik, name, exchange_sec]. Instrument-type exclusions (ETFs, funds) cannot be
    applied here — the SEC map does not carry the distinction — so `refine_universe` applies them
    once the price fetch has reported what each symbol actually is.
    """
    raw = fetch_sec_exchange_map(url)
    frame = raw.rename(columns={"exchange": "exchange_sec"}).copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()

    frame = frame[frame["exchange_sec"].isin(KEEP_EXCHANGES)]
    frame = frame[frame["ticker"].str.fullmatch(SYMBOL_RE)]
    # One CIK can carry several tickers (share classes); one ticker should carry one CIK.
    frame = frame.drop_duplicates(subset="ticker").sort_values("ticker").reset_index(drop=True)

    if frame.empty:
        raise RuntimeError("universe filtered to zero tickers; the source format likely changed")
    return frame[["ticker", "cik", "name", "exchange_sec"]]


def refine_universe(universe: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Join the feed's instrument metadata onto the universe and drop what is not a US common
    stock: funds, indices, and anything not quoted in USD.

    `meta` is `Bars.meta` — [ticker, exchange, instrument_type, currency, bars, first, last].
    """
    merged = universe.merge(meta, on="ticker", how="inner")
    merged = merged[~merged["instrument_type"].isin(DROP_INSTRUMENT_TYPES)]
    merged = merged[merged["currency"] == "USD"]
    return merged.reset_index(drop=True)


def universe_report(raw_rows: int, universe: pd.DataFrame) -> str:
    """A plain account of what was dropped and why. Written to results/ so a later run can see
    whether a universe change came from the market or from this code."""
    lines = [
        f"SEC map rows:            {raw_rows}",
        f"after exchange filter + plain-symbol filter: {len(universe)}",
        "",
        "by exchange:",
        universe["exchange_sec"].value_counts().to_string(),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    universe = build_universe()
    raw = fetch_sec_exchange_map()
    print(universe_report(len(raw), universe))
    buffer = io.StringIO()
    universe.to_csv(buffer, index=False)
    print(buffer.getvalue()[:400])
