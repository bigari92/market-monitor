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

# 20 years, not 5. The horizon test needs this depth to have any independent observations at all
# (results/horizon_test.md), and one cached panel serving every command beats two. It costs
# nothing in accuracy for `track`: the 2026-10-16 ranking is bit-identical on the 5-year and
# 20-year panels, which is the point-in-time property confirmed on real data rather than only in
# tests. Do NOT reach for `range=max` to go deeper -- see MAX_MEDIAN_GAP_DAYS in the Yahoo feed.
DEFAULT_YEARS = 20
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
    # Keyed by span as well as date, so a 5-year and a 20-year panel cannot be confused.
    cached = prices.cached_as_of_dates(feed_name, years=years)
    if cached and not refresh:
        bars, stats = prices.load_or_fetch(feed, tickers, cached[-1], years, refresh=False)
    else:
        bars = feed.fetch(tickers, years=years)
        stats = dict(getattr(feed, "stats", {}) or {})
        prices.write_panel(bars, prices.panel_key(_data_as_of(bars), years), feed.name,
                           stats=stats)
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


def cmd_replay(args: argparse.Namespace) -> int:
    """Run the tracker over past as-of dates from the cached panel, into a SEPARATE record.

    ## This is not a backtest, and the distinction is not pedantic

    It computes no forward return, reports no performance, and ranks no outcome. Its only
    purpose is mechanical: to show the exit rules firing on real price history rather than only
    on synthetic fixtures, and to produce a multi-run record a human can read.

    It could not be a backtest even if it tried, for the reason RECOVERY.md gives as defect 1:
    the universe is today's registrants, so every name in it survived to today. A performance
    figure computed here would be measuring that survival. The factors themselves are honest
    point-in-time (`test_point_in_time_a_later_bar_cannot_change_an_earlier_factor`), but a
    point-in-time factor over a survivor-only universe is still a biased sample.

    It writes to `results/replay/` and never touches `results/tracking/`, so the live record
    cannot be polluted by a replay.
    """
    uni, bars, stats, keep = _load(args.feed, args.years, args.refresh, args.limit)
    close, adjclose, volume = bars.close[keep], bars.adjclose[keep], bars.volume[keep]

    sessions = close.index
    # Monthly as-of dates, oldest first, each the last session on or before a month boundary.
    anchors: list[pd.Timestamp] = []
    cursor = sessions.max()
    for _ in range(args.months):
        anchors.append(cursor)
        earlier = sessions[sessions <= cursor - pd.DateOffset(months=1)]
        if len(earlier) == 0:
            break
        cursor = earlier.max()
    anchors = sorted(anchors)

    replay_dir = RESULTS / "replay"
    if replay_dir.exists():
        for stale in replay_dir.glob("*"):
            stale.unlink()

    rows = []
    for as_of in anchors:
        stamp = as_of.strftime("%Y-%m-%d")
        try:
            factor_frame = F.compute_factors(close.loc[:as_of], volume.loc[:as_of], as_of,
                                             adjclose=adjclose.loc[:as_of])
            result = tracker.run(factor_frame, data_as_of=stamp, feed_name=args.feed,
                                 tracking_dir=replay_dir)
        except signal.RefusedToRank as exc:
            print(f"{stamp}: REFUSED — {exc}", flush=True)
            continue
        exit_codes = result.exits["reason_code"].value_counts().to_dict() \
            if not result.exits.empty else {}
        rows.append({"as_of": stamp, "watchlist": len(result.watchlist),
                     "entered": len(result.buys), "held": len(result.holds),
                     "exited": len(result.exits), **exit_codes})
        print(f"{stamp}: watchlist {len(result.watchlist):3d} | entered {len(result.buys):2d} "
              f"| held {len(result.holds):2d} | exited {len(result.exits):2d} {exit_codes}",
              flush=True)

    summary = pd.DataFrame(rows).fillna(0)
    print("", flush=True)
    print(summary.to_string(index=False), flush=True)
    (replay_dir / "README.md").write_text(
        "# Replay — mechanical validation, NOT a backtest\n\n"
        f"Generated by `python -m market_monitor.cloud.run replay --months {args.months}`.\n\n"
        "Computes no forward return, reports no performance, ranks no outcome. It exists to show\n"
        "the exit rules firing on real price history instead of only on synthetic fixtures.\n\n"
        "It could not be a backtest: the universe is today's registrants, so every name in it\n"
        "survived to today (RECOVERY.md defect 1). The factors are honest point-in-time, but a\n"
        "point-in-time factor over a survivor-only universe is still a biased sample. Any\n"
        "performance number computed from these files would be measuring survival.\n\n"
        "The live record is `results/tracking/`. A replay never writes there.\n\n"
        "## Run-by-run\n\n```\n" + summary.to_string(index=False) + "\n```\n",
        encoding="utf-8")
    return 0


def cmd_horizon(args: argparse.Namespace) -> int:
    """Measure the signal's rank IC and tail behaviour at 3 and 12 months.

    Needs a long panel — the default 5 years leaves ~12 monthly rebalance dates once history and
    forward-return room are taken out, which cannot settle anything. Use `--years 20`.
    """
    from . import horizon as H

    uni, bars, stats, keep = _load(args.feed, args.years, args.refresh, args.limit)
    close, adjclose, volume = bars.close[keep], bars.adjclose[keep], bars.volume[keep]
    print(f"{len(keep)} names, {close.shape[0]} sessions from {close.index.min().date()}",
          flush=True)

    out = H.run(close, adjclose, volume)
    print(f"\npanel {out['panel_rows']:,} rows over {out['n_dates']} dates "
          f"({out['first_date']} .. {out['last_date']})", flush=True)
    print("\nbase rates (gated cohort):", flush=True)
    print(out["base_rates"].round(2).to_string(index=False), flush=True)
    print("\nrank IC:", flush=True)
    print(out["ic"].round(4).to_string(index=False), flush=True)

    selection = out["selection"]
    rows = []
    for label in ("3m", "12m"):
        rows.append({
            "horizon": label,
            "top_mean_%": 100 * selection[f"top_mean_{label}"].mean(),
            "cohort_mean_%": 100 * selection[f"cohort_mean_{label}"].mean(),
            "top_up50_%": 100 * selection[f"top_up50_{label}"].mean(),
            "cohort_up50_%": 100 * selection[f"cohort_up50_{label}"].mean(),
            "top_dn30_%": 100 * selection[f"top_dn30_{label}"].mean(),
            "cohort_dn30_%": 100 * selection[f"cohort_dn30_{label}"].mean(),
        })
    table = pd.DataFrame(rows)
    table["up_tail_lift_x"] = table["top_up50_%"] / table["cohort_up50_%"]
    table["dn_tail_cut_x"] = table["cohort_dn30_%"] / table["top_dn30_%"]
    print(f"\ntop-{out['top_n']} vs cohort:", flush=True)
    print(table.round(2).to_string(index=False), flush=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    selection.to_csv(RESULTS / "horizon_selection_by_date.csv", index=False)
    out["ic"].to_csv(RESULTS / "horizon_ic.csv", index=False)
    print(f"\nwrote {RESULTS / 'horizon_ic.csv'} and horizon_selection_by_date.csv", flush=True)
    print("The written verdict is results/horizon_test.md.", flush=True)
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

    replay = sub.add_parser(
        "replay", help="run past as-of dates into results/replay/ (mechanical check, NOT a backtest)")
    replay.add_argument("--months", type=int, default=12)
    replay.add_argument("--refresh", action="store_true")
    replay.set_defaults(func=cmd_replay)

    horizon_cmd = sub.add_parser(
        "horizon", help="rank IC and tail behaviour at 3m vs 12m (needs --years 20)")
    horizon_cmd.add_argument("--refresh", action="store_true")
    horizon_cmd.set_defaults(func=cmd_horizon)

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
