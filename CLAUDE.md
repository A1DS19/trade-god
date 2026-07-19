# Trade-God — Project Context for Claude

## What this is
Dual-strategy automated trading system on Binance:
1. **DCA Bot** — Dollar-Cost Averaging on Binance Spot (`app/bot/`)
2. **Swing Agent** — Rule-based futures trading on Binance USDT-M (`app/swing/`)

**Tech:** Python 3.12, FastAPI, PostgreSQL 16, Docker Compose, Alembic, AWS Lightsail 2GB RAM

---

## Directory Structure
```
app/
├── bot/          # DCA spot bot (trader.py, exchange.py, indicators.py, universe.py, notifier.py, commands.py)
├── swing/        # Swing futures agent (main.py, agent.py, snapshot.py, indicators.py, exchange.py, notifier.py, config.py, shadow.py, rebalance.py, grid_search.py, wf_grid_search.py, backtest_replay/)
├── db/           # SQLAlchemy models (models.py)
├── api/          # FastAPI routes (main.py)
└── config.py     # Shared DCA config + Telegram credentials

alembic/versions/ # 5 migrations (001–005)
docker-compose.yml
main.py           # DCA entrypoint
swing_main.py     # Swing entrypoint
api_main.py       # API entrypoint
```

---

## Docker Services
| Service | Description | Port |
|---------|-------------|------|
| db | PostgreSQL 16 | 5432 (internal) |
| migrate | Alembic upgrade head (run-once) | — |
| intraday | Intraday paper engine — keyless | — |
| api | FastAPI monitoring | 8000 |

**Key commands:**
```bash
docker compose up -d --build
docker compose logs -f intraday
docker compose logs --timestamps intraday > logs.txt 2>&1
```

---

## Intraday Engine (`app/intraday/`)

Phase 3 replacement for the DCA bot and swing agent: `mr_vwap` maker-limit mean-reversion,
paper mode only (`EXECUTION_MODE=paper`; `live` raises `NotImplementedError`), no API keys
required. Strategy params are **frozen** (pre-registered from 2b research — H=32 bars, K=10
slots, Z_ENTRY=−3.0; do not tune without a new research phase), 900s cycle aligned to 15m
candle close, $100 paper equity. Every placed virtual limit resolves to `trade_through` /
`touch_only` / `miss` and is logged as fill telemetry. Kill-switches (5% daily paper loss or
20% drawdown) halt trading and persist in `intraday_state`; resume requires an operator
restart with `INTRADAY_RESUME=1`. Universe: weekly top-30 by 30-day median quote volume.
Telemetry lives in `intraday_trades` / `intraday_limits` / `intraday_state`. Full design:
`docs/superpowers/specs/2026-07-15-intraday-engine-design.md`. Ops runbook (message
reference, monitoring SQL, resume procedure): `docs/intraday_operations.md`.

---

## Research Warehouse (`research/`, dev machine only)

Point-in-time market data for signal research/backtests — parquet per dataset per symbol under
gitignored `research/warehouse/` (~360MB, 6M+ rows, top-100 USDT perps since listing).
**Never ships to prod**: excluded via `.dockerignore`; deps in `requirements-research.txt`
(pandas/pyarrow/duckdb) are never installed on the Lightsail box.

Datasets: `klines_1h/4h/1d`, `funding` (full history), `premium_index_1h` (basis),
`oi_1h` + `long_short_1h` (Binance serves trailing 30d only — refresh ≥ monthly or history is lost),
`universe` (top-N snapshots with onboard dates), `klines_5m/15m` (intraday top-30 subset only —
5m trailing ~18 months, 15m since 2023-01-01; **excluded from the default dataset list** so the
weekly `--top 100` cron never fetches minute data for 100 symbols), `intraday_universe`
(top-30-by-30d-median-quote-volume snapshots).

```bash
python -m research.backfill --top 100          # resumable (per symbol×dataset high-water mark)
python -m research.backfill --symbols DOGEUSDT --datasets funding
python -m research.check                       # gap/staleness report
python -m research.intraday_universe --top 30 --save   # print + snapshot intraday top-30
# refresh klines_1d first so the 30d medians are current, then intraday klines (dev machine only):
python -m research.backfill --symbols "$(python -m research.intraday_universe --top 30 --save)" --datasets klines_5m,klines_15m
```

**Rules:** run backfills from the DEV machine only — never the prod IP (2026-06-05 -1003 ban).
All endpoints are unsigned (no API keys). Weekly refresh cron (also stitches the 30d OI/L-S window):
`0 6 * * 1 cd /home/dev/projects/trade-god && python -m research.backfill --top 100 >> /tmp/research-backfill.log 2>&1`

**Known data quirks:** Binance funding timestamps carry ms jitter (gap checker tolerates 1.5×);
ICPUSDT premium index has a genuine 77-day hole (2022-07-12 → 2022-09-27); OI/L-S endpoints are
END-anchored (`startTime`-only returns newest rows — fetchers paginate with explicit windows).

---

## Credentials (`.env`)
- `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` — Spot (DCA bot)
- `BINANCE_API_KEY_FUTURES` / `BINANCE_SECRET_KEY_FUTURES` — Futures (swing agent)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `DATABASE_URL` — `postgresql://tradegod:tradegod@db:5432/tradegod`

---

## Swing Agent (`app/swing/`)

Retired 2026-07-16 to `legacy/` (code + tests: `legacy/app/swing/`, `legacy/tests/swing/`,
`legacy/tests/backtest/`, `legacy/tests/property/`, `legacy/tests/integration/`, `legacy/swing_main.py`).
`swing_trades` table kept as history (see Database Schema); superseded by `app/intraday/` above.

## DCA Bot (`app/bot/`)

Retired 2026-07-16 to `legacy/` (code + tests: `legacy/app/bot/`, `legacy/tests/bot/`, `legacy/main.py`).
`positions`/`trades` tables kept as history; DCA spot holdings on Binance are left held, managed manually.

---

## Database Schema

### `positions` (DCA open positions)
coin (PK), avg_buy, qty, last_buy, peak_price, partial_taken

### `trades` (DCA audit log)
id, coin, side, price, qty, cost_usd, avg_buy, realized_pnl_usd, realized_pnl_pct, exit_reason (VARCHAR 30), timestamp

### `swing_trades`
id, coin, direction, entry_price, exit_price, qty, leverage, notional_usdt, entry_time, exit_time, realized_pnl_usd, realized_pnl_pct, exit_reason (VARCHAR 100), entry_sl_pct, entry_tp_pct, agent_confidence, agent_reasoning (**VARCHAR 500 — truncate to 499 chars**), status

### `daily_spend` / `coin_list`
Tracking tables for DCA daily cap and universe cache.

---

## FastAPI Endpoints (port 8000, tunnel-only)
`GET /` (HTML status page) `/health` `/intraday/{trades,stats,fills,state,gate}`
`/legacy/dca/{portfolio,pnl,trades,stats}` `/legacy/swing/{trades,stats}` `/docs`

## Telegram
- DCA bot: `/status` `/pnl` `/trades` `/balance` `/help` commands + buy/sell/daily summary alerts
- Swing: open/close alerts with confidence + reasoning
- **IMPORTANT:** Always `html.escape()` agent reasoning before sending (parse_mode=HTML)

---

## Known Issues & Fixes

### Fixed (2026-06-13): silent exchange-side fills + safety-net override + algo cancel + forming-candle indicators
- `app/swing/reconcile.py` diffs DB open rows vs exchange positions each cycle; backfills closes
  from `futures_account_trades` (exit = closing-fill VWAP bounded by row qty, PnL = summed
  realizedPnl), alerts, and feeds the loss cooldown. Empty fills retry 3 cycles before a
  price-estimated fallback; userTrades window clamped to <7d (-1127). Repaired silent algo-SL
  closes DOGE id=71 (2026-06-11) and BSV id=72 (2026-06-12) on first deploy.
- Client safety net now uses per-trade `entry_sl_pct`/`entry_tp_pct` via `_net_thresholds`
  (fallback: DEFAULT_*) — the flat 3%/8% net no longer preempts wider ATR stops.
- `cancel_open_orders` also DELETEs `/fapi/v1/algoOpenOrders` (placement was fixed 2026-06-05;
  cancellation wasn't) and never raises. `scripts/cleanup_orphan_algo_orders.py` audits orphans.
- Indicators drop the still-forming last kline (4h + 1d), RSI warms up on the full 200-bar
  series, daily fetch deepened to 601 for a converged EMA200. `snap["price"]` = last closed close.

### Fixed (2026-06-05): Binance -4120 SL/TP error — for real this time
Binance migrated USDT-M conditional orders to the **Algo service on 2025-12-09**.
`STOP_MARKET`/`TAKE_PROFIT_MARKET` on `POST /fapi/v1/order` now reject with `-4120`.
The 2026-04-02 "fix" (`quantity=qty, reduceOnly=True`) never worked — the 37-day HOLD
dry spell hid it until BSV (May 23). Every live trade since ran with **no exchange-side
stop** (only the hourly client-side net protected them).
**Real fix:** `app/swing/exchange.py:_place_conditional()` routes to `POST /fapi/v1/algoOrder`
with `algoType=CONDITIONAL`, `triggerPrice` (not `stopPrice`), `closePosition="true"`,
`workingType=MARK_PRICE`. python-binance 1.0.19 has no wrapper, so it calls the same
internal `_request_futures_api('post', 'algoOrder', True, data=...)` that `futures_create_order`
uses. Watch logs for `SL placed`/`TP placed` to confirm. Pinned by `tests/swing/test_exchange_sltp.py`.

### Gotcha: agent_reasoning VARCHAR(500)
Must truncate to 499 chars before DB insert.

### Gotcha: Telegram HTML mode
Escape all dynamic text with `html.escape()` before sending.

---

## Testing
- Run: `python -m pytest` (fast; fully green — no excepted failures). Config in `pyproject.toml`.
- Layout: `tests/{intraday,research}/` + `tests/conftest.py` (env stub set at import time — **don't re-add env/`sys.path` boilerplate in test files**). Legacy bot/swing tests live in `legacy/tests/` and are not collected.
- Markers: `property`, `integration`, `testnet` (skipped unless `RUN_TESTNET=1`), `slow`.
- Philosophy: money-paths first; the strategy lives ONCE in `app/intraday/strategy.py` (research imports it), and `tests/intraday/test_paper_book.py::test_replay_parity_with_batch_builder` pins the live PaperBook to the batch builder bar-for-bar.
