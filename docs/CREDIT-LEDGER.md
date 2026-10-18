# Credit ledger — the USD 90

A one-off budget that is not itself audited gets spent on whatever a session felt like doing.
Every dollar is accounted here against a named package or a named defect.

**Opening balance: USD 90.00. Spent to date: USD 0.00.**

## Status

| | |
|---|---|
| Repo exists and is pushed | **pending** — see the setup checklist below |
| Cloud availability | `available: false`, reason `no_readable_git_checkout` (probed 2026-10-18) |
| Cloud environment confirmed | **unknown** — a second precondition, separate from the repo |
| Does the credit expire? | **UNKNOWN — find out before planning around a multi-week local gate** |
| Real cost of one session | **UNMEASURED** — every figure below is provisional until C0 |

## Allocation — PROVISIONAL

No one has measured what a session of this shape actually costs, so these are guesses. **C0 is
spent first and the rest is re-allocated against the real reading.**

| | Package | ~USD | Spent | Gate it serves |
|---|---|---|---|---|
| C0 | Burn-rate calibration: one deliberately trivial session. Prove the mechanism — repo, venv, incremental commits, tests green in a PR — and read the actual consumption | 5 | — | Nothing expensive may depend on an untested platform |
| C1 | As-filed fundamentals from the SEC Financial Statement Data Sets (2009Q1–2026Q3), reduced to a committed parquet with a real filing date per row | 20 | — | Replaces the restatement-contaminated `frames` route; removes the 90-day-lag approximation |
| C2 | **Block bootstrap** — re-run the whole factor search per resample against the reconstructed trial count | 25 | — | **KILL GATE: p > 0.10 on the best configuration ends the prediction half** |
| C3 | Survivorship **bound** at three imputation severities, reported beside the survivor-only baseline | 15 | — | Only if the Form 25 join-rate test passes first (free, local, ~20 min) |
| C4 | Local review of everything the cloud committed | 0 | — | A cloud commit is a claim, not a result |
| C5 | Reserve, releasable only against a named failing test | 25 | — | Every stage finds one defect |

## Rules

1. **Nothing is spent until the free local gates have had their chance to end the project.**
   Stage 3 of the plan — reproduce, Newey-West on the actual IC series, the trials ledger, real
   costs — costs nothing and is the likeliest route to a verdict of "do not continue".
2. **C2 is a gate, not a line item.** Its kill condition is written above, before it runs.
3. The reserve is not a slush fund. Releasing it requires naming the failing test.
4. If a session overruns its package, it stops and records the overrun here rather than
   continuing on the next package's money.

## Log

| Date | Session | Package | USD | Balance | Outcome |
|---|---|---|---|---|---|
| 2026-10-18 | repo + venv setup (local) | — | 0.00 | 90.00 | Repo skeleton, enforcement tests, recovered pipeline committed. No credit touched. |
