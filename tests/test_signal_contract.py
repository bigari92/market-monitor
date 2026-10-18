"""The promises the signal makes, as tests rather than as prose.

Two of these guard rules that exist because a measurement said so, and a rule that lives only in
a docstring is a rule that a later edit removes by accident.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import signal as sig


def synthetic_cross_section(n=400, seed=7):
    """A cross-section wide enough to clear every refusal floor."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "price": rng.uniform(6, 300, n),
        "adv_3m_usd": rng.uniform(6e6, 9e8, n),
        "pct_of_52w_high": rng.uniform(0.3, 1.0, n),
        "max_dd_12m": -rng.uniform(0.05, 0.8, n),
        "mom_36": rng.uniform(-0.5, 4.0, n),
        "adv_3m_usd_log": np.nan,
        "days_above_ma200": rng.uniform(0, 1, n),
        "mom_12_1": rng.uniform(-0.6, 3.0, n),
        "skew_12m": rng.normal(0, 1, n),
        "vol_12m": rng.uniform(0.15, 1.8, n),
    }, index=[f"T{i:04d}" for i in range(n)])


# --- the non-negotiable --------------------------------------------------


def test_probability_columns_are_rejected():
    """An isotonic calibrator fitted on one regime moved Brier 0.120 -> 0.189 on another. The
    tool may never display a probability, so the check is mechanical."""
    for bad in ("prob_up", "p_up", "win_probability", "confidence", "expected_return_12m",
                "brier_score", "odds"):
        with pytest.raises(AssertionError, match="probabilities or expected performance"):
            sig.assert_no_probability_columns(pd.DataFrame({bad: [0.5]}))


def test_scored_output_carries_no_probability():
    scored = sig.score(synthetic_cross_section())
    sig.assert_no_probability_columns(scored)   # raises if the contract broke
    assert "score" in scored.columns and "rank" in scored.columns


def test_why_it_ranks_is_attribution_not_forecast():
    """The explanation describes the past. No output of this function may predict."""
    scored = sig.score(synthetic_cross_section())
    text = sig.why_it_ranks(scored.iloc[0]).lower()
    assert text
    for forecast_word in ("will ", "should rise", "expect", "forecast", "predict", "target"):
        assert forecast_word not in text


# --- the definition is pinned -------------------------------------------


def test_signal_version_is_deterministic():
    assert sig.signal_version() == sig.signal_version()
    assert len(sig.signal_version()) == 12


def test_signal_version_moves_when_a_weight_moves(monkeypatch):
    """The hash exists so two disagreeing runs can be told apart: market change, or definition
    change. If a weight edit left the hash alone, the record would quietly lie."""
    before = sig.signal_version()
    monkeypatch.setitem(sig.PRICE_W, "pct_of_52w_high", 1.25)
    assert sig.signal_version() != before


def test_weights_are_the_recovered_values():
    """CLOUD-RULES.md §5: a session does not re-weight factors. Pinned so a drift is a failure."""
    assert sig.PRICE_W == {
        "pct_of_52w_high": 1.0, "max_dd_12m": 1.0, "mom36_healthy": 0.75,
        "mom36_overext": -0.75, "adv_3m_usd_log": 0.75, "days_above_ma200": 0.5,
        "mom_12_1": 0.5, "skew_12m": -0.75,
    }
    assert (sig.MIN_PRICE, sig.MIN_ADV) == (5.0, 5_000_000.0)
    assert sig.VOL_GATE == (0.80, 1.00)


# --- it refuses ----------------------------------------------------------


def test_refuses_a_thin_cross_section():
    """'It ranks and refuses' (README). A refusal is an outcome, not an error to retry past."""
    with pytest.raises(sig.RefusedToRank, match="Refusing to rank"):
        sig.score(synthetic_cross_section(n=10))


def test_refuses_when_hard_filters_eliminate_the_universe():
    frame = synthetic_cross_section()
    frame["price"] = 1.0          # every name below MIN_PRICE
    with pytest.raises(sig.RefusedToRank, match="cleared price"):
        sig.score(frame)


def test_hard_filters_use_the_recovered_thresholds():
    frame = synthetic_cross_section(n=600)
    scored = sig.score(frame)
    assert (scored["price"] >= sig.MIN_PRICE).all()
    assert (scored["adv_3m_usd"] >= sig.MIN_ADV).all()


def test_volatility_gate_keeps_the_top_quintile():
    """The gate is not a risk preference: the asymmetry result only holds conditional on a name
    being capable of a large move, so the gate defines the measured population."""
    frame = synthetic_cross_section(n=1000)
    gated = sig.apply_gates(frame)
    assert gated["vol_12m"].min() >= frame["vol_12m"].quantile(0.79)
    assert len(gated) < len(frame) / 2


# --- ranks, not z-scores -------------------------------------------------


def test_cs_rank_is_a_centred_percentile():
    """Ranks were worth +3.91pp/yr over z-scores, because the factors are violently skewed."""
    ranked = sig.cs_rank(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert ranked.min() >= -1.0 and ranked.max() <= 1.0
    assert ranked.is_monotonic_increasing


def test_cs_rank_is_immune_to_an_outlier():
    """The property that motivated the switch: one absurd value must not dominate the scale."""
    normal = sig.cs_rank(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
    with_outlier = sig.cs_rank(pd.Series([1.0, 2.0, 3.0, 4.0, 1e9]))
    pd.testing.assert_series_equal(normal, with_outlier)


def test_contributions_sum_to_the_score():
    """The per-term columns are what make a past call auditable, so they must reconcile."""
    scored = sig.score(synthetic_cross_section())
    contributions = scored[[c for c in scored.columns if c.startswith("c_")]].sum(axis=1)
    pd.testing.assert_series_equal(contributions, scored["score"], check_names=False)
