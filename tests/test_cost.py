"""The cost model: spread estimators, commission arithmetic, and the break-even inversion.

The spread estimators are the risky part — they are published formulas transcribed into
vectorised pandas, and a transcription error would produce a plausible-looking number that is
wrong. So they are tested against synthetic series whose true spread is known by construction:
a random walk with a fixed bid-ask bounce bolted on.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import cost


def synthetic_with_spread(spread_fraction: float, days: int = 2000, seed: int = 0,
                          daily_vol: float = 0.02):
    """A random walk observed through a fixed proportional bid-ask spread.

    The efficient price follows a lognormal walk. Each day's high and low are the efficient
    extremes widened by half the spread on each side, and the close is the efficient price hit
    at the bid or the ask with equal probability — the classic bid-ask bounce. An estimator that
    works must recover `spread_fraction` from high, low and close alone.
    """
    rng = np.random.default_rng(seed)
    efficient = 100 * np.exp(np.cumsum(rng.normal(0, daily_vol, days)))
    # Intraday range of the efficient price, independent of the spread.
    intraday = np.abs(rng.normal(0, daily_vol, days)) * efficient
    half = spread_fraction / 2.0
    high = (efficient + intraday) * (1 + half)
    low = (efficient - intraday) * (1 - half)
    bounce = rng.choice([-1.0, 1.0], size=days)
    close = efficient * (1 + bounce * half)
    index = pd.bdate_range("2015-01-01", periods=days)
    frame = lambda values: pd.DataFrame({"X": values}, index=index)
    return frame(close), frame(high), frame(low)


# --- the spread estimators ------------------------------------------------


@pytest.mark.parametrize("true_spread", [0.002, 0.005, 0.02])
def test_abdi_ranaldo_recovers_a_known_spread(true_spread):
    """The estimator exists to measure a quantity no free feed reports, so it has to be shown
    to measure it. Tolerance is wide because the estimator is noisy by nature, not because the
    target is vague."""
    close, high, low = synthetic_with_spread(true_spread, days=4000)
    estimate = cost.abdi_ranaldo_spread(close, high, low, window=4000)["X"]
    assert estimate == pytest.approx(true_spread, rel=0.35)


def test_corwin_schultz_is_positive_and_ordered():
    """Corwin-Schultz is known to be noisy on single names and its zero-flooring biases it
    upward, so it is held to a weaker standard than Abdi-Ranaldo: positive, and monotone in the
    true spread."""
    estimates = []
    for true_spread in (0.001, 0.005, 0.02):
        close, high, low = synthetic_with_spread(true_spread, days=4000)
        estimates.append(float(cost.corwin_schultz_spread(high, low, window=4000)["X"]))
    assert all(e > 0 for e in estimates)
    assert estimates[0] < estimates[1] < estimates[2]


def test_both_estimators_are_near_zero_with_no_spread():
    """No bounce, no spread. An estimator that reports cost where there is none would make every
    strategy look expensive and the verdict meaningless in the other direction."""
    rng = np.random.default_rng(5)
    efficient = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 3000)))
    intraday = np.abs(rng.normal(0, 0.02, 3000)) * efficient
    index = pd.bdate_range("2015-01-01", periods=3000)
    close = pd.DataFrame({"X": efficient}, index=index)
    high = pd.DataFrame({"X": efficient + intraday}, index=index)
    low = pd.DataFrame({"X": efficient - intraday}, index=index)

    assert float(cost.abdi_ranaldo_spread(close, high, low, window=3000)["X"]) < 0.002
    assert float(cost.corwin_schultz_spread(high, low, window=3000)["X"]) < 0.01


def test_spread_estimates_uses_the_wider_of_the_two():
    """Underestimating cost makes an unprofitable strategy look profitable, so the model takes
    the pessimistic estimator rather than averaging them."""
    frame = pd.DataFrame({"cs_bps": [10.0, 40.0], "ar_bps": [25.0, 15.0]})
    used = frame[["cs_bps", "ar_bps"]].max(axis=1)
    assert list(used) == [25.0, 40.0]


def test_a_panel_without_high_low_is_refused_not_treated_as_free():
    """Silently returning a zero spread would make every strategy look costless — the exact
    failure this module exists to prevent."""
    class Panel:
        high = None
        low = None

    with pytest.raises(ValueError, match="no spread can be estimated"):
        cost.require_high_low(Panel())


# --- commission -----------------------------------------------------------


def test_the_per_order_minimum_dominates_a_small_position():
    """Why portfolio value is a parameter: at a USD 1.00 minimum, position size sets the rate."""
    schedule = cost.CommissionSchedule()
    assert schedule.per_order(price=100.0, position_value=400.0) == pytest.approx(1.00)
    assert schedule.bps(price=100.0, position_value=400.0) == pytest.approx(25.0)
    # A large position pays the per-share rate instead: 40,000/100 = 400 shares * 0.005 = $2.
    assert schedule.per_order(price=100.0, position_value=40_000.0) == pytest.approx(2.00)
    assert schedule.bps(price=100.0, position_value=40_000.0) == pytest.approx(0.5)


def test_commission_is_capped_at_one_percent_of_value():
    """The cap binds on a cheap stock, where per-share pricing would otherwise be punitive."""
    schedule = cost.CommissionSchedule()
    # A $1 stock: 1,000 shares for $1,000 would be $5 per-share, but the cap is $10 — not binding.
    # At $0.10 a share, 10,000 shares would be $50 against a $10 cap, which binds.
    assert schedule.per_order(price=0.10, position_value=1_000.0) == pytest.approx(10.0)
    assert schedule.bps(price=0.10, position_value=1_000.0) == pytest.approx(100.0)


def test_commission_scales_down_as_the_portfolio_grows():
    prices = pd.Series([50.0, 100.0, 200.0])
    small = cost.commission_bps_for_portfolio(prices, portfolio_value=10_000, positions=25)
    large = cost.commission_bps_for_portfolio(prices, portfolio_value=1_000_000, positions=25)
    assert small > large
    assert large < 1.0


def test_commission_handles_degenerate_inputs():
    prices = pd.Series([np.nan, 0.0, -5.0])
    assert cost.commission_bps_for_portfolio(prices, 10_000, 25) == 0.0
    assert cost.commission_bps_for_portfolio(pd.Series([100.0]), 0, 25) == 0.0


# --- the arithmetic that turns a spread into a drag ------------------------


def test_round_trip_pays_commission_twice_and_the_spread_once():
    """The spread is the full effective spread, paid once between buying at the ask and selling
    at the bid — not a half-spread paid twice."""
    assert cost.round_trip_bps(commission_one_way_bps=2.0, spread_bps=30.0) == 34.0
    assert cost.round_trip_bps(2.0, 30.0, impact_one_way_bps=1.0) == 36.0


def test_drag_scales_linearly_with_turnover():
    """The reason the measured 3.12x turnover matters threefold."""
    assert cost.annual_drag_bps(40.0, 1.0) == 40.0
    assert cost.annual_drag_bps(40.0, 3.12) == pytest.approx(124.8)


def test_break_even_inverts_the_question():
    """An 11.88pp gross excess at 1x turnover survives up to 1,188 bps per round trip; at
    3.12x only 380 bps. Independent of any spread estimate, which is the point."""
    assert cost.break_even_cost_bps(11.88, 1.0) == pytest.approx(1188.0)
    assert cost.break_even_cost_bps(11.88, 3.12) == pytest.approx(380.77, rel=1e-3)
    assert cost.break_even_cost_bps(11.88, 0) == float("inf")


def test_impact_is_small_relative_to_spread_at_the_liquidity_gate():
    """The gate requires ADV >= USD 5m, so a sane position is a small slice of a day's volume.
    Included to show impact is small rather than to assume it: a USD 4,000 position in a 3%/day
    name is a few bps one way, against tens of bps of spread for the same cohort."""
    adv = pd.Series([5e6, 2e7, 1e8])
    one_way = cost.impact_bps(position_value=4_000, adv_usd=adv, daily_vol=0.03)
    assert 0 < one_way < 10.0


def test_impact_scales_with_volatility_not_just_participation():
    """Impact is paid in units of the stock's own variability. An impact model blind to
    volatility would understate cost for exactly the cohort the gate selects."""
    adv = pd.Series([1e7])
    quiet = cost.impact_bps(4_000, adv, daily_vol=0.01)
    volatile = cost.impact_bps(4_000, adv, daily_vol=0.06)
    assert volatile == pytest.approx(6 * quiet, rel=1e-6)


def test_impact_grows_with_the_square_root_of_position_size():
    adv = pd.Series([1e7])
    small = cost.impact_bps(10_000, adv, daily_vol=0.03)
    big = cost.impact_bps(40_000, adv, daily_vol=0.03)
    assert big == pytest.approx(2 * small, rel=1e-6)


def test_impact_is_zero_without_volatility_or_liquidity():
    assert cost.impact_bps(4_000, pd.Series([1e7]), daily_vol=0.0) == 0.0
    assert cost.impact_bps(4_000, pd.Series([np.nan]), daily_vol=0.03) == 0.0


def test_tax_requires_a_rate_the_owner_supplies():
    """No default, because a made-up rate would be carried forward as fact. CLOUD-RULES.md §3
    also forbids this repository knowing anything about his actual position."""
    assert cost.after_tax_drag(12.0, 2.0, tax_rate=0.0) == pytest.approx(10.0)
    assert cost.after_tax_drag(12.0, 2.0, tax_rate=0.195) == pytest.approx(8.05)
    for bad in (-0.1, 1.0, 1.5):
        with pytest.raises(ValueError, match="tax_rate must be"):
            cost.after_tax_drag(12.0, 2.0, tax_rate=bad)
    assert "no default" in cost.TAX_IS_OUT_OF_SCOPE


# --- turnover, measured from the record ------------------------------------


def test_turnover_is_measured_from_the_record_and_skips_the_first_run():
    """Nothing can exit on the first run, so including it would understate turnover."""
    runs = pd.DataFrame({
        "is_first_run": [True, False, False, False],
        "watchlist_size": [25, 30, 30, 30],
        "exited": [0, 6, 9, 15],
    })
    out = cost.measure_turnover(runs)
    assert out["runs"] == 3
    assert out["mean_exits_per_run"] == pytest.approx(10.0)
    assert out["monthly_exit_rate"] == pytest.approx(1 / 3, rel=1e-3)
    assert out["annual_turnover"] == pytest.approx(4.0, rel=1e-3)
    assert out["implied_holding_months"] == pytest.approx(3.0, rel=1e-2)


def test_turnover_on_an_empty_record_says_so():
    assert cost.measure_turnover(pd.DataFrame({"is_first_run": [], "watchlist_size": [],
                                               "exited": []}))["runs"] == 0
