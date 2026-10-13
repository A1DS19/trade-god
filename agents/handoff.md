# Where we left off
_2026-10-13_

## This session

The session ran from 2026-10-12 into 10-13 and covered three things.

**First, an idea the owner dropped.** It was a platform where people log in with crypto wallets
and the system trades pairs for them. The owner scratched it before anything was built.

**Second, phase 2 (data) is closed.**
- **The archive download.**
  - It now downloads eight symbols side by side (`1aec1c3`), which took it from 2,300 to 19,900
    files an hour.
  - It finished on 2026-10-12 at 22:32: 2.41M rows and 0 failures.
- **Reconciliation against REST**, Task 5. The first real run failed on two findings, and the
  owner ruled on both (`104125b`, `d95b5c0`, `d8faa4c`):
  - **Monthly files that skip days.** Binance's monthly files skip days for 49 perps. Those days
    now come from the daily files.
  - **Three mismatches.** ACE, T and TRUMP on 2025-01-28 are reviewed exceptions that keep the
    archive's value.

  The rerun passed: 259 symbols, 253,392 shared days, 0 mismatches.
- **Task 12's checks found 4 more holes.** The month a contract settles in never gets a monthly
  file in its live folder. AERGO lost its last 23 trading days that way.
  - The owner ruled to fill them (`73b1b8d`, `5063e8a`).
  - The real run filled 104 rows. That left 0 data holes and 913 listings over 900 tickers.
- **The owner signed off the data step.** The exclusions were approved as drafted, and the step
  was closed in `b28e743`.

**Third, phase 3's plan is written and approved:**
`docs/superpowers/plans/2026-10-12-model-lab-phase3-timing-arms.md` (`4ad3ef5`).
- **Ten tasks**, from the spec's open definitions through the BTC and ETH arms' code to the
  validation study and the freeze.
- **The code is pre-tested.** Every code block was run in a scratch copy: 241 tests passed, and
  all 15 planted bugs were caught. The plan carries all of it verbatim, so the scratch copy is not
  needed.
- **Nothing has run on real data yet.**

### The owner's rulings this session

| Topic | Ruling |
|---|---|
| Wallet-login trading platform | Scratched |
| Archive fetcher | Eight symbols side by side, each still paced at 0.2 s |
| Days a monthly file skips | Fetched from Binance's daily files; a day with no daily file stays a hole |
| ACE, T and TRUMP closes on 2025-01-28 | Reviewed exceptions: the archive's value is kept, and they are reported apart |
| A settled contract's last month | Fetched from the live folder's daily files, once a month has passed |
| Exclusions | Approved as drafted; USTC, FRAX, STABLE, STBL, USUAL and PUMPBTC stay in |
| Data step | Signed off; phase 2 is closed |
| Weekly returns | **Summed, not compounded** (2026-10-13), for Sharpe, alpha and the deflated Sharpe |
| Phase 3 plan | Approved, to be run natively (in-session, one fresh reviewer at the end) |
| Push | Approved in a question, but the push command itself was declined as the session ended |

### What got caught by running things rather than reading them

- **Binance's monthly archive is incomplete in two ways.**
  - 49 perps' 1d klines for 2022-02 end on the 25th, and those for 2022-04 start on the 3rd.
  - A contract settled mid-month never gets that month's monthly file.

  The daily files hold the missing days in both cases.
- **The archive has no premium index for the 5 Chinese-character tickers** (none of its 982
  premium folders has one), though their klines and funding exist. Phase 4 must cope.
- **Compounding gave fractional positions free alpha.** `run_backtest` rebalances to the decided
  weight daily for free, and compounding those days into weeks let a constant fraction of BTC beat
  BTC's Sharpe with α > 0. In a toy series, half of BTC scored 43.7 against 41.2, with t(α) 5.9.
  That is why weekly returns are now summed.
- **The pipeline's power is low.** On synthetic markets a planted signal needed about 1% a day to
  be found reliably: a hit rate of 0.59–0.67. At 0.3–0.5% a day it was barely found. Overlapping
  7-day labels leave about 200 independent samples per refit.

## State

- **Git:** `main`, pushed through `d8faa4c`. Five commits are local and not pushed: `73b1b8d`,
  `5063e8a`, `b28e743`, `4ad3ef5` and this handoff.
- **Tests:** pytest, 195 passing.
- **The warehouse** is 1.3 GB, and the archive datasets hold 4,193,700 rows through 2026-09. The
  05:30 daily timer is unchanged. The `archive-backfill` unit has finished and is gone.
- **LightGBM is not installed yet.** Phase 3's Task 3 pins and installs 4.7.0.

## Next session

1. **Ask before pushing the five local commits.** The owner said yes in a question, then declined
   the push itself at the end of the session.
2. **Run phase 3's plan natively** (`superpowers:executing-plans`), task by task.
   - **Task 1** amends the spec with the approval and ruling dated 2026-10-13. It must be
     committed before Task 10's real-data run.
   - **Tasks 2–9** copy the plan's tested code verbatim, following red, then green, then commit.
   - **Task 10** runs the study:
     - first `python -m research.signals.model_lab.study`;
     - then the trial-log commit;
     - then the freeze in its own commit;
     - then CLAUDE.md and the roadmap.
     If the study raises, stop and show the owner; nothing may be picked after seeing train
     data.
   - **At the end,** one fresh reviewer checks everything phase 3 changed.
3. **Then phase 4's plan: the ranker.** The plan's "Handed on" section lists what carries over:
   - the shared trial log (append to it, never rewrite it);
   - the objective parameter for the regressor;
   - the percentile label;
   - Monday refits.

## Open items

- **The TypeSafe key** is still pending, and phase 1 waits on it.
- **Revoke trading-era keys.** `.env` still holds the Binance keys, Telegram token and Claude API
  key from the trading era. Revoke them at the source.
- **Dead docker volumes:** `trade-god_postgres_data`, `trade-god_klines_cache`,
  `trade-god_swing_data`.
- **Stale datasets.** The warehouse's 5m and 15m datasets stop at 2026-07-15. Experiment 1 does
  not need them.
- **Stale key file.** `LightsailDefaultKey-ap-southeast-1.pem` sits untracked in the repo root,
  but its account is closed.
- **Leftover folders.** `node_modules/` in the root and under `legacy/coinpicks/apps/`, plus
  `legacy/coinpicks/apps/web/dist`. They are gitignored, regenerable, and were blocked from
  deletion; remove them by hand if wanted.
