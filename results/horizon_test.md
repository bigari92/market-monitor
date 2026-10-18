# Horizon test — does the signal say anything at 3 months?

**Run:** 2026-10-18. 20-year panel (7,158 names, 5,031 sessions, 2006-10-17 .. 2026-10-16),
6,936 after the instrument filter. **190 monthly rebalance dates, 2010-01 .. 2025-10**, 63,176
scored name-dates. Signal version `383a5e2a568e`, unchanged throughout.

`recovered/horizon_test.py` asked this question and its *results* were never recovered — only the
script. It was the one thing blocking the tracker's review cadence, so it was measured.

**Verdict: yes, and the part that matters works better at 3 months than at 12.** Monthly review
is supported by measurement rather than by convention. The reasoning is in §5, and the reason it
is *not* a licence to trade quarterly is in §6.

---

## 1. Rank IC of the score

| horizon | mean IC | median IC | months positive | n dates | t naive | t Newey-West | t non-overlapping | independent obs |
|---|---|---|---|---|---|---|---|---|
| **3-month** | 0.0958 | 0.1018 | 74.2% | 190 | 9.36 | **5.95** | **5.39** | **63** |
| **12-month** | 0.1475 | 0.1732 | 83.2% | 190 | 14.30 | **5.23** | **4.21** | **15** |

The 12-month IC is the larger number and the **less certain** one. 190 monthly dates of
12-month returns contain only about 15 independent observations, because consecutive windows
share 11/12ths of their span; at 3 months they contain 63. More independent observations beat a
bigger point estimate.

**RECOVERY.md defect 3, demonstrated on live data.** The naive t-statistic — the one the
recovered script computes — is inflated **3.4×** at the 12-month horizon (14.30 → 4.21) and
1.7× at 3 months (9.36 → 5.39). The inflation is worst exactly where the recovered research drew
its conclusions. Newey-West and the non-overlapping subsample agree closely at both horizons,
which is what makes the correction believable rather than an artefact of either method.

## 2. What the top 25 actually did

| horizon | top-25 mean | cohort mean | excess | top-25 P(+50%) | cohort P(+50%) | **up-tail lift** | top-25 P(−30%) | cohort P(−30%) | **down-tail cut** |
|---|---|---|---|---|---|---|---|---|---|
| **3m** | +6.44% | +2.62% | +3.83pp | 5.68% | 5.93% | **0.96×** | 6.53% | 12.56% | **1.92×** |
| **12m** | +24.03% | +12.16% | +11.88pp | 23.05% | 20.41% | **1.13×** | 17.47% | 27.53% | **1.58×** |

Significance of the two quantities, by the honest standard errors:

| | 3-month | 12-month |
|---|---|---|
| excess return | +3.83pp, t_NW +4.00, **t_nonoverlap +3.51** | +11.88pp, t_NW +2.82, **t_nonoverlap +2.31** |
| down-tail reduction | +6.03pp, t_NW +7.02, **t_nonoverlap +5.65** | +10.06pp, t_NW +4.91, **t_nonoverlap +3.52** |

## 3. The loser-filter thesis, independently confirmed — and sharpened

The owner's prior research found that conditional on the volatility cohort, trend quality barely
moves the up-tail (18.7% → 21.9%) and roughly halves the down-tail (48.3% → 23.4%). This is a
separate 20-year sample, a separate implementation, and it reproduces the shape exactly:

**At 3 months the up-tail lift is 0.96× — that is not a small edge, it is no edge at all, very
slightly negative.** The top 25 is *no more likely* to produce a +50% move than the cohort it was
drawn from. At 12 months it manages 1.13×, which is barely anything either.

**The entire measurable edge is the down-tail, and it is strongest at the short horizon:** the
top 25 cuts the frequency of a −30% move by **1.92×** at 3 months versus 1.58× at 12 months,
with a higher t-statistic (5.65 vs 3.52).

The signal does not find winners. It declines to rank names that are falling apart. Anyone
reading the +24% 12-month top-25 mean as stock-picking skill has the mechanism backwards — it is
the same cohort, with fewer disasters in it.

### It is consistent, not a single-regime artefact

- **The down-tail cut is positive in 15 of 16 calendar years** at both horizons.
- The top 25 beat its cohort in 13 of 16 years at 3 months, 12 of 16 at 12 months.
- **Excluding 2020 entirely, everything survives and slightly strengthens:** 3m excess +3.77pp
  (t 3.59), down-tail cut +6.19pp (t 5.73); 12m excess +13.55pp (t 2.60), cut +11.27pp (t 4.17).

The clearest illustration is the worst year in the sample. In 2021 the gated cohort returned
**−37.9%** over 12 months with 69.2% of names suffering a −30% drawdown. The top 25 returned
**−18.7%** with 49.7%. It lost half as much. That is the product working as designed — and it
is also why the product must never be sold as a growth-finder.

| worst cohort years (12m) | top-25 mean | cohort mean | top-25 P(−30%) | cohort P(−30%) |
|---|---|---|---|---|
| 2021 | −18.7% | −37.9% | 49.7% | 69.2% |
| 2022 | −2.7% | −13.1% | 30.0% | 44.2% |
| 2015 | **−11.5%** | **−7.1%** | 26.0% | 31.9% |

2015 is the honest counter-example and is left in: the filter made things *worse* that year.

## 4. Base rates in the gated cohort

| horizon | P(+50%) | P(−30%) | mean | median |
|---|---|---|---|---|
| 3m | 6.51% | 14.23% | +2.09% | −1.04% |
| 12m | 20.51% | 30.30% | +11.21% | −3.52% |

Note the gap between mean and median at both horizons: the cohort's average is carried by a
minority of large winners while the typical name loses money. That is the distribution the
volatility gate deliberately selects for, and it is why a down-tail filter is worth more here
than an up-tail predictor would be.

## 5. The cadence verdict: monthly

Three reasons, in order of weight:

1. **The signal carries genuine 3-month information.** IC 0.096, positive in 74% of 190 months,
   t = 5.4 on 63 independent observations. A monthly-refreshed ranking is informative, not noise,
   so a monthly review is reading signal rather than reshuffling.
2. **The exit rules are better supported at short horizons than at long ones.** Exits exist to
   catch deterioration, and deterioration is precisely what the down-tail measures — 1.92× at 3
   months against 1.58× at 12, better identified. The one function the tracker performs on review
   is the function that works best at the cadence being chosen.
3. **Identification, not magnitude, is the binding constraint.** The 12-month horizon offers 15
   independent observations in 20 years. Monthly review accumulates evidence about the tracker's
   own calls four times faster, and `results/tracking/` is the only unbiased dataset this project
   will ever own.

Weekly was never a serious candidate and the measurement does not rescue it: nothing here speaks
to horizons below 63 trading days, and the exit rules are deliberately built to ignore the rank
noise a weekly cadence would surface.

`docs/TRACKER.md` §6 is updated from "recommended" to "measured".

## 6. What this does NOT license, stated plainly

**It is not permission to trade quarterly.** A 3-month holding period means roughly **4× the
turnover** of a 12-month one, and **nothing here deducts commission, spread or tax** —
RECOVERY.md defect 4 is still open. Every figure in §2 is gross. A gross comparison structurally
flatters the shorter horizon, because it charges it nothing for trading four times as often. On
these numbers it is simply not possible to say whether 3-month rebalancing beats 12-month
rebalancing net of costs, and this file does not claim it.

The distinction that makes the verdict safe: **reviewing monthly is not trading monthly.** The
exit rules fire on structural breaks, not rank drift, so a listing remains a long-horizon thesis
that gets *checked* often. The 24-month replay bears that out — 4 to 13 exits a month from a
watchlist of 28 to 38, not wholesale rotation.

**The absolute levels are inflated by survivorship and should not be quoted.** The universe is
today's registrants, so names that went to zero are absent (RECOVERY.md defect 1). Two
consequences:

- No number in §2 or §4 is an expected return, and none should be repeated outside this file.
- The distortion is **worse at 12 months than at 3**. Conditioning on survival to 2026 truncates
  a long forward window more than a short one — a survivor cannot have had a −100% twelve-month
  return, while it can easily have had a −50% quarter and recovered. So part of the 12-month IC
  advantage (0.1475 vs 0.0958) is bias rather than signal, which if anything strengthens the
  case for the shorter horizon.

**No probability here is a forecast.** These are historical frequencies on a biased sample,
reported in a research file. Nothing from this analysis reaches the tracker's output, which still
displays no probability at all, and `signal.assert_no_probability_columns` still enforces that.

**No parameter was changed to produce any of this.** The signal ran at version `383a5e2a568e`
throughout — the same weights, thresholds and gate as the live run. Two horizons were measured on
one fixed signal; no configuration was searched, so nothing here adds to the multiple-testing
count that package C2 is meant to score against (CLOUD-RULES.md §5).

## 7. Reproducing it

```bash
python -m market_monitor.cloud.run --years 20 horizon
```

~3 minutes to fetch the 20-year panel, ~6 minutes to score 190 dates. Per-date output is in
`results/horizon_selection_by_date.csv` and `results/horizon_ic.csv`. The statistics — Newey-West,
the non-overlapping subsample, and Spearman-without-scipy — are tested in `tests/test_horizon.py`
against properties that must hold, including that a 12-fold overlap inflates a naive t by more
than 2×.

A note on the panel span: `range=max` **cannot** be used to get a longer one. Asked for
`max` with `interval=1d` the endpoint returns 261 bars spanning 1962–2026 — roughly quarterly —
with HTTP 200 and no indication the granularity changed. `20y` works correctly. The feed now
measures the median bar gap and refuses a panel that comes back coarser than daily.
