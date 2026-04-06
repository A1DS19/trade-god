# Swing Strategy (Current Implementation)

This document describes the **actual strategy currently running** in the swing agent (`app/swing/*`).

## 1) High-level flow (every cycle)

1. Load open futures positions.
2. For each coin (`BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`):
   - Build snapshot (4h + daily indicators, funding, OI/L-S/taker data).
   - If a position exists: evaluate **exit rules** first.
   - If no position: apply **regime + entry filters**.
   - If entry passes, compute confidence; trade only if `confidence >= 0.80`.
3. Sleep `3600s` (1 hour).

## 2) Market regime filter (ADX)

Regime is based on 4h ADX:

- `ADX > 25` => `trending`
- `20 <= ADX <= 25` => `borderline`
- `ADX < 20` => `ranging`

Entry behavior:

- `ranging`: no entries (`HOLD conf=0.00 - ADX < 20`)
- minimum entry ADX is now `>= 25`
- directional DI alignment is required (`-DI > +DI` for shorts, `+DI > -DI` for longs)

## 3) Directional alignment filters

EMA alignment uses strict stack checks.

4h alignment (`ema9/21/50` with price):

- bullish: `price > ema9 > ema21 > ema50`
- bearish: `price < ema9 < ema21 < ema50`
- otherwise: mixed

Daily alignment (`ema21/50/200` with price):

- bullish: `price > ema21 > ema50 > ema200`
- bearish: `price < ema21 < ema50 < ema200`
- otherwise: mixed

## 4) Entry rules (must pass all)

### Short entry

Requires all:

- daily alignment = `bearish`
- 4h alignment is either:
  - strict bearish stack, or
  - partial bearish stack (early trend continuation) with confidence penalty
- `MACD histogram < 0`
- `ADX >= 25`

### Long entry

Requires all:

- daily alignment = `bullish`
- 4h alignment is either:
  - strict bullish stack, or
  - partial bullish stack (early trend continuation) with confidence penalty
- `MACD histogram > 0`
- `ADX >= 25`

RSI is no longer a hard pass/fail entry gate. It now influences confidence through soft penalties when conditions are stretched.

If either side fails, bot logs exactly why (the `No entry - short: ... | long: ...` text you are seeing).

## 5) Confidence model

After passing hard entry gates, confidence is scored from supporting/contradicting features:

- volume ratio
- funding rate
- open interest change
- RSI state
- price vs EMA200
- +DI/-DI alignment
- Stoch RSI
- long/short ratio
- taker buy/sell ratio
- ATR percentile
- price vs VWAP

Important:

- borderline ADX regime applies `-0.08` score penalty
- partial 4h alignment mode applies `-0.04` score penalty
- confidence threshold is strict: `MIN_CONFIDENCE = 0.80`
- below threshold => skip

## 6) Exit logic (if in a position)

### Hard exits

- 4h alignment flips against position
- daily alignment flips against position
- trend collapse (`ADX < 20`)
- client-side SL/TP hit

### Soft exits (momentum weakening)

Examples:

- mixed 4h EMA + weakening MACD + low ADX
- MACD divergence with vulnerable RSI
- OI drop with confirming momentum weakness

Soft-exit delay rule in main loop:

- if unrealized loss is small (`< 2%`) and exit is not hard, close is delayed.

## 7) Risk controls and execution

From `app/swing/config.py`:

- leverage: `5x`
- size per trade: confidence-scaled from `$5` to `$10`
- max open positions: `3`
- fallback SL: `3%`
- fallback TP: `8%`
- loss cooldown after losing trade: `4h`

Also generated per-snapshot:

- suggested SL: `max(1.5 * ATR/price, 1%)`
- suggested TP: `max(3.0 * ATR/price, 2%)`

## 8) Why your logs show constant HOLD

Your sample logs are consistent with strategy behavior, not a runtime bug.

Main repeated blockers:

- `ADX < 20` (regime gate) or `ADX < 22` (minimum entry ADX)
- daily/4h trend mostly `bearish` or `mixed` (blocks longs)
- for shorts, MACD histogram often `>= 0`; low RSI now penalizes confidence rather than hard-blocking

Net effect:

- strict trend-following setup + choppy market => very low trade frequency
- many cycles with `conf=0.00` because entry hard-fails before confidence scoring

## 9) Does this strategy make sense?

Yes, **internally it makes sense** for a conservative trend-following system:

- clear regime filter
- strict trend alignment
- momentum confirmation
- explicit risk controls

But with current thresholds, it is **very selective** and will frequently stay flat in ranging/choppy conditions. This is expected behavior under this design.

## 10) Source files

- `app/swing/agent.py`
- `app/swing/snapshot.py`
- `app/swing/main.py`
- `app/swing/config.py`

## 11) Agreed weaknesses and practical improvements

This section captures the points that are valid from an operational perspective.

### Weaknesses I agree with

- Trade frequency can still be low due to stacked gates (ADX, dual EMA alignment, MACD sign, confidence threshold).
- Hard `ADX > 25` entry gate delayed entries in prior version.
- 1-hour cycle can delay discretionary/soft-exit reaction (even though exchange-side SL/TP helps).

### Important caveats

- Confidence model is not opaque in code: feature weights and confidence mapping are explicit.
- Volatility is not fully missing: ATR percentile affects confidence, and SL/TP are ATR-derived.
- Borderline ADX is no longer used for entries (`MIN_ADX_ENTRY = 25`).

### Improvements that fit current architecture

1. ADX hard gate was loosened from `>25` to `>=22`, with penalty below 25.
2. RSI was converted from hard pass/fail into softer score penalties near extremes.
3. Strict EMA stack remains primary; partial 4h stack mode was added with penalty.
4. Confidence-based sizing bands were added (from `$5` to `$10`).
5. Confidence component logging now includes explicit signed contributions (`+/-`).
6. Optional: reduce cycle interval to 30m only after measuring API/load and false-exit impact.

## 12) Replay benchmark (v1 vs v2)

Run date: `2026-04-06` (UTC)  
Window: `2025-01-01` to `2026-01-01`  
Universe: `BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`

Command:

```bash
python -m app.swing.backtest_replay \
  --coins BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI \
  --start 2025-01-01T00:00:00Z \
  --end 2026-01-01T00:00:00Z
```

Aggregate results:

| Strategy | Trades | Win rate | Net PnL | Avg PnL/trade | Profit factor | Max drawdown | Avg entry confidence |
|---|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 57.89% | 3.36 | 0.09 | 1.32 | 4.65 | 0.76 |
| `v2` (current tuned) | 41 | 51.22% | 4.92 | 0.12 | 1.34 | 6.82 | 0.84 |

Interpretation:

- `v2` now runs at similar frequency (`41` vs `38`) due to stricter entry quality gates.
- In no-cost replay, `v2` outperforms `v1` on net PnL in this window.
- `v2` still carries higher drawdown.

Method caveats:

- Public kline replay only (no order book microstructure).
- Funding/OI/L-S/taker features are neutralized to baseline values.
- No fees/slippage/latency modeling.

Cost-aware command:

```bash
python -m app.swing.backtest_replay \
  --coins BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI \
  --start 2025-01-01T00:00:00Z \
  --end 2026-01-01T00:00:00Z \
  --fee-bps 4 \
  --slippage-bps 2
```

Cost-aware aggregate results (`fee=4 bps`, `slippage=2 bps`, per side):

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max drawdown | Avg entry confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 38 | 55.26% | 2.29 | 3.04 | 0.76 | 0.06 | 1.21 | 4.54 | 0.76 |
| `v2` (current tuned) | 41 | 48.78% | 3.43 | 4.47 | 1.04 | 0.08 | 1.22 | 6.89 | 0.84 |

Cost-aware interpretation:

- `v2` remains cost-sensitive but stays net positive in this window after modeled costs.
- `v2` slightly outperforms `v1` on net PnL, with higher drawdown.

## 13) 5-year benchmark (cost-aware)

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

Aggregate results:

| Strategy | Trades | Win rate | Net PnL | Gross PnL | Fees | Avg PnL/trade | Profit factor | Max drawdown | Avg entry confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1` (legacy strict) | 217 | 47.00% | -20.20 | -15.86 | 4.34 | -0.09 | 0.71 | 13.09 | 0.76 |
| `v2` (current tuned) | 182 | 44.51% | -16.93 | -12.30 | 4.63 | -0.09 | 0.78 | 21.69 | 0.84 |

Target status (`60–70% win rate` and `positive PnL`):

- Not achieved on this 5-year test.
- `v2` improves over `v1` on net PnL/profit factor, but remains negative and higher drawdown.
