"""The horizon test's statistics, checked against properties that must hold.

Two of these functions decide a conclusion — whether the signal's edge survives at 3 months —
so they are numerical code whose correctness a reader should not have to take on trust. The
Newey-West correction in particular is the difference between a t of 7.74 and a t of 2.31 on
the same data, which is the difference between a finding and an artefact.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import horizon


# --- Newey-West -----------------------------------------------------------


def naive_t(series: pd.Series) -> float:
    return series.mean() / (series.std(ddof=1) / np.sqrt(len(series)))


def test_newey_west_matches_the_naive_t_on_independent_data():
    """With no lags there is no autocorrelation to correct, so the two must agree. They differ
    only by the ddof convention, which vanishes in n."""
    rng = np.random.default_rng(0)
    series = pd.Series(rng.normal(0.4, 1.0, 4000))
    assert horizon.newey_west_t(series, lags=0) == pytest.approx(naive_t(series), rel=0.01)


def test_newey_west_shrinks_the_t_on_a_positively_autocorrelated_series():
    """The whole point. Overlapping windows make neighbouring observations near-duplicates, so
    the naive standard error is too small and the naive t too large."""
    rng = np.random.default_rng(1)
    shocks = rng.normal(0.3, 1.0, 2000)
    # A 12-period moving average: exactly the structure of 12-month returns on a monthly grid.
    overlapping = pd.Series(shocks).rolling(12).mean().dropna()

    corrected = horizon.newey_west_t(overlapping, lags=12)
    assert corrected < naive_t(overlapping)
    # The inflation is large, not marginal: roughly sqrt(12) for a 12-fold overlap.
    assert naive_t(overlapping) / corrected > 2.0


def test_newey_west_handles_a_degenerate_series():
    assert np.isnan(horizon.newey_west_t(pd.Series([1.0, 2.0]), lags=3))
    assert np.isnan(horizon.newey_west_t(pd.Series([], dtype=float), lags=3))


# --- non-overlapping subsample --------------------------------------------


def test_nonoverlapping_t_uses_one_observation_in_every_step():
    rng = np.random.default_rng(2)
    series = pd.Series(rng.normal(0.2, 1.0, 120))
    _, n = horizon.nonoverlapping_t(series, step=12)
    assert n == 10            # 120 observations, every 12th


def test_nonoverlapping_t_also_shrinks_an_overlapping_series_t():
    rng = np.random.default_rng(3)
    overlapping = pd.Series(rng.normal(0.3, 1.0, 2000)).rolling(12).mean().dropna()
    subsample_t, _ = horizon.nonoverlapping_t(overlapping, step=12)
    assert subsample_t < naive_t(overlapping)


def test_nonoverlapping_t_does_not_depend_on_where_the_grid_starts():
    """It averages over all `step` offsets, so a conclusion cannot be an accident of phase."""
    rng = np.random.default_rng(4)
    series = pd.Series(rng.normal(0.3, 1.0, 600))
    first, _ = horizon.nonoverlapping_t(series, step=12)
    second, _ = horizon.nonoverlapping_t(series.iloc[1:], step=12)
    assert abs(first - second) < 0.5


def test_nonoverlapping_t_refuses_too_short_a_series():
    assert horizon.nonoverlapping_t(pd.Series([1.0, 2.0, 3.0]), step=12) == (np.nan, 0) or \
        np.isnan(horizon.nonoverlapping_t(pd.Series([1.0, 2.0, 3.0]), step=12)[0])


# --- Spearman without scipy ------------------------------------------------


def test_spearman_equals_pearson_on_ranks():
    rng = np.random.default_rng(5)
    x = pd.Series(rng.normal(size=300))
    y = pd.Series(rng.normal(size=300))
    assert horizon.spearman(x, y) == pytest.approx(float(x.rank().corr(y.rank())))


def test_spearman_is_one_for_a_monotone_transform():
    """The property that makes it the right statistic here: it reads a monotone relationship as
    perfect regardless of scale, which is what a rank-based score deserves."""
    x = pd.Series(np.arange(1.0, 101.0))
    assert horizon.spearman(x, np.exp(x / 10)) == pytest.approx(1.0)
    assert horizon.spearman(x, -x) == pytest.approx(-1.0)


def test_spearman_declines_to_answer_on_too_few_points():
    assert np.isnan(horizon.spearman(pd.Series([1.0, 2.0]), pd.Series([1.0, 2.0])))


# --- the forward-looking bound ---------------------------------------------


def test_rebalance_dates_leave_room_for_the_realized_return():
    """A date is only usable if its forward return is already in the panel. Nothing may be
    scored against a future that has not happened."""
    sessions = pd.bdate_range("2010-01-01", periods=2000)
    dates = horizon.rebalance_dates(sessions, horizon=horizon.H12,
                                    window=horizon.FACTOR_WINDOW)
    assert dates
    for date in dates:
        position = sessions.searchsorted(pd.Timestamp(date))
        assert position >= horizon.FACTOR_WINDOW          # enough history behind
        assert position + horizon.H12 < len(sessions)     # enough future ahead


def test_rebalance_dates_are_one_per_month():
    sessions = pd.bdate_range("2010-01-01", periods=2500)
    dates = pd.DatetimeIndex(horizon.rebalance_dates(sessions))
    assert len(set(zip(dates.year, dates.month))) == len(dates)


def test_rebalance_dates_returns_nothing_for_too_short_a_panel():
    """A short panel must yield no dates rather than a few bad ones."""
    assert horizon.rebalance_dates(pd.bdate_range("2024-01-01", periods=500)) == []


def test_forward_return_is_none_past_the_end_of_the_panel():
    index = pd.bdate_range("2024-01-01", periods=100)
    adjclose = pd.DataFrame({"A": np.linspace(10, 20, 100)}, index=index)
    assert horizon.forward_return(adjclose, index, index[-5], horizon=63) is None


def test_forward_return_is_a_total_return_over_the_right_span():
    index = pd.bdate_range("2024-01-01", periods=300)
    adjclose = pd.DataFrame({"A": 100 * np.power(1.001, np.arange(300))}, index=index)
    got = horizon.forward_return(adjclose, index, index[0], horizon=63)
    assert got["A"] == pytest.approx(1.001 ** 63 - 1, rel=1e-9)
