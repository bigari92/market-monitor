"""Render the daily desk page: arithmetic over money already committed.

Nothing on this page is a forecast, a ranking or a probability. Every line is a figure
derived from the broker's own statement or from a rule the owner wrote in plan.md, which
means no line here can be wrong in the way a signal can be wrong — it can only be stale,
and staleness is printed at the top.

Two clocks, deliberately different:

* **Money windows** key off `data_as_of()` — the newest statement — so a figure does not
  drift between syncs.
* **Calendar countdowns** key off today, because a filing deadline is a wall-clock fact
  and does not wait for a sync. Each is labelled with which clock it used.

Written to reports/latest.md plus a dated copy, so `git diff` is not needed to see what
changed — though this folder is deliberately not a git repository.

Run:  python scripts/monitor/digest.py
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

from . import ledger as L

ROOT = L.ROOT
REPORTS = ROOT / "reports"

# --- rules, quoted from plan.md so the page cites the owner's own numbers ----
SLEEVE_CAP_PCT = 0.33          # Rule 3: sleeve never exceeds 33% of cumulative contributions
SLEEVE_CAP_EUR = 3000.0        # Rule 3: and never EUR 3,000 whatever the percentage says
MAX_CONCURRENT_BELOW_1000 = 1  # Rule 2: one position at a time below a EUR 1,000 sleeve
MIN_POSITION_EUR = 125.0       # Rule 1: cost floor
CIRCUIT_BREAKER_PCT = 0.50     # Rule 4: halt if sleeve < 50% of sleeve contributions
SLEEVE_MONTHLY_EUR = 50.0      # plan.md: sleeve funded EUR 50/month
SLEEVE_ACTIVATED = "2026-09-04"

# Dated obligations and pre-committed experiments that already exist.
CALENDAR = [
    ("2026-12-03", "Paper strategy 'Mechanical Quality-Value v1' first quarterly rebalance",
     "Written 2026-09-03, 10 names bought 2026-09-04, abandon rule at 8 quarters. "
     "Nothing is scheduled to run it."),
    ("2026-12-04", "Next quarterly core deployment",
     "Quarterly cadence from the first purchase on 2026-09-04."),
    ("2026-12-31", "Tax netting boundary",
     "plan.md calls this 'THE TIMING THAT DOES MATTER' - which calendar year's netting "
     "pot a sale lands in, and therefore which losses it can offset."),
    ("2027-01-31", "Annual review and sweep",
     "Four outputs plan.md names: sleeve money-weighted return, the same capital in VWCE "
     "on the same dates, the gap, and the sweep of anything above EUR 1,000."),
    ("2027-05-01", "Ukrainian annual declaration for 2026",
     "One filing, 23% on the calendar-year net. tax-record.csv is currently a bare header."),
]

# Decisions plan.md has no rule for. A breach gets louder on its own; a MISSING RULE gets
# quieter, so it is given its own section with a days-open counter.
UNRULED = [
    ("2026-09-21", "AI-complex rotation trigger",
     "plan.md records the concentration as intentional and time-limited, with no date, no "
     "amount and no condition. Its own words: \"'Later' is not a rule.\""),
    ("2026-09-21", "ANET's sleeve category",
     "Reclassified 'long-term', which creates a third category the plan has no rules for. "
     "Counted INSIDE the trading sleeve below, because excluding the largest sleeve "
     "position would understate concentration by exactly that position."),
    ("2026-09-05", "Rule 4's denominator",
     "'50% of cumulative contributions into the sleeve' - planned (EUR 50/month) or "
     "capital actually routed? They differ by ~4x. Both are shown below; neither is "
     "authoritative until this is written down."),
    ("2026-10-18", "The 'AI complex' ticker list",
     "No written membership, so a theme-concentration percentage cannot be computed "
     "without the tool inventing the convention. Deliberately NOT shown below."),
]


def _pct(part: float, whole: float) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "n/a"


def _days_until(iso: str, today: dt.date) -> int:
    return (dt.date.fromisoformat(iso) - today).days


def build(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    asof = L.data_as_of()
    rec = L.reconcile()
    sl = L.sleeves()
    contrib = L.contributions_eur()
    nav = rec["nav_eur"]
    trading = sl["trading_eur"]
    stale = L.staleness_days(today)

    out: list[str] = []
    w = out.append

    # ---------------------------------------------------------------- header
    w(f"# Desk page - {asof}")
    w("")
    w(f"Data as of **{asof}** (newest Flex statement). Rendered {today.isoformat()}.")
    if stale > 1:
        w("")
        w(f"> **STALE: {stale} business days since the last statement.** Every figure "
          f"below is from {asof}. Run `python scripts/daily_sync.py`.")
    recon = ("reconciles" if rec["ok"] else "**DOES NOT RECONCILE**")
    w("")
    w(f"Broker reconciliation: {recon} - {rec['position_count']} positions worth "
      f"EUR {rec['positions_eur']:,.2f} + EUR {rec['implied_cash_eur']:,.2f} cash "
      f"= EUR {nav:,.2f}, the statement's own endingValue. No figure on this page comes "
      f"from a hand-maintained file.")
    w("")

    # ---------------------------------------------------------------- limits
    w("## Limits")
    w("")
    cap_eur = contrib * SLEEVE_CAP_PCT
    over = trading - cap_eur
    w(f"| | actual | rule | |")
    w(f"|---|---|---|---|")
    w(f"| Trading sleeve | EUR {trading:,.2f} | <= EUR {cap_eur:,.2f} "
      f"({SLEEVE_CAP_PCT:.0%} of EUR {contrib:,.2f} contributed) | "
      f"{'**OVER by EUR %.2f**' % over if over > 0 else 'ok'} |")
    w(f"| Sleeve as % of contributions | {_pct(trading, contrib)} | <= 33% | "
      f"{'**breach**' if trading > cap_eur else 'ok'} |")
    w(f"| Sleeve as % of pool | {_pct(trading, nav)} | - | context |")
    w(f"| Sleeve absolute | EUR {trading:,.2f} | <= EUR {SLEEVE_CAP_EUR:,.0f} | "
      f"{'**breach**' if trading > SLEEVE_CAP_EUR else 'ok'} |")
    w(f"| Core (VWCE) | EUR {sl['core_eur']:,.2f} | - | "
      f"{_pct(sl['core_eur'], nav)} of pool |")
    w(f"| Cash | EUR {rec['implied_cash_eur']:,.2f} | - | "
      f"below the EUR {MIN_POSITION_EUR:.0f} position floor |")
    w("")

    # Circuit breaker, both denominators, because the rule does not say which.
    months = max(1, ((dt.date.fromisoformat(asof) - dt.date.fromisoformat(SLEEVE_ACTIVATED)).days // 30) + 1)
    planned = months * SLEEVE_MONTHLY_EUR
    w("**Rule 4 circuit breaker** - halt trading for the calendar year if the sleeve "
      "falls below 50% of cumulative sleeve contributions. The denominator is undefined, "
      "so both readings are shown:")
    w("")
    for label, denom in (
        (f"planned (EUR {SLEEVE_MONTHLY_EUR:.0f}/month x {months} months)", planned),
        ("capital actually routed to the sleeve (contributions less the core AT COST, "
         "not at market value)", L.sleeve_capital_eur()),
    ):
        threshold = denom * CIRCUIT_BREAKER_PCT
        headroom = trading - threshold
        state = "ok" if headroom > 0 else "**HALT**"
        w(f"- {label}: denominator EUR {denom:,.2f}, halt below EUR {threshold:,.2f}, "
          f"headroom EUR {headroom:,.2f} - {state}")
    w("")

    # -------------------------------------------------------------- breaches
    w("## Breaches of rules you wrote")
    w("")
    jr = L.journal()
    open_j = L.open_journal_trades()
    n_pos = len(sl["trading"])
    no_stop = [r for r in jr if not (r.get("stop_level") or "").strip()]
    no_thesis = [r for r in jr if not (r.get("thesis") or "").strip()]
    no_inval = [r for r in jr if not (r.get("invalidation") or "").strip()]
    # Rule 1 is a constraint on the position AT ENTRY — a cost floor, derived from the
    # round-trip commission as a share of the position. A position that has since FALLEN
    # below EUR 125 has not breached it; testing current value against an entry rule
    # manufactures breaches and hides the real ones. So: cost basis, not market value.
    small = []
    for r in sl["trading"]:
        basis = L.cost_basis_eur(r)
        if basis is not None and basis < MIN_POSITION_EUR:
            small.append((r["symbol"], basis))

    w("| rule | state |")
    w("|---|---|")
    w(f"| Rule 2 - one position at a time below a EUR 1,000 sleeve | "
      f"**{n_pos} open** against {MAX_CONCURRENT_BELOW_1000} permitted |")
    w(f"| Rule 5 - written thesis before entry | "
      f"{len(jr) - len(no_thesis)}/{len(jr)} filled"
      f"{' - **' + str(len(no_thesis)) + ' missing**' if no_thesis else ' - ok'} |")
    w(f"| Rule 5 - written invalidation before entry | "
      f"{len(jr) - len(no_inval)}/{len(jr)} filled"
      f"{' - **' + str(len(no_inval)) + ' missing**' if no_inval else ' - ok'} |")
    w(f"| A stop level on each position | "
      f"**{len(jr) - len(no_stop)}/{len(jr)}** - "
      f"{len(no_stop)} trades carry no stop |")
    if small:
        detail = ", ".join(f"{sym} EUR {val:,.0f}" for sym, val in sorted(small, key=lambda x: x[1]))
        state = f"**{len(small)} of {len(sl['trading'])} opened below the floor** - {detail}"
    else:
        state = "ok"
    w(f"| Rule 1 - minimum position EUR {MIN_POSITION_EUR:.0f} **at entry** "
      f"(cost basis, current FX) | {state} |")
    w("")
    w("Thesis and invalidation being complete is worth stating plainly: the discipline "
      "that is usually missing is present here. What is missing is the stop.")
    w("")

    # ---------------------------------------------------------------- unruled
    w("## Unruled - decisions with no rule yet")
    w("")
    w("| opened | days | question |")
    w("|---|---|---|")
    for opened, title, note in UNRULED:
        w(f"| {opened} | {(today - dt.date.fromisoformat(opened)).days} | "
          f"**{title}** - {note} |")
    w("")

    # ------------------------------------------------------------------ exits
    w("## Distance to your own exits")
    w("")
    w("Targets are the owner's written `target_level` from trade-journal.csv, against the "
      "statement's mark price. A blank target is a position with no written exit.")
    w("")
    targets = {}
    for r in jr:
        t = (r.get("target_level") or "").strip()
        if t and not (r.get("date_exit") or "").strip():
            try:
                targets[r["instrument"]] = float(t)
            except ValueError:
                pass
    # The mark and the target are in the POSITION's currency; the value is in EUR. Both
    # currencies on one row is how a page like this ends up comparing dollars to euros,
    # so the currency is named in its own column and the two are never mixed in a sum.
    w("| symbol | value EUR | mark | target | ccy | distance | unrealized |")
    w("|---|---|---|---|---|---|---|")
    for r in sorted(sl["trading"], key=lambda x: -L.position_value_eur(x)):
        mark = float(r["mark_price"]) if r["mark_price"] else None
        tgt = targets.get(r["symbol"])
        if mark and tgt:
            dist = f"{100.0 * (tgt - mark) / mark:+.1f}%"
            tgt_s = f"{tgt:g}"
        else:
            dist, tgt_s = "**no written exit**", "-"
        unreal = L._num(r["unrealized_pnl"])
        unreal_s = f"{unreal:+,.2f}" if unreal is not None else "-"
        w(f"| {r['symbol']} | {L.position_value_eur(r):,.2f} | {mark:g} | {tgt_s} | "
          f"{r['currency']} | {dist} | {unreal_s} |")
    w("")

    # --------------------------------------------------------------- calendar
    w("## Calendar")
    w("")
    w("Counted from today, not from the statement date - a deadline does not wait for a sync.")
    w("")
    w("| date | in | what |")
    w("|---|---|---|")
    for iso, title, note in CALENDAR:
        d = _days_until(iso, today)
        when = f"{d} days" if d >= 0 else f"**{-d} days ago**"
        w(f"| {iso} | {when} | **{title}** - {note} |")
    w("")

    # ------------------------------------------------------------------ money
    w("## Money")
    w("")
    pnl = nav - contrib
    w(f"- Contributed to date: **EUR {contrib:,.2f}** "
      f"(cross-checks against plan.md and funding-log.csv)")
    w(f"- Pool value: **EUR {nav:,.2f}** (broker endingValue)")
    w(f"- Difference: **EUR {pnl:+,.2f}** ({_pct(abs(pnl), contrib)} of contributions)")
    w("")
    w("> This difference is **not** a return. It ignores the timing of each contribution, "
      "and the funding rail cost ~3.4% before the money arrived. The money-weighted "
      "figure against VWCE and XDEM.DE on the same cashflow dates - the four outputs "
      "plan.md's 31 January rule actually names - needs a price series and is the next "
      "piece to build.")
    w("")
    w("---")
    w("")
    w(f"Generated by `scripts/monitor/digest.py` from data_as_of {asof}. "
      f"Positions, NAV and FX come from the IBKR Flex statements; rules and targets from "
      f"plan.md and trade-journal.csv. No forecast, no ranking, no probability.")
    w("")
    return "\n".join(out)


def main() -> int:
    try:
        page = build()
    except L.LedgerError as exc:
        print(f"REFUSING to render a page on bad data:\n  {exc}", file=sys.stderr)
        return 2
    REPORTS.mkdir(parents=True, exist_ok=True)
    latest = REPORTS / "latest.md"
    dated = REPORTS / f"desk-{L.data_as_of()}.md"
    for path in (latest, dated):
        path.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {latest.relative_to(ROOT)} and {dated.relative_to(ROOT)} "
          f"({len(page):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
