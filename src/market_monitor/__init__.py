"""market_monitor — the public-data half of a personal market monitoring tool.

Two halves, deliberately separated (see README.md):

* ``cloud``  — may run in an ephemeral cloud session. No yfinance, no personal data.
* ``local``  — runs on the owner's machine only. yfinance and read-only access to the
               personal folder are allowed here.

Nothing in this package holds money, places orders, or produces a recommendation.
"""

__all__ = ["cloud", "local"]
