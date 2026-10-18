"""The signal: `recovered/algo_v4.py` in price-only mode, ported with its definition pinned.

## What this is, and the one thing it is not

It is a **loser-filter**, and the owner's own research is what says so. Conditional on a name
being capable of a big move (the volatility gate), trend quality barely moves the up-tail
(18.7% -> 21.9%) and roughly halves the down-tail (48.3% -> 23.4%). The composite earns its keep
by declining to rank names that are falling apart, not by finding winners.

It is **not** a probability, and this module cannot be made to emit one. An isotonic calibrator
fitted on one regime carried a Brier score of 0.120 into another regime where it scored 0.189 —
worse than not calibrating. `assert_no_probability_columns` is called on every output frame so a
later edit cannot reintroduce one by accident.

The published +37.8%/yr against +14.6% rests on roughly **7 effective annual observations**
(t ~ 2.64) over a survivor-only universe. It is not an expected return and must never be shown as
one. No function here reports performance.

## Ported faithfully; three things deliberately not carried over

`PRICE_W`, `MIN_PRICE`, `MIN_ADV`, the gate and `cs_rank` are byte-for-byte the recovered values.
CLOUD-RULES.md §5 forbids re-weighting or threshold search, so nothing here is tunable by design:
the weights are a module constant, not a parameter.

1. **The fundamental block (`FUND_W`, `EXCL_R40`, `EXCL_INSTAB`) is absent.** It needs `rule40`,
   `rev_stability` and `net_margin` from the SEC datasets, which are not built yet. `run_algo_v4`
   found the price-only mode competitive, and `recovered/screen_v4.py` — the production screen —
   ran `mode="price"` with fundamentals attached *for context only*, "they did not improve
   selection, so they are reported, not scored". Price-only is therefore the validated
   configuration and not a shortcut.
2. **`screen_v4.py`'s industry-momentum overlay is absent.** It added
   `(industry_percentile - 0.5) * 1.0` to the score from a `nasdaq_screener.csv` industry column.
   That file came from the Nasdaq screener endpoint, which does not serve bulk downloads from
   this environment (results/price_feed_probe.md §2). Approximating industry from SIC codes would
   change the signal, and changing the signal to work around missing data is the tuning §5 bans.
   So the overlay is omitted, the omission is declared, and `signal_version()` hashes
   `industry_overlay: false` so a run with it can never be confused with a run without it.
3. **`mom_36` NaN handling stays as recovered** — `fillna(0.0)` inside `_derive`. A name without
   three years scores neutral on the long-term reversal terms rather than being excluded.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# The definition. Every value here is the recovered one. Not parameters.
# ---------------------------------------------------------------------------

PRICE_W: dict[str, float] = {
    "pct_of_52w_high": 1.0,
    "max_dd_12m": 1.0,
    "mom36_healthy": 0.75,
    "mom36_overext": -0.75,
    "adv_3m_usd_log": 0.75,
    "days_above_ma200": 0.5,
    "mom_12_1": 0.5,
    "skew_12m": -0.75,
}

# The fundamental block from `recovered/algo_v4.py`, ported verbatim and NOT enabled by default.
#
# Weights are proportional to measured residual IC from `orthogonality.py`
# (0.099 / 0.065 / 0.057 / 0.038) rather than chosen, which is why they are not round numbers.
# `recovered/screen_v4.py` — the production screen, written after the comparison — ran price-only
# and attached fundamentals "for CONTEXT ... they did not improve selection, so they are
# reported, not scored". That decision stands here: `MODES` exists so the four configurations
# `recovered/run_algo_v4.py` compared can be re-measured on new data, not so a session can pick
# whichever looks best. Switching the live signal is the owner's call.
FUND_W: dict[str, float] = {
    "rev_instability": -1.0,
    "r40_healthy": 0.65,
    "net_margin_c": 0.55,
    "profitable": 0.40,
}

R40_LO, R40_HI = -0.5, 0.6
# Exclusion thresholds from the recovered bucket tables: the buckets where P(-30%) > 45%.
EXCL_R40 = -1.0
EXCL_INSTAB = 0.80

# The four configurations compared in `recovered/run_algo_v4.py`, by its own names.
MODES = ("price", "rank_fund", "filter", "both")

MIN_PRICE: float = 5.0
MIN_ADV: float = 5_000_000.0

# The top volatility quintile, as `screen_v4.py` and `run_algo_v4.py` both ran it. This is not a
# risk preference: the asymmetry result only holds conditional on a name being *capable* of a
# large move, so the gate defines the population the loser-filter was measured on.
VOL_GATE: tuple[float, float] = (0.80, 1.00)

# Refusal floors, from `algo_v4.score`: below these the cross-section is too thin for a
# percentile rank to mean anything, and the run declines to produce a ranking.
MIN_AFTER_HARD_FILTERS = 50
MIN_AFTER_GATE = 40
MIN_AFTER_EXCLUSION = 30     # algo_v4's floor after the fundamental exclusion

TOP_N = 25

# Anything resembling a likelihood. Checked on every emitted frame.
FORBIDDEN_COLUMN_TOKENS = ("prob", "proba", "likelihood", "pct_chance", "odds",
                           "confidence", "p_up", "p_down", "brier", "expected_return")


class RefusedToRank(RuntimeError):
    """The cross-section was too thin to rank. A refusal is an outcome, not an error to retry."""


def assert_no_probability_columns(frame: pd.DataFrame) -> None:
    """The non-negotiable, enforced rather than remembered.

    The measured reason: an isotonic calibrator fitted on one regime moved Brier 0.120 -> 0.189
    on another. A displayed probability would be precise and wrong, and precision is what makes
    it persuasive. Ranks carry no such implication.
    """
    offenders = [c for c in frame.columns
                 if any(token in str(c).lower() for token in FORBIDDEN_COLUMN_TOKENS)]
    if offenders:
        raise AssertionError(
            f"these columns read as probabilities or expected performance: {offenders}. "
            "This tool ranks and refuses; it never states a likelihood. See this module's "
            "docstring for the Brier numbers behind that rule."
        )


def cs_rank(series: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank centred on zero, in [-1, +1].

    Ranks, not z-scores, and the difference was measured: ranks were worth +3.91pp/yr. The
    factors are violently skewed, so a z-score is dominated by its outliers even after clipping.
    """
    return (series.rank(pct=True) - 0.5) * 2.0


def _derive(frame: pd.DataFrame) -> pd.DataFrame:
    """The derived columns from `algo_v4._derive`.

    The fundamental derivations run only when `rule40` is present, exactly as recovered — so a
    cross-section with no fundamentals attached behaves identically to the price-only path.
    """
    d = frame.copy()
    d["adv_3m_usd_log"] = np.log(d["adv_3m_usd"].clip(lower=1))
    m36 = d["mom_36"].fillna(0.0)
    d["mom36_healthy"] = m36.clip(lower=-0.5, upper=2.0)
    # The overextension penalty only engages above +300% over three years; below that the
    # clip makes the term identically zero.
    d["mom36_overext"] = np.log1p(m36.clip(lower=3.0)) - np.log1p(3.0)
    if "rule40" in d.columns:
        d["r40_healthy"] = d["rule40"].clip(lower=R40_LO, upper=R40_HI)
        d["rev_instability"] = np.log1p(d["rev_stability"].clip(lower=0))
        d["net_margin_c"] = d["net_margin"]
    return d


def apply_fundamental_exclusion(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the names the recovered bucket tables put in a P(-30%) > 45% bucket.

    This is the half of the fundamental block the owner's research actually supports: the
    information is concentrated in avoiding a bad tail, not in ranking the good end, which
    argues for an exclusion rather than a tilt. Thresholds are `EXCL_R40` and `EXCL_INSTAB`,
    unchanged.
    """
    if "rule40" not in frame.columns:
        return frame
    bad = ((frame["rule40"] < EXCL_R40)
           | (np.log1p(frame["rev_stability"].clip(lower=0)) > np.log1p(EXCL_INSTAB)))
    return frame[~bad.fillna(False)]


def apply_gates(factors: pd.DataFrame, vol_gate: tuple[float, float] = VOL_GATE) -> pd.DataFrame:
    """The hard filters and the volatility gate, with a refusal when too little survives."""
    before = len(factors)
    d = factors[(factors["price"] >= MIN_PRICE) & (factors["adv_3m_usd"] >= MIN_ADV)].copy()
    after_hard = len(d)
    if after_hard < MIN_AFTER_HARD_FILTERS:
        raise RefusedToRank(
            f"only {after_hard} of {before} names cleared price >= {MIN_PRICE} and "
            f"ADV >= {MIN_ADV:,.0f} (floor {MIN_AFTER_HARD_FILTERS}). Refusing to rank."
        )

    if vol_gate is not None:
        percentile = d["vol_12m"].rank(pct=True)
        d = d[(percentile >= vol_gate[0]) & (percentile <= vol_gate[1])]
    if len(d) < MIN_AFTER_GATE:
        raise RefusedToRank(
            f"only {len(d)} names survived the volatility gate {vol_gate} (floor "
            f"{MIN_AFTER_GATE}). Refusing to rank."
        )
    d.attrs["funnel"] = {"input": before, "after_hard_filters": after_hard,
                         "after_vol_gate": len(d)}
    return d


def score(factors: pd.DataFrame, vol_gate: tuple[float, float] = VOL_GATE,
          mode: str = "price") -> pd.DataFrame:
    """Rank the cross-section. Returns every gated name with its score and rank, best first.

    The returned frame carries one column per weighted term holding that term's *rank
    contribution*, so the reason a name ranks where it does is readable off the row rather than
    inferred. That is what makes a past call auditable.

    `mode` selects one of `recovered/run_algo_v4.py`'s four configurations. **It defaults to
    "price", which is what the production screen ran and what the live tracker uses.** The other
    three require fundamentals joined onto `factors` and exist to be measured, not to be chosen
    by a session.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")

    gated = apply_gates(factors, vol_gate)
    if mode in ("filter", "both"):
        gated = apply_fundamental_exclusion(gated)
        if len(gated) < MIN_AFTER_EXCLUSION:
            raise RefusedToRank(
                f"only {len(gated)} names survived the fundamental exclusion "
                f"(floor {MIN_AFTER_EXCLUSION}). Refusing to rank."
            )
    d = _derive(gated)

    weights = dict(PRICE_W)
    if mode in ("rank_fund", "both"):
        weights.update(FUND_W)

    total = pd.Series(0.0, index=d.index)
    contributions: dict[str, pd.Series] = {}
    for name, weight in weights.items():
        if name not in d.columns:
            if name in PRICE_W:
                raise AssertionError(f"the signal needs price factor {name!r} and it is absent")
            # A fundamental term with no data contributes nothing, as recovered (`continue`).
            # Silent for the fundamental block only, where a missing column is a join miss
            # rather than a broken panel.
            continue
        # Rank among the names that have the factor; a NaN contributes exactly zero, as recovered.
        ranked = cs_rank(d[name].dropna())
        aligned = pd.Series(0.0, index=d.index)
        aligned.loc[ranked.index] = ranked
        contributions[f"c_{name}"] = weight * aligned
        total = total + weight * aligned

    d["score"] = total
    for name, series in contributions.items():
        d[name] = series
    d = d.sort_values("score", ascending=False)
    d["rank"] = np.arange(1, len(d) + 1)
    d.attrs["funnel"] = gated.attrs.get("funnel", {})
    assert_no_probability_columns(d)
    return d


def why_it_ranks(row: pd.Series, top_k: int = 4) -> str:
    """The plain-language reason a name sits where it does: its largest rank contributions.

    Deliberately phrased as attribution, never as a forecast. "Near its 52-week high" is a
    statement about the past; "will rise" is not something this tool is allowed to say.
    """
    labels = {
        "c_pct_of_52w_high": "near its 52-week high",
        "c_max_dd_12m": "shallow 12m drawdown",
        "c_mom36_healthy": "healthy 3-year trend",
        "c_mom36_overext": "3-year move overextended",
        "c_adv_3m_usd_log": "liquid",
        "c_days_above_ma200": "persistently above its 200-day average",
        "c_mom_12_1": "12-month momentum (skipping last month)",
        "c_skew_12m": "return skew",
    }
    terms = {k: row[k] for k in labels if k in row.index and pd.notna(row[k])}
    if not terms:
        return "no attributable contributions"
    ordered = sorted(terms.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
    parts = [f"{labels[k]} ({v:+.2f})" for k, v in ordered]
    return "; ".join(parts)


def _definition(mode: str = "price") -> dict:
    """The dict the version hash covers.

    For `mode="price"` this is byte-identical to what it was before the other three modes
    existed, so the live record's `383a5e2a568e` keeps its meaning. Adding a capability must not
    retroactively change the identity of runs that did not use it.
    """
    definition = {
        "price_w": dict(sorted(PRICE_W.items())),
        "min_price": MIN_PRICE,
        "min_adv": MIN_ADV,
        "vol_gate": list(VOL_GATE),
        "min_after_hard_filters": MIN_AFTER_HARD_FILTERS,
        "min_after_gate": MIN_AFTER_GATE,
        "rank_transform": "cs_rank:(rank_pct-0.5)*2",
        "mode": "price_only" if mode == "price" else mode,
        "fundamental_block": mode != "price",
        "industry_overlay": False,
        "mom36_nan_fill": 0.0,
        "source": "recovered/algo_v4.py@PRICE_W",
    }
    if mode != "price":
        definition["fund_w"] = dict(sorted(FUND_W.items()))
        definition["excl_r40"] = EXCL_R40
        definition["excl_instab"] = EXCL_INSTAB
        definition["r40_clip"] = [R40_LO, R40_HI]
        definition["min_after_exclusion"] = MIN_AFTER_EXCLUSION
    return definition


def signal_version(mode: str = "price") -> str:
    """A short hash of the signal *definition*.

    Every output is stamped with it. Two runs that disagree are then either a market change or a
    definition change, and the hash says which without anyone having to remember. Any edit to a
    weight, a threshold, the gate, or the factor list moves the hash — and so does the mode, so
    a price-only run can never be confused with a fundamentals run.
    """
    blob = json.dumps(_definition(mode), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def signal_definition(mode: str = "price") -> dict:
    """The definition the hash covers, for writing beside a run."""
    out = {
        "signal_version": signal_version(mode),
        "price_w": dict(sorted(PRICE_W.items())),
        "min_price": MIN_PRICE,
        "min_adv": MIN_ADV,
        "vol_gate": list(VOL_GATE),
        "top_n": TOP_N,
        "mode": "price_only" if mode == "price" else mode,
        "never_emitted": "probability, expected return, or any performance figure",
    }
    if mode == "price":
        out["omitted"] = [
            "fundamental_block (ported in signal.FUND_W; NOT scored — screen_v4.py ran "
            "price-only because fundamentals 'did not improve selection')",
            "industry_overlay (nasdaq screener unavailable from cloud)",
        ]
    else:
        out["fund_w"] = dict(sorted(FUND_W.items()))
        out["exclusion"] = {"excl_r40": EXCL_R40, "excl_instab": EXCL_INSTAB}
    return out


def factor_diagnostics(factors: pd.DataFrame) -> dict:
    """RECOVERY.md's fifth item, measured rather than assumed.

    A design review called `pct_of_52w_high` and `max_dd_12m` the same quantity. Reading the code
    they are not — one is today's price over the 252-day maximum, the other the deepest trough
    against its own running maximum anywhere in the window. Both carry weight 1.0, so if they
    were near-identical the composite would be half one idea. This reports the correlation; it
    does not act on it, because collapsing a factor would be a signal change.
    """
    pair = factors[["pct_of_52w_high", "max_dd_12m"]].dropna()
    if len(pair) < 50:
        return {"n": len(pair), "note": "too few names to measure"}
    return {
        "n": int(len(pair)),
        "pearson": round(float(pair.corr().iloc[0, 1]), 4),
        "spearman": round(float(pair.corr(method="spearman").iloc[0, 1]), 4),
        "note": ("both carry weight 1.0 in PRICE_W. Reported, not acted on: collapsing a factor "
                 "would change the signal, which CLOUD-RULES.md §5 forbids a session from doing "
                 "to improve a result."),
    }
