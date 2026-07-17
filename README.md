# trade-god

![CI](https://github.com/A1DS19/trade-god/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Binance](https://img.shields.io/badge/Binance-USDT--M%20market%20data-F0B90B?logo=binance&logoColor=black)
![Deploy](https://img.shields.io/badge/Deployed-AWS%20Lightsail-FF9900?logo=amazonaws&logoColor=white)

A research-first intraday trading system on Binance USDT-M futures — currently running
**paper-only**, by design.

The live component is a mean-reversion paper engine (`app/intraday/`) whose strategy
survived a pre-registered research pipeline but **failed its out-of-sample cost gates** —
so instead of trading it, the engine shadow-trades it with full fill telemetry to answer
the one question no backtest can: *do maker limits actually fill the way the backtest
assumed?* Live execution is gated behind four weeks of positive paper PnL and a manual
operator decision.

## The intraday engine

- **Strategy:** `mr_vwap` — long-only mean reversion on deep oversold vs 24h VWAP
  (z < −3.0 on 15m bars). Parameters are frozen from pre-registered research
  (H=32 bars, K=10 slots) — no live tuning.
- **Execution:** virtual maker limits on $100 paper equity. A limit only "fills" on
  strict trade-through (bar low below the limit) — every placement is logged as
  `trade_through` / `touch_only` / `miss` fill telemetry.
- **Keyless:** unsigned market-data endpoints only. No Binance API keys on the box.
- **Cycle:** every 15 minutes, aligned to candle close. Universe: weekly top-30 USDT
  perps by 30-day median quote volume.
- **Risk:** kill-switches halt trading at 5% daily paper loss or 20% drawdown; halts
  persist across restarts and require an explicit operator resume.
- **Telegram:** per-fill and per-exit alerts, daily equity summary, weekly fill-telemetry
  report.

Full docs: [operations guide](docs/intraday_operations.md) ·
[design spec](docs/superpowers/specs/2026-07-15-intraday-engine-design.md)

## Research warehouse (dev machine only)

`research/` maintains a point-in-time parquet warehouse (klines, funding, basis, OI,
long/short, universe snapshots for the top-100 USDT perps) used for signal research and
backtests. It never ships to prod. The strategy code is shared: research imports
`app/intraday/strategy.py`, and a replay-parity test pins the live engine to the batch
backtester bar-for-bar.

## Stack

- **Python 3.12** — engine loop + API
- **FastAPI + Uvicorn** — REST API (port 8000, legacy trade history)
- **PostgreSQL 16** — paper trades, fill telemetry, engine state (+ legacy history)
- **Alembic** — migrations (run automatically via the `migrate` service)
- **Docker Compose** — four services: `db`, `migrate`, `intraday`, `api`
- **Telegram Bot API** — alerts and summaries

No API keys, no external AI — fully self-contained.

---

## Step 1 — Telegram Bot

1. Open Telegram → **@BotFather** → `/newbot` → copy the token
2. Start a chat with your new bot
3. Get your Chat ID:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Send a message to the bot first, then copy the `"id"` from `"chat"` in the response
4. Paste both into `.env`

## Step 2 — Environment variables

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://tradegod:tradegod@db:5432/tradegod
```

No Binance keys are required — the paper engine only reads public market data.

## Step 3 — Deploy on AWS Lightsail (recommended)

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
docker compose logs -f intraday
```

On startup, Docker Compose will:
1. Start PostgreSQL and wait for it to be healthy
2. Run `alembic upgrade head` (the `migrate` service)
3. Start `intraday` and `api` only after migrations succeed

**Firewall (Lightsail → Networking tab):**

| Port | Restrict to |
|---|---|
| 22 | Your IP only |
| 8000 | Your IP only |

Postgres (5432) is bound to loopback in `docker-compose.yml` — access it via an SSH
tunnel, never a firewall rule.

Monitoring, kill-switch resume, and telemetry SQL:
[docs/intraday_operations.md](docs/intraday_operations.md).

---

## API

The API runs on port 8000 (interactive docs at `http://<your-ip>:8000/docs`) and serves
**historical data from the retired strategies** (`positions`/`trades`); intraday paper
telemetry is read via SQL for now.

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /portfolio` | Open positions with cost basis (legacy DCA) |
| `GET /pnl` | Realized P&L today and all-time (legacy DCA) |
| `GET /trades?limit=20&coin=BTC&side=SELL` | Trade history (legacy DCA) |
| `GET /stats` | Win rate, avg P&L, best/worst trade (legacy DCA) |

---

## Testing

```bash
python -m pytest              # full suite (fast, fully green)
```

Money-paths first: strategy core parity with research, PaperBook goldens, the
live↔backtest replay-parity test, engine cycle/halt semantics, kill-switch edges.
Full guide: [docs/testing.md](docs/testing.md).

---

## Project structure

```
app/
  intraday/          — the paper engine
    main.py          — entrypoint: state restore, resume flag, 15m-aligned loop
    engine.py        — the cycle: data → z → paper book → risk → persist → Telegram
    strategy.py      — frozen mr_vwap core (shared with research backtests)
    paper.py         — PaperBook: virtual limits, fills, horizon exits, funding
    risk.py          — kill-switches + consecutive-error tracker
    data.py          — closed-bar kline/funding fetchers
    universe.py      — weekly top-30 resolve
    notifier.py      — Telegram messages
    config.py        — frozen params + env flags
  api/main.py        — FastAPI routes (legacy history)
  db/models.py       — SQLAlchemy models + intraday persistence helpers
  config.py          — shared env vars
research/            — parquet warehouse + backtest harness (dev only, see CLAUDE.md)
legacy/              — retired DCA bot + swing agent (code, tests, docs)
alembic/             — migrations (001–006)
intraday_main.py     — engine entrypoint
api_main.py          — API entrypoint
tests/               — pytest suite (see docs/testing.md)
```

---

## History

Two earlier strategies (a DCA spot bot and a rule-based swing futures agent) ran live
from 2026-03 to 2026-07. After an honest walk-forward evaluation showed no durable edge,
both were retired on 2026-07-16 — code and docs preserved under [`legacy/`](legacy/),
research trail under [`docs/superpowers/`](docs/superpowers/). Their trade history
remains in the database and API.

---

## ⚠️ Risk Warning

The engine currently places **no real orders** — it is a paper-trading telemetry system.
If a future phase enables live execution, the same rules apply as ever: past performance
doesn't guarantee future results; never risk more than you can afford to lose.
