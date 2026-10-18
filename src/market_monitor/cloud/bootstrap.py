"""C2 — the block bootstrap. The designated kill gate.

> **C2. Block bootstrap** — re-run the whole factor search per resample against the
> reconstructed trial count.
> **KILL GATE: p > 0.10 on the best configuration ends the prediction half.**

That condition is in this repository's **first commit**, written before any measurement in this
project existed. It is a pre-registration, not a bar chosen after seeing a number, and nothing
in this module may move it.

## What is being tested, and why the naive p-value cannot do it

Every other result here reports the significance of **one** configuration. The weight vector in
`signal.PRICE_W` was not handed down — it came out of a search across factors, weightings,
concentration levels and horizons. The probability that *the best of many tried* looks good by
chance is far higher than the probability that *one particular* configuration does, and no
single-configuration t-statistic can see that.

So two corrections are needed at once, and they pull in the same direction:

1. **Multiplicity.** White's (2000) **Reality Check**: under the null that no configuration has
   skill, build the distribution of the **maximum** statistic across all configurations searched,
   and compare the observed maximum to it. The null is imposed by demeaning each
   configuration's own series, and the same resampled blocks are used for every configuration,
   so the strong cross-configuration correlation (these factors overlap heavily — see
   `results/factor_redundancy.md`) is preserved rather than assumed away.
2. **Autocorrelation.** A monthly grid of 12-month forward returns has consecutive observations
   sharing 11/12ths of their window. An i.i.d. bootstrap would treat 190 near-duplicates as 190
   independent draws. A **circular block bootstrap** with block length ~12 resamples contiguous
   runs instead, so the dependence survives resampling.

## The honest limitation, stated before the result

**The true trial count is unknowable.** The recovered scripts document on the order of 50
configurations explicitly evaluated against forward returns (`reconstructed_trial_count`), but
the eight weights in `PRICE_W` are chosen numbers, and choosing them implies a search whose size
was never recorded. So the p-value is reported **as a function of the assumed trial count**, and
the gate is read against the documented count with the sensitivity beside it. A gate that
depended on a number nobody can know would not be a gate.

Nothing here is tuned. No configuration is adopted, dropped or re-weighted on the strength of
this file — CLOUD-RULES.md §5 — and the live signal is untouched whatever the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# The overlap in the validated horizon: 12-month returns on a monthly grid. Also the natural
# block length, since a block must be long enough to carry the dependence it is preserving.
DEFAULT_BLOCK = 12
DEFAULT_RESAMPLES = 5000

# The pre-registered bar, from the repository's first commit. Read, never set, by this module.
KILL_THRESHOLD = 0.10


@dataclass
class RealityCheck:
    """The result of one Reality Check: the observed maximum against its null distribution."""
    best_config: str
    observed_best: float
    n_configs: int
    n_periods: int
    block_length: int
    n_resamples: int
    p_reality_check: float          # corrected for searching n_configs
    p_single_config: float          # as if only the winner had ever been tried
    null_quantiles: dict = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        """True when the gate is cleared. The threshold is pre-registered, not chosen here."""
        return self.p_reality_check <= KILL_THRESHOLD

    def verdict(self) -> str:
        state = "PASS" if self.passes else "FAIL — KILL CONDITION MET"
        return (f"{state}: p_reality_check = {self.p_reality_check:.4f} against a "
                f"pre-registered threshold of {KILL_THRESHOLD:.2f} "
                f"({self.n_configs} configurations, block length {self.block_length})")

    def as_row(self) -> dict:
        return {
            "best_config": self.best_config, "observed_best": round(self.observed_best, 6),
            "n_configs": self.n_configs, "n_periods": self.n_periods,
            "block_length": self.block_length, "n_resamples": self.n_resamples,
            "p_single_config": round(self.p_single_config, 4),
            "p_reality_check": round(self.p_reality_check, 4),
            "passes": self.passes,
        }


def circular_block_indices(n_periods: int, block_length: int,
                           rng: np.random.Generator) -> np.ndarray:
    """Row indices for one circular-block resample of length `n_periods`.

    Circular rather than plain blocks so every observation has equal probability of selection;
    a non-circular scheme under-samples the ends of the series.
    """
    if block_length < 1:
        raise ValueError("block_length must be >= 1")
    n_blocks = int(np.ceil(n_periods / block_length))
    starts = rng.integers(0, n_periods, size=n_blocks)
    offsets = np.arange(block_length)
    picked = (starts[:, None] + offsets[None, :]).ravel() % n_periods
    return picked[:n_periods]


def reality_check(stats: pd.DataFrame, block_length: int = DEFAULT_BLOCK,
                  n_resamples: int = DEFAULT_RESAMPLES, seed: int = 20261018,
                  focus: str | None = None) -> RealityCheck:
    """White's Reality Check on a (periods x configurations) frame of per-period statistics.

    `stats` holds one column per configuration searched and one row per rebalance date, e.g. the
    per-date rank IC. The null is "no configuration has any skill", imposed by demeaning each
    column; the alternative is that the best one does.

    `focus` names the configuration whose single-configuration p-value is also reported — the
    one actually shipped, which is not always the best in sample.
    """
    if stats.empty or stats.shape[1] == 0:
        raise ValueError("no configurations to check")
    clean = stats.dropna(axis=0, how="any")
    if len(clean) < 3 * block_length:
        raise ValueError(
            f"{len(clean)} periods cannot support block length {block_length}; "
            "the bootstrap would resample almost the whole series as one block"
        )

    values = clean.to_numpy(dtype=float)
    observed = values.mean(axis=0)
    best_index = int(np.argmax(observed))
    best_config = str(clean.columns[best_index])
    focus_index = (list(clean.columns).index(focus) if focus in clean.columns else best_index)

    # Impose the null: every configuration has mean zero, dependence structure untouched.
    centred = values - observed

    rng = np.random.default_rng(seed)
    n_periods = len(clean)
    null_max = np.empty(n_resamples)
    null_focus = np.empty(n_resamples)
    for b in range(n_resamples):
        idx = circular_block_indices(n_periods, block_length, rng)
        means = centred[idx].mean(axis=0)
        null_max[b] = means.max()
        null_focus[b] = means[focus_index]

    p_rc = float((null_max >= observed[best_index]).mean())
    p_single = float((null_focus >= observed[focus_index]).mean())

    return RealityCheck(
        best_config=best_config, observed_best=float(observed[best_index]),
        n_configs=int(clean.shape[1]), n_periods=n_periods, block_length=block_length,
        n_resamples=n_resamples, p_reality_check=p_rc, p_single_config=p_single,
        null_quantiles={f"p{int(q * 100)}": float(np.quantile(null_max, q))
                        for q in (0.5, 0.9, 0.95, 0.99)},
    )


def pvalue_vs_trial_count(stats: pd.DataFrame, trial_counts: tuple[int, ...],
                          block_length: int = DEFAULT_BLOCK,
                          n_resamples: int = 2000, n_subsets: int = 40,
                          seed: int = 20261018) -> pd.DataFrame:
    """The Reality Check p-value as a function of how many configurations are assumed searched.

    The true trial count is unknowable (see the module docstring), so the gate is read with this
    beside it. For each assumed count `n`, random subsets of that size are drawn — always
    including the in-sample winner, because a real search that found it necessarily contained it
    — and the p-values averaged. Reported so the reader can see how large the search would have
    to have been to change the verdict.
    """
    clean = stats.dropna(axis=0, how="any")
    observed = clean.to_numpy(dtype=float).mean(axis=0)
    winner = int(np.argmax(observed))
    others = [i for i in range(clean.shape[1]) if i != winner]
    rng = np.random.default_rng(seed)

    rows = []
    for n in trial_counts:
        n = min(n, clean.shape[1])
        ps = []
        repeats = 1 if n >= clean.shape[1] else n_subsets
        for _ in range(repeats):
            extra = rng.choice(others, size=n - 1, replace=False) if n > 1 else []
            columns = clean.columns[[winner, *np.atleast_1d(extra).astype(int)]]
            ps.append(reality_check(clean[columns], block_length, n_resamples,
                                    seed=int(rng.integers(1, 2**31))).p_reality_check)
        rows.append({"assumed_trials": n, "p_reality_check": float(np.mean(ps)),
                     "p_sd_across_subsets": float(np.std(ps)) if len(ps) > 1 else 0.0,
                     "passes": float(np.mean(ps)) <= KILL_THRESHOLD})
    return pd.DataFrame(rows)


# --- the reconstructed trial count ----------------------------------------

RECONSTRUCTED_TRIALS = {
    "run_backtest.py: single-factor rank IC": 8,
    "run_asymmetry.py: factors tested in the high-vol cohort": 15,
    "run_algo.py: composite variants A/B/C": 3,
    "run_algo_v3.py: v2 / v3 / v3-strict": 3,
    "run_algo_v4.py: v2-z plus four v4 modes": 5,
    "run_concentration.py: 4 top-N levels x 3 modes": 12,
    "horizon_test.py: 3-month and 12-month horizons": 2,
    "retest_fundamentals.py: fundamental factors IC'd": 10,
    "run_model.py / run_model2.py: 2 models, 2 label thresholds": 4,
}


def reconstructed_trial_count() -> dict:
    """What the recovered scripts document having evaluated against forward returns.

    A floor, not an estimate. It counts configurations that appear explicitly in the recovered
    code. It cannot count the search behind `PRICE_W`'s eight chosen weights, which is the
    largest unrecorded part, so the true count is higher by an unknown factor.
    """
    total = sum(RECONSTRUCTED_TRIALS.values())
    return {
        "documented_total": total,
        "by_script": dict(RECONSTRUCTED_TRIALS),
        "uncounted": ("the eight weights in PRICE_W are chosen values (1.0 / 0.75 / 0.5 / "
                      "-0.75). Choosing them implies a search whose size was never recorded, "
                      "and FUND_W's weights were set from residual IC measured on the same "
                      "data, which is a fit rather than a trial but spends the same degrees of "
                      "freedom."),
        "treat_as": "a floor; report p against assumed counts well above it",
    }
