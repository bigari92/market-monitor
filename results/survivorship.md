# Survivorship — bounded, and the Sharadar decision priced against it

**Run:** 2026-10-18. Form 25 census over 2009–2026 from EDGAR full-index (72 quarters,
**30,809 filings, 9,460 distinct CIKs**), cross-referenced against the 1.57 GB SEC submissions
bulk and today's listed universe. USD 0.00 of data cost.

Two questions, and they have different answers:

1. **How wrong are the survivor-only numbers?** Measurably, and less than expected: the
   delisting rate is **7.71% a year**, which overstates the measured edge by **8.4%**. Even at
   four times that rate the edge survives. **Survivorship does not threaten this strategy.**
2. **Should you buy Sharadar at USD 199/yr?** **Not yet — and not with this budget.** USD 47
   remains, which is 24% of the price. More importantly the bound above already answers the
   decision Sharadar would inform, and **C2's block bootstrap (USD 25) is the gate that could
   make the question moot.** Sequence matters: §6.

---

## 1. Why the free route is blocked — measured, not assumed

Before bounding the bias I tried to fix it. The attempt failed for a specific, checkable reason
worth recording, because it is what Sharadar's money actually buys.

SEC publishes delisting events for free. **Form 25** — "notification of removal from listing" —
gives a CIK and a date for every security removed from an exchange. 30,809 of them over
2009–2026. So the *events* are free.

The *prices* are not reachable, and the blocker is upstream of the prices:

**SEC clears a company's ticker when it deregisters.** Verified against the submissions bulk:

| CIK | company | outcome | `tickers` |
|---|---|---|---|
| 912183 | Cubist Pharmaceuticals | acquired 2014 | **`[]`** |
| 1292426 | GFI Group | acquired 2015 | **`[]`** |
| 320193 | Apple | live | `['AAPL']` |
| 1041061 | Yum Brands | live | `['YUM']` |
| 29534 | Dollar General | live | `['DG']` |
| 936468 | Lockheed Martin | live | `['LMT']` |

Of the 9,460 Form-25 CIKs, **7,686 (81%) have had their ticker cleared**. So for a delisted
company SEC tells you *that it left* and *when*, but not *what it was called* — and without a
ticker there is nothing to ask a price feed for. The chain breaks at the symbol, one step before
the data.

**That is precisely the gap Sharadar sells:** delisted tickers and their price history in the
same table, survivorship-bias-free. It is not a convenience purchase; it closes a gap that no
amount of care with free sources can close.

## 2. The delisting rate

A raw Form 25 count overstates company deaths — the form is filed per *security*, so a delisted
warrant, unit or preferred line counts while the common stock stays listed, and it is also filed
on an exchange move. Three filters, increasingly strict, against a universe of 6,936 names:

| year | Form 25 filings | distinct CIKs | gone **and** ticker cleared | loose rate | **strict rate** |
|---|---|---|---|---|---|
| 2010 | 1,399 | 626 | 532 | 9.03% | **7.67%** |
| 2013 | 1,490 | 663 | 539 | 9.56% | **7.77%** |
| 2016 | 1,711 | 699 | 588 | 10.08% | **8.48%** |
| 2019 | 1,765 | 683 | 507 | 9.85% | **7.31%** |
| 2020 | 1,941 | 656 | 455 | 9.46% | **6.56%** |
| 2022 | 2,105 | 846 | 647 | 12.20% | **9.33%** |
| 2023 | 2,436 | 1,029 | 795 | 14.84% | **11.46%** |
| 2025 | 1,928 | 875 | 590 | 12.62% | **8.51%** |

**Median strict rate, 2010–2025: 7.71%. Mean: 7.90%. Range: 6.56% – 11.46%.**

2023 is the peak at 11.46%, which is what the 2022 rate-shock cycle looks like on the way out.
Filings rose steadily from ~1,400/yr to ~2,000+/yr while the strict rate stayed near 8%, meaning
most of the growth is multi-class delistings (SPAC warrants and units, overwhelmingly) rather
than more companies dying.

## 3. The bound — C3's deliverable

Package C3 asked for a "survivorship **bound** at three imputation severities, reported beside
the survivor-only baseline". With `f` the delisting rate and `r` the return imputed to a
delisted name:

| severity | imputed return | measured excess | **pessimistic** | optimistic | overstatement |
|---|---|---|---|---|---|
| total loss | −100% | 11.88pp | **10.96pp** | 20.52pp | **1.084×** |
| severe | −50% | 11.88pp | **10.96pp** | 16.67pp | **1.084×** |
| neutral | cohort median (+12.2%) | 11.88pp | **10.96pp** | 11.88pp | **1.084×** |

**The pessimistic bound is identical across all three severities, and that is algebra rather
than coincidence.** If delisted names would have entered the top 25 at the same rate as
everything else, then:

```
top_adj    = (1-f)·top    + f·r
cohort_adj = (1-f)·cohort + f·r
excess_adj = top_adj - cohort_adj = (1-f)·excess        ← the imputed return cancels
```

So the pessimistic bound needs no assumption about how badly delisted names did. That is what
makes a bound computable when the prices are unavailable, and `tests/test_survivorship.py`
pins it so a later edit cannot quietly make the result depend on a guess.

The optimistic end is the mirror case — the signal avoids every delisting, so the benchmark gets
worse while the top 25 does not, and removing the bias *raises* the measured excess.

### The direction of the bias depends on how good the filter is

RECOVERY.md says survivorship is "exactly where a cheapness signal's apparent edge hides". That
is right about a **cheapness** signal: a value screen loads up on the distressed names that
delist, so survivorship flatters it badly. **This is not a cheapness signal.** It is a
trend-quality filter whose entire measured edge is a 1.9× cut in the down-tail with *no up-tail
lift at all* (`results/horizon_test.md` §3) — a signal that actively declines to rank the names
that die. So the truth sits closer to the optimistic end than it would for a value strategy, and
the pessimistic bound is genuinely conservative rather than merely cautious.

### Sensitivity, because the cohort's own rate is unmeasurable

`f = 7.71%` is universe-wide. The volatility gate selects the fragile end of the market on
purpose, so the gated cohort certainly delists faster — and **that rate cannot be measured here,
because measuring it needs the delisted tickers.** So the response is a sensitivity sweep rather
than a point estimate:

| delisting rate `f` | pessimistic excess | overstatement |
|---|---|---|
| 7.71% (measured, universe) | 10.96pp | 1.083× |
| 10% | 10.69pp | 1.111× |
| 15% | 10.09pp | 1.176× |
| 20% | 9.50pp | 1.250× |
| 25% | 8.91pp | 1.333× |
| 33% | 7.96pp | 1.493× |

**At four times the measured rate the edge is still +7.96pp.** The strategy would need a
delisting rate above **78%** to lose money after costs. That is not a near miss; it is three
orders of magnitude of comfort on the only axis RECOVERY.md called structural.

## 4. The full stack: gross → survivorship → cost

Every haircut this project has measured, applied in order. Nothing here is an expected return —
see §5.

| strategy | gross | after survivorship | cost drag | **after both** | total haircut |
|---|---|---|---|---|---|
| 12-month hold, USD 50k | 11.88pp | 10.96pp | 1.01pp | **9.95pp** | **16.2%** |
| 12-month hold, USD 250k | 11.88pp | 10.96pp | 0.97pp | **9.99pp** | **15.9%** |
| as configured, USD 50k | 15.31pp | 14.13pp | 3.29pp | **10.84pp** | **29.2%** |
| as configured, USD 250k | 15.31pp | 14.13pp | 3.15pp | **10.98pp** | **28.3%** |

The two cadences remain a wash after both haircuts, exactly as `results/cost_model.md` §5 found
on costs alone — survivorship applies the same proportional dilution to both, so it does not
break the tie.

## 5. What is still wrong with these numbers

**They are not expected returns and must never be quoted as such.** Three reasons stand
independent of everything above:

1. **~15 independent observations.** The 12-month excess rests on 15 non-overlapping windows in
   20 years (`results/horizon_test.md` §1), and its honest t-statistic is 2.31. A bound on
   survivorship does not add a single degree of freedom.
2. **The trial count is unpaid.** The weight vector came from a factor search whose multiple-
   testing bar has never been scored. **That is C2, it is the designated kill gate, and until it
   runs none of these figures is established** — bounded, cost-adjusted or otherwise.
3. **The bound is a bound.** It brackets the bias; it does not measure it. The pessimistic end
   assumes the filter has no skill at avoiding deaths, the optimistic end assumes perfect skill,
   and the truth is an unmeasured point between them.

What *is* unbiased is the forward record in `results/tracking/` — point-in-time by construction,
with exits retained. It is one run long. Its value is entirely in accumulating, and nothing
substitutes for elapsed time.

## 6. The Sharadar decision

**Recommendation: do not buy it now. Spend USD 25 on C2 first.**

| | |
|---|---|
| Sharadar Prices, 10y history | **USD 199/yr** |
| Sharadar Prices, full history | **USD 299/yr** |
| Remaining credit | **USD 47.00** |

Four reasons, in order of weight:

1. **It is 4.2× the remaining budget.** USD 199 against USD 47 is not a session expense; it is a
   separate purchase decision, and a cloud session must not make it (CLOUD-RULES.md §4 — a paid
   key arrives as an environment variable and is never committed).
2. **The bound already answers the question Sharadar would inform.** It would convert an 8.4%
   overstatement into a point estimate. An 8.4% correction on a figure whose t-statistic is 2.31
   changes no decision anyone would make.
3. **C2 could make the question moot, and it is affordable.** The block bootstrap is the
   designated kill gate: *"p > 0.10 on the best configuration ends the prediction half"*. It
   costs USD 25, which fits in USD 47. Spending USD 199 to refine a number that C2 might
   invalidate entirely is the wrong order of operations.
4. **The free forward record is the unbiased dataset.** It is accruing now, costs nothing, and
   is survivorship-bias-free by construction rather than by correction.

### When to revisit, and what it would buy

**Buy it if C2 passes and you then want a backtest you can trust.** At that point Sharadar is
the only thing that closes the gap measured in §1 — delisted tickers with their prices — and it
would deliver three things the free route cannot:

- the cohort-specific delisting rate, replacing the sensitivity sweep in §3 with a measurement;
- a genuine survivorship-free backtest, replacing the bound with a point estimate;
- the delisted names' actual returns, which is the only way to test the loser-filter thesis
  where it matters most — on the names that actually died.

`src/market_monitor/cloud/feeds/sharadar.py` is already the seam: a working key in
`SHARADAR_API_KEY` and a reader against the live schema is the whole job. The stub deliberately
raises rather than guessing at that schema.

**The 10-year product (USD 199) is sufficient.** This project's price panel is 20 years and its
fundamental panel effectively starts in 2012, so full history at USD 299 buys depth the rest of
the stack cannot use.

## 7. Reproducing it

```bash
python -m market_monitor.cloud.run survivorship     # bound + delisting rate from cached census
```

The Form 25 census (72 quarterly `form.idx` files, ~3.6 GB) and the submissions bulk (1.57 GB)
are fetched once into `data/sec_delist/` (gitignored). The census writer is **resumable, one
parquet per quarter** — the first version was not, died at quarter 56 of 72, and wrote nothing,
which is CLOUD-RULES.md §1 demonstrated on my own code rather than quoted at someone else's.

Outputs: `results/survivorship_delisting_rate.csv`, `results/survivorship_stack.csv`. The bound
algebra is tested in `tests/test_survivorship.py`, including the property that the pessimistic
bound is independent of the imputed return.
