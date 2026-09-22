# trade-god

![Node](https://img.shields.io/badge/Node-26-339933?logo=nodedotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Hono](https://img.shields.io/badge/Hono-4-E36002?logo=hono&logoColor=white)
![TanStack Start](https://img.shields.io/badge/TanStack%20Start-1.168-EF4444)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)

TypeScript **5.9.3** and Vitest **4.1.11** are deliberate catalog pins, not drift — latest are
TypeScript 7.0.2 (a brand-new Go-native major) and Vitest 5.0.1 (days old); the Hono RPC and
Drizzle `$inferSelect` type workloads get a known-good compiler until the first report commits.
Everything else tracks latest.

> The repo name is historical. What lives here now is **CoinPicks** — a personal crypto
> research platform. The trading system it used to be is archived under [`legacy/`](legacy/).

## What this is

A single-user research tool for analysing crypto tokens against the **CoinPicks** fundamental
framework, and then finding out whether that framework actually works.

The loop is:

1. Research a token and **type every score yourself**. The rubric formulas are frozen and
   implemented exactly as published — nothing is tuned, nothing is clamped.
2. Attach a citation to each claim. A citation counts only once its quote has been
   **mechanically found at its URL** — not "a link was provided".
3. **Commit** the report. A committed report is immutable: enforced by a database trigger, not by
   a convention or a UI that hides the edit button.
4. Committed reports accumulate into a **ledger**, later joined against 30/90/180/365-day forward
   returns computed from a local parquet warehouse of Binance market data.

The ledger is the point. Everything else is scaffolding to make it honest. It may well report
that none of these scores predict anything — that is a result worth having, and the reason every
report is point-in-time and unrewritable.

An LLM is used in exactly one place: as an **EvidenceFinder** that proposes candidate
`{url, quote}` pairs, every one of which is run through the deterministic verifier before it is
even shown. It never proposes a number.

## History — why this repo is named after a trading bot

From 2026-03 to 2026-09 this was an automated trading system on Binance, in four generations: a
DCA spot bot, a rule-based swing futures agent (v1), a retuned swing v2, and finally a
mean-reversion intraday engine — each replacing the last after the previous one failed honest
evaluation. The final one failed too: its pre-registered out-of-sample run
(`research/signals/intraday/output/2b/oos_results.csv`) measured
**−15.19% return, profit factor 0.986, Sharpe −0.29 over 2,791 trades** — −25.2% under stress —
against a training-set profit factor of 1.021. A 66-day paper run *did* look positive, but it was
~1.8 months drawn from a ~6%-monthly-volatility distribution, checked at three sequential gates,
with essentially the whole gain sitting in ~10 of 312 trades. Separately, AWS closed the account
holding the server, which destroyed the paper telemetry. The closure is the occasion for the
pivot, not the cause of it: four systems in a row had measured negative.

What survived is the part that was always the real asset — the point-in-time market-data
warehouse and the discipline of pre-registering a test before running it. Both carry directly
into the ledger.

## What's in `legacy/`

Every retired system, moved unchanged, kept for provenance:

| Path | What |
|---|---|
| `legacy/app/intraday/` | the mean-reversion paper engine (retired 2026-09-21) |
| `legacy/app/swing/`, `legacy/app/bot/` | swing futures agent + DCA spot bot (retired 2026-07-16) |
| `legacy/app/{api,db}/`, `legacy/alembic/` | FastAPI monitoring, SQLAlchemy models, six migrations |
| `legacy/docker-compose.yml`, `legacy/Dockerfile` | the old four-service deployment |
| `legacy/tests/` | their test suites — not collected by pytest |
| `legacy/research/v2_eval/` | a strategy evaluator that had been broken since 2026-07-16 |
| `legacy/docs/` | the swing-era operating docs |

None of it is imported, tested, or deployed. The one module that survived the archive is the
intraday strategy core, which moved to `research/signals/intraday/strategy_core.py` and kept its
test — because `v2_eval` is what happens to an untested module when the thing it imports goes away.

The research trail for all of it is under [`docs/superpowers/`](docs/superpowers/).

## Running it

Requirements: Node 26, pnpm 10, Docker, and Python 3.14 for the warehouse.

```bash
docker compose up -d db     # postgres:16-alpine, 127.0.0.1:5433, volume coinpicks_data
pnpm install
pnpm dev                    # API on :8789, web on :5173 (proxies /api)
```

Port **5433**, not 5432 — 5432 on this machine is held by an unrelated container,
`medi-pal-db-1` (postgres:17.2).

```env
DATABASE_URL=postgresql://coinpicks:coinpicks@localhost:5433/coinpicks
```

Migrations are generated by Drizzle, committed as plain `.sql` under `apps/api/drizzle/`, and
applied by the API at boot before it takes the port. Drizzle is the only thing that writes DDL.

The app binds to loopback only, with no authentication. That is deliberate: one user, one writer,
no `user_id` in any table, and no egress surface for a verifier whose whole job is to fetch
arbitrary third-party URLs.

### Tests

```bash
pnpm test                   # Vitest — scoring and commit-gate paths first
pnpm check                  # Biome
python -m pytest -q         # the Python research suite
```

The commit gate's end-to-end test runs against real PostgreSQL or it does not run at all. An
in-memory store has no transactions, no CHECK constraints and no triggers, so passing against one
would prove nothing about the two properties that matter: atomicity and immutability.

### Research warehouse

`research/` maintains a gitignored point-in-time parquet warehouse (klines, funding, basis, open
interest, long/short ratio, universe snapshots for the top-100 USDT perpetuals). It is dev-machine
only and feeds the ledger's forward returns.

```bash
python -m research.backfill --top 100    # resumable
python -m research.check                 # gap / staleness report
```

## Status

Early. The archive is done and the frozen scoring core is next; the honest estimate is 9–10
working days to the first committed report, with the on-chain liquidity layer excluded from that.
Detailed context for contributors (and for Claude) lives in [CLAUDE.md](CLAUDE.md); decisions and
their reversal costs are in [`agents/`](agents/).

## Not a trading system

This repo places no orders and holds no exchange API keys. Nothing in it is financial advice, and
the framework it implements is explicitly on trial rather than endorsed.
