"""The fundamental panel: Q4 derivation, as-originally-filed, and the point-in-time cutoff.

These are the parts with no counterpart in the recovered code, so there is nothing to compare
against and they are tested against arithmetic. Each of the three has a way of being wrong that
would not show up in the output: a Q4 silently summed from the wrong year, a restated value
quietly replacing the original, or a factor visible a quarter before it was filed.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import fundamentals as FU
from market_monitor.cloud import sec_fsds as S


def facts_for(cik=1234, quarters=12, start="2020-03-31", revenue=100.0, growth=1.05,
              sic=7372):
    """Quarterly facts for one company: Q1-Q3 reported quarterly, Q4 only inside the annual.

    This mirrors what the data actually looks like — a 10-K states the year, not its fourth
    quarter — so a builder that cannot derive Q4 produces a panel with a hole every year.
    """
    rows = []
    period_ends = pd.date_range(start, periods=quarters, freq="QE")
    values = {}
    for index, period_end in enumerate(period_ends):
        value = revenue * (growth ** index)
        values[period_end] = value
        filed = period_end + pd.Timedelta(days=40)
        is_q4 = period_end.month == 12
        if not is_q4:
            for tag, scale in (("Revenues", 1.0), ("GrossProfit", 0.5),
                               ("OperatingIncomeLoss", 0.2), ("NetIncomeLoss", 0.1)):
                rows.append({"cik": cik, "ddate": period_end, "qtrs": 1, "tag": tag,
                             "value": value * scale, "filed": filed, "form": "10-Q",
                             "sic": sic, "fy": period_end.year, "fp": "Q1"})
    # Annual rows: the fiscal year total, filed with the 10-K.
    for year in sorted({p.year for p in period_ends}):
        in_year = [p for p in period_ends if p.year == year]
        if len(in_year) != 4:
            continue
        year_end = max(in_year)
        total = sum(values[p] for p in in_year)
        filed = year_end + pd.Timedelta(days=70)
        for tag, scale in (("Revenues", 1.0), ("GrossProfit", 0.5),
                           ("OperatingIncomeLoss", 0.2), ("NetIncomeLoss", 0.1)):
            rows.append({"cik": cik, "ddate": year_end, "qtrs": 4, "tag": tag,
                         "value": total * scale, "filed": filed, "form": "10-K",
                         "sic": sic, "fy": year, "fp": "FY"})
    frame = pd.DataFrame(rows)
    frame["cik"] = frame["cik"].astype("Int64")
    frame["sic"] = frame["sic"].astype("Int64")
    return frame


# --- Q4 derivation ---------------------------------------------------------


def test_q4_is_derived_from_the_annual_minus_three_quarters():
    """FY - (Q1+Q2+Q3), exactly. A 10-K states the year, so without this the panel has a hole
    at every Q4 and rolling(4).sum() with min_periods=4 cannot step over it."""
    facts = facts_for(quarters=8, start="2020-03-31", growth=1.0, revenue=100.0)
    panel = FU.build_panel(facts)

    q4s = panel[panel["period_end"].dt.month == 12]
    assert len(q4s) == 2, "both fiscal years should yield a derived Q4"
    # Flat revenue of 100/quarter: FY = 400, Q1+Q2+Q3 = 300, so Q4 = 100 and TTM = 400.
    full_year = panel[(panel["period_end"].dt.month == 12)
                      & panel["rev_ttm"].notna()]
    assert full_year["rev_ttm"].iloc[0] == pytest.approx(400.0)


def test_q4_carries_the_annual_filing_date_not_the_quarter_end():
    """Q4 becomes knowable when the 10-K lands, never earlier. Dating it from the quarter end
    would make it visible ~70 days before it was filed."""
    facts = facts_for(quarters=8, start="2020-03-31", growth=1.0)
    panel = FU.build_panel(facts)
    q4 = panel[panel["period_end"] == pd.Timestamp("2020-12-31")].iloc[0]
    assert q4["filed"] == pd.Timestamp("2020-12-31") + pd.Timedelta(days=70)
    assert q4["avail_date"] >= q4["filed"]


def test_q4_is_not_derived_when_a_quarter_is_missing():
    """Three quarters or nothing. Deriving from two would silently book a half-year as a
    quarter, which is a large error in exactly one direction."""
    facts = facts_for(quarters=8, start="2020-03-31", growth=1.0)
    # Drop Q2 of 2020 entirely.
    facts = facts[~((facts["ddate"] == pd.Timestamp("2020-06-30")) & (facts["qtrs"] == 1))]
    panel = FU.build_panel(facts)
    assert panel[panel["period_end"] == pd.Timestamp("2020-12-31")].empty


def test_a_reported_q4_is_preferred_over_a_derived_one():
    facts = facts_for(quarters=8, start="2020-03-31", growth=1.0)
    reported = pd.DataFrame([{
        "cik": 1234, "ddate": pd.Timestamp("2020-12-31"), "qtrs": 1, "tag": "Revenues",
        "value": 999.0, "filed": pd.Timestamp("2021-02-01"), "form": "10-K",
        "sic": 7372, "fy": 2020, "fp": "FY"}])
    reported["cik"] = reported["cik"].astype("Int64")
    reported["sic"] = reported["sic"].astype("Int64")
    panel = FU.build_panel(pd.concat([facts, reported], ignore_index=True))
    q4 = panel[panel["period_end"] == pd.Timestamp("2020-12-31")].iloc[0]
    assert q4["filed"] == pd.Timestamp("2021-02-01")


# --- as originally filed ---------------------------------------------------


def test_as_originally_filed_keeps_the_earliest_report_of_a_value():
    """The reason CLOUD-RULES.md §4 bans the frames API. A later restatement must not become
    visible at the original date — that is how a 2014 backtest sees a 2017 number."""
    base = {"cik": 1, "ddate": pd.Timestamp("2020-03-31"), "qtrs": 1, "tag": "Revenues",
            "form": "10-Q", "sic": 7372, "fy": 2020, "fp": "Q1"}
    facts = pd.DataFrame([
        {**base, "value": 100.0, "filed": pd.Timestamp("2020-05-10")},   # as first reported
        {**base, "value": 80.0, "filed": pd.Timestamp("2021-03-01")},    # later restatement
    ])
    kept = S.as_originally_filed(facts)
    assert len(kept) == 1
    assert kept.iloc[0]["value"] == 100.0
    assert kept.iloc[0]["filed"] == pd.Timestamp("2020-05-10")


def test_restatement_rate_reports_the_size_of_the_problem():
    base = {"cik": 1, "ddate": pd.Timestamp("2020-03-31"), "qtrs": 1, "tag": "Revenues",
            "form": "10-Q", "sic": 7372, "fy": 2020, "fp": "Q1"}
    facts = pd.DataFrame([
        {**base, "value": 100.0, "filed": pd.Timestamp("2020-05-10")},
        {**base, "value": 80.0, "filed": pd.Timestamp("2021-03-01")},
        {**base, "tag": "NetIncomeLoss", "value": 5.0, "filed": pd.Timestamp("2020-05-10")},
    ])
    out = S.restatement_rate(facts)
    assert out["groups"] == 2
    assert out["value_actually_changed"] == 1
    assert out["median_relative_change"] == pytest.approx(0.2)


# --- the point-in-time cutoff ---------------------------------------------


def test_as_of_hides_a_row_until_the_day_it_was_filed():
    facts = facts_for(quarters=12, start="2020-03-31")
    panel = FU.build_panel(facts)
    row = panel.dropna(subset=["rev_ttm"]).iloc[0]

    day_before = FU.as_of(panel, row["avail_date"] - pd.Timedelta(days=1))
    on_the_day = FU.as_of(panel, row["avail_date"])
    seen_before = set(zip(day_before["cik"], day_before["period_end"])) if len(day_before) else set()
    assert (row["cik"], row["period_end"]) not in seen_before
    assert (row["cik"], row["period_end"]) in set(zip(on_the_day["cik"],
                                                      on_the_day["period_end"]))


def test_as_of_returns_at_most_one_row_per_company():
    facts = pd.concat([facts_for(cik=1), facts_for(cik=2)], ignore_index=True)
    panel = FU.build_panel(facts)
    latest = FU.as_of(panel, "2023-06-30")
    assert latest["cik"].is_unique


def test_as_of_drops_a_company_that_has_stopped_reporting():
    """A company whose last fiscal period ended 15 months ago is not described by that report.
    The 460-day bound is screen_v4.py's."""
    facts = facts_for(quarters=8, start="2015-03-31")
    panel = FU.build_panel(facts)
    assert not FU.as_of(panel, "2017-06-30").empty
    assert FU.as_of(panel, "2026-01-01").empty


def test_as_of_on_an_empty_visible_set_returns_empty_not_an_error():
    panel = FU.build_panel(facts_for())
    assert FU.as_of(panel, "1999-01-01").empty


# --- the factor arithmetic, unchanged from the recovered definitions -------


def test_ttm_growth_on_a_known_compounder():
    """Revenue growing 5% per quarter: TTM year-on-year growth converges on 1.05^4 - 1."""
    facts = facts_for(quarters=16, start="2019-03-31", revenue=100.0, growth=1.05)
    panel = FU.build_panel(facts).dropna(subset=["rev_yoy_ttm"])
    assert not panel.empty
    assert panel["rev_yoy_ttm"].iloc[-1] == pytest.approx(1.05 ** 4 - 1, rel=1e-6)


def test_margins_come_from_ttm_and_rule40_is_their_sum_with_growth():
    facts = facts_for(quarters=16, start="2019-03-31", growth=1.0)
    panel = FU.build_panel(facts).dropna(subset=["op_margin", "rule40", "rev_yoy_ttm"])
    row = panel.iloc[-1]
    assert row["gross_margin"] == pytest.approx(0.5)
    assert row["op_margin"] == pytest.approx(0.2)
    assert row["net_margin"] == pytest.approx(0.1)
    assert row["rule40"] == pytest.approx(row["rev_yoy_ttm"] + row["op_margin"])
    assert row["profitable"] == 1.0


def test_scale_errors_are_clipped_as_in_the_recovered_code():
    facts = facts_for(quarters=16, start="2019-03-31", growth=1.0)
    # A single absurd quarter, the shape of an XBRL scale error.
    mask = (facts["ddate"] == pd.Timestamp("2021-03-31")) & (facts["tag"] == "Revenues")
    facts.loc[mask, "value"] = 1e12
    panel = FU.build_panel(facts)
    assert (panel["rev_yoy_ttm"].abs() > 10).sum() == 0
    assert (panel["op_margin"] > 5).sum() == 0


def test_filing_lag_profile_measures_what_lag_days_90_assumed():
    facts = facts_for(quarters=12, start="2020-03-31")
    profile = FU.filing_lag_profile(FU.build_panel(facts))
    assert profile["n"] > 0
    # The fixture files quarterlies at +40 days and annuals at +70.
    assert 40 <= profile["median_days"] <= 70
    assert profile["share_within_90d_%"] == 100.0


def test_sic_is_attached_from_the_filings():
    facts = facts_for(sic=3674)
    panel = FU.attach_sic(FU.build_panel(facts), facts)
    assert (panel["sic"] == 3674).all()
