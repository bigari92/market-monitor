"""The feed contract: a feed that answers without data must never pass as a feed that answered.

This is the failure that cost the most to discover (results/price_feed_probe.md §4):
nasdaqtrader.com returns HTTP 200 with a 212-byte Imperva challenge body, and Stooq is
documented to return empty bodies rather than errors. Neither looks like a failure from the
status code, so the guard is structural rather than a check at one call site.
"""
import pandas as pd
import pytest

from market_monitor.cloud import prices
from market_monitor.cloud.feeds import (Bars, FeedEmptyError, FeedError, PriceFeed, get_feed)


def make_bars(tickers=("AAA", "BBB"), sessions=300):
    index = pd.bdate_range("2024-01-01", periods=sessions)
    wide = pd.DataFrame({t: range(sessions) for t in tickers}, index=index, dtype=float) + 10.0
    return Bars(
        close=wide, adjclose=wide * 1.01, volume=wide * 1000,
        events=pd.DataFrame(columns=["ticker", "date", "kind", "value"]),
        meta=pd.DataFrame({"ticker": list(tickers), "exchange": "NYSE",
                           "instrument_type": "EQUITY", "currency": "USD",
                           "bars": sessions, "first": index[0], "last": index[-1]}),
    )


def test_a_panel_with_no_columns_is_an_error_not_an_empty_market():
    empty = pd.DataFrame(index=pd.bdate_range("2024-01-01", periods=10))
    with pytest.raises(FeedEmptyError, match="silent-zero-rows"):
        Bars(close=empty, adjclose=empty, volume=empty,
             events=pd.DataFrame(), meta=pd.DataFrame())


def test_bars_summary_states_coverage_and_actions():
    text = make_bars().summary()
    assert "2 tickers" in text and "sessions" in text and "corporate actions" in text


def test_unknown_feed_names_the_known_ones():
    with pytest.raises(ValueError, match="yahoo_chart"):
        get_feed("definitely_not_a_feed")


def test_the_yahoo_feed_satisfies_the_protocol():
    feed = get_feed("yahoo_chart")
    assert isinstance(feed, PriceFeed)
    assert feed.name == "yahoo_chart"


def test_the_yahoo_feed_refuses_an_empty_request():
    """No network: an empty ticker list must fail before a request is made."""
    with pytest.raises(FeedEmptyError, match="empty ticker list"):
        get_feed("yahoo_chart").fetch([])


def test_sharadar_states_the_purchase_decision_rather_than_failing_obscurely(monkeypatch):
    """A missing paid-feed key is a decision the owner has not made, and the error says so,
    with the price and what the money buys."""
    monkeypatch.delenv("SHARADAR_API_KEY", raising=False)
    with pytest.raises(FeedError, match="purchase decision"):
        get_feed("sharadar").fetch(["AAPL"])


# --- the cache ------------------------------------------------------------


def test_panel_round_trips_through_the_cache(tmp_path):
    bars = make_bars()
    prices.write_panel(bars, "2026-10-16", "test_feed", root=tmp_path)
    back = prices.read_panel("2026-10-16", "test_feed", root=tmp_path)
    # check_freq=False: parquet stores the index values, not a DatetimeIndex's inferred `freq`
    # attribute. The dates round-trip exactly; only the bdate_range annotation is lost, and
    # nothing downstream reads it.
    pd.testing.assert_frame_equal(bars.close, back.close, check_freq=False)
    pd.testing.assert_frame_equal(bars.adjclose, back.adjclose, check_freq=False)


def test_cached_as_of_dates_survives_an_underscore_in_the_feed_name(tmp_path):
    """The bug this test exists for: splitting 'yahoo_chart_2026-10-16' on the FIRST underscore
    yields 'chart_2026-10-16', which misses the cache and then writes a second, wrongly-named
    copy next to it — a 149-second refetch that looks like a cache hit failure."""
    prices.write_panel(make_bars(), "2026-10-16", "yahoo_chart", root=tmp_path)
    assert prices.cached_as_of_dates("yahoo_chart", root=tmp_path) == ["2026-10-16"]


def test_reading_a_missing_panel_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        prices.read_panel("1999-01-01", "test_feed", root=tmp_path)


def test_a_stale_panel_is_refused():
    """A ranking computed on three-week-old prices is indistinguishable from a current one in
    the output, so staleness has to be caught at the input."""
    bars = make_bars()
    last = bars.close.index.max()
    with pytest.raises(FeedEmptyError, match="Refusing to rank a stale panel"):
        prices.assert_fresh(bars, last + pd.Timedelta(days=30), max_staleness_days=7)


def test_assert_fresh_accepts_a_tz_aware_reference():
    """Callers reach for Timestamp.utcnow(), which is tz-aware while the panel index is naive.
    Subtracting one from the other raises, so both sides are normalised."""
    bars = make_bars()
    reference = pd.Timestamp(bars.close.index.max()).tz_localize("UTC")
    prices.assert_fresh(bars, reference, max_staleness_days=7)


def test_coverage_report_counts_what_the_factor_floor_admits():
    bars = make_bars(sessions=300)
    report = prices.coverage_report(bars, min_bars=273)
    assert report["scorable"].all()
    assert prices.coverage_report(make_bars(sessions=100), min_bars=273)["scorable"].sum() == 0
