# Trade-God — Project Context for Claude

> The repo name is historical. What lives in it now is a **model lab**: a point-in-time parquet
> warehouse of Binance market data, a backtest library, and pre-registered experiments that test
> whether a trained model beats holding BTC after costs. Every retired system is archived under
> `legacy/`. Nothing there is imported, collected by tests, or deployed.

## What this is

The owner's goal, in their words: build a trading model. "No edge found" is an acceptable answer,
and it is the most likely one. Constraints that shape everything here:

- **Capital is under $1,000.** Real money waits for a forward record, and then only a slice of
  it.
- **Experiment 1 is a daily-to-weekly model** on this warehouse. Its pre-registration spec is
  `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`.
- **The research that set this direction** is in
  `docs/superpowers/specs/2026-10-02-trading-model-research-findings.md`.

## Why the earlier eras ended

**The trading era ended on 2026-09-21.**
- `research/signals/intraday/output/2b/oos_results.csv` measured the surviving strategy at
  **−15.19% return, profit factor 0.986, Sharpe −0.29 over 2,791 trades** (−25.2% under stress).
  Its training-set PF was 1.021.
- The 66-day paper run that looked positive owed its entire gain to about 10 of 312 trades.
- AWS closed the account holding the server. That was the occasion for the pivot, not its cause.

**CoinPicks ended on 2026-10-02.**
- It was a fundamental-scoring tool for altcoins.
- In this warehouse, about 9 in 10 surviving altcoins lagged BTC from every start year since 2022.
- The course framework carried no evidence of its own.
- It was archived to `legacy/coinpicks/`.

State each once, when it is relevant. Do not re-litigate either one, and do not dramatise them.

---

## PRE-REGISTRATION — the rule that outranks every other rule here

An experiment's question, universe, features, target, model family, trial budget, cost model,
gates and sealed out-of-sample window are **committed before the first real-data run**. The git
log is the proof of order.

- **Train is the only place choices are made.** OOS stays sealed until `frozen_params.json` is
  committed in its own commit.
- **The unseal is one-shot,** judged mechanically against the pre-registered gates. A variant that
  fails is recorded as failed. It is never re-tuned against the OOS it failed on, and never
  unsealed twice.
- **Every trial on train is counted.** The deflated Sharpe and the probability of backtest
  overfitting depend on that count.
- **All P&L flows through `research/siglib`** (`backtest.py`, `costs.py`, `data.py`, `events.py`).
  Its look-ahead contract is pinned by tests: a same-bar cheat is worth about zero, and a future
  signal is worth the full budget. A strategy that computes its own P&L outside `siglib` has not
  been tested.
- **Costs are never optimistic.** Taker is 5 bp per side plus slippage (`CostModel`), and the
  pre-registered stress variant doubles the slippage. Maker fills must model adverse selection.
  Phase 2b's maker model was, if anything, generous.
- **A failed experiment is a result.** Write it up like `docs/superpowers/specs/2026-07-15-mr-vwap-2b-findings.md`.

## Standing rulings (`agents/decisions.md`)

- **No seconds-scale or intraday trading.** At retail fee tiers a round trip (10 bp taker, 4 bp
  maker) costs more than the predictable move: about 0.25 bp at 1 second, at most 1.3 bp at 15
  minutes. Re-open this only on new evidence about **costs**. A better model is not that evidence.
- **No real money before a forward record** (paper results gathered in real time, after the
  freeze).
- **The owner's own investing is not this repo's job.** The lab tests models; it does not manage
  savings.

---

## Directory structure

```
research/             # the live code: warehouse fetch/store/check, siglib, signal studies
├── siglib/           # backtest engine, cost models, data loading, event studies — ALL P&L here
├── signals/          # finished studies (carry, xs_momentum, basis_mr, intraday)
└── warehouse/        # gitignored parquet, one file per dataset per symbol
tests/research/       # the Python suite (244 tests)
agents/               # paper trail: handoff.md, CONTEXT.md, decisions.md, roadmap.md
docs/superpowers/     # specs/ (designs + findings) and plans/
legacy/               # every retired system. Not imported, not collected, not deployed.
.github/workflows/ci.yml   # one job: research (python)
```

---

## Stack

- **Python 3.14** with pandas, pyarrow, numpy and duckdb (`requirements-research.txt`), plus
  `requirements.txt`. All of it is dev-machine only; there is no deployment target.
- **Libraries an experiment adds** (for example a gradient-boosting library) are pinned at the
  latest stable at the moment its plan is written, and recorded in the spec.
- **LightGBM 4.7.0** is pinned for Experiment 1 (`requirements-research.txt`).
- **There is no database in the live tree.** The CoinPicks Postgres is archived with its code:
  container `coinpicks-db`, volume `coinpicks_data`, port 5433, compose file now at
  `legacy/coinpicks/docker-compose.yml`. Its volume is kept, not deleted.
  - Port 5432 on this machine belongs to an unrelated container (`medi-pal-db-1`).
  - Never reuse `trade-god_postgres_data`, which holds the dead trading database.

---

## Research Warehouse (`research/`, dev machine only)

Point-in-time market data for experiments.
- **Layout:** parquet, one file per dataset per symbol, under gitignored `research/warehouse/`.
- **Size (2026-10-02):** 1.1 GB, 18.3M rows. Daily klines exist for 219 symbols, with BTC since
  2019-09-09.
- **No order-book or tick data.**
- **Never ships anywhere.**

### Datasets

- `klines_1h/4h/1d`.
- `funding` (full history).
- `premium_index_1h` (basis).
- `oi_1h` and `long_short_1h`. Binance serves only the trailing 30 days, so refresh at least
  monthly or that history is lost.
- `universe` (top-N snapshots with onboard dates).
- `klines_5m/15m` (the intraday top-30 subset only; 5m trailing about 18 months, 15m since
  2023-01-01).
  - These are **excluded from the default dataset list**, so the daily `--top 100` run never
    fetches minute data for 100 symbols.
  - As a result they stop at 2026-07-15. Refresh them explicitly if an experiment needs them.
- `intraday_universe` (top-30 by 30-day median quote volume, as snapshots).
- **Archive datasets**, from Binance's public archive (`data.binance.vision`):
  - `archive_spot_klines_1d/1h`: BTC and ETH since 2017-08.
  - `archive_um_klines_1d`, `archive_um_funding` and `archive_um_premium_1d`: every USDT perp in
    the archive, live or delisted, including 17 settled folders.
  - These are monthly files, so they end at the last complete month. Refresh them with
    `python -m research.archive_backfill`; the daily timer does not touch them.

### Commands

```bash
python -m research.backfill --top 100          # resumable (per symbol×dataset high-water mark)
python -m research.backfill --symbols DOGEUSDT --datasets funding
python -m research.check                       # gap/staleness report
python -m research.intraday_universe --top 30 --save   # print + snapshot intraday top-30
python -m research.archive_backfill            # the public archive; resumable, 8 symbols at a time
python -m research.archive_reconcile           # archive daily closes vs REST; exits 1 on a mismatch
python -m research.signals.model_lab.universe  # listings, data holes, the yearly universe table
python -m research.signals.model_lab.study     # train-only trials + freeze; ran once, never rerun
```

**Rules:** run backfills from the DEV machine only, never from a hosted IP (the 2026-06-05 −1003
ban). Every endpoint is unsigned, so no API keys are needed.

### The daily refresh

A systemd user timer runs `python -m research.backfill --top 100` every day at 05:30.
- **History.** On 2026-10-08 it replaced a cron job that had been installed on 2026-09-22, after
  the warehouse silently stopped in mid-July. The cron refreshed the warehouse on only 3 of 16
  mornings: the machine is usually off at 05:30, and one run failed because `/tmp` was full.
- **Missed runs.** The timer sets `Persistent=true`, so a run missed while the machine was off
  happens at the next boot, once `nm-online` sees the network. Lingering is on, so no login is
  needed.
- **Each run** resolves the day's top-100 USDT perps, saves that universe snapshot, and resumes
  every dataset from its high-water mark.
- **Units:** `~/.config/systemd/user/research-backfill.{service,timer}`.
  `systemctl --user list-timers` shows the last and next run.
- **The log** is the journal, which survives reboots: `journalctl --user -u research-backfill`.

### Survivorship

The warehouse holds today's survivors. A universe drawn from it by today's ranking flatters
anything long-biased.
- An experiment that ranks coins needs a point-in-time universe that includes delisted contracts.
- Binance's public archive (`data.binance.vision`) keeps klines for delisted perps.

### Known data quirks

- **Funding timestamps** carry millisecond jitter (the gap checker tolerates 1.5×).
- **ICPUSDT premium index** has a genuine 77-day hole (2022-07-12 → 2022-09-27).
- **The OI and long/short endpoints are END-anchored.** A `startTime`-only request returns the
  newest rows, so the fetchers paginate with explicit windows.
- **`oi_1h` and `long_short_1h` have a permanent hole** from 2026-06-12 to about 2026-08-24.
- **Binance's archive** has tick-level futures `bookTicker` only through about March 2024.
  `aggTrades` and `bookDepth` are current.
- **Settled folders and relisted tickers.** In the archive, a settled perp gets a flat, zero-trade
  bar every day until its ticker is relisted. A relisted ticker continues the old contract's file
  at an unrelated price. 17 settled folders (`…SETTLED`, `…SETTLEDSETTLED`, `ICPUSDT_SETTLED`)
  hold old contracts' last days. `research/signals/model_lab/listings.py` turns all of this into
  listings, so build price panels from its output, never from raw `archive_um_klines_1d`.
- **Spot archive timestamps** are in microseconds from 2025-01; the parser converts them to ms.
- **Futures archive CSVs** have a header row only from about 2022.
- **Five tickers are Chinese characters** (币安人生USDT, 龙虾USDT …), so archive URLs are
  percent-encoded. The archive has no premium index for any of them.
- **212 TradFi perps** (stocks, ETFs, commodities, FX, pre-IPO) share the UM archive since
  2025-12. `research/signals/model_lab/exclusions.py` keeps them out of the ranker, along with a
  stablecoin, gold tokens and indexes.
- **Some monthly archive files lack days** that daily files hold. 49 perps' 1d klines skip the end
  of 2022-02 and the start of 2022-04. The month a contract settles in gets only daily files in
  its live folder (AERGO's 2026-07). `archive_backfill` fetches both from the daily files, the
  second once a month has passed. A day with no daily file stays a hole; funding has no daily
  files.
- **Three archive closes differ from REST** on 2025-01-28 (ACE, T and TRUMP). The owner ruled
  that the archive's value stands, and `archive_reconcile` reports them apart.

### Signal code

`research/signals/` keeps the finished studies: carry, xs_momentum, basis_mr and intraday.
- `research/signals/intraday/strategy_core.py` moved out of the archived trading engine and is
  kept under test at `tests/research/test_strategy_core.py`.
- The train/OOS runner pattern (mechanical freeze, then a sealed judge) is in
  `research/signals/intraday/mr_vwap_train.py` and `mr_vwap_oos.py`. Reuse it.

Experiment 1's frozen parameters live in
`research/signals/model_lab/output/{arm}/frozen_params.json`. Never edit a frozen file; a change
is a new experiment. The study ran once (2026-10-15): a rerun rewrites the trial log and both
freezes.

---

## The archive map (`legacy/`)

Kept for provenance. Nothing in the live tree imports it, and pytest does not collect it.

| Was | Now |
|---|---|
| CoinPicks: `apps/{api,web}`, `framework/` (the vendored course lessons), pnpm workspace, biome/tsconfig, `docker-compose.yml` | `legacy/coinpicks/` (archived 2026-10-02), with its vocabulary at `legacy/coinpicks/CONTEXT.md` |
| `app/{intraday,api,db,config.py,__init__.py}` | `legacy/app/` |
| `app/intraday/strategy.py` | `research/signals/intraday/strategy_core.py` (kept alive) |
| `alembic/`, `alembic.ini`, `api_main.py`, `intraday_main.py`, the trading-era `docker-compose.yml` and `Dockerfile` | `legacy/` |
| `tests/{intraday,api}/` | `legacy/tests/` |
| `research/v2_eval/` | `legacy/research/v2_eval/` (already broken when archived) |
| DCA bot + swing agent (retired 2026-07-16) | `legacy/app/{bot,swing}/`, `legacy/tests/`, `legacy/docs/` |

Notes on the archive:
- `legacy/SALVAGE.md` is a 2026-09-21 assessment written for CoinPicks. It is history.
- `legacy/coinpicks/` keeps CoinPicks' own rule that its formulas are frozen. If it is ever
  revived, read `legacy/coinpicks/framework/README.md` and its decisions entries first.

---

## How to run

```bash
python -m pytest -q          # the research suite (244 tests)
python -m compileall -q research
```

---

## Testing

Money-paths first. Here that means `siglib` (costs, the backtest engine, the look-ahead contract)
and each experiment's gate logic, not I/O breadth.

- **The suite:** `python -m pytest -q`, configured in `pyproject.toml` (`testpaths = ["tests"]`).
- **The testnet hook:** `tests/conftest.py` skips anything marked `@pytest.mark.testnet` unless
  `RUN_TESTNET=1`. That hook is live infrastructure; don't duplicate it per test file.
- **Markers:** `pyproject.toml` declares **exactly one marker, `testnet`**. `property`,
  `integration` and `slow` left with the suites that used them; do not cite them as available.
- **CI guards against a silently empty suite.** `tests/research/conftest.py` calls
  `pytest.importorskip("pyarrow")`, so an install without the research requirements skips every
  test and still exits 0.
- **Chain test commands with `&&`, never `;`.** A red commit once landed that way.

---

## Session convention

Read `agents/handoff.md` first at session start.
- When a session ends with "let's continue tomorrow" (or similar), overwrite it: what was done, the
  current state, and the next session's plan.
- Record hard decisions in `agents/decisions.md` and completed milestones in `agents/roadmap.md`
  **as they happen**, not at the end.
- `agents/CONTEXT.md` holds the canonical vocabulary. Use its words.

## Git

- Commits land on `main` directly. This is a personal repo, and the owner has said branch ceremony
  is unnecessary here.
- **Never add AI attribution:** no `Co-Authored-By: Claude …` trailers and no generated-with
  footers. The owner is the sole author.
- Write concise commit messages focused on *why*.
- Run the touched suite before calling anything done.
