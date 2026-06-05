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
├── swing/        # Swing futures agent (main.py, agent.py, snapshot.py, indicators.py, exchange.py, notifier.py, config.py)
├── db/           # SQLAlchemy models (models.py)
├── api/          # FastAPI routes (main.py)
└── config.py     # Shared DCA config + Telegram credentials

alembic/versions/ # 4 migrations (001–004)
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
| bot | DCA spot bot | 8080 (health) |
| swing | Swing futures agent | — |
| api | FastAPI monitoring | 8000 |

**Key commands:**
```bash
docker compose up -d --build
docker compose logs -f swing
docker compose logs --timestamps swing > logs.txt 2>&1
```

---

## Credentials (`.env`)
- `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` — Spot (DCA bot)
- `BINANCE_API_KEY_FUTURES` / `BINANCE_SECRET_KEY_FUTURES` — Futures (swing agent)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `DATABASE_URL` — `postgresql://tradegod:tradegod@db:5432/tradegod`

---

## Swing Agent (`app/swing/`)

### Coins (13)
DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA, FET, ENS, TON, HYPE — Binance USDT-M perpetuals. Screened from top 100 by market cap (see `docs/coin_screening_and_selection.md`). DOT removed 2026-04-11 (net-negative at MIN_CONFIDENCE=0.80). 2026-06-05: FET + ENS + TON added (walk-forward validated — positive in both train & OOS windows); ZEC rejected (net-negative OOS); HYPE re-added by user request despite failing walk-forward (only ~1yr history, −0.31 OOS — weakest in the book).

### Config (`app/swing/config.py`)
| Param | Value |
|-------|-------|
| LEVERAGE | 5x |
| POSITION_USDT | $5–$10 (confidence-scaled, notional $25–$50) |
| MAX_OPEN | 3 simultaneous positions |
| DEFAULT_SL_PCT | 3% (client-side safety net) |
| DEFAULT_TP_PCT | 8% (client-side safety net) |
| MIN_CONFIDENCE | 0.80 |
| MIN_ADX_ENTRY | 28.0 (hard entry gate) |
| MIN_RSI_SHORT | 42.0 (soft — confidence penalty only) |
| MAX_RSI_LONG | 58.0 (soft — confidence penalty only) |
| SHORT_ENTRY_RSI_FLOOR | 32.0 (**HARD** gate — block short if RSI below; = exit floor) |
| LONG_ENTRY_RSI_CEIL | 68.0 (**HARD** gate — block long if RSI above; = exit ceil) |
| BORDERLINE_ADX_PENALTY | 0.08 |
| ENABLE_PARTIAL_ENTRIES | False |
| REQUIRE_DI_ALIGNMENT | True |
| LONG_EXIT_RSI_CEIL | 68.0 |
| SHORT_EXIT_RSI_FLOOR | 32.0 |
| CHECK_INTERVAL | 3600s (1 hour) |
| LOSS_COOLDOWN_HRS | 4h |

### Strategy — 4-step pipeline (`app/swing/agent.py`)

**Step 1: Exit Check**
- Longs exit: 4h EMA bearish, daily EMA bearish, RSI > 68, MACD divergence with RSI > 68, OI drop >3% + MACD weakening, ADX < 20
- Shorts exit: inverse conditions (RSI < 32, MACD_DIV_EXIT_RSI_SHORT = 32)
- Mixed EMA alone does NOT exit (removed 2026-04-08 — see `project_exit_tuning_2026-04-08.md`)

**Step 2: Regime Gate**
- ADX > 25 → trending label
- ADX 20–25 → borderline label (−0.08 confidence penalty)
- ADX < 20 → ranging (NO new entries)
- Note: `MIN_ADX_ENTRY = 28` is a separate, stricter hard gate — trending setups with ADX 25–27 are blocked at the entry check.

**Step 3: Entry Conditions (ALL required)**
- Short: daily EMA bearish + 4h EMA bearish (strict stack) + MACD hist < 0 + ADX ≥ 28 + -DI > +DI
- Long: daily EMA bullish + 4h EMA bullish (strict stack) + MACD hist > 0 + ADX ≥ 28 + +DI > -DI
- RSI **hard gate** (added 2026-06-05): block short if RSI < `SHORT_ENTRY_RSI_FLOOR` (32), block long if RSI > `LONG_ENTRY_RSI_CEIL` (68) — don't enter the zone your own exit rule would immediately close. The softer `MIN_RSI_SHORT` (42) / `MAX_RSI_LONG` (58) still feed confidence penalties on top. See `project_rsi_entry_gate_2026-06-05.md`.

**Step 4: Confidence Scoring (must reach ≥ 0.80)**
- Confirming signals: vol spike (+0.05), funding (+0.04), OI rising (+0.04), DI alignment (+0.04), Stoch RSI extreme (+0.04), L/S ratio crowded (+0.04), RSI healthy zone (+0.03), EMA200 alignment (+0.03), ATR rank >70% (+0.03), VWAP (+0.03), taker ratio (+0.03)
- Contradicting signals: −0.02 to −0.08 each
- Borderline ADX penalty: −0.08

### SL/TP Sizing (`app/swing/snapshot.py`)
```
SL = ATR14 × 1.5  (min 1%)
TP = ATR14 × 3.0  (min 2%)
```

### Two-Layer SL/TP
1. **Exchange-side:** `STOP_MARKET` + `TAKE_PROFIT_MARKET` orders in `app/swing/exchange.py:_place_sl_tp()`
2. **Client-side safety net:** Every cycle checks price vs entry in `main.py`

### Indicators (`app/swing/indicators.py`)
4h: EMA 9/21/50, RSI14, Stoch RSI, MACD 12/26/9, ATR14 + percentile rank, ADX14 + DI+/DI−, VWAP, OI%, L/S ratio, taker ratio, vol ratio
Daily: EMA 21/50/200

---

## DCA Bot (`app/bot/`)

### Universe
Top 20 by market cap (CoinGecko, refreshed daily). Blacklist: stablecoins, wrapped tokens, WLFI, ZEC.

### Config (`app/config.py`)
| Param | Value |
|-------|-------|
| TRADE_AMOUNT_USDT | $8 per buy |
| MAX_POSITION_USDT | $50 per coin |
| MAX_DAILY_SPEND | $80/day |
| DIP_THRESHOLD | 3% (dynamic: max(ATR14×0.8%, 3%)) |
| TAKE_PROFIT | +5% → partial sell |
| PARTIAL_TAKE_PROFIT_PCT | 60% sold at TP |
| TRAILING_STOP_PCT | 10% from peak |
| DCA_DROP_PCT | 3% below avg_buy → rebuy |
| BUY_COOLDOWN_HRS | 4h |
| CHECK_INTERVAL | 300s (5 min) |
| RSI_BUY_THRESHOLD | 45 (above EMA50) |
| RSI_BUY_BELOW_EMA50 | 38 (in pullback zone) |
| VOLUME_SPIKE_RATIO | 2.0 |

### Buy Logic (all conditions required)
1. Dip ≥ max(ATR14×0.8%, 3%) from 24h high OR Bollinger %B < 0.2
2. Price > EMA200, EMA200 slope rising, price > weekly EMA200
3. BTC above 200-day AND 200-week EMA (macro gate)
4. RSI < 45 (or < 38 in pullback zone)
5. MACD histogram improving
6. Volume ratio < 2.0
7. Cooldown ok + position cap ok + daily cap ok

### Exit: Partial TP at +5% (sell 60%), trailing stop at −10% from peak

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

## FastAPI Endpoints (port 8000)
`GET /health` `/portfolio` `/pnl` `/trades` `/stats` `/docs`

## Telegram
- DCA bot: `/status` `/pnl` `/trades` `/balance` `/help` commands + buy/sell/daily summary alerts
- Swing: open/close alerts with confidence + reasoning
- **IMPORTANT:** Always `html.escape()` agent reasoning before sending (parse_mode=HTML)

---

## Known Issues & Fixes

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
- Run: `python -m pytest` (fast; testnet tests auto-skip). Config in `pyproject.toml`. Full guide: `docs/testing.md`.
- Layout: `tests/{swing,bot,backtest,property,integration}/` + `tests/conftest.py`. Dev deps `pytest`+`hypothesis` in `requirements.txt`.
- Fixtures (conftest): `snapshot` (swing-snapshot factory), `fake_client` (FakeBinanceClient recording order calls), env stub set at import time. **Don't re-add env/`sys.path` boilerplate in test files.**
- Markers: `property`, `integration`, `testnet` (skipped unless `RUN_TESTNET=1`), `slow`.
- Philosophy: money-paths first; Hypothesis invariants; indicator golden tests vs analytically-known values; `tests/backtest/test_live_backtest_parity.py` fails if live `agent.decide()` and backtest `decide_v2()` diverge.
- **Scope C (not yet done):** DCA buy/sell gates are inline in `trader.run()` (untested); live & backtest duplicate strategy logic (`agent.py` vs `backtest_replay/strategy.py`) — the parity test guards it.
