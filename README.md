# trade-god — DCA Crypto Bot

## What it does

- Watches the top 20 coins by market cap (refreshed daily from CoinGecko)
- Buys $8 worth when a coin dips 3%+ from its 24h high, RSI < 45, above 200 EMA, and BTC is in an uptrend
- Sells at +5% take profit or -15% stop loss
- Sends Telegram notifications for every trade + daily summary at 8am UTC
- Health check endpoint at `GET /health` (port 8080)
- Watchdog alert via Telegram if no cycle completes in 15 minutes

---

## Stack

- **Python 3.12** — trading loop
- **PostgreSQL** (Railway) — persists positions, daily spend, coin list
- **Docker** — containerised, runs on any VPS
- **Binance API** — market data + order execution
- **CoinGecko / CoinPaprika** — coin universe (CoinPaprika fallback)
- **Telegram Bot API** — trade alerts and daily summary

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

## Step 3 — Database (Railway)

1. [railway.app](https://railway.app) → New Project → Provision PostgreSQL
2. Connect tab → copy the `DATABASE_URL`
3. Paste into `.env`

---

## Step 4 — Environment variables

Create a `.env` file in the project root:

```env
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://...
```

---

## Step 5 — Deploy on AWS EC2 (recommended)

**Instance:** t3.micro (1GB RAM), Ubuntu 24.04, `ap-southeast-1` (Singapore)

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

**Health check:**
```bash
curl http://localhost:8080/health
```

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
| `TAKE_PROFIT` | 5% | Sell when position is up this much |
| `STOP_LOSS` | 15% | Sell to protect capital |
| `BUY_COOLDOWN_HRS` | 4h | Min time between buys per coin |
| `CHECK_INTERVAL` | 300s | Seconds between market scans |
| `WATCHDOG_TIMEOUT_MINS` | 15 | Telegram alert if no cycle in this many minutes |

---

## Project structure

```
app/
  bot/
    trader.py       — main loop, buy/sell logic
    exchange.py     — Binance API wrappers with retry logic
    indicators.py   — EMA, RSI, volume ratio
    universe.py     — top coin list (CoinGecko + CoinPaprika fallback)
    notifier.py     — Telegram alerts and daily summary
    heartbeat.py    — shared cycle heartbeat for watchdog + health check
    healthcheck.py  — HTTP health check server (port 8080)
  db/
    models.py       — SQLAlchemy models + state persistence
  config.py         — all env vars and strategy constants
```

---

## Manually seeding a position

If you bought a coin outside the bot, insert it directly into the DB:

```sql
INSERT INTO positions (coin, avg_buy, qty, last_buy)
VALUES ('TAO', 284.60, 0.0281, '2026-03-15T19:25:11+00:00')
ON CONFLICT (coin) DO UPDATE
  SET avg_buy = EXCLUDED.avg_buy, qty = EXCLUDED.qty, last_buy = EXCLUDED.last_buy;
```

---

## ⚠️ Risk Warning

This bot trades real money. Past performance doesn't guarantee future results.
Start with small amounts and monitor the first few days closely.
Never invest more than you can afford to lose.
