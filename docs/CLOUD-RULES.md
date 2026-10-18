# Rules for every cloud session in this repository

Paste this into the brief of any cloud session. A cloud session is ephemeral, has no
conversational channel back, and spends a fixed one-off budget — so every rule here exists
because breaking it burns money and leaves nothing behind.

## 1. Commits are the only output

Anything not committed and pushed did not happen. Commit **after every step**, never once at the
end. Before starting, name in the brief the intermediate artefact a successor session would
resume from; a session that dies 90% through a single monolithic job has produced nothing.

## 2. No `yfinance`, ever, on any path reachable here

A datacentre IP was reported rate-limited across every yfinance endpoint with no recovery in 48
hours. The session cannot tell anyone it is throttled. It will spend credit retrying and commit
nothing. Public bulk sources only.

Enforced by `tests/test_no_yfinance_in_cloud_paths.py`. If a cloud job needs prices, a local run
writes a committed artefact first and the cloud path reads that.

## 3. No personal financial data

Nothing here reads `C:\Users\valer\Investing`, and a cloud session cannot see it anyway. Never add
a personal file, never `git add -A`. `tools/githooks/pre-commit` and
`tests/test_no_personal_data.py` block it; do not use `--no-verify`.

## 4. Respect the sources

- **SEC EDGAR** — declare a User-Agent in the form `Name email@domain`; at most 10 requests/second.
  A missing User-Agent returns an "Undeclared Automated Tool" response. `companyfacts.zip` and
  `submissions.zip` are nightly bulk recompiles (~03:00 ET); `full-index` rebuilds early Saturday.
- **Do not use the EDGAR `frames` API for historical panels.** A frames fact comes from the
  entity's *last filed* submission, so values silently mix originally-filed and restated numbers,
  concentrated in exactly the companies that restate. Use the quarterly **Financial Statement Data
  Sets** instead: as-filed, "presented without change", with a real filing date per row.
- **FINRA** short interest is free, twice monthly.
- Anything paid (e.g. Sharadar) requires an API key that is **never committed**. If a job needs
  one, it arrives as an environment variable and the session must not echo it.

## 5. The session runs tests; it does not search for a better answer

Do **not** tune `algo_v4.py`, re-weight factors, adjust thresholds or try configurations to
improve a result. Every configuration tried inflates the multiple-testing bar that the same
project is trying to measure honestly, and an unwatched session with a budget will happily search.
If a job's result looks wrong, report it; do not fix it by tuning.

## 6. Write the verdict down

Every gate produces a file in `results/` stating the numbers and a plain pass/fail verdict —
including when it fails. A gate whose result is only in a session transcript has not been
recorded, because the transcript is not read again.

## 7. Account for the money

Append to `docs/CREDIT-LEDGER.md` before the session ends: what was spent, against which package,
and the remaining balance.
