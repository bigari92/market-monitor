"""The price panel on disk: fetch once, score many times.

A cloud session's budget is spent on wall-clock, and the sweep is the expensive part. Caching it
to parquet under `data/` turns a 4-minute fetch into a 2-second read, so the scoring step — which
is the part worth iterating on — stops paying for the fetch step. `data/` is gitignored
(.gitignore explains why: a full panel is hundreds of MB and GitHub rejects it), so the cache is
a local convenience and never an artefact. What gets committed is the *ranking*, which is small.

The cache is keyed by feed name and the as-of date. It is never partially overwritten: a sweep
that ends in `FeedThrottledError` writes nothing under that key, so a later read cannot silently
pick up a half-market panel and rank it as though it were the whole market.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .feeds import Bars, FeedEmptyError, PriceFeed

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

_WIDE = ("close", "adjclose", "volume")


def cache_dir(as_of: str, feed_name: str, root: Path | None = None) -> Path:
    return (root or DATA_DIR) / "panels" / f"{feed_name}_{as_of}"


def cached_as_of_dates(feed_name: str, root: Path | None = None) -> list[str]:
    """As-of dates this feed has cached, oldest first.

    Parsed by stripping the known feed prefix, not by splitting on the first underscore: feed
    names contain underscores ("yahoo_chart"), and splitting on the first one yields the
    cache-missing, cache-duplicating key "chart_2026-10-16".
    """
    panels = (root or DATA_DIR) / "panels"
    if not panels.is_dir():
        return []
    prefix = f"{feed_name}_"
    found = [p.name[len(prefix):] for p in panels.iterdir()
             if p.is_dir() and p.name.startswith(prefix) and not p.name.endswith(".partial")]
    return sorted(found)


def write_panel(bars: Bars, as_of: str, feed_name: str, root: Path | None = None,
                stats: dict | None = None) -> Path:
    """Write a complete panel. Writes to a temporary sibling then renames, so an interrupted
    write cannot leave a readable-but-truncated panel behind."""
    target = cache_dir(as_of, feed_name, root)
    staging = target.with_name(target.name + ".partial")
    if staging.exists():
        for stale in staging.iterdir():
            stale.unlink()
    staging.mkdir(parents=True, exist_ok=True)

    for name in _WIDE:
        getattr(bars, name).to_parquet(staging / f"{name}.parquet")
    bars.events.to_parquet(staging / "events.parquet")
    bars.meta.to_parquet(staging / "meta.parquet")
    (staging / "fetch_stats.json").write_text(
        json.dumps(stats or {}, indent=2, default=str), encoding="utf-8")

    if target.exists():
        for stale in target.iterdir():
            stale.unlink()
        target.rmdir()
    staging.rename(target)
    return target


def read_panel(as_of: str, feed_name: str, root: Path | None = None) -> Bars:
    source = cache_dir(as_of, feed_name, root)
    if not source.is_dir():
        raise FileNotFoundError(f"no cached panel at {source}")
    frames = {name: pd.read_parquet(source / f"{name}.parquet") for name in _WIDE}
    return Bars(events=pd.read_parquet(source / "events.parquet"),
                meta=pd.read_parquet(source / "meta.parquet"), **frames)


def load_or_fetch(feed: PriceFeed, tickers: list[str], as_of: str, years: int = 5,
                  root: Path | None = None, refresh: bool = False) -> tuple[Bars, dict]:
    """Read the cached panel for (feed, as_of) if present, otherwise sweep and cache it.

    Returns the panel and the fetch stats (empty when served from cache).
    """
    if not refresh:
        try:
            bars = read_panel(as_of, feed.name, root)
            print(f"panel from cache: {bars.summary()}", flush=True)
            return bars, {"source": "cache"}
        except FileNotFoundError:
            pass

    print(f"fetching {len(tickers)} tickers from {feed.name} ({years}y daily)...", flush=True)
    bars = feed.fetch(tickers, years=years)
    stats = dict(getattr(feed, "stats", {}) or {})
    where = write_panel(bars, as_of, feed.name, root, stats)
    print(f"panel written to {where}: {bars.summary()}", flush=True)
    return bars, stats


def coverage_report(bars: Bars, min_bars: int) -> pd.DataFrame:
    """How many names clear the bar-count the factor code needs.

    `factors.compute_factors` refuses to score a cross-section with fewer than 273 sessions of
    history, and silently returns NaN for the 3-year momentum term below 756. A name short of
    history is not an error; being unable to say how many there are would be.
    """
    counts = bars.close.notna().sum().rename("bars")
    frame = counts.to_frame()
    frame["scorable"] = frame["bars"] >= min_bars
    return frame.sort_values("bars")


def assert_fresh(bars: Bars, as_of: pd.Timestamp, max_staleness_days: int = 7) -> None:
    """Refuse a panel whose last session is too old to be ranked as current.

    The silent-stale-panel failure is the one that cannot be noticed from the output: a ranking
    computed on three-week-old prices looks exactly like a ranking computed on today's.
    """
    last = pd.Timestamp(bars.close.index.max()).tz_localize(None).normalize()
    # Both sides forced tz-naive: the panel index is naive and a caller passing
    # `Timestamp.utcnow()` is aware, which raises rather than comparing.
    reference = pd.Timestamp(as_of)
    if reference.tzinfo is not None:
        reference = reference.tz_convert(None)
    gap = (reference.normalize() - last).days
    if gap > max_staleness_days:
        raise FeedEmptyError(
            f"panel's last session is {last:%Y-%m-%d}, {gap} days before as_of "
            f"{pd.Timestamp(as_of):%Y-%m-%d} (limit {max_staleness_days}). Refusing to rank a "
            "stale panel: the output would be indistinguishable from a current one."
        )
