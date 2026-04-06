# trade-god

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Binance](https://img.shields.io/badge/Binance-Futures%20%26%20Spot-F0B90B?logo=binance&logoColor=black)
![Deploy](https://img.shields.io/badge/Deployed-AWS%20Lightsail-FF9900?logo=amazonaws&logoColor=white)

Two independent trading strategies running in parallel on Binance.

| Strategy | Market | Style | Docs |
|---|---|---|---|
| **DCA Bot** | Spot | Buy dips, partial TP, trailing stop | [app/bot/README.md](app/bot/README.md) |
| **Swing Agent** | USDT-M Futures | Rule-based longs & shorts, hourly re-evaluation | [app/swing/README.md](app/swing/README.md) |

---

## DCA Bot

- Watches the top 20 coins by market cap (refreshed daily from CoinGecko)
- Buys when price dips ≥ ATR-adjusted threshold from 24h high, or Bollinger %B < 0.2
- Requires: RSI < 45 (or < 38 in EMA50–200 pullback zone), price above 200 EMA, EMA slope up, MACD histogram improving, no volume spike, BTC above 200-day and 200-week EMA
- Partial exit at +5% take profit (sells 60%, lets 40% ride to trailing stop)
- Trailing stop at -10% from position peak
- DCA buys more if price drops 3% below avg buy price
- Logs every trade (buy/sell) with realized P&L to the database
- REST API for portfolio data, trade history, and strategy stats
- Telegram commands: `/status`, `/pnl`, `/trades`, `/balance`
- Telegram notifications for every trade + daily summary at 8am UTC
- Health check endpoint at `GET /health` (port 8080)
- Watchdog alert via Telegram if no cycle completes in 15 minutes

## Swing Agent

- Trades 9 USDT-M perpetual futures pairs (BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI)
- Rule-based decision engine — no LLM, fully deterministic
- Indicators: EMA stack (9/21/50 on 4h, 21/50/200 daily), RSI, Stochastic RSI, MACD, ATR, ATR percentile, ADX (+DI/−DI), VWAP, volume ratio, funding rate, open interest change, long/short ratio, taker buy/sell ratio
- Regime filter: no entries in ranging markets (`ADX < 20`), minimum entry ADX `>= 22`
- Entry uses daily bias + 4h strict or partial alignment + MACD direction + ADX gate; RSI now contributes via confidence penalties (not hard block)
- Confidence scored from 11 confirming/contradicting signals; minimum 0.80 to enter
- Exit on MACD divergence, RSI threshold breach, EMA flip, ADX collapse, or OI drop
- ATR-based SL/TP sizing (1.5× and 3× ATR14); client-side safety net enforced each cycle
- Position size scales by confidence (`$5` to `$10`)
- Telegram notifications for every open and close

### Swing replay benchmark (v1 vs v2)

Run date: `2026-04-06` (UTC)  
Window: `2025-01-01` to `2026-01-01`  
Universe: `BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`

| Strategy | Trades | Win rate | Net PnL | Avg PnL/trade | Profit factor | Max DD | Avg entry conf |
|---|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 57.89% | 3.36 | 0.09 | 1.32 | 4.65 | 0.76 |
| `v2` (current tuned) | 41 | 51.22% | 4.92 | 0.12 | 1.34 | 6.82 | 0.84 |

Reproduce:

```bash
python -m app.swing.backtest_replay \
  --coins BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI \
  --start 2025-01-01T00:00:00Z \
  --end 2026-01-01T00:00:00Z \
  --fee-bps 4 \
  --slippage-bps 2
```

Notes: public kline replay, neutralized funding/OI/L-S/taker features, configurable fees/slippage, no latency modeling.

Cost-aware aggregate snapshot (`fee=4 bps`, `slippage=2 bps`, per side):

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 55.26% | 2.29 | 3.04 | 0.76 | 0.06 | 1.21 | 4.54 |
| `v2` (current tuned) | 41 | 48.78% | 3.43 | 4.47 | 1.04 | 0.08 | 1.22 | 6.89 |

5-year cost-aware aggregate snapshot (`2021-01-01` to `2026-01-01`, same fee/slippage):

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 217 | 47.00% | -20.20 | -15.86 | 4.34 | -0.09 | 0.71 | 13.09 |
| `v2` (current tuned) | 182 | 44.51% | -16.93 | -12.30 | 4.63 | -0.09 | 0.78 | 21.69 |

Target status (`60–70% win rate` and `positive PnL`): not met yet on 5-year data.

---

## Stack

- **Python 3.12** — trading loop + API
- **FastAPI + Uvicorn** — REST API (port 8000)
- **PostgreSQL** — persists positions, trades, daily spend, coin list, swing trade history
- **Alembic** — database migrations (run automatically on startup via `migrate` service)
- **Docker Compose** — five services: `db`, `migrate`, `bot`, `swing`, `api`
- **Binance API** — market data + order execution (spot + futures)
- **CoinGecko / CoinPaprika** — coin universe (CoinPaprika fallback)
- **Telegram Bot API** — trade alerts, daily summary, commands

No external AI APIs — fully self-contained.

---

## Step 1 — Binance API Keys

1. Binance → Profile → API Management → Create API key
2. Enable: **Spot & Margin Trading**
3. Disable: Withdrawals
4. Copy the key and secret into `.env`

For the swing agent, create a **second** API key with **Futures Trading** enabled.

---

## Step 2 — Telegram Bot

1. Open Telegram → **@BotFather** → `/newbot` → copy the token
2. Start a chat with your new bot
3. Get your Chat ID:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Send a message to the bot first, then copy the `"id"` from `"chat"` in the response
4. Paste both into `.env`

---

## Step 3 — Environment variables

Create a `.env` file in the project root:

```env
# DCA Bot (spot)
BINANCE_API_KEY=your_spot_key
BINANCE_SECRET_KEY=your_spot_secret

# Swing Agent (futures) — separate API key with Futures Trading enabled
BINANCE_API_KEY_FUTURES=your_futures_key
BINANCE_SECRET_KEY_FUTURES=your_futures_secret

# Shared
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://tradegod:tradegod@db:5432/tradegod
```

---

## Step 4 — Deploy on AWS Lightsail (recommended)

**Instance:** 2GB RAM, Ubuntu 24.04

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu && newgrp docker

# Add swap (safety net)
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Clone and run
git clone https://github.com/your-username/trade-god.git && cd trade-god
# copy your .env file here
docker compose up -d --build
docker compose logs -f bot
```

On startup, Docker Compose will:
1. Start PostgreSQL and wait for it to be healthy
2. Run `alembic upgrade head` (the `migrate` service)
3. Start `bot`, `swing`, and `api` only after migrations succeed

**Firewall (Lightsail → Networking tab):**

| Port | Restrict to |
|---|---|
| 22 | Your IP only |
| 8000 | Your IP only |
| 8080 | Your IP only |
| 5432 | Remove rule (internal only) |

---

## API

The API runs on port 8000. Interactive docs at `http://<your-ip>:8000/docs`.

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /portfolio` | Open positions with cost basis |
| `GET /pnl` | Realized P&L today and all-time |
| `GET /trades?limit=20&coin=BTC&side=SELL` | Trade history |
| `GET /stats` | Win rate, avg P&L, best/worst trade |

---

## Telegram Commands

| Command | Description |
|---|---|
| `/status` | Open positions |
| `/pnl` | Realized P&L + win rate |
| `/trades [n]` | Last N trades (default 5) |
| `/balance` | Free USDT + portfolio cost |
| `/help` | Command list |

---

## Configuration

DCA bot settings in `app/config.py`, swing agent settings in `app/swing/config.py`.

| Setting | Default | What it does |
|---|---|---|
| `TOP_N_COINS` | 20 | Coins to watch (by market cap) |
| `TRADE_AMOUNT_USDT` | $8 | Spent per buy |
| `MAX_POSITION_USDT` | $50 | Max cost basis per coin |
| `MAX_DAILY_SPEND` | $80 | Max spend per UTC day |
| `DIP_THRESHOLD` | 3% | Minimum dip from 24h high to trigger buy |
| `RSI_BUY_THRESHOLD` | 45 | RSI(14) limit when price is above EMA50 |
| `RSI_BUY_BELOW_EMA50` | 38 | Stricter RSI limit in EMA50–EMA200 pullback zone |
| `TAKE_PROFIT` | 5% | Partial sell trigger |
| `PARTIAL_TAKE_PROFIT_PCT` | 60% | Fraction sold at take profit |
| `TRAILING_STOP_PCT` | 10% | Sell if price drops this much from peak |
| `DCA_DROP_PCT` | 3% | Buy more if price drops below avg buy by this much |
| `BUY_COOLDOWN_HRS` | 4h | Min time between buys per coin |
| `CHECK_INTERVAL` | 300s | Seconds between market scans |
| `WATCHDOG_TIMEOUT_MINS` | 15 | Telegram alert if no cycle in this many minutes |

---

## Project structure

```
app/
  api/
    main.py         — FastAPI routes (/portfolio, /pnl, /trades, /stats)
  bot/              — DCA spot bot (see app/bot/README.md)
    trader.py       — main loop, buy/sell logic
    commands.py     — Telegram command handler (polling)
    exchange.py     — Binance spot wrappers with retry logic
    indicators.py   — EMA, RSI, MACD, Bollinger Bands, ATR, volume ratio
    universe.py     — top coin list (CoinGecko + CoinPaprika fallback)
    notifier.py     — Telegram alerts and daily summary
    heartbeat.py    — shared cycle heartbeat for watchdog + health check
    healthcheck.py  — HTTP health check server (port 8080)
  swing/            — Rule-based swing agent on futures (see app/swing/README.md)
    main.py         — main loop, trade execution, client-side SL/TP safety net
    agent.py        — deterministic rule engine (regime, entry, exit, confidence scoring)
    snapshot.py     — market snapshot assembly with ATR-based SL/TP hints
    indicators.py   — EMA, RSI, Stoch RSI, MACD, ATR, ATR percentile, ADX, VWAP, OI, L/S ratio, taker ratio
    exchange.py     — Binance Futures wrappers (open/close, SL/TP)
    notifier.py     — Telegram alerts (open, close)
    config.py       — swing-specific strategy constants and env vars
  db/
    models.py       — SQLAlchemy models, state persistence, log_trade()
  config.py         — shared env vars and DCA strategy constants
alembic/            — database migrations (run automatically on startup)
main.py             — DCA bot entrypoint
swing_main.py       — swing agent entrypoint
api_main.py         — API entrypoint
```

---

## Manually seeding a position

If you bought a coin outside the bot, insert it directly into the DB:

```sql
INSERT INTO positions (coin, avg_buy, qty, last_buy, partial_taken)
VALUES ('BTC', 82000.00, 0.0001, '2026-03-15T19:25:11+00:00', false)
ON CONFLICT (coin) DO UPDATE
  SET avg_buy = EXCLUDED.avg_buy, qty = EXCLUDED.qty, last_buy = EXCLUDED.last_buy;
```

---

## ⚠️ Risk Warning

This bot trades real money. Past performance doesn't guarantee future results.
Start with small amounts and monitor the first few days closely.
Never invest more than you can afford to lose.
