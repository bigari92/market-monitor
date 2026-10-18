# Do the fundamentals improve selection? No — and that confirms the recovered decision

**Run:** 2026-10-18. 190 monthly rebalance dates, 2010-01 .. 2025-10, on the 20-year price panel
joined to the as-filed fundamental panel (`results/fundamentals_build.md`). Four configurations,
each scored on the same dates against the same reference cohort.

**Verdict: keep price-only.** No fundamental configuration beats it on mean return at either
horizon, and none of the differences is distinguishable from zero. `recovered/screen_v4.py`
concluded the same thing in Sept 2026 — "they did not improve selection, so they are reported,
not scored" — and that decision now survives re-testing on a strictly harder dataset.

**The live signal is unchanged and stays on `price`.** Nothing in this file was used to select it;
the status quo won, so there is no selection to worry about.

---

## 1. Why this is a confirmation and not a repetition

The recovered comparison ran on frames data with `avail_date = period_end + 90 days`. Two
consequences, both of which flattered the fundamental modes:

- **Restated values.** A frames fact comes from the entity's last filed submission, and 9.59% of
  figures are later restated (median change 5%, p90 104% — measured in
  `results/fundamentals_build.md` §1). A restated number is a *better* number, so a signal
  reading it early is being handed hindsight.
- **Lookahead on the comparative-only rows.** For the 12.8% of periods that first appear as a
  prior-year comparative in a later filing, `period_end + 90 days` dates a figure as knowable
  about ten months before any filing reported it.

Both are removed here: as-originally-filed values, dated by the real `filed` date. So the
fundamental modes are being tested without the two advantages they previously had — and they
come out slightly *worse* than price-only, which is the direction that change predicts.

## 2. The four configurations

Pre-specified in `recovered/run_algo_v4.py`; `FUND_W`, `EXCL_R40` and `EXCL_INSTAB` ported
verbatim. `price` is the reference cohort for every excess figure.

| mode | top-25 mean 12m | excess 12m | t (NW) | t (non-overlap) | top-25 mean 3m | excess 3m | t (NW) | t (non-overlap) |
|---|---|---|---|---|---|---|---|---|
| **price** | **24.03%** | +11.88pp | +2.82 | **+2.31** | **6.44%** | +3.83pp | +4.00 | **+3.51** |
| rank_fund | 22.98% | +10.82pp | +2.86 | +2.31 | 5.64% | +3.03pp | +3.35 | +2.91 |
| filter | 23.94% | +11.79pp | +2.79 | +2.24 | 6.40% | +3.78pp | +4.00 | +3.43 |
| both | 22.73% | +10.58pp | +2.86 | +2.28 | 5.39% | +2.77pp | +3.03 | +2.68 |

Independent observations: **15** at the 12-month horizon, **63** at 3 months. Per
`results/horizon_test.md`, the 3-month column is the better-identified one.

## 3. Paired against price-only, on the same dates

A paired test, because comparing two mode-level averages ignores that both saw the same market —
and nearly all the variance is the market.

| mode | 12m difference | t (NW) | t (non-overlap) | dates better | 3m difference | t (NW) | t (non-overlap) | dates better |
|---|---|---|---|---|---|---|---|---|
| rank_fund | **−1.05pp** | −0.52 | −0.33 | 44.7% | **−0.80pp** | −1.49 | −1.11 | 40.0% |
| filter | **−0.09pp** | −0.18 | −0.19 | 41.1% | **−0.04pp** | −0.17 | −0.16 | 43.7% |
| both | **−1.30pp** | −0.64 | −0.44 | 46.8% | **−1.06pp** | −1.71 | −1.37 | 39.5% |

**Every difference is negative, and every one is indistinguishable from zero** (largest |t| is
1.71, on the mode that does worst). Each mode also beats price on fewer than half the dates.

The `filter` mode is interesting for being almost exactly neutral: −0.09pp at 12 months,
−0.04pp at 3. It drops names without changing the outcome.

## 4. The one thing the fundamentals do measurably: a slightly better down-tail

The owner's prior research says the fundamental payoff is "concentrated in avoiding a bad tail,
not in ranking the good end, which argues for an exclusion rather than a tilt". That claim is
supported in **direction**, and it is small:

| mode | top-25 P(−30%) | cohort P(−30%) | down-tail cut | t (non-overlap) | top-25 P(+50%) |
|---|---|---|---|---|---|
| price | 17.47% | 27.53% | 10.06pp | +3.52 | **23.05%** |
| rank_fund | 16.95% | 27.53% | 10.58pp | **+4.74** | 22.32% |
| filter | 17.41% | 27.53% | 10.12pp | +3.66 | 22.86% |
| **both** | **17.10%** | 27.53% | **10.44pp** | **+4.96** | 22.08% |

`both` and `rank_fund` cut the down-tail slightly more than price does and, more notably, do it
**more consistently** — the t-statistic on the cut rises from 3.52 to 4.96.

But the trade is visible in the same table: the up-tail falls from 23.05% to 22.08%, and the mean
return falls with it. **The fundamentals shave a little off both tails.** Since the down-tail cut
gains (+0.4pp) less than the up-tail loses (−1.0pp), the net effect on the mean is the small
negative in §3. The thesis is right about *where* the information sits and wrong about it being
worth scoring.

## 5. Coverage is the binding limitation, and it is stated rather than worked around

The fundamental join reaches a **median of 106 of 324 gated names (33%)** across 2010–2025. For
the other two thirds the fundamental terms contribute a centred rank of zero — i.e. those names
score as median on every fundamental factor, which dilutes any real effect toward nothing.

Coverage improves markedly over the window, and so does the exclusion's bite:

| era | median cohort | names dropped by the exclusion |
|---|---|---|
| 2010–2014 | 223 | 8 (3.6%) |
| 2015–2019 | 312 | 34 (10.9%) |
| **2020–2025** | 436 | **93 (21.3%)** |

So in the recent era the exclusion is removing a fifth of the cohort — it is doing real work —
and still produces no improvement (2020–2025 paired difference: `filter` −0.73pp, `both`
−4.54pp).

**The per-era numbers are reported but must not be read as evidence.** An era holds 5 independent
12-month observations; every per-era |t| is below 1.2, including the ones with the largest point
estimates. The era split exists to show that the conclusion does not depend on the thin early
years, not to find an era where fundamentals work. (The split is by calendar time, chosen before
looking at the result, not by outcome.)

## 6. What was and was not tested

**Four configurations, zero new ones.** `price`, `rank_fund`, `filter`, `both` are exactly the
four `recovered/run_algo_v4.py` compared. No weight in `FUND_W` was changed, `EXCL_R40` and
`EXCL_INSTAB` were not moved, and no fifth variant was invented. Those four trials were spent in
Sept 2026; re-measuring the same four on a differently-built panel is an out-of-sample test of a
decision already made, not a new search, so it adds nothing to the multiple-testing count that
package C2 is meant to score against (CLOUD-RULES.md §5).

Had any mode won, the right response would have been to report it and let the owner decide, not
to switch the signal. It did not win, so even that question does not arise.

**Still untested, and worth naming:** this measures the fundamentals as `algo_v4` uses them — a
rank tilt and a two-threshold exclusion on `rule40` and `rev_stability`. It says nothing about
whether some *other* use of as-filed fundamentals would help. That would be new configurations
and therefore new trials, and belongs behind the block bootstrap rather than in front of it.

## 7. What this does not change

Everything in `results/horizon_test.md` and `results/factor_redundancy.md` stands: the signal is a
loser-filter, the edge is in the down-tail, and the live configuration is the price-only v4
composite at `signal_version` `383a5e2a568e`.

What the fundamentals are now good for is **context** — which is exactly what `screen_v4.py` used
them for. The tracker's run report carries `rule40`, operating margin, revenue growth and revenue
instability beside each listed name, plus the SIC sector mix, none of it scored. The first thing
that context shows is worth seeing: three of the live top 25 — **IOVA** (revenue instability
+93.5 against a 0.80 threshold), **RLAY** (`rule40` −29.8) and **MRNA** (`rule40` −1.77, both
against a −1.0 threshold) — sit past the recovered exclusion thresholds. The price composite
ranks all three inside the top 20. On this evidence excluding them would not have improved
returns, but the owner can now see that the composite is ranking three companies whose
fundamentals are in poor shape, and decide what to do with that himself.

## 8. Reproducing it

```bash
python -m market_monitor.cloud.run fundamentals          # build the panel first
python -m market_monitor.cloud.run --years 20 modes      # ~20 min for 190 dates x 4 modes
```

Per-date output in `results/mode_test_by_date.csv`, the summary in
`results/mode_test_summary.csv`. The statistics are the same tested ones used by the horizon
test (`tests/test_horizon.py`), and `tests/test_signal_contract.py` holds that a cross-section
with no fundamentals joined scores identically in all four modes — so a join miss shows up as a
join miss rather than quietly altering a ranking.
