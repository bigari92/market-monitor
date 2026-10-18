"""Invariants the desk page depends on. Exits non-zero when one breaks.

No pytest here on purpose: this folder is not a repository and has no test harness, while
scripts/daily_sync.py already establishes the house pattern — run the steps, fail loudly,
exit non-zero so a scheduled task cannot report success on bad data. This file is that
pattern applied to the numbers rather than to the fetch.

Each check is a thing that, if it silently broke, would make the page confidently wrong.

Run:  python scripts/monitor/selfcheck.py
"""
from __future__ import annotations

import pathlib
import sys

from . import ledger as L

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


@check("positions + implied cash equal the broker's own NAV")
def _reconciles():
    r = L.reconcile()
    if not r["ok"]:
        return (f"implied cash is EUR {r['implied_cash_eur']:,.2f} — negative means a "
                f"position is missing, mispriced or double-counted")
    return None


@check("implied cash is not absurd (< NAV, so positions are not being dropped)")
def _cash_sane():
    r = L.reconcile()
    if r["implied_cash_eur"] > r["nav_eur"] * 0.9:
        return (f"cash is EUR {r['implied_cash_eur']:,.2f} of a EUR {r['nav_eur']:,.2f} "
                f"pool — the position snapshot is probably empty or stale")
    return None


@check("contributions cross-check against plan.md's EUR 600 deposited")
def _contributions():
    total = L.contributions_eur()
    # Not pinned to exactly 600: it grows with every deposit. What is checked is that it
    # has not silently changed by a factor, which is what a currency mix-up looks like.
    if not 550.0 <= total <= 20_000.0:
        return (f"contributions computed as EUR {total:,.2f}. plan.md and funding-log.csv "
                f"independently record EUR 600 deposited as of 2026-10-16. A figure far "
                f"from that usually means USD rows were summed with EUR ones.")
    return None


@check("the NAV series is single-currency after the documented switch")
def _single_currency():
    try:
        rows = L.nav_series()
    except L.LedgerError as exc:
        return str(exc)
    bad = {r["currency"] for r in rows} - {L.BASE_CCY}
    if bad:
        return f"NAV series contains {sorted(bad)} as well as {L.BASE_CCY}"
    return None


@check("every position carries a base-currency value")
def _fx_complete():
    missing = [
        r["symbol"] for r in L.positions()
        if L._num(r.get("position_value_base")) is None
    ]
    if missing:
        return (f"no base-currency value for {', '.join(missing)} — exposure and "
                f"concentration cannot be computed, so the page must not claim them")
    return None


@check("the statement is not stale")
def _fresh():
    days = L.staleness_days()
    if days > 3:
        return (f"{days} business days since the newest statement "
                f"({L.data_as_of()}) — run scripts/daily_sync.py")
    return None


@check("no hand-maintained file is being read as a source")
def _no_handmade():
    """holdings.json was wrong three ways on 2026-10-18 while looking authoritative.

    Delegated to market_monitor.codeaudit, which distinguishes a string literal in
    running code from the same words in a docstring. The first version of this check was
    a text search and failed on ledger.py's own docstring, which names the file precisely
    to explain why it is not used.
    """
    from market_monitor import codeaudit

    here = pathlib.Path(__file__).resolve().parent
    offenders = codeaudit.scan(here.glob("*.py"), "holdings.json",
                               exclude_names={"selfcheck.py"})
    if offenders:
        return (f"holdings.json reaches running code at {', '.join(offenders)}. It is "
                f"hand-maintained and was stale and wrong on 2026-10-18: five positions "
                f"listed against seven open, ANET at 0.5 after averaging to 0.6, MXCT "
                f"and NBIS missing entirely.")
    return None


def main() -> int:
    print(f"self-check against data_as_of {L.data_as_of()}")
    failures = []
    for name, fn in CHECKS:
        try:
            problem = fn()
        except Exception as exc:                      # noqa: BLE001
            problem = f"{type(exc).__name__}: {exc}"
        if problem:
            failures.append((name, problem))
            print(f"  FAIL  {name}\n        {problem}")
        else:
            print(f"  ok    {name}")
    if failures:
        print(f"\n{len(failures)} of {len(CHECKS)} checks failed. The desk page should "
              f"not be trusted until these are resolved.")
        return 1
    print(f"\nall {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
