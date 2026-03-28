# Swing Agent

Rule-based swing trading bot for USDT-M perpetual futures on Binance. Evaluates market conditions every hour and takes long or short positions based on a 5-indicator quant framework. No LLM — all decisions are deterministic Python.

---

## How it works

Every hour the agent:
1. Fetches 4h and daily candles for each coin
2. Computes EMA stack, RSI, MACD, ATR, ADX, volume ratio, open interest change, and funding rate
3. Runs the rule engine to decide: enter / hold / exit
4. Executes on Binance Futures with ATR-based SL/TP

---

## Decision framework

### 1. Exit check (open positions evaluated first)

| Condition | Triggers close |
|---|---|
| 4h EMA flipped bullish or mixed | Short exits |
| Daily EMA flipped bullish | Short exits |
| RSI < 38 | Short exits (approaching oversold) |
| MACD hist rising AND RSI < 45 | Short exits (bearish momentum exhaustion) |
| OI change < −3% AND MACD rising | Short exits (shorts covering) |
| ADX < 20 | Any position exits (trend collapsed) |
| Symmetric inverses of the above | Long exits |

### 2. Regime gate

ADX < 20 → no new entries (ranging/choppy market). ADX 20–25 → borderline (confidence penalty applied).

### 3. Entry conditions (all 5 required)

| # | Short | Long |
|---|---|---|
| 1 | `market_regime == "trending"` (ADX > 25) | same |
| 2 | `daily_ema_alignment == "bearish"` | `"bullish"` |
| 3 | `ema_alignment (4h) == "bearish"` | `"bullish"` |
| 4 | `macd_hist < 0` | `macd_hist > 0` |
| 5 | `RSI > 42` | `RSI < 58` |

RSI gate is also enforced in code (`main.py`) regardless of the rule engine output.

### 4. Confidence scoring

Base confidence from number of net confirming signals:

| Net confirming | Confidence band |
|---|---|
| 3+ | 0.85–0.94 |
| 2 | 0.75–0.84 |
| 1 | 0.70–0.74 |
| < 1 | hold |

**Confirming signals** (+0.03–0.05 each): `vol_ratio > 1.5`, funding rate aligns, OI rising with price, RSI in 40–60, `price_vs_ema200` confirms, `minus_di > plus_di` (short) or reverse.

**Contradicting signals** (−0.04–0.06 each): RSI approaching exit zone, funding opposes, OI falling, MACD hist moving against position.

Trades with confidence < 0.70 are skipped.

### 5. SL/TP

ATR-based, volatility-adjusted:

| | Formula | Minimum |
|---|---|---|
| Stop loss | 1.5 × ATR14 | 1% |
| Take profit | 3.0 × ATR14 | 2% |
| R:R ratio | TP ≥ 2 × SL | — |

Exchange-side SL/TP orders (`STOP_MARKET` / `TAKE_PROFIT_MARKET`) are attempted at entry. A client-side safety net in `main.py` also checks price vs entry at the start of every cycle using `DEFAULT_SL_PCT` / `DEFAULT_TP_PCT` from config.

---

## Configuration

All settings in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `COINS` | ETH, SOL, BNB, XRP | Futures pairs to watch |
| `LEVERAGE` | 5x | Futures leverage |
| `POSITION_USDT` | $5 | Margin per trade (notional = $25) |
| `MAX_OPEN` | 3 | Max simultaneous open positions |
| `DEFAULT_SL_PCT` | 3% | Client-side stop loss fallback |
| `DEFAULT_TP_PCT` | 8% | Client-side take profit fallback |
| `MIN_CONFIDENCE` | 0.70 | Minimum confidence to enter |
| `MIN_RSI_SHORT` | 42.0 | RSI floor for short entries |
| `MAX_RSI_LONG` | 58.0 | RSI ceiling for long entries |
| `CHECK_INTERVAL` | 3600s | Seconds between scans |
| `LOSS_COOLDOWN_HRS` | 4h | Hours to skip a coin after a losing trade |

---

## Environment variables

```env
BINANCE_API_KEY_FUTURES=your_futures_key
BINANCE_SECRET_KEY_FUTURES=your_futures_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://tradegod:tradegod@db:5432/tradegod
```

Binance futures keys require **Futures Trading** enabled. Keep withdrawals disabled.

---

## Files

| File | Description |
|---|---|
| `main.py` | Main loop — scan coins, execute decisions, client-side SL/TP safety net |
| `agent.py` | Deterministic rule engine — exit check, entry check, confidence scoring |
| `snapshot.py` | Assembles market snapshot (indicators + ATR-based SL/TP hints) |
| `indicators.py` | EMA, RSI, MACD, ATR, ADX (+DI/-DI), volume ratio, OI change |
| `exchange.py` | Binance Futures wrappers (open/close, SL/TP, positions) |
| `notifier.py` | Telegram alerts (open, close) |
| `config.py` | Strategy constants and env vars |

---

## Telegram notifications

| Event | Message |
|---|---|
| Position opened | Coin, direction, entry price, SL%, TP%, confidence, reasoning |
| Position closed | Coin, entry price, realized PnL, exit reason |
| Startup | Active coins, leverage, size, confidence threshold |
