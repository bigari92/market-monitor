"""The survivorship bound. Its central claim is algebraic, so it is tested algebraically.

The pessimistic case has a property worth pinning: the imputed return **cancels out**, so the
bound does not depend on guessing how badly delisted names did. If a future edit broke that,
the bound would silently become a function of an arbitrary assumption.
"""
import pandas as pd
import pytest

from market_monitor.cloud import survivorship as S


def test_pessimistic_bound_is_independent_of_the_imputed_return():
    """The algebra: (1-f)*top + f*r minus (1-f)*cohort + f*r leaves (1-f)*excess. The r cancels.

    This is the whole reason a bound is computable without the missing prices, so it is the one
    property that must not break.
    """
    bounds = [S.bound_excess(11.88, cohort_mean_pp=12.16, delisting_rate=0.10, severity=s)
              for s in ("total_loss", "severe", "neutral")]
    pessimistic = {round(b.pessimistic_pp, 9) for b in bounds}
    assert len(pessimistic) == 1, "the pessimistic bound must not depend on severity"
    assert bounds[0].pessimistic_pp == pytest.approx(0.90 * 11.88)


def test_overstatement_is_one_over_one_minus_f():
    b = S.bound_excess(10.0, cohort_mean_pp=12.0, delisting_rate=0.20)
    assert b.pessimistic_pp == pytest.approx(8.0)
    assert b.overstatement_factor == pytest.approx(1.25)


def test_a_perfect_filter_is_flattered_not_hurt():
    """If the signal avoids every delisting, removing survivorship bias RAISES the excess,
    because the benchmark it is measured against gets worse while the top N does not."""
    b = S.bound_excess(11.88, cohort_mean_pp=12.16, delisting_rate=0.10, severity="total_loss")
    assert b.optimistic_pp > b.measured_excess_pp
    # excess + f*(cohort - r) = 11.88 + 0.10*(12.16 - (-100))
    assert b.optimistic_pp == pytest.approx(11.88 + 0.10 * (12.16 + 100.0))


def test_the_neutral_severity_leaves_the_optimistic_end_untouched():
    """If delisting carries no return signal, a delisted name earns the cohort median, so
    removing it from the cohort changes nothing at the optimistic end."""
    b = S.bound_excess(11.88, cohort_mean_pp=12.16, delisting_rate=0.10, severity="neutral")
    assert b.imputed_return == pytest.approx(0.1216)
    assert b.optimistic_pp == pytest.approx(11.88)
    # The pessimistic end still bites, because the excess itself is diluted.
    assert b.pessimistic_pp == pytest.approx(10.692)


def test_zero_delisting_rate_is_a_no_op():
    b = S.bound_excess(11.88, 12.16, delisting_rate=0.0, severity="severe")
    assert b.pessimistic_pp == pytest.approx(11.88)
    assert b.optimistic_pp == pytest.approx(11.88)
    assert b.overstatement_factor == pytest.approx(1.0)


def test_severities_are_the_three_c3_asked_for():
    assert set(S.SEVERITIES) == {"total_loss", "severe", "neutral"}
    assert S.SEVERITIES["total_loss"] == -1.00
    assert S.SEVERITIES["severe"] == -0.50
    assert S.SEVERITIES["neutral"] is None   # resolved to the cohort median at call time


def test_bad_inputs_are_rejected():
    for rate in (-0.1, 1.0, 2.0):
        with pytest.raises(ValueError, match="delisting_rate must be"):
            S.bound_excess(10.0, 12.0, rate)
    with pytest.raises(ValueError, match="severity must be one of"):
        S.bound_excess(10.0, 12.0, 0.1, severity="whatever_is_convenient")


def test_bound_table_reports_all_three_beside_the_baseline():
    table = S.bound_table(11.88, 12.16, 0.10)
    assert list(table["severity"]) == ["total_loss", "severe", "neutral"]
    assert (table["measured_excess_pp"] == 11.88).all()
    # One pessimistic number across all three, three different optimistic ones.
    assert table["pessimistic_pp"].nunique() == 1
    assert table["optimistic_pp"].nunique() == 3


# --- the delisting rate ----------------------------------------------------


def test_delisting_rate_filters_securities_that_did_not_actually_leave():
    """Form 25 is filed per security and also on an exchange move, so a company still in the
    live universe must not count as a death."""
    form25 = pd.DataFrame({
        "cik": [1, 1, 2, 3, 4],        # cik 1 filed twice (two security classes)
        "year": [2015, 2015, 2015, 2015, 2015],
        "form": ["25"] * 5,
    })
    live = {3, 4}                      # 3 and 4 are still listed: moved exchange or delisted a
    out = S.delisting_rate(form25, live, universe_size=1000)   # non-common line
    row = out.iloc[0]
    assert row["form25_filings"] == 5
    assert row["distinct_ciks"] == 4
    assert row["gone_and_ticker_cleared"] == 2      # only 1 and 2
    assert row["rate_gone_%"] == pytest.approx(0.2)


def test_delisting_rate_uses_the_cleared_ticker_signal_when_given():
    """SEC clears a company's ticker on deregistration, which is the closest free proxy for
    'left and did not come back'."""
    form25 = pd.DataFrame({"cik": [1, 2], "year": [2015, 2015], "form": ["25", "25"]})
    # Neither is in the live universe, but cik 2 still has a ticker — so it is not confirmed gone.
    out = S.delisting_rate(form25, live_ciks=set(), ticker_present={1: False, 2: True},
                           universe_size=1000)
    assert out.iloc[0]["gone_and_ticker_cleared"] == 1
