# Swing Agent

LLM-driven swing trading bot for USDT-M perpetual futures on Binance. Evaluates market conditions every hour and takes long or short positions based on EMA alignment, RSI, volume, and funding rate.

---

## How it works

Every hour the agent:
1. Builds a market snapshot for each coin (EMAs, RSI, volume, funding rate, last 5 candles)
2. Sends the snapshot to an LLM (Llama 3.3 70B via NVIDIA API) for a trading decision
3. Executes the decision on Binance Futures with bracket SL/TP orders

### Entry logic

The LLM must see at least 2 aligned signals to enter:

| Primary (required) | Supporting (need 1+) |
|---|---|
| `ema_alignment` bullish (price > EMA9 > EMA21 > EMA50) | RSI < 30 (oversold) |
| `ema_alignment` bearish (price < EMA9 < EMA21 < EMA50) | Funding rate extreme (> 0.05% or < -0.05%) |
| | Volume ratio > 1.5 |

- Bearish EMA stack → agent looks for shorts, not longs
- Bullish EMA stack → agent looks for longs, not shorts
- Funding rate alone is a weak signal and cannot override EMA direction
- `price_vs_ema200` (daily) is used as session bias

### Confidence gate

The LLM scores its own confidence (0.0–1.0). Trades are skipped if confidence < 0.70.

| Range | Meaning |
|---|---|
| 0.90–1.00 | EMA + RSI extreme + volume + funding all aligned |
| 0.80–0.89 | EMA + 2 other signals, no contradictions |
| 0.70–0.79 | EMA + 1 other signal |
| < 0.70 | Hold — not enough conviction |

### Exit logic

While a position is open, the agent re-evaluates every hour:

| Condition | Action |
|---|---|
| Position contradicts EMA alignment | `close` |
| Strong trend reversal (confidence ≥ 0.85) | flip direction |
| Signals support continuation | `hold` |
| SL/TP hit on exchange | auto-closed by Binance |

---

## Configuration

All settings in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `COINS` | ETH, SOL, BNB, XRP | Futures pairs to watch |
| `LEVERAGE` | 5x | Futures leverage |
| `POSITION_USDT` | $5 | Margin per trade (notional = $25) |
| `MAX_OPEN` | 3 | Max simultaneous positions |
| `DEFAULT_SL_PCT` | 3% | Stop loss from entry |
| `DEFAULT_TP_PCT` | 8% | Take profit from entry |
| `MIN_CONFIDENCE` | 0.70 | Minimum LLM confidence to trade |
| `CHECK_INTERVAL` | 3600s | Seconds between scans |

---

## Environment variables

```env
BINANCE_API_KEY_FUTURES=your_futures_key
BINANCE_SECRET_KEY_FUTURES=your_futures_secret
NVIDIA_API_KEY=your_nvidia_api_key
```

Binance futures keys require **Futures Trading** enabled. Keep withdrawals disabled.

---

## Files

| File | Description |
|---|---|
| `main.py` | Main loop — scan coins, execute decisions |
| `agent.py` | LLM decision engine (system prompt + Nemotron API call) |
| `snapshot.py` | Assembles market snapshot dict for the agent |
| `indicators.py` | EMA, RSI, volume ratio calculations |
| `exchange.py` | Binance Futures wrappers (open/close, SL/TP, positions) |
| `notifier.py` | Telegram alerts (open, close, skip) |
| `config.py` | Strategy constants and env vars |

---

## Telegram notifications

| Event | Message |
|---|---|
| Position opened | Coin, direction, entry price, SL%, TP%, confidence, reasoning |
| Position closed | Coin, entry price, realized PnL |
| Startup | Active coins, leverage, size, confidence threshold |
