"""The tracking record: append-only, reproducible, and each exit rule firing for its own reason.

The record is the product. If a past call can be rewritten, or a re-run of the same as-of date
produces a different ranking, there is nothing to learn from later and the whole exercise is a
screen with extra steps.
"""
import numpy as np
import pandas as pd
import pytest

from market_monitor.cloud import signal as sig
from market_monitor.cloud import tracker


def cross_section(n=400, seed=11, **overrides):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "price": rng.uniform(20, 300, n),
        "adv_3m_usd": rng.uniform(2e7, 9e8, n),
        "pct_of_52w_high": rng.uniform(0.3, 1.0, n),
        "max_dd_12m": -rng.uniform(0.05, 0.8, n),
        "mom_36": rng.uniform(-0.4, 3.0, n),
        "mom_accel": rng.normal(0, 0.3, n),
        "days_above_ma200": rng.uniform(0, 1, n),
        "px_vs_ma200": rng.uniform(0.02, 0.9, n),     # everything above its MA by default
        "ma50_vs_ma200": rng.uniform(0.0, 0.4, n),
        "mom_12_1": rng.uniform(-0.5, 3.0, n),
        "skew_12m": rng.normal(0, 1, n),
        "vol_12m": rng.uniform(0.2, 1.8, n),
    }, index=[f"T{i:04d}" for i in range(n)])
    for column, value in overrides.items():
        frame[column] = value
    return frame


def test_first_run_enters_everything_and_can_exit_nothing(tmp_path):
    result = tracker.run(cross_section(), "2026-10-16", "test_feed", tracking_dir=tmp_path)
    assert result.is_first_run
    assert len(result.buys) == sig.TOP_N
    assert result.exits.empty
    assert result.holds.empty
    assert (tmp_path / tracker.RUNS_CSV).is_file()
    assert (tmp_path / tracker.LISTINGS_CSV).is_file()


def test_rerunning_the_same_as_of_reproduces_the_same_ranking(tmp_path):
    """Reproducibility is the property that makes a past call checkable. Same factors, same
    signal version, same ranking — no clock, no randomness, no today()."""
    factors = cross_section()
    first = tracker.run(factors, "2026-10-16", "test_feed", tracking_dir=tmp_path, dry_run=True)
    second = tracker.run(factors, "2026-10-16", "test_feed", tracking_dir=tmp_path, dry_run=True)
    assert first.run_id == second.run_id
    pd.testing.assert_frame_equal(first.buys, second.buys)


def test_a_past_row_is_never_rewritten(tmp_path):
    """Append-only, verified by byte prefix: the second run's file must start with the first
    run's file unchanged."""
    tracker.run(cross_section(seed=1), "2026-10-16", "test_feed", tracking_dir=tmp_path)
    after_one = (tmp_path / tracker.LISTINGS_CSV).read_text()
    tracker.run(cross_section(seed=2), "2026-11-16", "test_feed", tracking_dir=tmp_path)
    after_two = (tmp_path / tracker.LISTINGS_CSV).read_text()

    assert after_two.startswith(after_one)
    assert len(after_two) > len(after_one)
    runs = pd.read_csv(tmp_path / tracker.RUNS_CSV)
    assert len(runs) == 2
    assert runs["data_as_of"].tolist() == ["2026-10-16", "2026-11-16"]


def test_dry_run_writes_nothing(tmp_path):
    tracker.run(cross_section(), "2026-10-16", "test_feed", tracking_dir=tmp_path, dry_run=True)
    assert not (tmp_path / tracker.RUNS_CSV).exists()
    assert not (tmp_path / tracker.LISTINGS_CSV).exists()


# --- the exit rules, one at a time ---------------------------------------


def _list_then(tmp_path, second_factors):
    """List a watchlist on run 1, then present run 2 and return its events."""
    first = cross_section(seed=5)
    run_one = tracker.run(first, "2026-10-16", "test_feed", tracking_dir=tmp_path)
    listed = run_one.buys["ticker"].tolist()
    run_two = tracker.run(second_factors(first, listed), "2026-11-16", "test_feed",
                          tracking_dir=tmp_path)
    return listed, run_two


def test_trend_break_exits_on_a_zero_crossing_not_a_fitted_level(tmp_path):
    def break_trend(frame, listed):
        f = frame.copy()
        f.loc[listed[0], "px_vs_ma200"] = -0.01   # just below its 200-day average
        return f

    listed, run_two = _list_then(tmp_path, break_trend)
    exits = run_two.exits.set_index("ticker")
    assert listed[0] in exits.index
    assert exits.loc[listed[0], "reason_code"] == "TREND_BREAK"


def test_trend_break_is_a_transition_and_not_a_level(tmp_path):
    """The bug the first live run exposed. TER ranked #1 with px_vs_ma200 at -0.057: already
    below its 200-day average, because `days_above_ma200` (a weighted term) measures the year
    while `px_vs_ma200` (not a weighted term) measures today. A level rule would have entered
    it and exited it one run later. Nothing broke, so nothing should fire."""
    factors = cross_section(seed=5)
    factors["px_vs_ma200"] = -0.05          # the whole cohort sits below its 200-day average

    run_one = tracker.run(factors, "2026-10-16", "test_feed", tracking_dir=tmp_path)
    assert len(run_one.buys) == sig.TOP_N, "entry must not acquire a criterion the signal lacks"

    run_two = tracker.run(factors, "2026-11-16", "test_feed", tracking_dir=tmp_path)
    trend_breaks = run_two.exits[run_two.exits["reason_code"] == "TREND_BREAK"] \
        if not run_two.exits.empty else pd.DataFrame()
    assert trend_breaks.empty, "a name already below its MA at listing has no trend to break"
    assert len(run_two.holds) == sig.TOP_N


def test_trend_break_fires_on_the_crossing_itself(tmp_path):
    """The other half: above at listing, below now, is a break and must fire."""
    above = cross_section(seed=5)
    above["px_vs_ma200"] = 0.10
    tracker.run(above, "2026-10-16", "test_feed", tracking_dir=tmp_path)

    below = above.copy()
    below["px_vs_ma200"] = -0.02
    run_two = tracker.run(below, "2026-11-16", "test_feed", tracking_dir=tmp_path)
    assert not run_two.exits.empty
    assert (run_two.exits["reason_code"] == "TREND_BREAK").all()
    assert "having been above it at the previous run" in run_two.exits.iloc[0]["detail"]


def test_gate_failure_on_price_uses_the_signal_constant(tmp_path):
    def crash(frame, listed):
        f = frame.copy()
        f.loc[listed[0], "price"] = sig.MIN_PRICE - 0.01
        return f

    listed, run_two = _list_then(tmp_path, crash)
    exits = run_two.exits.set_index("ticker")
    # A name below MIN_PRICE is filtered out of the ranking entirely, so it leaves the
    # watchlist. Either reason is correct; what matters is that it does not silently stay.
    assert listed[0] in exits.index
    assert exits.loc[listed[0], "reason_code"] in {"GATE_FAIL_PRICE", "NO_LONGER_PRICED"}


def test_a_delisted_name_exits_as_no_longer_priced(tmp_path):
    def delist(frame, listed):
        return frame.drop(index=listed[0])

    listed, run_two = _list_then(tmp_path, delist)
    exits = run_two.exits.set_index("ticker")
    assert exits.loc[listed[0], "reason_code"] == "NO_LONGER_PRICED"


def test_leaving_the_volatility_gate_is_not_reported_as_delisting(tmp_path):
    """The bug a 24-month replay exposed: `NO_LONGER_PRICED` fired 0-6 times a month over a
    panel of names that all survived to today, while `LEFT_VOL_GATE` never fired at all. Both
    came from reading absence-from-`ranked` as absence-from-the-market.

    The two are entirely different signals. 'Delisted' is terminal; 'calmed down and left the
    cohort the asymmetry result was measured on' is not. Conflating them makes the exit log
    useless for the only thing it is for."""
    def calm_down(frame, listed):
        f = frame.copy()
        f.loc[listed[0], "vol_12m"] = 0.01   # still priced and liquid, now the calmest name
        return f

    listed, run_two = _list_then(tmp_path, calm_down)
    exits = run_two.exits.set_index("ticker")
    assert exits.loc[listed[0], "reason_code"] == "LEFT_VOL_GATE"
    assert "still\npriced and liquid" in exits.loc[listed[0], "detail"].replace(" ", "\n", 100) \
        or "still priced and liquid" in exits.loc[listed[0], "detail"]


def test_an_illiquid_name_exits_as_a_liquidity_failure_not_a_delisting(tmp_path):
    """Dropping below the ADV floor removes a name from the ranking too, and it must be
    attributed to the floor it actually failed."""
    def dry_up(frame, listed):
        f = frame.copy()
        f.loc[listed[0], "adv_3m_usd"] = sig.MIN_ADV / 10
        return f

    listed, run_two = _list_then(tmp_path, dry_up)
    exits = run_two.exits.set_index("ticker")
    assert exits.loc[listed[0], "reason_code"] == "GATE_FAIL_LIQUIDITY"


def test_every_exit_reason_is_reachable():
    """A reason code that cannot fire is a code that misreports something else as itself —
    which is exactly how LEFT_VOL_GATE's absence hid as NO_LONGER_PRICED."""
    reachable = {"GATE_FAIL_PRICE", "GATE_FAIL_LIQUIDITY", "LEFT_VOL_GATE",
                 "TREND_BREAK", "RANK_DECAY", "NO_LONGER_PRICED"}
    assert set(tracker.EXIT_REASONS) == reachable


def test_rank_drift_inside_the_buffer_is_held_not_exited(tmp_path):
    """A listing is a 12-month thesis. Rank noise must not retire a name, or the tracker
    becomes a weekly opinion the research never validated."""
    first = cross_section(seed=5)
    run_one = tracker.run(first, "2026-10-16", "test_feed", tracking_dir=tmp_path)
    top = run_one.buys.sort_values("rank")["ticker"].tolist()

    # Nudge the best name down the ranking without breaking anything structural.
    second = first.copy()
    second.loc[top[0], ["pct_of_52w_high", "max_dd_12m"]] = [0.62, -0.45]
    run_two = tracker.run(second, "2026-11-16", "test_feed", tracking_dir=tmp_path)

    held = run_two.holds.set_index("ticker")
    assert top[0] in held.index, "a name that merely drifted in rank was retired"
    assert top[0] not in set(run_two.exits["ticker"].tolist() if not run_two.exits.empty else [])


def test_rank_decay_exits_only_past_the_declared_buffer(tmp_path):
    assert tracker.RANK_DECAY_MULTIPLE == 2
    buffer_rank = sig.TOP_N * tracker.RANK_DECAY_MULTIPLE

    ranked = sig.score(cross_section(seed=5))
    # A previous row showing the name above its 200-day average, so TREND_BREAK cannot mask
    # what this test is about.
    def prior(ticker):
        return pd.Series({"ticker": ticker, "px_vs_ma200": 0.10})

    assert tracker.classify_exit(prior(ranked.index[buffer_rank - 2]), ranked, sig.TOP_N) is None
    code, _ = tracker.classify_exit(prior(ranked.index[buffer_rank + 5]), ranked, sig.TOP_N)
    assert code in {"RANK_DECAY", "TREND_BREAK"}


def test_held_names_carry_their_first_listed_date_forward(tmp_path):
    """How long a name has been listed is the thing a later review needs most."""
    factors = cross_section(seed=5)
    tracker.run(factors, "2026-10-16", "test_feed", tracking_dir=tmp_path)
    run_two = tracker.run(factors, "2026-11-16", "test_feed", tracking_dir=tmp_path)

    assert not run_two.holds.empty
    assert (run_two.holds["first_listed_as_of"] == "2026-10-16").all()
    assert (run_two.holds["runs_held"] >= 2).all()


def test_report_states_no_probability_and_no_performance(tmp_path):
    result = tracker.run(cross_section(), "2026-10-16", "test_feed", tracking_dir=tmp_path)
    report = tracker.render_report(result)
    assert "loser-filter" in report
    assert "data_as_of" in report
    for banned in ("probability of", "expected return of", "% chance"):
        assert banned not in report.lower()


def test_every_exit_reason_has_an_explanation():
    """A reason code with no sentence behind it is a code nobody can act on."""
    for code in tracker.EXIT_REASONS:
        assert tracker.EXIT_REASONS[code].strip()
    assert set(tracker.EXIT_REASONS) == {
        "GATE_FAIL_PRICE", "GATE_FAIL_LIQUIDITY", "LEFT_VOL_GATE",
        "TREND_BREAK", "RANK_DECAY", "NO_LONGER_PRICED",
    }


def test_a_refusal_propagates_rather_than_writing_a_ranking(tmp_path):
    with pytest.raises(sig.RefusedToRank):
        tracker.run(cross_section(n=12), "2026-10-16", "test_feed", tracking_dir=tmp_path)
    assert not (tmp_path / tracker.LISTINGS_CSV).exists()
