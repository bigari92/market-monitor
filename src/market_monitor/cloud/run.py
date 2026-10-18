"""The entry point: one dated run, start to finish.

    python -m market_monitor.cloud.run track          # the run that produces the record
    python -m market_monitor.cloud.run track --dry-run  # score and report, write nothing
    python -m market_monitor.cloud.run probe          # re-measure the feed
    python -m market_monitor.cloud.run universe       # the universe funnel alone

`data_as_of` is never a command-line argument and never `today()`. It is the last completed
session present in the panel, discovered from the data. On a Sunday that is Friday's close; the
distinction is not cosmetic, because a ranking stamped with the wrong date cannot be reproduced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import factors as F
from . import prices, signal, tracker, universe
from .feeds import FeedError, get_feed

DEFAULT_FEED = "yahoo_chart"
DEFAULT_YEARS = 5
RESULTS = Path(__file__).resolve().parents[3] / "results"


def _data_as_of(bars) -> str:
    """The panel's last completed session. The one honest answer to 'as of when'."""
    return pd.Timestamp(bars.close.index.max()).strftime("%Y-%m-%d")


def _load(feed_name: str, years: int, refresh: bool, limit: int | None):
    uni = universe.build_universe()
    tickers = uni["ticker"].tolist()
    if limit:
        tickers = tickers[:limit]
        print(f"NOTE: limited to the first {limit} tickers; this is a smoke test, not a run",
              flush=True)

    feed = get_feed(feed_name)
    # The cache key needs an as-of date, but the as-of date comes from the panel. Resolve by
    # probing the cache for the most recent panel this feed has written, and falling back to a
    # fetch when there is none.
    cached = prices.cached_as_of_dates(feed_name)
    if cached and not refresh:
        bars, stats = prices.load_or_fetch(feed, tickers, cached[-1], years, refresh=False)
    else:
        bars = feed.fetch(tickers, years=years)
        stats = dict(getattr(feed, "stats", {}) or {})
        prices.write_panel(bars, _data_as_of(bars), feed.name, stats=stats)
        print(f"panel written: {bars.summary()}", flush=True)

    uni = universe.refine_universe(uni, bars.meta)
    keep = [t for t in uni["ticker"] if t in bars.close.columns]
    return uni, bars, stats, keep


def cmd_track(args: argparse.Namespace) -> int:
    uni, bars, stats, keep = _load(args.feed, args.years, args.refresh, args.limit)
    as_of = _data_as_of(bars)
    prices.assert_fresh(bars, pd.Timestamp.utcnow(), max_staleness_days=args.max_staleness)

    close = bars.close[keep]
    adjclose = bars.adjclose[keep]
    volume = bars.volume[keep]

    coverage = F.coverage(close, as_of)
    print(f"as_of {as_of} | {coverage['scorable']} of {coverage['tickers_in_panel']} names "
          f"have {coverage['min_sessions']}+ sessions", flush=True)

    factor_frame = F.compute_factors(close, volume, as_of, adjclose=adjclose)
    diagnostics = {
        "coverage": coverage,
        "pct_of_52w_high_vs_max_dd_12m": signal.factor_diagnostics(factor_frame),
        "corporate_actions_in_panel": int(len(bars.events)),
        "feed": stats,
    }

    try:
        result = tracker.run(factor_frame, data_as_of=as_of, feed_name=args.feed,
                             panel_stats={"tickers": int(close.shape[1]),
                                          "sessions": int(close.shape[0])},
                             dry_run=args.dry_run)
    except signal.RefusedToRank as exc:
        # A refusal is a result and gets written down, per CLOUD-RULES.md §6.
        verdict = (f"# Run refused — {as_of}\n\n"
                   f"The cross-section was too thin to rank:\n\n> {exc}\n\n"
                   f"Diagnostics:\n\n```json\n{json.dumps(diagnostics, indent=2)}\n```\n")
        (RESULTS / "tracking").mkdir(parents=True, exist_ok=True)
        (RESULTS / "tracking" / "latest_run.md").write_text(verdict, encoding="utf-8")
        print(f"REFUSED: {exc}", flush=True)
        return 3

    report = tracker.render_report(result, diagnostics)
    if not args.dry_run:
        (RESULTS / "tracking").mkdir(parents=True, exist_ok=True)
        (RESULTS / "tracking" / "latest_run.md").write_text(report, encoding="utf-8")
    print("", flush=True)
    print(report, flush=True)
    print("", flush=True)
    print(f"run_id {result.run_id} | entered {len(result.buys)} | held {len(result.holds)} "
          f"| exited {len(result.exits)}"
          + ("  [DRY RUN — nothing written]" if args.dry_run else ""), flush=True)
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Re-measure the feed. The committed measurement is results/price_feed_probe.md."""
    uni = universe.build_universe()
    feed = get_feed(args.feed)
    sample = uni["ticker"].tolist()[:args.limit or 300]
    try:
        bars = feed.fetch(sample, years=args.years)
    except FeedError as exc:
        print(f"FEED FAILED: {type(exc).__name__}: {exc}", flush=True)
        print(json.dumps(getattr(feed, "stats", {}), indent=2, default=str), flush=True)
        return 2
    print(json.dumps(feed.stats, indent=2, default=str), flush=True)
    print(bars.summary(), flush=True)
    return 0


def cmd_universe(args: argparse.Namespace) -> int:
    raw = universe.fetch_sec_exchange_map()
    uni = universe.build_universe()
    print(universe.universe_report(len(raw), uni), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="market_monitor.cloud.run",
                                     description="Market tracker: ranks and refuses.")
    parser.add_argument("--feed", default=DEFAULT_FEED)
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS)
    parser.add_argument("--limit", type=int, default=None,
                        help="smoke-test only: cap the ticker count")
    sub = parser.add_subparsers(dest="command", required=True)

    track = sub.add_parser("track", help="score, diff against the record, append")
    track.add_argument("--dry-run", action="store_true")
    track.add_argument("--refresh", action="store_true", help="re-fetch rather than use cache")
    track.add_argument("--max-staleness", type=int, default=7)
    track.set_defaults(func=cmd_track)

    probe = sub.add_parser("probe", help="re-measure the feed")
    probe.set_defaults(func=cmd_probe, refresh=True)

    uni = sub.add_parser("universe", help="the universe funnel")
    uni.set_defaults(func=cmd_universe, refresh=False)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FeedError as exc:
        print(f"FEED FAILED: {type(exc).__name__}: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
