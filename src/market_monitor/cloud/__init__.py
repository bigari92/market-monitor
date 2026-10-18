"""Modules a cloud session may run.

Rules for everything in this package, enforced by tests/test_no_yfinance_in_cloud_paths.py
and docs/CLOUD-RULES.md:

* No ``yfinance`` anywhere on the import graph. Datacentre IPs get rate-limited across every
  endpoint, and a cloud session cannot tell anyone it failed — commits are its only output.
* No personal financial data. Nothing here reads C:\\Users\\valer\\Investing.
* Public sources only, with their own rules respected: SEC EDGAR wants a declared User-Agent
  and at most 10 requests/second.
* Commit after every step. A session that dies with uncommitted work spent credit for nothing.
"""
