# C2 — the block bootstrap kill gate: **PASS**

**Run:** 2026-10-18. 190 monthly rebalance dates (2010-01 … 2025-10), 40 candidate
configurations, circular block bootstrap at 5,000 resamples (20,000 for the headline), block
lengths 6 / 12 / 24, both horizons.

**Verdict: the gate passes, decisively. p < 0.00005 at every block length and both horizons.**

The pre-registered condition and the rule for reading it were committed in `ab5f6f7`, **before
this result existed**. The condition itself is in the repository's first commit (`e355d76`).

---

## 1. The condition, and that it was not moved

From `docs/CREDIT-LEDGER.md`, first commit:

> **C2. Block bootstrap** — re-run the whole factor search per resample against the
> reconstructed trial count.
> **KILL GATE: p > 0.10 on the best configuration ends the prediction half.**

`bootstrap.KILL_THRESHOLD` reads 0.10 and a test asserts it. The three block lengths and two
horizons below were specified in the pre-registration commit and **all of them are reported**.

## 2. The result

| horizon | block | best configuration | observed mean IC | p (single config) | **p (Reality Check)** | |
|---|---|---|---|---|---|---|
| 12-month | 6 | `m:rank_fund` | +0.1585 | <0.00005 | **<0.00005** | PASS |
| 12-month | **12** | `m:rank_fund` | +0.1585 | <0.00005 | **<0.00005** | **PASS** |
| 12-month | 24 | `m:rank_fund` | +0.1585 | <0.00005 | **<0.00005** | PASS |
| 3-month | 6 | `-f:vol_6m` | +0.1007 | <0.00005 | **<0.00005** | PASS |
| 3-month | **12** | `-f:vol_6m` | +0.1007 | <0.00005 | **<0.00005** | PASS |
| 3-month | 24 | `-f:vol_6m` | +0.1007 | <0.00005 | **<0.00005** | PASS |

p is reported as `<0.00005` rather than `0.0000`: **a bootstrap p-value cannot be zero**, it is
bounded below by 1/B, and with 20,000 resamples that floor is 0.00005. Reporting "0" would
overstate the precision of the method.

Sensitivity to the assumed trial count — the thing the gate is correcting for — is flat because
the margin is so large:

| assumed trials searched | 1 | 5 | 10 | 20 | 40 |
|---|---|---|---|---|---|
| p (Reality Check) | <0.0005 | <0.0005 | <0.0005 | <0.0005 | <0.0005 |

## 3. Why p is that small, checked rather than assumed

A p-value of zero across every setting is the shape a bug makes, so it was verified two ways.

**The null distribution does not reach the observation.** Over 20,000 resamples of the
demeaned series:

| null distribution of the maximum mean IC | value |
|---|---|
| median | 0.0392 |
| 90th percentile | 0.0610 |
| 95th percentile | 0.0682 |
| 99th percentile | 0.0840 |
| **largest of 20,000** | **0.1317** |
| **observed** | **0.1585** |

The observation sits **7.8 standard deviations above the null mean and above the largest of
20,000 null maxima.** There is no resample in which a skill-free search produced what was
observed.

**It agrees with the independent Newey-West work.** The same IC series, measured by a different
method in `results/horizon_test.md`, reproduces exactly:

| | this run | horizon_test.md |
|---|---|---|
| `m:price` mean IC (12m) | 0.1475 | 0.1475 |
| t, Newey-West | +5.23 | +5.23 |
| t, non-overlapping (n=15) | +4.21 | +4.21 |

A t-statistic of 4–5 is a single-configuration p of order 1e-4. Correcting that for 40 heavily
correlated trials moves it very little, so a Reality Check p below 1/20,000 is **consistent with
what was already known, not a new and surprising claim.** The gate's contribution is to confirm
that the search did not manufacture the result — not to discover the result.

## 4. What the pass does and does not establish

**It establishes:** the ranking ability is not an artefact of having searched. The 62
documented configurations (and whatever larger number the `PRICE_W` weight choices imply) are
not enough to explain an IC this far from the null.

**It does not establish that the strategy makes money.** Rank IC measures ordering ability. Three
things already measured stand entirely unchanged by this result:

- **~15 independent observations.** The 12-month excess rests on 15 non-overlapping windows
  (`results/horizon_test.md`). The gate adds no degrees of freedom; it only rules out one
  specific alternative explanation.
- **Survivorship.** The IC is computed on a survivor-only universe, and unlike the excess return
  in `results/survivorship.md` the *direction* of that bias on IC is not even signable: it
  depends on how the missing names would have ranked, which is unmeasurable without their
  tickers. **The bound in C3 covers the excess return, not this IC.**
- **Costs.** 16–29% of the gross excess (`results/cost_model.md`). The gate is on gross
  ordering ability and says nothing about what survives execution.

And the standing rule is untouched: **no probability and no expected return is displayed**, for
the measured reasons in `signal.py`.

## 5. Two findings the gate turned up, neither of them acted on

### The best configuration is not the one shipped — and the shipped one is right anyway

`m:rank_fund` has the highest 12-month IC (0.1585) against the shipped `m:price` (0.1475), which
ranks **4th of 40**. That looks like an argument for switching, and it is not, because
`results/fundamentals_modes.md` already measured what matters:

| | 12m rank IC | 12m top-25 excess vs price |
|---|---|---|
| `m:price` (shipped) | 0.1475 | — |
| `m:rank_fund` | **0.1585** | **−1.05pp** |

**Higher IC across the whole cohort, worse selection at the top.** IC rewards ordering the entire
distribution correctly; the strategy only ever buys 25 names. A configuration can order the
cohort better and still pick worse from its own head, and that is exactly what this pair does.
The two measurements are not in conflict — they are measuring different things, and the one that
pays is the second.

### Low volatility inside the high-volatility cohort is the strongest single factor

Two single factors beat the shipped composite on IC at 12 months, and one beats every composite
at 3 months:

| configuration | 12m IC | 3m IC |
|---|---|---|
| `-f:vol_6m` (low 6-month volatility) | 0.1499 | **0.1007** (best overall) |
| `-f:vol_12m` (low 12-month volatility) | 0.1491 | — |
| `m:price` (shipped 8-factor composite) | 0.1475 | — |

Within the top volatility quintile, the **less** volatile names rank better — the low-volatility
anomaly appearing inside a cohort selected for being volatile. `vol_12m` is used by the signal
only as a *gate*, never as a scored factor, so the composite leaves this on the table. A
plausible mechanism is simple regression toward the middle: "the calmest of the wild" may just be
names whose volatility is mean-reverting. That is a hypothesis, not a finding.

**Nothing is done about either.** Adding a volatility term, or switching mode, is a **new
configuration and therefore a new trial** — and a trial spent *after* seeing the gate's output is
the worst kind, because the gate can no longer price it. CLOUD-RULES.md §5 forbids it
independently. Both are recorded here for the owner, who can decide whether to spend a future
pre-registered trial on them.

## 6. What this unlocks

C2 was the binding item: *"until C2 runs, none of the measured figures is established."* It has
run and it passed, so:

- The measured figures are established **to the extent the gate covers them** — i.e. the ordering
  ability is real; the return magnitude still carries the caveats in §4.
- **The Sharadar question is now live.** `results/survivorship.md` §6 recommended waiting for C2
  precisely because a FAIL would have made the purchase pointless. It passed, so the condition
  it was waiting on is met: USD 199/yr for Sharadar Prices (10-year) would convert the
  survivorship *bound* into a measurement and allow a backtest that is not survivor-only. That
  is now a reasonable purchase — and still **not one a session can make**: USD 47 remains, and a
  paid key arrives as an environment variable that is never committed (CLOUD-RULES.md §4).

## 7. Reproducing it

```bash
python -m market_monitor.cloud.run c2          # re-runs the gate from the cached IC series
```

The IC series are in `results/c2_ic_by_date_12m.csv` and `..._3m.csv` (190 dates x 40
configurations); full output in `results/c2_bootstrap_stats.json` and
`results/c2_sensitivity.csv`. Regenerating the IC series from the panel takes ~35 minutes.

The machinery is calibrated in both directions in `tests/test_bootstrap.py`: 40 correlated
skill-free series do **not** clear the gate, one genuinely skilful configuration among 39 noise
ones does, a nested wider search makes the same winner less impressive, and block bootstrapping
is never more permissive than i.i.d. on an autocorrelated series.
