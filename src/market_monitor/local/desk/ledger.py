"""Readers over the ledger. Every number the desk page prints comes from here.

One rule governs this module: **no hand-maintained file is a source.** holdings.json was
stamped as_of 2026-10-08 and was wrong three ways by 2026-10-18 — five positions listed
against seven open, ANET at 0.5 after it had been averaged to 0.6, MXCT and NBIS missing
entirely — and every concentration figure computed from it inherited all three errors.
The sources here are the IBKR Flex statements, imported by scripts/import_flex.py, which
carry the broker's own NAV, positions and FX rates.

Two things this module refuses to do, because both produce a plausible wrong answer:

* **Mix currencies.** The account's base currency was USD on 2026-09-02 and EUR from
  2026-09-03. Summing `deposits_withdrawals` across that boundary adds dollars to euros
  and silently overstates contributions. `nav_series()` splits the boundary explicitly.
* **Use today's date.** Every window is anchored on the newest statement
  (`data_as_of()`), never on the clock, so a figure does not change between syncs and a
  stale sync is visible rather than invisible. Same rule as the Alcor feeds.
"""
from __future__ import annotations

import csv
import datetime as dt
import pathlib

from . import paths

ROOT = paths.personal_root()
DATA = ROOT / "data"

NAV_CSV = DATA / "ledger_nav.csv"
POSITIONS_CSV = DATA / "ledger_positions.csv"
TRADES_CSV = DATA / "ledger_trades.csv"
CASH_CSV = DATA / "ledger_cash.csv"
JOURNAL_CSV = ROOT / "trade-journal.csv"

# The documented base-currency change. Statements on or after this date report in EUR;
# the single earlier day reports in USD. Asserted rather than assumed: if a future
# statement arrives in a third currency, the loaders raise instead of quietly adding it.
BASE_CCY = "EUR"
BASE_CCY_FROM = "2026-09-03"
# What the pre-EUR day became after conversion, from the statement pair itself:
# 2026-09-02 ended at USD 34.77, and 2026-09-03 opened at EUR 30.00.
OPENING_EUR = 30.00
OPENING_DATE = "2026-09-02"

# The core sleeve is this instrument and nothing else; everything else is the trading
# sleeve. Taken from plan.md, where the owner recorded the choice on 2026-09-04.
CORE_SYMBOLS = {"VWCE"}


class LedgerError(RuntimeError):
    """Raised when the ledger cannot support a number, instead of returning a wrong one."""


def _rows(path: pathlib.Path) -> list[dict]:
    paths.require()          # names the folder, and says so plainly when it is absent
    if not path.exists():
        raise LedgerError(
            f"{path.name} is missing. Run scripts/daily_sync.py, or "
            f"scripts/import_flex.py over data/raw/, before reading the ledger."
        )
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(value: str | None) -> float | None:
    """Blank stays blank. A missing number must not become 0.0 and flatter a total."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- NAV

def nav_series() -> list[dict]:
    """Daily NAV in the base currency, newest last, with the USD day excluded.

    The excluded day is not dropped silently — `opening_eur()` carries it forward as the
    EUR opening balance, which is what it actually became.
    """
    out = []
    for r in _rows(NAV_CSV):
        ccy = r["currency"]
        if r["date"] < BASE_CCY_FROM:
            if ccy == BASE_CCY:
                raise LedgerError(
                    f"{r['date']} reports in {BASE_CCY} but predates the documented "
                    f"switch on {BASE_CCY_FROM}. Re-check BASE_CCY_FROM in this module."
                )
            continue
        if ccy != BASE_CCY:
            raise LedgerError(
                f"NAV row {r['date']} is in {ccy}, not {BASE_CCY}. The base currency "
                f"changed again; this module's arithmetic is no longer valid and must be "
                f"updated deliberately rather than coerced."
            )
        out.append(r)
    if not out:
        raise LedgerError("no NAV rows in the base currency")
    return sorted(out, key=lambda r: r["date"])


def data_as_of() -> str:
    """The newest statement date. Every window keys off this, never off today()."""
    return nav_series()[-1]["date"]


def staleness_days(today: dt.date | None = None) -> int:
    """Business days between the newest statement and today. The page shows this loudly."""
    end = today or dt.date.today()
    start = dt.date.fromisoformat(data_as_of())
    days, cursor = 0, start
    while cursor < end:
        cursor += dt.timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days


def nav(date: str | None = None) -> float:
    """The broker's own endingValue. This is the authoritative number on the page."""
    date = date or data_as_of()
    for r in nav_series():
        if r["date"] == date:
            value = _num(r["ending_value"])
            if value is None:
                raise LedgerError(f"NAV row {date} has no ending_value")
            return value
    raise LedgerError(f"no NAV row for {date}")


def contributions_eur(upto: str | None = None) -> float:
    """Cumulative deposits in EUR, including the converted opening.

    Cross-check: this returns 600.00 at 2026-10-16, which is what plan.md and
    funding-log.csv independently record as deposited. Three sources agreeing is the
    reason to trust it.
    """
    upto = upto or data_as_of()
    total = OPENING_EUR
    for r in nav_series():
        if r["date"] <= upto:
            total += _num(r["deposits_withdrawals"]) or 0.0
    return total


# ----------------------------------------------------------------- positions

def positions(date: str | None = None) -> list[dict]:
    """Per-symbol positions on `date`, from the broker's own snapshot.

    SUMMARY rows only. At Lots level of detail IBKR emits both a per-symbol SUMMARY row
    and the LOT rows that add up to it, so taking everything double-counts the portfolio.
    Lots are the right grain for tax; summaries are the right grain for exposure.
    """
    date = date or data_as_of()
    rows = [
        r for r in _rows(POSITIONS_CSV)
        if r["report_date"] == date and r["level"] == "SUMMARY"
    ]
    if not rows:
        raise LedgerError(
            f"no position snapshot for {date}. The newest NAV is {data_as_of()}; if the "
            f"Flex query lacks OpenPositions, exposure cannot be computed at all."
        )
    return sorted(rows, key=lambda r: r["symbol"])


def position_value_eur(row: dict) -> float:
    """Position value in base currency, using the statement's OWN fx rate.

    Deliberately not an external rate: with IBKR's own number the positions sum to IBKR's
    NAV by construction, so a reconciliation failure means a real discrepancy rather than
    two sources disagreeing about FX.
    """
    value = _num(row["position_value_base"])
    if value is None:
        raise LedgerError(
            f"{row['symbol']} on {row['report_date']} has no base-currency value "
            f"(fx_rate_to_base={row.get('fx_rate_to_base')!r}). Refusing to guess."
        )
    return value


def reconcile(date: str | None = None) -> dict:
    """Positions + implied cash against the broker's NAV. The Stage 1 gate.

    There is no cash-balance section in the Flex query, so cash is derived as
    NAV - positions rather than read. That makes this an identity, not an independent
    check of NAV — what it genuinely verifies is that every position carries a usable
    base-currency value and that the implied remainder is plausible. A negative cash
    balance means a position is missing, mispriced, or double-counted.
    """
    date = date or data_as_of()
    rows = positions(date)
    total = sum(position_value_eur(r) for r in rows)
    broker_nav = nav(date)
    cash = broker_nav - total
    return {
        "date": date,
        "positions_eur": total,
        "nav_eur": broker_nav,
        "implied_cash_eur": cash,
        "position_count": len(rows),
        "ok": cash >= -0.01,
    }


def cost_basis_eur(row: dict) -> float | None:
    """What was paid for the position, in base currency.

    Converted at the statement's CURRENT fx rate, not the rate on the entry date, which
    the ledger does not carry per trade. The error is a few per cent of FX drift — fine
    for asking whether a position cleared a EUR 125 floor, wrong for a tax cost basis,
    where the NBU rate on the trade date is the only legal answer.
    """
    basis = _num(row.get("cost_basis_money"))
    fx = _num(row.get("fx_rate_to_base"))
    if basis is None or fx is None:
        return None
    return basis * fx


def core_capital_eur(date: str | None = None) -> float:
    """Contributions routed to the core, measured at COST, not market value.

    Using the core's market value here would make the trading sleeve's circuit-breaker
    denominator move with VWCE's price, which has nothing to do with how much money was
    sent to the core. Cost is the right measure of capital routed.
    """
    total = 0.0
    for r in positions(date):
        if r["symbol"] in CORE_SYMBOLS:
            basis = cost_basis_eur(r)
            if basis is None:
                raise LedgerError(
                    f"{r['symbol']} on {r['report_date']} has no cost basis, so capital "
                    f"routed to the core cannot be computed."
                )
            total += basis
    return total


def sleeve_capital_eur(date: str | None = None) -> float:
    """Cumulative contributions routed to the trading sleeve: contributions less the core.

    NOT the sum of current holdings' cost bases — realised proceeds get recycled into the
    next position, so summing cost bases counts the same euro twice. Three closed trades
    (ADPT, INTC, the first NBIS) were recycled this way.
    """
    return contributions_eur(date) - core_capital_eur(date)


def sleeves(date: str | None = None) -> dict:
    """Split the snapshot into the two sleeves plan.md actually defines."""
    rows = positions(date)
    core = [r for r in rows if r["symbol"] in CORE_SYMBOLS]
    trading = [r for r in rows if r["symbol"] not in CORE_SYMBOLS]
    return {
        "core": core,
        "trading": trading,
        "core_eur": sum(position_value_eur(r) for r in core),
        "trading_eur": sum(position_value_eur(r) for r in trading),
    }


# -------------------------------------------------------------------- journal

def journal() -> list[dict]:
    """The owner's pre-trade journal. Read-only here; the monitor never writes it."""
    return _rows(JOURNAL_CSV)


def open_journal_trades() -> list[dict]:
    return [r for r in journal() if not (r.get("date_exit") or "").strip()]


def trades() -> list[dict]:
    """Executed trades from the broker, which is the record that settles disputes."""
    return _rows(TRADES_CSV)
