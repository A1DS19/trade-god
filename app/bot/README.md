# DCA Bot

Spot trading bot that buys dips on the top 20 coins by market cap and exits via partial take profit and trailing stop. Runs on Binance spot with a 5-minute scan cycle.

---

## How it works

Every 5 minutes the bot:
1. Refreshes the top 20 coins by market cap (CoinGecko, CoinPaprika fallback)
2. Checks each coin for a buy signal
3. Manages open positions (partial TP, trailing stop, DCA)

### Buy signal

All conditions must be true:

| Condition | Detail |
|---|---|
| **Dip signal** (either) | Price dipped ≥ ATR-adjusted threshold from 24h high, OR Bollinger %B < 0.2 (price near lower band) |
| **Trend** | Price above 200-day EMA AND 200-day EMA is rising |
| **RSI** | RSI(14) < 45 if price above EMA50; RSI(14) < 38 if in EMA50–EMA200 pullback zone |
| **MACD** | Daily MACD histogram improving (hist > prev bar) — selling pressure easing |
| **BTC macro** | BTC price above 200-day EMA (rising) AND above 200-week EMA |
| **Volume** | No volume spike (vol ratio < 2×) — avoids panic dumps and news events |
| **Cooldown** | No buy in the last 4h for this coin |
| **Limits** | Daily spend and per-coin position cap not exceeded |

**Dip threshold is dynamic:** `max(ATR14 × 0.8%, DIP_THRESHOLD)` — adapts to each coin's current volatility instead of a fixed 3% for everything.

### Exit logic

| Trigger | Action |
|---|---|
| Price up 5% from avg buy | Sell 60%, let 40% ride to trailing stop |
| Price drops 10% from position peak | Full trailing stop exit |
| Price drops 3% below avg buy price | DCA — buy another $8 |

### DCA (Dollar-Cost Averaging)

After the first buy, if price falls 3%+ below the avg buy price the bot buys again, lowering the cost basis. The same cooldown and position cap apply.

---

## Configuration

All settings in `app/config.py`:

| Setting | Default | Description |
|---|---|---|
| `TOP_N_COINS` | 20 | Coins to watch (by market cap) |
| `TRADE_AMOUNT_USDT` | $8 | Spent per buy |
| `MAX_POSITION_USDT` | $50 | Max cost basis per coin |
| `MAX_DAILY_SPEND` | $80 | Max spend per UTC day |
| `DIP_THRESHOLD` | 3% | Dip from 24h high to trigger buy |
| `RSI_BUY_THRESHOLD` | 45 | RSI limit when price is above EMA50 |
| `RSI_BUY_BELOW_EMA50` | 38 | Stricter RSI limit in EMA50–EMA200 pullback zone |
| `BB_OVERSOLD_PCT_B` | 0.2 | Bollinger %B threshold for lower-band dip signal |
| `VOLUME_SPIKE_RATIO` | 2.0 | Skip buy if vol ratio exceeds this |
| `TAKE_PROFIT` | 5% | Partial sell trigger |
| `PARTIAL_TAKE_PROFIT_PCT` | 60% | Fraction sold at take profit |
| `TRAILING_STOP_PCT` | 10% | Exit if price drops this far from peak |
| `DCA_DROP_PCT` | 3% | DCA trigger below avg buy price |
| `BUY_COOLDOWN_HRS` | 4h | Min time between buys per coin |
| `CHECK_INTERVAL` | 300s | Seconds between market scans |
| `WATCHDOG_TIMEOUT_MINS` | 15 | Telegram alert if no cycle in this long |
| `INDICATOR_TTL_SECS` | — | Indicator cache TTL (avoids redundant API calls) |

Per-coin overrides are supported via `COIN_OVERRIDES` in `app/config.py`.

---

## Environment variables

```env
BINANCE_API_KEY=your_spot_key
BINANCE_SECRET_KEY=your_spot_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://tradegod:tradegod@db:5432/tradegod
```

---

## Files

| File | Description |
|---|---|
| `trader.py` | Main loop — buy/sell logic, DCA, trailing stop, watchdog |
| `exchange.py` | Binance spot wrappers with retry logic |
| `indicators.py` | EMA50/200 (daily + weekly slope), RSI, MACD, Bollinger Bands, ATR, volume ratio with cache |
| `universe.py` | Top coin list (CoinGecko + CoinPaprika fallback) |
| `commands.py` | Telegram command handler (`/status`, `/pnl`, `/trades`, `/balance`) |
| `notifier.py` | Telegram alerts and daily 8am UTC summary |
| `heartbeat.py` | Shared cycle timestamp for watchdog + health check |
| `healthcheck.py` | HTTP health check server on port 8080 |

---

## Telegram commands

| Command | Description |
|---|---|
| `/status` | Open positions |
| `/pnl` | Realized P&L + win rate |
| `/trades [n]` | Last N trades (default 5) |
| `/balance` | Free USDT + portfolio cost |
| `/help` | Command list |

---

## Manually seeding a position

If you bought a coin outside the bot:

```sql
INSERT INTO positions (coin, avg_buy, qty, last_buy, partial_taken)
VALUES ('BTC', 82000.00, 0.0001, '2026-03-15T19:25:11+00:00', false)
ON CONFLICT (coin) DO UPDATE
  SET avg_buy = EXCLUDED.avg_buy, qty = EXCLUDED.qty, last_buy = EXCLUDED.last_buy;
```
