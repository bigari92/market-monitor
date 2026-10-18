"""The factor port, checked against hand-computable values.

`recovered/factors.py` is evidence: never edited, never imported (docs/RECOVERY.md). So the port
cannot be tested by comparing against it directly. It is tested against arithmetic instead, on
synthetic series whose factor values are knowable by hand — which is the stronger check anyway,
since it would also catch an error the recovered code already contained.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import factors as F

SESSIONS = 800  # over 3 years, so mom_36 is defined


def panel(series_by_ticker: dict[str, np.ndarray]) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(next(iter(series_by_ticker.values())))
    index = pd.bdate_range("2020-01-01", periods=n)
    close = pd.DataFrame(series_by_ticker, index=index)
    volume = pd.DataFrame({t: np.full(n, 1_000_000.0) for t in series_by_ticker}, index=index)
    return close, volume


def test_monotone_riser_has_the_factor_values_arithmetic_demands():
    """A price that only ever rises: at its 52-week high, never drawn down, always above its
    moving average. Every one of these is exactly computable, so an off-by-one in the
    positional offsets shows up here."""
    growth = 100 * np.power(1.001, np.arange(SESSIONS))
    close, volume = panel({"UP": growth})
    f = F.compute_factors(close, volume, close.index[-1])

    row = f.loc["UP"]
    assert row["price"] == pytest.approx(growth[-1])
    assert row["pct_of_52w_high"] == pytest.approx(1.0)
    assert row["max_dd_12m"] == pytest.approx(0.0, abs=1e-12)
    assert row["days_above_ma200"] == pytest.approx(1.0)
    assert row["px_vs_ma200"] > 0
    assert row["ma50_vs_ma200"] > 0

    # The N-1 window, which is a property of the recovered definitions and is kept, not fixed:
    # `iloc[-1] / iloc[-63]` spans 62 intervals, not 63, because iloc[-1] is itself one of the
    # endpoints. Every momentum term inherits the same one-session shortfall. It is economically
    # irrelevant at these horizons, but asserting the intended 63 instead of the actual 62 would
    # hide a future off-by-one rather than catch one. Correcting it would be a signal change,
    # which CLOUD-RULES.md §5 does not permit a session to make.
    assert row["mom_3"] == pytest.approx(1.001 ** 62 - 1, rel=1e-9)
    assert row["mom_1"] == pytest.approx(1.001 ** 20 - 1, rel=1e-9)
    # mom_12_1 skips the most recent month: iloc[-22] / iloc[-273] - 1, so 251 intervals.
    assert row["mom_12_1"] == pytest.approx(1.001 ** 251 - 1, rel=1e-9)
    assert row["mom_36"] == pytest.approx(1.001 ** 755 - 1, rel=1e-9)
    # mom_accel inherits an ASYMMETRIC pair of windows: recent is iloc[-1]/iloc[-126] (125
    # intervals) while prior is iloc[-126]/iloc[-252] (126). So a perfectly constant trend
    # registers as very slightly decelerating rather than as exactly zero. The size of it is
    # -0.11pp on a 0.1%/session compounder — far below anything the percentile rank resolves —
    # but it is a real property of the recovered definition, so it is asserted rather than
    # smoothed over.
    assert row["mom_accel"] == pytest.approx((1.001 ** 125 - 1) - (1.001 ** 126 - 1), rel=1e-9)
    assert -0.002 < row["mom_accel"] < 0.0
    # A deterministic series has no return variance.
    assert row["vol_12m"] == pytest.approx(0.0, abs=1e-9)


def test_drawdown_is_the_deepest_trough_and_not_the_distance_from_the_high():
    """RECOVERY.md's fifth item: `pct_of_52w_high` and `max_dd_12m` were called the same
    quantity. They are not, and a series that falls and fully recovers proves it — it ends at
    its 52-week high with a large drawdown behind it."""
    # The trough must sit INSIDE the trailing 252 sessions that max_dd_12m looks at. With
    # 80 + 120 = 200 sessions after the peak, the window covers the fall and the recovery.
    up = np.linspace(100, 200, 400)
    down = np.linspace(200, 120, 80)        # a 40% trough, inside the 12-month window
    back = np.linspace(120, 260, 120)       # recovers to a new high
    close, volume = panel({"V": np.concatenate([up, down, back])})
    f = F.compute_factors(close, volume, close.index[-1])
    row = f.loc["V"]

    assert row["pct_of_52w_high"] == pytest.approx(1.0)   # ends at its high
    assert row["max_dd_12m"] < -0.3                        # yet carries a deep trough
    assert row["max_dd_12m"] != pytest.approx(row["pct_of_52w_high"] - 1.0)


def test_short_history_names_are_dropped_and_counted_not_scored():
    """The recovered code returned None for the whole cross-section below 273 sessions. Per
    ticker here: a short name leaves the frame rather than being scored on thin history."""
    long_series = 100 * np.power(1.0005, np.arange(SESSIONS))
    short = np.full(SESSIONS, np.nan)
    short[-100:] = np.linspace(50, 60, 100)     # only 100 real sessions
    close, volume = panel({"LONG": long_series, "SHORT": short})

    f = F.compute_factors(close, volume, close.index[-1])
    assert "LONG" in f.index
    assert "SHORT" not in f.index

    cover = F.coverage(close, close.index[-1])
    assert cover["scorable"] == 1
    assert cover["short_history"] == 1
    assert cover["min_sessions"] == F.MIN_SESSIONS == 273


def test_raises_rather_than_returning_an_empty_frame():
    """An unscoreable panel is a data problem, not an empty market."""
    short = pd.DataFrame({"A": np.linspace(10, 11, 50)},
                         index=pd.bdate_range("2024-01-01", periods=50))
    volume = pd.DataFrame({"A": np.full(50, 1e6)}, index=short.index)
    with pytest.raises(ValueError, match="too short to score"):
        F.compute_factors(short, volume, short.index[-1])


def test_point_in_time_a_later_bar_cannot_change_an_earlier_factor():
    """No lookahead. The factor set as of date T must be identical whether or not the panel
    happens to carry data after T — the property the whole exercise depends on."""
    rng = np.random.default_rng(3)
    walk = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, SESSIONS + 200)))
    close, volume = panel({"W": walk})
    as_of = close.index[SESSIONS]

    truncated = F.compute_factors(close.loc[:as_of], volume.loc[:as_of], as_of)
    with_future = F.compute_factors(close, volume, as_of)
    pd.testing.assert_frame_equal(truncated, with_future)


def test_dividends_do_not_register_as_a_drawdown():
    """RECOVERY.md defect 2, as a behaviour test. `auto_adjust=True` gave the recovered code one
    series, so a dividend was indistinguishable from a price fall. Here trend and drawdown read
    `close` while momentum reads `adjclose`, so a dividend-paying flat stock shows no drawdown
    while its total return is positive."""
    flat = np.full(SESSIONS, 100.0)
    # A total-return series that climbs only through reinvested dividends.
    total_return = 100 * np.power(1.0002, np.arange(SESSIONS))
    close, volume = panel({"D": flat})
    adjclose = pd.DataFrame({"D": total_return}, index=close.index)

    f = F.compute_factors(close, volume, close.index[-1], adjclose=adjclose)
    row = f.loc["D"]
    assert row["max_dd_12m"] == pytest.approx(0.0, abs=1e-12)   # price never fell
    assert row["pct_of_52w_high"] == pytest.approx(1.0)
    assert row["mom_12_1"] > 0        # but a holder did make money
    assert row["price"] == pytest.approx(100.0)


def test_every_recovered_factor_is_present():
    """The port is complete, or this fails. Eighteen factors, the recovered list."""
    growth = 100 * np.power(1.001, np.arange(SESSIONS))
    close, volume = panel({"UP": growth, "UP2": growth * 1.5})
    f = F.compute_factors(close, volume, close.index[-1])
    assert list(f.columns) == list(F.FACTOR_NAMES)
    assert len(F.FACTOR_NAMES) == 18
