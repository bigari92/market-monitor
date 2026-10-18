# The cost model — RECOVERY.md defect 4, closed

**Run:** 2026-10-18, `data_as_of` 2026-10-16, on the 20-year panel re-fetched with daily
high/low. Turnover measured from the 23-run replay record; spread estimated by two published
estimators; commission from a published rate card.

> **RECOVERY.md defect 4. No cost model.** Nothing deducts commission, spread or tax anywhere.

**Verdict: costs take a real bite and do not erase the edge — but they erase the apparent
advantage of trading faster.** The strategy survives with **2.7× to 13× headroom** over the
cost that would break it. The tracker as configured turns over **3.25× a year** and gives up
**21–40% of its gross excess** to costs, against 8–16% for a 12-month hold. Net of costs the two
are a wash, which is a finding the gross numbers actively concealed.

---

## 1. The spread, and the gate's bill

No free feed carries quotes, so the effective spread is reconstructed from the daily range by
**Corwin-Schultz (2012)** and **Abdi-Ranaldo (2017)**, both reported. Medians in basis points at
a 504-day window:

| population | n | Corwin-Schultz | Abdi-Ranaldo | used (max) |
|---|---|---|---|---|
| whole scorable universe | 5,791 | 90.7 | 64.6 | 103.7 |
| **after price + liquidity floors** | 2,697 | 73.7 | 52.7 | **79.5** |
| **gated cohort — what gets ranked** | 540 | 137.3 | 82.9 | **144.8** |
| top 25 — what gets bought | 25 | 99.1 | 96.1 | 116.9 |

**The volatility gate nearly doubles the spread it has to pay: 79.5 bps → 144.8 bps.** That was
the thing worth measuring. The gate exists because the asymmetry result only holds for names
capable of large moves, and the market charges for exactly that property. Costs here are not a
uniform haircut; they land hardest on the cohort the signal is built to rank.

**But the composite partly pays for itself.** The top 25 trades at 116.9 bps against 144.8 for
the cohort it is drawn from — because `adv_3m_usd_log` carries weight 0.75 in `PRICE_W`, so the
ranking already prefers liquid names. That liquidity term was never justified as a cost control
in the recovered work; on this evidence it functions as one, worth roughly **28 bps** of round-trip
cost.

### The two estimators disagree, and the window is why

| window | Corwin-Schultz | Abdi-Ranaldo | names where AR floored to zero |
|---|---|---|---|
| 21d | 107 bps | 22 bps | 48% |
| 252d | 116 bps | 35 bps | 36% |
| **504d** | **99 bps** | **96 bps** | **12%** |

Abdi-Ranaldo estimates a variance that can come out negative in a short sample, and the
convention floors it at zero — so on a 21-day window it collapses for nearly half the cohort
and the "two estimator" check silently becomes one. At 504 days they agree to within 3 bps.
`DEFAULT_WINDOW` is 504 for that reason, and a cost model wants a stable average anyway.

Both bounds are carried through everything below: **88.7 bps** (converged, 504d, median across
15 annual dates) and **135.4 bps** (conservative, 21d, essentially Corwin-Schultz alone, which
its zero-flooring biases upward).

Spread is not stable across regimes: the annual medians run 74–89 bps through 2012–2019 and
jump to **137–151 bps in 2020–2021** before easing. A cost assumption fixed at the quiet-period
level would understate the bill in precisely the years the strategy struggled.

## 2. Commission: the per-order minimum is what matters

Schedule: Interactive Brokers' advertised US-stock **fixed** tier — USD 0.005/share, USD 1.00
minimum per order, 1% cap. **A published rate card, not a claim about what the owner pays**; this
repository has no access to his account and must not have (CLOUD-RULES.md §3).

| portfolio | position size | commission, one way |
|---|---|---|
| USD 10,000 | USD 400 | **25.0 bps** |
| USD 25,000 | USD 1,000 | 10.0 bps |
| USD 50,000 | USD 2,000 | 5.1 bps |
| USD 100,000 | USD 4,000 | 2.7 bps |
| USD 250,000 | USD 10,000 | 1.5 bps |
| USD 1,000,000 | USD 40,000 | 1.1 bps |

For a 25-name book the USD 1.00 minimum dominates below about USD 100,000: at USD 10,000 the
commission alone is **25 bps each way**, more than a quarter of the spread. The per-share rate
only binds for large positions. **A 25-name equal-weighted portfolio is an expensive shape for a
small account**, and that is a structural fact about the design rather than about the signal.

## 3. Market impact: present, and not the problem

Square-root impact scaled by the cohort's own daily volatility (top-25 median **4.38%/day**),
because impact is paid in units of a stock's variability and this cohort is volatile by
construction:

| portfolio | impact, one way |
|---|---|
| USD 10,000 | 0.5 bps |
| USD 100,000 | 1.6 bps |
| USD 1,000,000 | 5.2 bps |

Negligible beside the spread at any size the gate's ADV ≥ USD 5m floor permits — which is
reported rather than assumed. If it ever stops being negligible, the portfolio has outgrown the
gate.

## 4. Turnover: measured, and three times what the research implies

From the 23-run replay record (`results/replay/runs.csv`), excluding the first run because
nothing can exit on it:

| | |
|---|---|
| mean watchlist | 31.3 names |
| mean exits per run | 8.35 |
| monthly exit rate | **27.1%** |
| **annualised turnover** | **3.25×** |
| implied average holding period | **3.7 months** |

The recovered research validated a **12-month hold**. The tracker's conservative exit rules —
structural breaks only, no rank-noise retirement — still produce an average holding period of
under four months. **Cost scales linearly with turnover, so this multiplies the bill by 3.25.**

## 5. The drag

Round trip = 2 × commission + spread + 2 × impact. The spread is paid once per round trip (buy
at the ask, sell at the bid); commission and impact are paid on both legs.

| portfolio | strategy | spread case | round trip | annual drag | gross excess | **net** | drag as % of gross |
|---|---|---|---|---|---|---|---|
| 10k | 12-month hold | converged | 139.8 bps | 1.40pp | 11.88pp | **10.48pp** | 11.8% |
| 10k | 12-month hold | conservative | 186.4 bps | 1.86pp | 11.88pp | **10.01pp** | 15.7% |
| 10k | **as configured** | converged | 139.8 bps | 4.54pp | 15.31pp | **10.76pp** | **29.7%** |
| 10k | **as configured** | conservative | 186.4 bps | 6.06pp | 15.31pp | **9.25pp** | **39.6%** |
| 50k | 12-month hold | converged | 101.2 bps | 1.01pp | 11.88pp | **10.86pp** | 8.5% |
| 50k | **as configured** | converged | 101.2 bps | 3.29pp | 15.31pp | **12.02pp** | 21.5% |
| 50k | **as configured** | conservative | 147.8 bps | 4.80pp | 15.31pp | **10.50pp** | 31.4% |
| 250k | 12-month hold | converged | 96.9 bps | 0.97pp | 11.88pp | **10.91pp** | 8.2% |
| 250k | **as configured** | converged | 96.9 bps | 3.15pp | 15.31pp | **12.16pp** | 20.6% |
| 1m | **as configured** | conservative | 147.8 bps | 4.81pp | 15.31pp | **10.50pp** | 31.4% |

Gross figures are from `results/horizon_test.md`: +11.88pp excess at the 12-month horizon, and
+3.83pp per 3-month period which is annualised here as ×4 — **an annualisation that assumes the
quarterly edge repeats independently, which overlapping-window evidence cannot confirm.** It
flatters the faster strategy, and even so:

**Net of costs, trading faster wins nothing.** The 12-month hold nets 10.0–10.9pp. The tracker as
configured nets 9.3–12.2pp — a wider range that straddles it, and the wide end depends on the
generous annualisation above. The 3-month horizon's higher gross excess (15.31 vs 11.88) is
almost exactly consumed by its 3.25× turnover.

This directly answers the question `results/horizon_test.md` §6 had to leave open: *"it is simply
not possible to say whether 3-month rebalancing beats 12-month rebalancing net of costs."* It is
now possible, and the answer is **no — they are a wash, and the faster one is more fragile to the
cost assumption.**

## 6. Break-even: the verdict without the estimate

The round-trip cost that would exactly erase the gross excess. Independent of any spread
estimator, so it survives both being wrong.

| strategy | turnover | gross excess | break-even round trip | headroom vs 88.7 bps | headroom vs 135.4 bps |
|---|---|---|---|---|---|
| 12-month hold | 1.00× | 11.88pp | **1,187 bps** | **13.4×** | 8.8× |
| as configured | 3.25× | 15.31pp | **471 bps** | 5.3× | 3.5× |
| as configured, on the 12m excess | 3.25× | 11.88pp | **365 bps** | 4.1× | **2.7×** |

**The edge would have to be wrong about costs by a factor of 2.7 to 13 before costs erase it.**
Even on the least favourable combination — the tracker's turnover, the conservative spread, and
the lower gross excess — there is 2.7× headroom. Execution cost is not what kills this strategy.

## 7. What is NOT in this model, and it matters more than what is

**Tax is deliberately out of scope.** It depends on the owner's jurisdiction, account type, other
income, holding periods and loss carry-forwards. None of that is public, none of it belongs in
this repository (CLOUD-RULES.md §3), and a cloud session cannot see it. `cost.after_tax_drag`
takes a rate the owner supplies and **has no default** — a made-up rate would be carried forward
as fact. One thing is worth flagging: a **3.7-month average holding period is short-term in most
jurisdictions**, so the turnover this model measures has a tax consequence as well as a
commission one, and it points the same way.

**Costs do not fix survivorship.** Every gross figure above inherits the survivor-only universe
of `results/horizon_test.md` — the names that went to zero are absent (RECOVERY.md defect 1).
The net numbers are gross-of-survivorship-bias and should not be read as expected returns. **A
cost model makes an optimistic number less optimistic; it does not make it right.** Defect 1
remains structural and only a survivorship-bias-free price source (`feeds/sharadar.py`) addresses
it.

**The spread is estimated, not observed.** Two estimators converging at 96–99 bps is reasonable
evidence, not a quote. The owner's actual fills are the only ground truth, and they live in
records this repository must never read.

**No slippage beyond spread and impact**, no borrow costs (the strategy is long-only), no
currency conversion, no partial-fill or opportunity cost from a limit order that never executes.

## 8. What it changes

1. **The cadence verdict stands but its reasoning narrows.** Monthly *review* remains right —
   reviewing is not trading. But the 3.25× turnover that review currently produces costs
   3× what a 12-month hold costs and buys nothing net. **The conservative exit rules are not
   merely defensible, they are load-bearing**, and anything that loosens them trades real money
   for noise.
2. **Turnover is now a number to watch, not a side effect.** `runs.csv` already records exits per
   run, so the drag can be recomputed from the record at any time. An exit rule change that
   pushes turnover from 3.25× to 5× would cost roughly another 1.5pp a year.
3. **Portfolio size changes the design.** Below ~USD 100,000 the USD 1.00 commission minimum
   makes a 25-name equal-weighted book expensive (25 bps a side at USD 10,000). Fewer, larger
   positions would cut commission at the price of concentration — a real trade-off, and the
   owner's to make, not a session's.
4. **The liquidity weight is doing unacknowledged work.** `adv_3m_usd_log` saves ~28 bps of round
   trip relative to the gated cohort. It is not to be removed as "redundant" on the strength of
   `results/factor_redundancy.md` without pricing that in.

## 9. Reproducing it

```bash
python -m market_monitor.cloud.run --years 20 cost
```

Needs a panel with daily high/low — a panel fetched before the cost model existed has none, and
`cost.require_high_low` **refuses** rather than treating the spread as zero, which is the failure
that would make every strategy look costless. Detailed output in `results/cost_model_stats.json`,
`cost_model_drag.csv` and `cost_model_spread.csv`.

The estimators are tested in `tests/test_cost.py` against synthetic series carrying a known
bid-ask bounce: Abdi-Ranaldo recovers a 20, 50 and 200 bps spread to within 35%, Corwin-Schultz
is held to positivity and monotonicity (it is noisier), and both read near zero when no spread
is present.
