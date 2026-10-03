# trade-god

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)

> The repo name is historical. What lives here now is a **model lab**: a point-in-time warehouse of
> Binance market data, plus a backtest library, used to test trading models under pre-registration.
> The systems this repo used to be are archived under [`legacy/`](legacy/).

## What this is

A single-user lab for one question, asked carefully, one experiment at a time: **can a model
trained on this data beat holding BTC, after costs?**

Each experiment follows the same loop:

1. **Pre-register.** The spec, the gates and the code are committed before the first real-data
   run, so the git log proves which came first.
2. **Train only on the train period.** Every trial is counted, and costs come from one shared cost
   model.
3. **Freeze, then unseal once.** The chosen parameters are committed, and only then is the sealed
   out-of-sample period evaluated, mechanically, against the pre-registered gates.
4. **Forward record before money.** A strategy that passes earns a paper record in real time.
   Real money waits for that record.

"No edge found" is an acceptable answer, and is the most likely one. It has been the answer to
every candidate tested here so far.

The first experiment is a **daily-to-weekly model**. Seconds-scale trading is ruled out, because
at retail fee tiers a round trip costs more than the move a model can predict. The evidence is in
[`docs/superpowers/specs/2026-10-02-trading-model-research-findings.md`](docs/superpowers/specs/2026-10-02-trading-model-research-findings.md).

## History — why this repo is named after a trading bot

**2026-03 → 2026-09: automated trading on Binance, in four generations.** A DCA spot bot, a
rule-based swing futures agent (v1), a retuned swing v2, and a mean-reversion intraday engine. Each
replaced the last after the previous one failed honest evaluation.

The last one failed too. Its pre-registered out-of-sample run
(`research/signals/intraday/output/2b/oos_results.csv`) measured
**−15.19% return, profit factor 0.986, Sharpe −0.29 over 2,791 trades**.

**2026-09-21 → 2026-10-02: CoinPicks**, a tool that scored altcoins against a course framework.
It was built through its editor and then retired:
- In this warehouse, about 9 in 10 surviving altcoins lagged BTC from every start year since 2022.
- The framework carried no evidence of its own.

**What survived both eras** is the part that was always the real asset: the warehouse, and the
discipline of pre-registering a test before running it.

## What's in `legacy/`

Every retired system, moved unchanged and kept for provenance:

| Path | What |
|---|---|
| `legacy/coinpicks/` | CoinPicks: Hono API, TanStack Start editor, Drizzle schema with immutability triggers, vendored framework lessons (retired 2026-10-02) |
| `legacy/app/intraday/` | the mean-reversion paper engine (retired 2026-09-21) |
| `legacy/app/swing/`, `legacy/app/bot/` | swing futures agent + DCA spot bot (retired 2026-07-16) |
| `legacy/app/{api,db}/`, `legacy/alembic/` | FastAPI monitoring, SQLAlchemy models, six migrations |
| `legacy/docker-compose.yml`, `legacy/Dockerfile` | the old four-service deployment |
| `legacy/tests/` | their test suites — not collected by pytest |
| `legacy/research/v2_eval/` | a strategy evaluator that had been broken since 2026-07-16 |
| `legacy/docs/` | the swing-era operating docs |

None of it is imported, tested or deployed. The one module that survived the trading archive is the
intraday strategy core, which moved to `research/signals/intraday/strategy_core.py` and kept its
test.

The research trail for all of it is under [`docs/superpowers/`](docs/superpowers/).

## Running it

Requirements: Python 3.14 and the packages in `requirements.txt` + `requirements-research.txt`.

```bash
python -m research.backfill --top 100    # resumable; a 05:30 cron runs this daily
python -m research.check                 # gap / staleness report
python -m pytest -q                      # the research suite
```

`research/` maintains the gitignored point-in-time parquet warehouse: klines, funding, basis, open
interest, long/short ratio, and universe snapshots for the top-100 USDT perpetuals. It is
dev-machine only. Run backfills from a home connection, never from a hosted IP.

Detailed context for contributors (and for Claude) lives in [CLAUDE.md](CLAUDE.md). Decisions and
their reversal costs are in [`agents/`](agents/).

## Not a trading system

This repo places no orders and holds no exchange API keys. Nothing in it is financial advice.
