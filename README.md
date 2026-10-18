# market-monitor

Public-data half of a personal market monitoring tool. Code, factor definitions and small
derived artefacts. Cloud-session enabled.

Plan: `../market-monitor-plan.md`.

## Two rules this repository exists to enforce

**1. No personal financial data, ever.** The owner's records — trade journal, holdings, ledger,
tax record, IBKR Flex statements — live in `C:\Users\valer\Investing`, which is **not** a git
repository and must never become one. Dependency is one-way: code *there* may read *here*;
nothing here ever reads a personal file. Three layers enforce it, because `.gitignore` alone does
not stop `git add -f` or a file that is already tracked:

- `.gitignore` — basename patterns for every personal filename
- `tests/test_no_personal_data.py` — fails if any tracked path matches, if anything under
  `data/` is tracked, or if any tracked file exceeds 50 MiB
- `tools/pre-commit` — blocks the commit itself

**2. No `yfinance` on any cloud code path.** A datacentre IP was reported rate-limited across
every yfinance endpoint with no recovery in 48 hours. A cloud session's only durable output is
commits, so a throttled fetch burns credit and commits nothing. yfinance is for local use only.
`tests/test_no_yfinance_in_cloud_paths.py` walks the import graph from every module under
`src/market_monitor/cloud/` and fails if it can reach yfinance.

## Layout

```
recovered/   the Sept-2026 research pipeline, recovered verbatim from a session
             transcript after its scratch directory was deleted. NEVER EDITED.
             See RECOVERY.md. Code recovered is not result validated.
src/market_monitor/
  cloud/     modules a cloud session may run. No yfinance, no personal data.
  local/     modules that run only on the owner's machine. yfinance allowed here.
tests/       the enforcement tests above, plus unit tests
tools/       pre-commit hook and the transcript extractor
results/     written verdicts from gates (committed; they are the evidence trail)
docs/        CLOUD-RULES.md, CREDIT-LEDGER.md, RECOVERY.md
data/        NOT committed. Raw downloads and the price panel live here.
```

## Setup

The virtualenv lives outside OneDrive on purpose, so site-packages is not sync-churned:

```
C:\Users\valer\.venvs\market-monitor\Scripts\python.exe
```

It is also kept separate from the global interpreter because that one runs the owner's work ETL
(nine scheduled Alcor tasks). Never `pip install` into the global interpreter for this project.

```bash
C:/Users/valer/.venvs/market-monitor/Scripts/python.exe -m pytest -q
```

## What this repository is not

It holds no money, places no orders, and contains no recommendation. It ranks and refuses; the
owner decides. It will never display a probability — see §2 of the plan for the measured reason.
