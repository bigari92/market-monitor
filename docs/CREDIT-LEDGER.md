# Credit ledger — the USD 90

A one-off budget that is not itself audited gets spent on whatever a session felt like doing.
Every dollar is accounted here against a named package or a named defect.

**Opening balance: USD 90.00. Spent to date: USD 0.00.**

## Status

| | |
|---|---|
| Repo exists locally | **yes** — first commit 2026-10-18, 52 files, clean tree |
| Pushed to GitHub | **yes** — `bigari92/market-monitor`, PRIVATE, default branch `main`, 2026-10-18 |
| Published content verified clean | **yes** — the remote tree (52 blobs) and *every* commit were scanned for personal filenames; none present, largest blob 9.5 KB. A push publishes all commits, not just the tip, so the history scan is the one that matters |
| Cloud availability | **`available: true`** once the session's project folder became this repo (2026-10-18). Listed as `market-monitor -> bigari92/market-monitor` |
| Cloud environment confirmed | **yes** — one environment, `Default` (`hosted: true`, `isDefault: true`, `env_01LSggXGXzzEW1UYAbN3Ygcz`). All three preconditions cleared; the USD 90 is now spendable |

### Three preconditions, not one

Measured, not assumed. Each was discovered by probing rather than by reading docs:

1. **A GitHub remote.** `gh` is installed (2.102.0) but not authenticated, and `gh auth login` is
   interactive — the owner runs it, nobody else can.
2. **A cloud environment.** Separate from the repo, and it can be refused on its own
   (`hosted: false` means it needs the owner's click; `fitsRepository: false` means it cannot run
   this repository). Still unverified.
3. **The repo must be the session's *project folder*, or be named explicitly.** This one is easy
   to miss: after the first commit here, availability was still `no_readable_git_checkout`,
   because the app checks the session's project folder — `C:\Users\valer\OneDrive\Рабочий
   стол\Claude` — and a git repo *nested inside* it does not count. Two ways round it: open
   `market-monitor` as its own session folder, or start the cloud session with an explicit
   `repository: "<owner>/market-monitor"`, which is permitted even when the current project has
   no repo of its own.
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
| 2026-10-18 | push to GitHub (local) | — | 0.00 | 90.00 | bigari92/market-monitor created PRIVATE and pushed. Remote tree and full history verified free of personal data. Preconditions 1 of 3 cleared; 2 unknown, 3 pending a turn boundary. No credit touched. |
| 2026-10-18 | **first cloud session** — feed probe + tracker build + horizon test | C0, overran into tracker work | **not self-measurable — see below** | **unknown; owner must read it** | Feed question settled (free panel viable, zero data cost). Tracker built, tested, first dated run committed. Cadence settled by measurement, not judgement: `results/horizon_test.md`. Six commits on `main-grop3y`. |

## C0 — the burn-rate calibration, and the one thing it could not do

C0's purpose was to "prove the mechanism — repo, venv, incremental commits, tests green — and
read the actual consumption". The mechanism is proven. **The consumption is not readable from
inside the session, and this is a finding C0 was supposed to produce.**

A cloud session has no access to its own billing. It cannot see a dollar figure, a token count,
or a remaining balance, so rule 7 — "append what was spent before the session ends" — cannot be
satisfied by the session alone. The honest entry is a blank with a pointer, not a guess, and an
invented figure would be worse than a blank because it would be carried forward as fact.

**The owner closes this loop**, by reading the actual spend from the Claude console and replacing
the row above. Until then no package below should be planned against a per-session cost.

What *is* measurable from inside, as a proxy for the next session's planner:

| | |
|---|---|
| Wall-clock, end to end | ~70 minutes |
| Full-universe price sweeps | 3 — two 5-year (149s, 150s) and one 20-year (179s). ~2 GB fetched, **0 failures across 21,477 requests** |
| 24-month replay over the cached panel | 1, ~90s |
| Horizon test: 190 rebalance dates scored at two horizons | 1, ~6 min |
| Test suite runs | 11 (12 tests at start → 78 at end) |
| Commits pushed | 6 |
| Peak disk for the cached panel | 270 MB (gitignored, never committed) |
| **Data cost** | **USD 0.00 — every source used is free** |

### What this session actually did against the plan

It was not a trivial session, so it did not stay inside C0's USD 5 shape. The brief directed it
to settle the feed question first and then build the tracker, which is a larger job than a
calibration run. Recorded as an overrun rather than quietly re-scoped: if the owner's console
shows this cost materially more than USD 5, **the C1–C5 allocations below are still provisional
and should be re-cut against the real reading before C1 is authorised.**

The work does, however, remove cost from two later packages:

- **C1 (as-filed fundamentals, USD 20)** is now cheaper and de-risked: the SEC Financial
  Statement Data Sets were measured at 60 MB in 1.2 s from this environment, and the universe
  already carries the CIK, so the ticker-matching step C1 assumed is gone.
- **C3 (survivorship bound, USD 15)** is narrower than written: the *forward* tracking record is
  survivorship-bias-free by construction, so C3 is now only about rehabilitating the historical
  backtest, which is a separable question the tracker does not depend on.

Neither saving is booked until someone measures it.
