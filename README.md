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
- Buys when a coin dips 3%+ from its 24h high, RSI < 45, above 200 EMA, and BTC is in an uptrend
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

- Trades USDT-M perpetual futures (long and short)
- Rule-based decision engine evaluates market regime, EMA stack, MACD, RSI, ADX, volume, funding rate, and open interest every hour
- Regime filter: ADX > 25 required — no trades in ranging/choppy markets
- Entry requires all 5 conditions: daily EMA bias + 4h EMA alignment + MACD direction + ADX + RSI gate (> 42 for shorts, < 58 for longs)
- Confidence scored from supporting/contradicting signals; minimum 0.70 to enter
- Exit on MACD divergence, RSI threshold breach, EMA flip, ADX collapse, or OI drop
- ATR-based SL/TP sizing (1.5× and 3× ATR14); client-side safety net enforced each cycle
- Telegram notifications for every open and close

---

## Stack

- **Python 3.12** — trading loop + API
- **FastAPI + Uvicorn** — REST API (port 8000)
- **PostgreSQL** — persists positions, trades, daily spend, coin list
- **Alembic** — database migrations (run automatically on API startup)
- **Docker Compose** — three services: `bot`, `swing`, and `api`
- **Binance API** — market data + order execution
- **CoinGecko / CoinPaprika** — coin universe (CoinPaprika fallback)
- **Telegram Bot API** — trade alerts, daily summary, commands

No external AI APIs — the swing agent uses a deterministic rule-based engine.

---

## Step 1 — Binance API Keys

1. Binance → Profile → API Management → Create API key
2. Enable: **Spot & Margin Trading**
3. Disable: Withdrawals
4. Copy the key and secret into `.env`

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

All strategy settings live in `app/config.py`:

| Setting | Default | What it does |
|---|---|---|
| `TOP_N_COINS` | 20 | Coins to watch (by market cap) |
| `TRADE_AMOUNT_USDT` | $8 | Spent per buy |
| `MAX_POSITION_USDT` | $50 | Max cost basis per coin |
| `MAX_DAILY_SPEND` | $80 | Max spend per UTC day |
| `DIP_THRESHOLD` | 3% | Dip from 24h high that triggers a buy |
| `RSI_BUY_THRESHOLD` | 45 | Only buy when RSI(14) is below this |
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
    indicators.py   — EMA, RSI, volume ratio
    universe.py     — top coin list (CoinGecko + CoinPaprika fallback)
    notifier.py     — Telegram alerts and daily summary
    heartbeat.py    — shared cycle heartbeat for watchdog + health check
    healthcheck.py  — HTTP health check server (port 8080)
  swing/            — Rule-based swing agent on futures (see app/swing/README.md)
    main.py         — main loop, trade execution, client-side SL/TP safety net
    agent.py        — deterministic rule engine (regime, entry, exit, confidence scoring)
    snapshot.py     — market snapshot assembly with ATR-based SL/TP hints
    indicators.py   — EMA, RSI, MACD, ATR, ADX, OI change (4h + daily)
    exchange.py     — Binance Futures wrappers (open/close, SL/TP)
    notifier.py     — Telegram alerts (open, close)
    config.py       — swing-specific strategy constants and env vars
  db/
    models.py       — SQLAlchemy models, state persistence, log_trade()
  config.py         — shared env vars and DCA strategy constants
alembic/            — database migrations
main.py             — DCA bot entrypoint
swing_main.py       — swing agent entrypoint
api_main.py         — API entrypoint (runs migrations then starts uvicorn)
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
