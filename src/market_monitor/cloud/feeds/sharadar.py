"""Sharadar Equity Prices (SEP), the paid alternative — priced, not wired up.

This module is deliberately a non-working stub that raises with instructions. It exists so the
decision is visible in the code rather than living in a chat message, and so switching feeds is
a one-word change once a key exists.

## Why it is the right thing to buy if this tracker ever matters

One reason, and it is not convenience: **delisted tickers are in the same table**. RECOVERY.md
defect 1 — the survivor-only universe — is the defect that cannot be fixed by being careful,
because the data to fix it is absent. Sharadar's SEP includes companies that went to zero, so a
backtest run against it measures the strategy rather than measuring the set of companies that
survived long enough to be in today's ticker list. Nothing else on the pricing list changes a
conclusion; that one does.

It also carries an explicit `closeunadj` alongside the adjusted series and a separate actions
table, which is RECOVERY.md defect 2 handled at the source instead of reconstructed.

## Pricing, as advertised (api.sharadar.com, checked against the brief, not re-verified here)

| product                      | USD/yr | what it buys                                      |
|------------------------------|--------|---------------------------------------------------|
| Sharadar Prices, 10y history | 199    | enough for the tracker and a 10-year backtest     |
| Sharadar Prices, full history| 299    | full depth, survivorship-bias-free                |

Against the USD 90 session budget: **neither fits.** This is a separate purchase decision for the
owner, not something a cloud session can quietly expense. It is also not urgent — the free feed
measured in `results/price_feed_probe.md` runs the forward tracker today, and the forward tracker
is survivorship-bias-free by construction (see `universe.py`). The purchase buys back the *past*,
which is what a backtest needs and what the tracker does not.

## Wiring it up, when a key exists

The key arrives as the environment variable `SHARADAR_API_KEY` and is never committed
(CLOUD-RULES.md §4). Bulk export, not per-ticker requests: SEP ships as a single table download,
so the fan-out and throttle machinery in `yahoo_chart.py` is unnecessary here.
"""
from __future__ import annotations

import os

from . import Bars, FeedError

API_KEY_ENV = "SHARADAR_API_KEY"

PRICING = {"prices_10y_usd_per_year": 199, "prices_full_history_usd_per_year": 299}


class SharadarFeed:
    name = "sharadar"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get(API_KEY_ENV)

    def fetch(self, tickers: list[str], years: int = 5) -> Bars:
        if not self.api_key:
            raise FeedError(
                f"the Sharadar feed needs {API_KEY_ENV} in the environment and no key is set. "
                f"This is a purchase decision, not a bug: Prices/10y is USD "
                f"{PRICING['prices_10y_usd_per_year']}/yr and full history USD "
                f"{PRICING['prices_full_history_usd_per_year']}/yr, both above the USD 90 "
                "session budget. See this module's docstring for what the money buys "
                "(delisted tickers in the same table — the one defect care cannot fix)."
            )
        raise NotImplementedError(
            "a key is present but the SEP bulk-export reader is not written. It is a single "
            "table download rather than a per-ticker fan-out; write it against the live schema "
            "rather than against a guess at it, then return a Bars with closeunadj mapped to "
            "`close`, the adjusted series to `adjclose`, and the actions table to `events`."
        )
