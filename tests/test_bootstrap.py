"""The kill gate's machinery, tested against cases whose answer is known in advance.

This is the one piece of code in the project that can end the project, so it is tested for
calibration in both directions: it must not pass noise, and it must not kill real skill.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import bootstrap as B


def pure_noise(n_periods=190, n_configs=40, seed=0, scale=0.15):
    """Configurations with no skill whatsoever, but correlated with each other — the shape of a
    real factor search, where every candidate is a variation on the same few ideas."""
    rng = np.random.default_rng(seed)
    common = rng.normal(0, scale, size=(n_periods, 1))
    idiosyncratic = rng.normal(0, scale, size=(n_periods, n_configs))
    values = 0.7 * common + 0.7 * idiosyncratic
    return pd.DataFrame(values, columns=[f"c{i:02d}" for i in range(n_configs)])


# --- the block bootstrap itself -------------------------------------------


def test_block_indices_have_the_right_length_and_stay_in_range():
    rng = np.random.default_rng(1)
    idx = B.circular_block_indices(190, 12, rng)
    assert len(idx) == 190
    assert idx.min() >= 0 and idx.max() < 190


def test_blocks_are_contiguous_and_wrap():
    """Contiguity is the whole point: it is what preserves the autocorrelation that overlapping
    forward returns create. Wrapping keeps every observation equally likely."""
    rng = np.random.default_rng(2)
    idx = B.circular_block_indices(100, 10, rng)
    for start in range(0, 100, 10):
        block = idx[start:start + 10]
        steps = np.diff(block) % 100
        assert set(steps.tolist()) == {1}, "a block must be consecutive, modulo wrap"


def test_block_length_one_is_an_iid_bootstrap():
    rng = np.random.default_rng(3)
    idx = B.circular_block_indices(50, 1, rng)
    assert len(idx) == 50


def test_a_bad_block_length_is_rejected():
    with pytest.raises(ValueError, match="block_length must be"):
        B.circular_block_indices(50, 0, np.random.default_rng(4))


# --- calibration: it must not pass noise ----------------------------------


def test_pure_noise_does_not_clear_the_gate():
    """40 skill-free configurations. The best of them will look good in sample — that is the
    entire problem the Reality Check exists to catch — and the gate must not be fooled."""
    result = B.reality_check(pure_noise(), block_length=12, n_resamples=2000)
    assert result.observed_best > 0, "the best of 40 noise series is positive in sample"
    assert not result.passes, "the gate passed pure noise"
    assert result.p_reality_check > B.KILL_THRESHOLD


def test_the_multiplicity_correction_is_what_catches_it():
    """On the same noise, pretending only the winner was ever tried can look significant. The
    gap between the two p-values IS the multiple-testing correction."""
    result = B.reality_check(pure_noise(), block_length=12, n_resamples=2000)
    assert result.p_single_config < result.p_reality_check
    assert result.p_single_config < 0.25 < result.p_reality_check


# --- calibration: it must not kill real skill ------------------------------


def test_a_genuinely_skilful_configuration_clears_the_gate():
    """One configuration with a real, persistent edge among 39 noise ones. A gate that killed
    this would be useless in the other direction."""
    frame = pure_noise(seed=7)
    frame["skilled"] = 0.15 + np.random.default_rng(8).normal(0, 0.10, len(frame))
    result = B.reality_check(frame, block_length=12, n_resamples=2000)
    assert result.best_config == "skilled"
    assert result.passes
    assert result.p_reality_check < B.KILL_THRESHOLD


def test_more_configurations_make_the_gate_stricter():
    """The core property: searching more makes the same winning result less impressive.

    The comparison has to be NESTED to mean anything — the small search must be a subset of the
    large one, containing the same winner. Two independently generated noise matrices have
    different winners and their p-values are not comparable, which is a mistake worth leaving a
    note about rather than a property of the method.
    """
    wide = pure_noise(n_configs=60, seed=11)
    winner = wide.mean().idxmax()
    narrow = wide[[winner, *[c for c in wide.columns if c != winner][:4]]]

    narrow_p = B.reality_check(narrow, 12, 2000).p_reality_check
    wide_p = B.reality_check(wide, 12, 2000).p_reality_check
    assert wide_p >= narrow_p, "a wider search must not make the same winner look better"


def test_longer_blocks_are_stricter_than_iid_on_autocorrelated_data():
    """An i.i.d. bootstrap treats 190 overlapping observations as 190 independent ones and so
    understates the p-value. Blocks must not be more permissive than i.i.d. on such a series."""
    rng = np.random.default_rng(13)
    shocks = rng.normal(0.02, 0.15, 400)
    overlapping = pd.Series(shocks).rolling(12).mean().dropna().reset_index(drop=True)
    frame = pd.DataFrame({f"c{i}": overlapping.values for i in range(3)})
    frame += rng.normal(0, 0.01, frame.shape)
    iid_p = B.reality_check(frame, block_length=1, n_resamples=1500).p_reality_check
    block_p = B.reality_check(frame, block_length=12, n_resamples=1500).p_reality_check
    assert block_p >= iid_p


# --- reporting ------------------------------------------------------------


def test_focus_reports_the_shipped_configuration_not_just_the_winner():
    """The configuration actually shipped is not always the best in sample, and the gate should
    say something about the one in production."""
    frame = pure_noise(seed=5)
    result = B.reality_check(frame, 12, 1000, focus="c03")
    assert 0.0 <= result.p_single_config <= 1.0
    assert result.best_config in frame.columns


def test_verdict_names_the_pre_registered_threshold():
    result = B.reality_check(pure_noise(), 12, 500)
    text = result.verdict()
    assert "0.10" in text
    assert ("PASS" in text) or ("KILL CONDITION MET" in text)


def test_the_threshold_is_the_pre_registered_one():
    """From the repository's first commit. This module reads it and must never set it."""
    assert B.KILL_THRESHOLD == 0.10


def test_too_few_periods_for_the_block_length_is_refused():
    with pytest.raises(ValueError, match="cannot support block length"):
        B.reality_check(pure_noise(n_periods=20), block_length=12, n_resamples=100)


def test_empty_input_is_refused():
    with pytest.raises(ValueError, match="no configurations"):
        B.reality_check(pd.DataFrame(), 12, 100)


def test_pvalue_rises_with_the_assumed_trial_count():
    table = B.pvalue_vs_trial_count(pure_noise(seed=17), (1, 5, 20, 40),
                                    block_length=12, n_resamples=600, n_subsets=6)
    assert list(table["assumed_trials"]) == [1, 5, 20, 40]
    assert table["p_reality_check"].is_monotonic_increasing


def test_the_reconstructed_trial_count_is_documented_as_a_floor():
    out = B.reconstructed_trial_count()
    assert out["documented_total"] == sum(B.RECONSTRUCTED_TRIALS.values())
    assert out["documented_total"] >= 50
    assert "PRICE_W" in out["uncounted"]
    assert "floor" in out["treat_as"]
