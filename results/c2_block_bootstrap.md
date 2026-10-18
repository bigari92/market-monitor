# C2 — the block bootstrap kill gate

**Status: RUNNING.** This file was committed *before* the result, with the interpretation rule
written down, so that the verdict cannot be shaped after the fact. The numbers follow in a second
commit.

## The pre-registered condition

From `docs/CREDIT-LEDGER.md`, in **this repository's first commit** (`e355d76`), before any
measurement in this project existed:

> **C2. Block bootstrap** — re-run the whole factor search per resample against the
> reconstructed trial count.
> **KILL GATE: p > 0.10 on the best configuration ends the prediction half.**

> **C2 is a gate, not a line item.** Its kill condition is written above, before it runs.

## How I will read the result — decided in advance

**If p ≤ 0.10 — the gate passes.** The edge survives correction for the search that produced it.
This is not a vindication of anything else: the ~15 independent observations
(`results/horizon_test.md`), the 8.4% survivorship overstatement
(`results/survivorship.md`) and the 16–29% cost haircut (`results/cost_model.md`) all still
stand, and the figure still may not be displayed as an expected return.

**If p > 0.10 — the kill condition is met and the prediction half ends.** Then:

- I will report it plainly as a FAIL. The ledger says it ends the prediction half, and it does.
- **I will not search for a variant that passes.** Trying configurations until one clears the
  gate is precisely the behaviour the gate exists to penalise, and it would invalidate the gate
  itself. CLOUD-RULES.md §5 forbids it independently.
- I will not re-run with a different block length, horizon, or candidate set *in order to* get a
  different answer. The three block lengths (6, 12, 24) and two horizons are specified here in
  advance, and all of them get reported whatever they say.
- What survives a FAIL is the **recording** half, not the prediction half: `results/tracking/`
  is an unbiased point-in-time dataset accumulating at zero cost, and it remains worth keeping
  even if the signal's edge is unproven. The tracker would become an instrument for finding out,
  rather than a thing that already knows.

## Method, specified in advance

- **Statistic:** per-date rank IC between a configuration's score and the realised forward
  return, on the gated cohort, averaged over 190 monthly rebalance dates (2010-01 … 2025-10).
- **Null:** no configuration has skill, imposed by demeaning each configuration's own IC series.
- **Multiplicity:** White (2000) Reality Check — the null distribution of the **maximum** mean IC
  across all configurations searched, resampled jointly so the heavy cross-configuration
  correlation is preserved rather than assumed away.
- **Dependence:** circular block bootstrap, 5,000 resamples, block lengths **6, 12 and 24**
  reported. 12 is the overlap in the validated horizon.
- **Candidate set:** all 18 factors in both directions (a real search would flip a factor with a
  negative IC) plus the four pre-specified `algo_v4` composites — 40 configurations.
- **Trial count:** the recovered scripts document **62** configurations evaluated against
  forward returns, and that is a **floor**: the eight weights in `PRICE_W` are chosen values and
  the search behind them was never recorded. The p-value is therefore reported against a range
  of assumed trial counts, not one number.

Nothing in the live signal changes on the strength of this file, whatever it says.
