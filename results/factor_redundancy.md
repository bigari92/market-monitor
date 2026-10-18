# Factor redundancy in the v4 price composite — measured, not acted on

**Run:** 2026-10-18, on the live gated cross-section (`data_as_of` 2026-10-16, signal version
`383a5e2a568e`). 5,941 scorable names, 555 past the volatility gate.

`docs/RECOVERY.md` closes with an open question rather than a defect:

> A fifth item is a question, not a defect: `pct_of_52w_high` and `max_dd_12m` were described in
> a design review as the same quantity. Reading `factors.py` they are not — one is today's price
> over the 252-day maximum, the other the deepest trough relative to its own running maximum
> anywhere in the window. **Measure their correlation before collapsing them.**

Measured. The answer is more interesting than either side of the original argument, and it is
**reported here and deliberately not acted on** — CLOUD-RULES.md §5 forbids a session from
changing the signal to improve a result, and collapsing a factor is exactly that.

---

## 1. The pair the design review named: not identical, and the gate matters

| population | n | Pearson | Spearman |
|---|---|---|---|
| full scorable universe | 5,941 | **+0.930** | +0.891 |
| **gated cohort — what actually gets ranked** | 555 | **+0.731** | +0.728 |

Both readings of the design review were partly right, and the distinction nobody drew is the
one that matters: **which population you measure on.**

Across the whole market the two factors are nearly the same thing (0.93). Inside the top
volatility quintile — the only population the signal ever ranks — the correlation falls to 0.73.
That is still high, but it is not duplication: roughly half the rank variance of one is
unexplained by the other. The code reading in RECOVERY.md was correct that they are different
quantities, and the design review was correct that they are heavily entangled. The gate is what
separates those two claims.

Together they carry **33.3% of the composite's total absolute weight mass** (2.0 of 6.0), the two
largest weights in `PRICE_W`.

## 2. The larger redundancy was never flagged by anyone

Ranked by absolute Spearman correlation among the eight weighted rank contributions, on the
gated cohort:

| pair | Spearman |
|---|---|
| **`days_above_ma200` vs `mom_12_1`** | **+0.865** |
| `pct_of_52w_high` vs `max_dd_12m` | +0.728 |
| `mom36_healthy` vs `mom36_overext` | −0.659 |
| `max_dd_12m` vs `days_above_ma200` | +0.611 |
| `max_dd_12m` vs `mom_12_1` | +0.611 |

**The tightest pair in the composite is not the one the design review argued about.**
`days_above_ma200` and `mom_12_1` correlate at **+0.865** — materially higher than the audited
pair — and no review raised them. They carry 0.5 each, so the exposure is smaller than the
headline pair's, but the duplication is worse.

The `mom36_healthy` / `mom36_overext` anti-correlation of −0.659 is expected and not a defect:
both are clipped transforms of the same `mom_36` variable, designed to separate a healthy
multi-year trend from a parabolic one. It is listed for completeness.

## 3. Eight terms, about five ideas

Eigenvalues of the 8×8 rank-correlation matrix of the weighted contributions:

```
3.52  1.53  0.90  0.75  0.67  0.29  0.23  0.11
```

- The leading component explains **44.0%** of the covariance among terms.
- **Effective dimensionality: 5.12 of 8** (entropy of the normalised eigenvalue spectrum).

So the composite expresses roughly five independent ideas through eight terms. That is not
damning on its own — correlated factors can still each add signal, and `orthogonality.py` was
written to test precisely that for the fundamental block — but it does mean the weight vector is
less expressive than its eight entries suggest, and that a term's weight overstates its
influence wherever a neighbour duplicates it.

## 4. Leave-one-term-out: weight is a poor guide to influence

Each term removed from the composite in turn (arithmetic only — nothing re-fitted, nothing
re-weighted), against the unmodified top 25:

| term | weight | Spearman vs full | top-25 names kept |
|---|---|---|---|
| `mom36_overext` | −0.75 | 0.9837 | **15 / 25** |
| `pct_of_52w_high` | **1.00** | 0.9430 | 18 / 25 |
| `skew_12m` | −0.75 | 0.9669 | 18 / 25 |
| `adv_3m_usd_log` | 0.75 | 0.9623 | 18 / 25 |
| `max_dd_12m` | **1.00** | 0.9557 | 20 / 25 |
| `mom36_healthy` | 0.75 | 0.9677 | 21 / 25 |
| `days_above_ma200` | 0.50 | 0.9893 | **22 / 25** |
| `mom_12_1` | 0.50 | 0.9890 | **22 / 25** |

Three things fall out of this table, and the first is the most surprising result in the file.

**`mom36_overext` is the single largest influence on who makes the top 25, and it is zero for
most of the market.** By construction it is `log1p(mom_36.clip(lower=3.0)) - log1p(3.0)`, so it
is identically zero for any name whose three-year return is under +300%. It therefore does
nothing at all across the great majority of the universe — and yet removing it changes 10 of the
25 selected names, more than removing either weight-1.0 factor. The reason is selection: the top
of a trend-quality composite is exactly where extreme three-year momentum concentrates, so a
term that is dormant market-wide is active precisely where the output is decided. **A factor's
average influence and its influence on the published list are different quantities**, and only
the second one reaches the owner.

**The two weight-1.0 factors are each individually removable with modest effect** (18/25 and
20/25) — which is the signature of the 0.73 correlation in §1. Each is partly covering for the
other, so neither looks essential in isolation while the pair together carries a third of the
weight mass.

**The 0.865-correlated pair barely registers individually** (22/25 each, Spearman 0.989). This
is textbook redundancy: either one alone is nearly free to remove, because the other absorbs its
role.

## 5. What is deliberately NOT being done about any of this

No weight is changed, no factor is collapsed, no threshold is moved. §5 exists because every
configuration tried inflates the multiple-testing bar the project is trying to measure honestly,
and an unwatched session with a budget will happily search. The entire point of writing this file
instead of editing `signal.py` is that the finding survives without the search.

Three consequences stand, though, and they are for the owner to weigh rather than for a session
to implement:

1. **The RECOVERY.md question is answered and can be closed.** The factors are not the same
   quantity. On the population that matters they share about half their rank variance. Whether
   that justifies collapsing them is a judgement about how much weight one idea should carry, not
   a question about the data.
2. **If anything in the composite deserves scrutiny first, it is `days_above_ma200` /
   `mom_12_1` at 0.865, not the audited pair at 0.728.** The review looked at the wrong pair.
3. **`mom36_overext` deserves its own examination** — not because it is wrong, but because a
   term that is dormant for most names and dominant at the top is the kind of thing that should
   be understood deliberately rather than discovered by accident. It is also the term most
   exposed to a handful of extreme names, which is where an overfit would hide.

Any change to the weight vector is a new configuration and belongs in the trials ledger that
package C2 (the block bootstrap) is meant to score against. Making the change here would corrupt
that count before it is taken.

## 6. Reproducing it

```bash
python -m market_monitor.cloud.run track    # prints the §1 correlation in its diagnostics
```

`signal.factor_diagnostics` reports the §1 pair on every run, so a drift in it is visible without
anyone rerunning this analysis. Sections 2–4 were computed ad hoc from the cached panel; the
numbers above are from `data_as_of` 2026-10-16 and will move with the cross-section.
