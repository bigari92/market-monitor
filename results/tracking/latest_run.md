# Run 2026-10-30_383a5e2a568e

- **data_as_of:** 2026-10-30 (the panel's last completed session, not today)
- **signal_version:** `383a5e2a568e` (price-only v4 composite)
- **universe funnel:** 5798 scorable → 2692 after price/liquidity floors → 539 after the volatility gate
- **watchlist:** 28 names (8 entered, 20 held, 5 exited)

## BUY candidates

| rank | ticker | score | price | %52w high | max DD 12m | why it ranks |
|---|---|---|---|---|---|---|
| 11 | **ENTG** | +2.830 | 154.39 | 0.839 | -0.418 | near its 52-week high (+0.63); shallow 12m drawdown (+0.61); liquid (+0.55); persistently above its 200-day average (+0.34) |
| 17 | **OKTA** | +2.657 | 208.24 | 0.897 | -0.331 | shallow 12m drawdown (+0.89); near its 52-week high (+0.75); liquid (+0.63); healthy 3-year trend (+0.54) |
| 19 | **TWST** | +2.568 | 152.78 | 0.745 | -0.352 | shallow 12m drawdown (+0.84); 3-year move overextended (-0.66); liquid (+0.55); healthy 3-year trend (+0.54) |
| 20 | **FIGS** | +2.542 | 21.31 | 0.988 | -0.460 | near its 52-week high (+0.95); healthy 3-year trend (+0.54); shallow 12m drawdown (+0.45); persistently above its 200-day average (+0.31) |
| 21 | **RXO** | +2.494 | 27.49 | 0.938 | -0.409 | near its 52-week high (+0.84); shallow 12m drawdown (+0.66); return skew (+0.48); liquid (+0.19) |
| 22 | **COHU** | +2.494 | 50.79 | 0.687 | -0.468 | return skew (+0.51); persistently above its 200-day average (+0.46); shallow 12m drawdown (+0.43); 12-month momentum (skipping last month) (+0.42) |
| 24 | **RVMD** | +2.424 | 191.31 | 0.865 | -0.250 | shallow 12m drawdown (+0.99); near its 52-week high (+0.68); 3-year move overextended (-0.65); return skew (-0.64) |
| 25 | **VSXY** | +2.397 | 96.62 | 0.966 | -0.356 | near its 52-week high (+0.90); shallow 12m drawdown (+0.83); return skew (-0.62); healthy 3-year trend (+0.54) |

## SELL / EXIT signals

| ticker | reason | detail | rank prev → now |
|---|---|---|---|
| **UMC** | `TREND_BREAK` | price -2.2% vs its 200-day average, having been above it at the previous run | 5 → 23 |
| **SSRM** | `TREND_BREAK` | price -12.7% vs its 200-day average, having been above it at the previous run | 9 → 30 |
| **IOVA** | `RANK_DECAY` | rank 68 past the carry buffer of 50 | 12 → 68 |
| **INTC** | `TREND_BREAK` | price -24.3% vs its 200-day average, having been above it at the previous run | 13 → 46 |
| **TGB** | `TREND_BREAK` | price -3.6% vs its 200-day average, having been above it at the previous run | 22 → 32 |

## Held

| rank | ticker | rank change | runs held | score |
|---|---|---|---|---|
| 1 | **PBF** | +1 | 2 | +3.397 |
| 2 | **P** | +2 | 2 | +3.356 |
| 3 | **AMD** | +0 | 2 | +3.338 |
| 4 | **TXG** | +2 | 2 | +3.245 |
| 5 | **TER** | -4 | 2 | +3.241 |
| 6 | **MTSI** | +2 | 2 | +3.019 |
| 7 | **RNG** | +13 | 2 | +2.998 |
| 8 | **NET** | -1 | 2 | +2.990 |
| 9 | **RLAY** | +9 | 2 | +2.949 |
| 10 | **MRNA** | +6 | 2 | +2.932 |
| 12 | **MU** | +2 | 2 | +2.798 |
| 13 | **SANM** | -3 | 2 | +2.714 |
| 14 | **LITE** | +5 | 2 | +2.708 |
| 15 | **SMTC** | -4 | 2 | +2.697 |
| 16 | **SYRE** | +8 | 2 | +2.660 |
| 18 | **VSAT** | -1 | 2 | +2.627 |
| 29 | **TWLO** | -8 | 2 | +2.337 |
| 35 | **ZETA** | -20 | 2 | +2.257 |
| 41 | **LRCX** | -16 | 2 | +2.164 |
| 49 | **FORM** | -26 | 2 | +2.050 |

## Diagnostics

```json
{
  "coverage": {
    "tickers_in_panel": 6924,
    "scorable": 5798,
    "short_history": 1126,
    "min_sessions": 273,
    "have_3y_for_mom36": 5050
  },
  "pct_of_52w_high_vs_max_dd_12m": {
    "n": 5798,
    "pearson": 0.9277,
    "spearman": 0.8819,
    "note": "both carry weight 1.0 in PRICE_W. Reported, not acted on: collapsing a factor would change the signal, which CLOUD-RULES.md \u00a75 forbids a session from doing to improve a result."
  },
  "corporate_actions_in_panel": 60866,
  "feed": {
    "feed": "yahoo_chart",
    "requested": 7144,
    "attempted": 7144,
    "status_counts": {
      "ok": 7143,
      "granularity": 1
    },
    "wall_seconds": 127.6,
    "requests_per_second": 56.0,
    "stopped_early": false
  }
}
```

## What this is not

No probability appears above, and none can: an isotonic calibrator fitted on one regime
carried Brier 0.120 into another where it scored 0.189. No performance figure appears
either. The published +37.8%/yr against +14.6% rests on roughly 7 effective annual
observations (t ~ 2.64) over a survivor-only universe, and is not an expected return.

The signal is a **loser-filter**: conditional on the volatility cohort, trend quality
barely moves the up-tail (18.7% → 21.9%) and roughly halves the down-tail
(48.3% → 23.4%). It ranks and it refuses. The owner decides.