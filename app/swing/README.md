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

ADX < 20 → no new entries (ranging/choppy market).  
Minimum entry ADX is 22. ADX 22–25 is treated as borderline and penalized in confidence.

### 3. Entry conditions

| # | Short | Long |
|---|---|---|
| 1 | `ADX >= 25` | same |
| 2 | `daily_ema_alignment == "bearish"` | `"bullish"` |
| 3 | 4h strict bearish OR partial bearish stack | 4h strict bullish OR partial bullish stack |
| 4 | `macd_hist < 0` | `macd_hist > 0` |
| 5 | RSI affects confidence (soft penalties), not hard-block | same |

Partial 4h alignment entries are allowed but get a confidence penalty.

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

**Contradicting signals** reduce score by 0.02–0.05 each.  
ADX borderline regime applies a −0.08 penalty. Partial 4h alignment applies a −0.04 penalty.

Trades with final confidence < 0.80 are skipped.

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
| `POSITION_USDT_MIN` | $5 | Min trade size |
| `POSITION_USDT_MAX` | $10 | Max trade size for high-confidence trades |
| `MAX_OPEN` | 3 | Max simultaneous open positions |
| `DEFAULT_SL_PCT` | 3% | Client-side stop loss fallback |
| `DEFAULT_TP_PCT` | 8% | Client-side take profit fallback |
| `MIN_CONFIDENCE` | 0.80 | Minimum confidence to enter |
| `MIN_ADX_ENTRY` | 25.0 | Minimum ADX for entries |
| `PARTIAL_MIN_ADX` | 25.0 | Minimum ADX for partial (mixed 4h) entries |
| `PARTIAL_MIN_CONFIDENCE` | 0.80 | Higher confidence floor for partial entries |
| `ENABLE_PARTIAL_ENTRIES` | `False` | Disable mixed/partial entries (quality-first) |
| `REQUIRE_DI_ALIGNMENT` | `True` | Require `-DI > +DI` for shorts and `+DI > -DI` for longs |
| `MIN_RSI_SHORT` | 42.0 | RSI comfort zone reference for shorts (soft penalty below) |
| `MAX_RSI_LONG` | 58.0 | RSI comfort zone reference for longs (soft penalty above) |
| `EST_FEE_BPS` | 4.0 | Estimated fee per side used by expected-move filter |
| `EST_SLIPPAGE_BPS` | 2.0 | Estimated slippage per side used by expected-move filter |
| `MIN_TP_TO_COST_MULT` | 3.0 | Minimum TP multiple over estimated round-trip costs |
| `MIN_NET_TP_PCT` | 0.40% | Minimum net TP after estimated costs |
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

---

## Replay backtest (v1 vs v2)

Compare legacy strict rules (`v1`) against current tuned rules (`v2`) on the same historical candles:

```bash
python -m app.swing.backtest_replay \
  --coins BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI \
  --start 2025-01-01T00:00:00Z \
  --end 2026-01-01T00:00:00Z \
  --fee-bps 4 \
  --slippage-bps 2
```

Notes:

- Uses public kline data and replays OHLC candle closes/intrabar SL-TP touches.
- Funding/OI/L-S/taker features are neutralized to baseline values in replay.
- Fees/slippage are configurable (`--fee-bps`, `--slippage-bps`) and applied per side.
- Still no latency model; use it for **relative v1 vs v2 comparison**, not exact live expectancy.

### Latest benchmark snapshot

Run date: `2026-04-06` (UTC)  
Window: `2025-01-01` to `2026-01-01`  
Universe: `BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`

Aggregate:

| Strategy | Trades | Win rate | Net PnL | Avg PnL/trade | Profit factor | Max DD | Avg entry conf |
|---|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 57.89% | 3.36 | 0.09 | 1.32 | 4.65 | 0.76 |
| `v2` (current tuned) | 41 | 51.22% | 4.92 | 0.12 | 1.34 | 6.82 | 0.84 |

Observed from this replay:

- `v2` now trades at similar cadence to `v1` (`41` vs `38`) with stricter quality gates.
- Before costs, `v2` outperformed `v1` in this window (`4.92` vs `3.36`), at the expense of higher drawdown.

### Cost-aware benchmark snapshot (4 bps fee + 2 bps slippage per side)

Run date: `2026-04-06` (UTC)  
Window: `2025-01-01` to `2026-01-01`  
Universe: `BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`

Aggregate:

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max DD | Avg entry conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 55.26% | 2.29 | 3.04 | 0.76 | 0.06 | 1.21 | 4.54 | 0.76 |
| `v2` (current tuned) | 41 | 48.78% | 3.43 | 4.47 | 1.04 | 0.08 | 1.22 | 6.89 | 0.84 |

Observed from this replay:

- After costs, `v2` stays positive and outperforms `v1` on net PnL in this window.
- `v2` still carries higher drawdown than `v1`.

### 5-year cost-aware benchmark snapshot (4 bps fee + 2 bps slippage per side)

Run date: `2026-04-06` (UTC)  
Window: `2021-01-01` to `2026-01-01`  
Universe: `BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`

Command:

```bash
python -m app.swing.backtest_replay \
  --coins BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI \
  --start 2021-01-01T00:00:00Z \
  --end 2026-01-01T00:00:00Z \
  --fee-bps 4 \
  --slippage-bps 2
```

Aggregate:

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max DD | Avg entry conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 217 | 47.00% | -20.20 | -15.86 | 4.34 | -0.09 | 0.71 | 13.09 | 0.76 |
| `v2` (current tuned) | 182 | 44.51% | -16.93 | -12.30 | 4.63 | -0.09 | 0.78 | 21.69 | 0.84 |

Target status (`60–70% win rate` and `positive PnL`):

- Not met yet on 5-year data.
- `v2` is less negative than `v1`, but still below target and with higher drawdown.
