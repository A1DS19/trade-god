# Swing Strategy (Current Implementation)

This document describes the **actual strategy currently running** in the swing agent (`app/swing/*`).

## 1) High-level flow (every cycle)

1. Load open futures positions.
2. For each coin (`DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA, DOT`):
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
- minimum entry ADX is now `>= 32`
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
- `ADX >= 32`
- `-DI > +DI` (directional alignment)

### Long entry

Requires all:

- daily alignment = `bullish`
- 4h alignment = strict bullish stack
- `MACD histogram > 0`
- `ADX >= 32`
- `+DI > -DI` (directional alignment)

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
- ADX >= 32 entry gate means the bot sits flat for extended periods in choppy markets (by design — grid search showed PF 1.93 vs 1.20 at lower thresholds).
- 1-hour cycle can delay discretionary/soft-exit reaction (even though exchange-side SL/TP helps).

### Important caveats

- Confidence model is not opaque in code: feature weights and confidence mapping are explicit.
- Volatility is not fully missing: ATR percentile affects confidence, and SL/TP are ATR-derived.
- Borderline ADX is no longer used for entries (`MIN_ADX_ENTRY = 32`).

### Improvements that fit current architecture

1. ADX hard gate was raised to `>= 32` after grid search (PF 1.93, DD $7 vs PF 1.20, DD $15 at lower thresholds).
2. RSI was converted from hard pass/fail into softer score penalties near extremes.
3. Strict EMA stack remains primary; partial 4h stack mode was added with penalty.
4. Confidence-based sizing bands were added (from `$5` to `$10`).
5. Confidence component logging now includes explicit signed contributions (`+/-`).
6. Optional: reduce cycle interval to 30m only after measuring API/load and false-exit impact.

## 12) Current benchmark (10-coin set, cost-aware)

Run date: `2026-04-11` (UTC)
Coin selection from 2026-04-09 top-100 screening. See `docs/coin_screening_and_selection.md` for full methodology.

Universe: `DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA, DOT`

**Note (2026-04-11):** Earlier benchmarks ran v2 with `V2_MIN_CONFIDENCE = 0.85` in the backtest strategy while the live bot has been at `MIN_CONFIDENCE = 0.80` since 2026-04-06. The backtest was under-reporting live performance by ~21% net PnL for the entire life of the backtest. The table below reflects the aligned v2 (0.80) that matches live behavior.

### 1-year (Apr 2025 – Apr 2026), fee=4 bps, slippage=2 bps per side:

| Strategy | Trades | Win rate | Net PnL | Profit factor | Max drawdown | Avg conf | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 31 | 87.10% | $37.80 | 13.64 | $8.48 | 0.81 | 75.61% |
| v2 | 40 | 72.50% | $52.96 | 6.57 | $10.21 | 0.86 | 70.61% |

### 5-year (Apr 2021 – Apr 2026), fee=4 bps, slippage=2 bps per side:

| Strategy | Trades | Win rate | Net PnL | Profit factor | Max drawdown | Avg conf | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 81 | 55.56% | $42.83 | 2.20 | $15.58 | 0.80 | 17.12% |
| v2 | 146 | 50.00% | $76.46 | 1.96 | $25.32 | 0.85 | 20.38% |

Both strategies beat the 10% annual ROI target across all tested periods (bear, bull, sideways, recovery). See `docs/coin_screening_and_selection.md` for cross-period validation and vs. S&P 500 comparison.

**Per-coin watch-outs (5-year, v2 at true 0.80 threshold):**
- `DOT`: turns **net-negative** (−$0.89, 29 trades, 31% WR) — was +$1.14 when backtest was at 0.85. The 0.85 filter was masking a structural DOT weakness. Candidate for removal pending investigation.
- `RUNE`: drops from $4.34 to $1.81 (−58%). Still profitable but marginal.
- `1000FLOKI`: small decline from $18.83 to $16.47; still the top PnL contributor.
- `DOGE`, `1000SHIB`, `IOTA`, `BSV`, `TURBO` all materially improve.

## 13) Previous benchmarks (old 9-coin set, archived)

The old 9-coin set (`BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`) was net negative over 5 years. The coin selection was the primary issue — BTC/ETH/AVAX/XRP dragged performance. After screening and re-selection, the new 10-coin set is consistently profitable.
