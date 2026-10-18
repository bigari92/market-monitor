"""The tracking state — the part that is actually the product.

A screen that prints today's top 25 and forgets is not a tool, it is a mood. What makes this
worth running is the record: what entered, what left, why, and how ranks moved. Three properties
make that record load-bearing:

**Append-only.** A run never rewrites a past row. A call made in March is still readable in
September exactly as it was made, together with the `signal_version` that made it and the
`data_as_of` it saw. Nothing retroactively improves.

**Point-in-time, so it is survivorship-bias-free going forward.** RECOVERY.md defect 1 — a
survivor-only universe — is fatal to the recovered backtest and cannot be fixed there, because
the delisted names are simply absent. It does not apply to what this accumulates: a name that is
listed and then collapses stays in `events.csv` with an exit reason. The forward record is the
one honest dataset this project will own. It is also, at the start, an empty one — the first run
has nothing to compare against and says so.

**Reproducible.** `data_as_of` is the last session in the panel, discovered from the data and
never `today()`. A re-run of the same as-of date against the same signal version must reproduce
the same ranking, and `tests/test_tracker_reproducible.py` checks that it does.

## The exit rules, and why none of them is a fitted number

The recovered research validated a **12-month hold on a monthly rebalance grid**. It contains no
exit logic whatsoever, so every rule here is new, and new rules are exactly where a session can
quietly invent a strategy. Two safeguards:

1. **A listing is a 12-month thesis, not a weekly opinion.** Exits fire on a structural break,
   never on rank noise. A name that drifts from rank 3 to rank 30 is still held.
2. **No exit threshold was chosen by looking at outcomes.** Each is either a constant the signal
   already had, or a natural zero:

| reason | trigger | where the number comes from |
|---|---|---|
| `GATE_FAIL_PRICE` | price < 5.0 | `signal.MIN_PRICE`, unchanged |
| `GATE_FAIL_LIQUIDITY` | ADV < 5,000,000 | `signal.MIN_ADV`, unchanged |
| `LEFT_VOL_GATE` | out of the top volatility quintile | `signal.VOL_GATE`, unchanged |
| `TREND_BREAK` | price below its 200-day average | zero crossing of `px_vs_ma200`, not a level |
| `RANK_DECAY` | rank falls past 2x TOP_N | a stated convention (50), declared below |
| `NO_LONGER_PRICED` | absent from the panel | delisting or a feed gap, distinguished |

`RANK_DECAY`'s buffer is the one judgement call in the file. It is set to `2 * TOP_N` as a
convention and is *not* to be tuned: CLOUD-RULES.md §5 forbids moving it to improve a result, and
`signal_version` does not cover it, so `runs.csv` records it per run instead.

**The horizon caveat, stated because it is real:** this tracker reviews more often than once a
year, while the signal's evidence is a 12-month holding period.
`recovered/horizon_test.py` asked what the screen says at 3 months and its *results* were never
recovered — only the script. So the exit rules are reasoned, not validated, and the honest
description of them is "a conservative break-detector on an annual thesis", not "a validated
exit model". Anything the tracker accumulates about them is evidence to be read later, not a
claim being made now.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import signal as sig

TRACKING_DIR = Path(__file__).resolve().parents[3] / "results" / "tracking"

RUNS_CSV = "runs.csv"
LISTINGS_CSV = "listings.csv"
EVENTS_CSV = "events.csv"

# The rank a listed name must fall past before rank decay alone retires it. A convention, and
# deliberately loose: see the module docstring on why it is not tuned.
RANK_DECAY_MULTIPLE = 2

# Factor values carried into the record for every listed name, so a past call can be read back
# without the panel that produced it.
CARRIED_FACTORS = ("price", "pct_of_52w_high", "max_dd_12m", "mom_12_1", "mom_36",
                   "mom_accel", "days_above_ma200", "px_vs_ma200", "ma50_vs_ma200",
                   "vol_12m", "skew_12m", "adv_3m_usd")

EXIT_REASONS = {
    "GATE_FAIL_PRICE": "price fell below the minimum the signal requires",
    "GATE_FAIL_LIQUIDITY": "dollar volume fell below the liquidity floor",
    "LEFT_VOL_GATE": "no longer in the volatility cohort the asymmetry result applies to",
    "TREND_BREAK": "price closed below its 200-day average",
    "RANK_DECAY": "rank decayed past the carry buffer",
    "NO_LONGER_PRICED": "absent from the panel entirely (delisted, renamed, or a feed gap)",
}


@dataclass(frozen=True)
class RunResult:
    """What one run produced. Returned so a caller can report without re-reading the files."""
    run_id: str
    data_as_of: str
    signal_version: str
    buys: pd.DataFrame
    exits: pd.DataFrame
    holds: pd.DataFrame
    watchlist: pd.DataFrame
    funnel: dict
    is_first_run: bool


def _read(path: Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates or [])


def _append(path: Path, frame: pd.DataFrame) -> None:
    """Append rows, writing the header only when the file is new. Never rewrites a past row."""
    if frame.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, mode="a" if path.is_file() else "w",
                 header=not path.is_file(), index=False)


def load_state(tracking_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    base = tracking_dir or TRACKING_DIR
    return {
        "runs": _read(base / RUNS_CSV),
        "listings": _read(base / LISTINGS_CSV),
        "events": _read(base / EVENTS_CSV),
    }


def current_watchlist(listings: pd.DataFrame) -> pd.DataFrame:
    """The names carried out of the most recent run, i.e. what this run inherits."""
    if listings.empty:
        return pd.DataFrame()
    last_run = listings["run_id"].iloc[-1]
    return listings[listings["run_id"] == last_run].copy()


def classify_exit(previous: pd.Series, ranked: pd.DataFrame, top_n: int,
                  universe: pd.DataFrame | None = None) -> tuple[str, str] | None:
    """Why a previously-listed name should leave, or None to keep holding it.

    `previous` is that name's row from the last run, so a rule can compare state against state.
    `ranked` is the scored, gated cross-section. `universe` is the *ungated* factor frame, and
    passing it is what lets the reason be accurate rather than merely true.

    Rules are evaluated structural-break-first, so the recorded reason is the most informative
    one: a name that broke trend *and* decayed in rank is recorded as a trend break.

    ## Why `universe` is needed: the reason code was lying

    A 24-month replay reported `NO_LONGER_PRICED` 0-6 times a month over a panel containing only
    names that survived to today, where a genuine delisting is nearly impossible. Meanwhile
    `LEFT_VOL_GATE` never fired once. Both had the same cause: `apply_gates` removes a name
    before `classify_exit` ever sees it, so absence from `ranked` was being read as absence from
    the market.

    They are entirely different signals to act on. "Delisted" is terminal; "no longer in the
    volatility cohort the asymmetry result was measured on" means the name has calmed down and
    the evidence simply no longer covers it. Reporting the second as the first would make the
    exit log useless for the one thing it exists for.

    With `universe` in hand the absence is attributable: not in the panel at all, present but
    below a hard floor, or present and solvent but outside the gate.

    ## Why TREND_BREAK needs the previous row

    The first live run ranked TER at #1 with `px_vs_ma200` at -0.057 — already below its 200-day
    average, because `days_above_ma200` (0.99, one of the eight weighted terms) measures the
    *year*, while `px_vs_ma200` (not a weighted term at all) measures *today*. A rule that fired
    on the level alone would therefore have entered TER and exited it one run later, which is not
    a signal disagreeing with itself so much as a badly posed rule: nothing *broke*.

    A break is a transition. TREND_BREAK fires only when the name was at or above its 200-day
    average at the previous run and is below it now. A name that was already below when listed
    has no trend to break, and its deterioration is RANK_DECAY's business.

    The alternative — filtering such names out at entry — was rejected: it would add a criterion
    the composite does not have, and CLOUD-RULES.md §5 does not allow a session to change the
    signal. Fixing the new exit rule is in scope; changing the validated entry rule is not.
    """
    ticker = previous["ticker"]
    if ticker not in ranked.index:
        # Attribute the absence rather than assuming the worst reading of it.
        if universe is None or ticker not in universe.index:
            return "NO_LONGER_PRICED", "absent from the panel entirely"
        row = universe.loc[ticker]
        if pd.isna(row.get("price")) or row["price"] < sig.MIN_PRICE:
            return "GATE_FAIL_PRICE", f"price {row['price']:.2f} < {sig.MIN_PRICE}"
        if pd.isna(row.get("adv_3m_usd")) or row["adv_3m_usd"] < sig.MIN_ADV:
            return "GATE_FAIL_LIQUIDITY", (f"ADV {row['adv_3m_usd']:,.0f} < "
                                           f"{sig.MIN_ADV:,.0f}")
        return "LEFT_VOL_GATE", (
            f"12m volatility {row['vol_12m']:.2f} is outside the gate {sig.VOL_GATE}; still "
            "priced and liquid, but no longer in the cohort the asymmetry result covers")

    now = ranked.loc[ticker]
    if now["price"] < sig.MIN_PRICE:
        return "GATE_FAIL_PRICE", f"price {now['price']:.2f} < {sig.MIN_PRICE}"
    if now["adv_3m_usd"] < sig.MIN_ADV:
        return "GATE_FAIL_LIQUIDITY", f"ADV {now['adv_3m_usd']:,.0f} < {sig.MIN_ADV:,.0f}"

    was_above = previous.get("px_vs_ma200")
    was_above = True if pd.isna(was_above) else float(was_above) >= 0
    if was_above and now["px_vs_ma200"] < 0:
        return "TREND_BREAK", (f"price {100 * now['px_vs_ma200']:+.1f}% vs its 200-day average, "
                               f"having been above it at the previous run")

    buffer_rank = top_n * RANK_DECAY_MULTIPLE
    if now["rank"] > buffer_rank:
        return "RANK_DECAY", f"rank {int(now['rank'])} past the carry buffer of {buffer_rank}"
    return None


def _listing_rows(ranked: pd.DataFrame, tickers: list[str], run_id: str, data_as_of: str,
                  signal_version: str, first_seen: dict[str, str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        if ticker not in ranked.index:
            continue
        r = ranked.loc[ticker]
        row = {
            "run_id": run_id, "data_as_of": data_as_of, "signal_version": signal_version,
            "ticker": ticker, "rank": int(r["rank"]), "score": round(float(r["score"]), 4),
            "first_listed_as_of": first_seen.get(ticker, data_as_of),
            "reason": sig.why_it_ranks(r),
        }
        for factor in CARRIED_FACTORS:
            if factor in r.index:
                value = r[factor]
                row[factor] = None if pd.isna(value) else round(float(value), 6)
        rows.append(row)
    return pd.DataFrame(rows)


def run(factors: pd.DataFrame, data_as_of: str, feed_name: str,
        panel_stats: dict | None = None, top_n: int = sig.TOP_N,
        tracking_dir: Path | None = None, dry_run: bool = False) -> RunResult:
    """Score one cross-section, diff it against the previous run, and append the record.

    `factors` is the output of `factors.compute_factors`, indexed by ticker.
    `data_as_of` is the panel's last session — never today's date.
    """
    base = tracking_dir or TRACKING_DIR
    state = load_state(base)
    previous = current_watchlist(state["listings"])
    is_first_run = state["runs"].empty

    signal_version = sig.signal_version()
    ranked = sig.score(factors)          # raises RefusedToRank if the cross-section is too thin
    funnel = dict(ranked.attrs.get("funnel", {}))

    run_id = f"{data_as_of}_{signal_version}"

    # Where each name was last run, for the rank-movement column.
    if previous.empty:
        prior_rank: dict[str, int] = {}
        prior_score: dict[str, float] = {}
        first_seen: dict[str, str] = {}
        prior_rows: dict[str, pd.Series] = {}
    else:
        prior_rank = dict(zip(previous["ticker"], previous["rank"]))
        prior_score = dict(zip(previous["ticker"], previous["score"]))
        first_seen = dict(zip(previous["ticker"], previous["first_listed_as_of"]))
        prior_rows = {row["ticker"]: row for _, row in previous.iterrows()}

    held_before = list(prior_rank)
    top_now = list(ranked.index[:top_n])

    # --- the three decisions ------------------------------------------------
    exits: list[dict] = []
    holds: list[str] = []
    for ticker in held_before:
        # The previous row, so a break can be judged as a transition rather than a level.
        prior = prior_rows.get(ticker, pd.Series({"ticker": ticker}))
        verdict = classify_exit(prior, ranked, top_n, universe=factors)
        if verdict is None:
            holds.append(ticker)
            continue
        code, detail = verdict
        now_rank = int(ranked.loc[ticker, "rank"]) if ticker in ranked.index else None
        exits.append({
            "run_id": run_id, "data_as_of": data_as_of, "signal_version": signal_version,
            "ticker": ticker, "event": "EXIT", "reason_code": code,
            "reason": EXIT_REASONS[code], "detail": detail,
            "rank_prev": int(prior_rank[ticker]), "rank_now": now_rank,
            "score_prev": float(prior_score[ticker]),
            "score_now": round(float(ranked.loc[ticker, "score"]), 4)
            if ticker in ranked.index else None,
            "first_listed_as_of": first_seen.get(ticker),
        })

    entries = [t for t in top_now if t not in prior_rank]
    enter_rows = [{
        "run_id": run_id, "data_as_of": data_as_of, "signal_version": signal_version,
        "ticker": t, "event": "ENTER", "reason_code": "TOP_N",
        "reason": f"entered the top {top_n} of the gated cross-section",
        "detail": sig.why_it_ranks(ranked.loc[t]),
        "rank_prev": None, "rank_now": int(ranked.loc[t, "rank"]),
        "score_prev": None, "score_now": round(float(ranked.loc[t, "score"]), 4),
        "first_listed_as_of": data_as_of,
    } for t in entries]

    # The watchlist carried forward: everything still held, plus the new entries.
    carried = holds + [t for t in entries if t not in holds]
    for t in entries:
        first_seen[t] = data_as_of

    listings = _listing_rows(ranked, carried, run_id, data_as_of, signal_version, first_seen)
    if not listings.empty:
        listings["rank_prev"] = listings["ticker"].map(prior_rank).astype("Int64")
        listings["rank_change"] = listings["rank_prev"] - listings["rank"]
        listings["status"] = listings["ticker"].apply(
            lambda t: "ENTER" if t in entries else "HOLD")
        listings["runs_held"] = listings["ticker"].map(
            lambda t: int((state["listings"]["ticker"] == t).sum()) + 1
            if not state["listings"].empty else 1)

    events = pd.DataFrame(enter_rows + exits)
    run_row = pd.DataFrame([{
        "run_id": run_id,
        "run_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_as_of": data_as_of, "signal_version": signal_version, "feed": feed_name,
        "top_n": top_n, "rank_decay_buffer": top_n * RANK_DECAY_MULTIPLE,
        "universe_in": funnel.get("input"),
        "after_hard_filters": funnel.get("after_hard_filters"),
        "after_vol_gate": funnel.get("after_vol_gate"),
        "watchlist_size": len(carried), "entered": len(entries), "exited": len(exits),
        "held": len(holds),
        "panel_tickers": (panel_stats or {}).get("tickers"),
        "panel_sessions": (panel_stats or {}).get("sessions"),
        "is_first_run": is_first_run,
    }])

    buys = listings[listings["status"] == "ENTER"] if not listings.empty else pd.DataFrame()
    held = listings[listings["status"] == "HOLD"] if not listings.empty else pd.DataFrame()
    exit_frame = pd.DataFrame(exits)

    if not dry_run:
        _append(base / LISTINGS_CSV, listings)
        _append(base / EVENTS_CSV, events)
        _append(base / RUNS_CSV, run_row)
        (base / "signal_definition.json").write_text(
            json.dumps(sig.signal_definition(), indent=2), encoding="utf-8")

    for frame in (buys, held, exit_frame, listings):
        if not frame.empty:
            sig.assert_no_probability_columns(frame)

    return RunResult(run_id=run_id, data_as_of=data_as_of, signal_version=signal_version,
                     buys=buys, exits=exit_frame, holds=held, watchlist=listings,
                     funnel=funnel, is_first_run=is_first_run)


def render_report(result: RunResult, diagnostics: dict | None = None) -> str:
    """The human-readable run summary written to results/tracking/latest_run.md.

    Contains no probability and no performance figure, by construction — `signal.py` explains the
    measured reason for both.
    """
    lines = [
        f"# Run {result.run_id}",
        "",
        f"- **data_as_of:** {result.data_as_of} (the panel's last completed session, not today)",
        f"- **signal_version:** `{result.signal_version}` (price-only v4 composite)",
        f"- **universe funnel:** {result.funnel.get('input')} scorable → "
        f"{result.funnel.get('after_hard_filters')} after price/liquidity floors → "
        f"{result.funnel.get('after_vol_gate')} after the volatility gate",
        f"- **watchlist:** {len(result.watchlist)} names "
        f"({len(result.buys)} entered, {len(result.holds)} held, {len(result.exits)} exited)",
        "",
    ]
    if result.is_first_run:
        lines += [
            "> **First run.** There is no previous state to diff against, so every name is an",
            "> entry and no exit can fire. The tracking record starts here; its value is in the",
            "> second run and after.",
            "",
        ]

    lines += ["## BUY candidates", ""]
    if result.buys.empty:
        lines.append("_None entered this run._")
    else:
        lines.append("| rank | ticker | score | price | %52w high | max DD 12m | why it ranks |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, r in result.buys.sort_values("rank").iterrows():
            lines.append(
                f"| {int(r['rank'])} | **{r['ticker']}** | {r['score']:+.3f} | "
                f"{r['price']:.2f} | {r['pct_of_52w_high']:.3f} | "
                f"{r['max_dd_12m']:+.3f} | {r['reason']} |")
    lines.append("")

    lines += ["## SELL / EXIT signals", ""]
    if result.exits.empty:
        lines.append("_None. No listed name triggered an exit rule._")
    else:
        lines.append("| ticker | reason | detail | rank prev → now |")
        lines.append("|---|---|---|---|")
        for _, r in result.exits.iterrows():
            now = "—" if pd.isna(r.get("rank_now")) else int(r["rank_now"])
            lines.append(f"| **{r['ticker']}** | `{r['reason_code']}` | {r['detail']} | "
                         f"{int(r['rank_prev'])} → {now} |")
    lines.append("")

    lines += ["## Held", ""]
    if result.holds.empty:
        lines.append("_Nothing carried from a previous run._")
    else:
        lines.append("| rank | ticker | rank change | runs held | score |")
        lines.append("|---|---|---|---|---|")
        for _, r in result.holds.sort_values("rank").iterrows():
            change = "—" if pd.isna(r.get("rank_change")) else f"{int(r['rank_change']):+d}"
            lines.append(f"| {int(r['rank'])} | **{r['ticker']}** | {change} | "
                         f"{int(r['runs_held'])} | {r['score']:+.3f} |")
    lines.append("")

    if diagnostics:
        lines += ["## Diagnostics", "",
                  "```json", json.dumps(diagnostics, indent=2), "```", ""]

    lines += [
        "## What this is not",
        "",
        "No probability appears above, and none can: an isotonic calibrator fitted on one regime",
        "carried Brier 0.120 into another where it scored 0.189. No performance figure appears",
        "either. The published +37.8%/yr against +14.6% rests on roughly 7 effective annual",
        "observations (t ~ 2.64) over a survivor-only universe, and is not an expected return.",
        "",
        "The signal is a **loser-filter**: conditional on the volatility cohort, trend quality",
        "barely moves the up-tail (18.7% → 21.9%) and roughly halves the down-tail",
        "(48.3% → 23.4%). It ranks and it refuses. The owner decides.",
    ]
    return "\n".join(lines)
