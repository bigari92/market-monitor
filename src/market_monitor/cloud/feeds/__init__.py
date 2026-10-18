"""Price feeds, behind one interface, so the provider is a decision and not an assumption.

The Sept-2026 pipeline hard-coded yfinance and inherited two of its defects: `auto_adjust=True`
left corporate actions invisible (RECOVERY.md defect 2), and a single rate-limited IP could end a
run with nothing to show. Both are provider properties, so the provider belongs behind a seam.

Two failure modes are raised, never retried-around, because each is the exact way an unwatched
cloud session burns its budget and commits nothing:

- `FeedEmptyError` — the feed answered but carried no rows. Stooq's documented failure mode is an
  empty body with a 200, not an error, so "it returned" is not evidence that it returned data.
- `FeedThrottledError` — the feed is rate-limiting. A session that retries through a throttle
  spends credit to learn nothing. It stops instead, and what it already cached stays cached.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd


class FeedError(RuntimeError):
    """Base for feed failures that must end a run rather than be retried through."""


class FeedEmptyError(FeedError):
    """The feed answered without data. Never let this pass as a successful fetch."""


class FeedThrottledError(FeedError):
    """The feed is rate-limiting this IP. Stop; do not spend the budget on retries."""


@dataclass(frozen=True)
class Bars:
    """A price panel, with corporate actions kept visible rather than folded into the prices.

    `close` and `adjclose` are both carried on purpose. A factor computed on `adjclose` cannot
    distinguish a 30% fall from a 30% dividend; one computed on `close` alone mis-reads a split as
    a crash. Keeping both, plus `events`, is what makes the difference auditable.

    close    : wide, dates x tickers. Split-adjusted, dividends NOT removed.
    adjclose : wide, dates x tickers. Split- and dividend-adjusted (total return).
    volume   : wide, dates x tickers. Share volume, split-adjusted to match `close`.
    events   : long [ticker, date, kind, value]; kind in {"split", "dividend"}.
    meta     : one row per ticker [ticker, exchange, instrument_type, currency, bars, first, last].
    high/low : wide, split-adjusted daily extremes. Needed only by the spread estimators in
               `cost.py`, which reconstruct an effective bid-ask spread from the daily range
               because no free feed carries quotes. None on a panel fetched before they existed.
    """

    close: pd.DataFrame
    adjclose: pd.DataFrame
    volume: pd.DataFrame
    events: pd.DataFrame
    meta: pd.DataFrame
    # Optional, and optional on purpose: panels cached before the cost model existed have no
    # high/low, and a missing pair must degrade to "no spread estimate" rather than breaking a
    # ranking run. `cost.require_high_low` is what refuses when an estimator actually needs them.
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None

    def __post_init__(self) -> None:
        if self.close.empty or self.close.shape[1] == 0:
            raise FeedEmptyError(
                "a feed produced a Bars with no columns; this is the silent-zero-rows failure "
                "the feed layer exists to make loud"
            )

    @property
    def tickers(self) -> list[str]:
        return list(self.close.columns)

    def summary(self) -> str:
        return (f"{self.close.shape[1]} tickers x {self.close.shape[0]} sessions "
                f"[{self.close.index.min():%Y-%m-%d}..{self.close.index.max():%Y-%m-%d}], "
                f"{len(self.events)} corporate actions")


@runtime_checkable
class PriceFeed(Protocol):
    """What the pipeline needs from any price source, free or paid."""

    name: str

    def fetch(self, tickers: list[str], years: int) -> Bars:
        """Daily bars for `tickers` covering roughly `years` back from today.

        Must raise rather than return a partial panel disguised as a whole one. A feed that
        cannot serve a ticker omits its column; a feed that cannot serve the *request* raises.
        """
        ...


def get_feed(name: str, **kwargs) -> PriceFeed:
    """Resolve a feed by name. Imports lazily so a missing optional dependency or an absent API
    key only breaks the feed that needs it, not the whole pipeline."""
    if name == "yahoo_chart":
        from .yahoo_chart import YahooChartFeed

        return YahooChartFeed(**kwargs)
    if name == "sharadar":
        from .sharadar import SharadarFeed

        return SharadarFeed(**kwargs)
    raise ValueError(
        f"unknown feed {name!r}; known feeds: 'yahoo_chart' (free, unlicensed, measured in "
        "results/price_feed_probe.md), 'sharadar' (paid, survivorship-bias-free)"
    )
