# Swing Agent

Rule-based swing trading bot for USDT-M perpetual futures on Binance. Evaluates market conditions every hour and takes long or short positions based on a multi-indicator quant framework. No LLM — all decisions are deterministic Python.

---

## How it works

Every hour the agent:
1. Fetches 4h and daily candles for each coin
2. Computes EMA stack, RSI, Stochastic RSI, MACD, ATR, ADX, volume ratio, VWAP, open interest change, funding rate, long/short ratio, and taker buy/sell ratio
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

Each confirming or contradicting signal adjusts a raw score. The score maps to a confidence band:

| Raw score | Confidence band |
|---|---|
| ≥ 0.12 | 0.85–0.94 |
| ≥ 0.07 | 0.75–0.84 |
| ≥ 0.03 | 0.70–0.74 |
| < 0.03 | hold |

**Confirming signals** (each adds to score):

| Signal | Weight |
|---|---|
| Volume ratio > 1.5 | +0.05 |
| Funding rate aligns with direction | +0.04 |
| OI rising with price momentum | +0.04 |
| −DI > +DI (short) or +DI > −DI (long) | +0.04 |
| Stochastic RSI > 80 (short) or < 20 (long) | +0.04 |
| L/S ratio ≥ 2.0 crowded longs (short) or ≤ 0.5 crowded shorts (long) | +0.04 |
| RSI in 40–60 range | +0.03 |
| Price vs EMA200 confirms direction | +0.03 |
| ATR percentile rank > 70% (vol expanding) | +0.03 |
| VWAP bias confirms direction | +0.03 |
| Taker buy/sell ratio aligns (< 0.8 for short, > 1.2 for long) | +0.03 |

**Contradicting signals** reduce score by 0.02–0.05 each. ADX borderline regime applies a −0.08 penalty.

Trades with final confidence < 0.70 are skipped.

### 5. SL/TP

ATR-based, volatility-adjusted:

| | Formula | Minimum |
|---|---|---|
| Stop loss | 1.5 × ATR14 | 1% |
| Take profit | 3.0 × ATR14 | 2% |
| R:R ratio | TP ≥ 2 × SL | — |

Exchange-side SL/TP orders (`STOP_MARKET` / `TAKE_PROFIT_MARKET`) are attempted at entry. A client-side safety net in `main.py` also checks price vs entry at the start of every cycle using `DEFAULT_SL_PCT` / `DEFAULT_TP_PCT` from config.

---

## Coins

BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI (9 coins, configurable in `config.py`).

---

## Configuration

All settings in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `COINS` | 9 pairs | Futures pairs to watch |
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
| `indicators.py` | EMA, RSI, Stochastic RSI, MACD, ATR, ATR percentile, ADX, VWAP, volume ratio, OI change, L/S ratio, taker ratio |
| `exchange.py` | Binance Futures wrappers (open/close, SL/TP, positions) |
| `notifier.py` | Telegram alerts (open, close) |
| `config.py` | Strategy constants and env vars |

---

## Telegram notifications

| Event | Message |
|---|---|
| Position opened | Coin, direction, entry price, SL%, TP%, confidence, reasoning |
| Position closed | Coin, entry/exit price, realized PnL, exit reason |
| Startup | Active coins, leverage, size, confidence threshold |
