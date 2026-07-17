# Swing Strategy (Current Implementation)

This document describes the **actual strategy currently running** in the swing agent (`app/swing/*`).

## 1) High-level flow (every cycle)

1. Load open futures positions.
2. For each coin (`DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA`):
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

## 12) Current benchmark (9-coin set, cost-aware)

Run date: `2026-04-11` (UTC)
Coin selection: original 2026-04-09 top-100 screening minus DOT. See `docs/coin_screening_and_selection.md` for full methodology.

Universe: `DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA`

**History notes (2026-04-11):**
1. Earlier benchmarks ran v2 with `V2_MIN_CONFIDENCE = 0.85` in the backtest while live has been at `MIN_CONFIDENCE = 0.80` since 2026-04-06. The backtest was under-reporting live PnL by ~21% for the entire life of the backtest. Fixed — tables below reflect the aligned v2 that matches live.
2. **DOT was removed.** At the true 0.80 threshold it was net-negative over 5 years (−$0.89 / 29 trades / 31% WR). The exit breakdown showed 10 stop-outs totaling −$13.73, most on shorts blown out by sharp upward impulses, with avg entry ADX only 35.7 (weak selectivity on DOT specifically). DOT was picked in the 2026-04-09 screening based on the over-filtered 0.85 numbers. Removing it improved every aggregate metric.
3. **Walk-forward validation exposes significant overfit.** The tables in §12a are *in-sample* — coin selection and measurement overlap. Honest out-of-sample estimates are in §12b. The delta between in-sample and out-of-sample is the overfit premium (~41pp on 2025-2026 annual ROI), which is large. Treat the in-sample numbers as a ceiling, not a forecast.

### 12a) In-sample benchmarks (coin selection overlaps with measurement window)

⚠️ **These numbers include selection bias.** The 9 coins were picked using 2021-2026 data; measuring them on any subset of that window overstates forward-looking performance. Kept here as a reference ceiling, not a forecast.

#### 1-year (Apr 2025 – Apr 2026), fee=4 bps, slippage=2 bps per side:

| Strategy | Trades | Win rate | Net PnL | Profit factor | Max drawdown | Avg conf | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 30 | 86.67% | $35.92 | 13.00 | $8.48 | 0.80 | 79.82% |
| v2 | 37 | 75.68% | $51.80 | 8.01 | $9.81 | 0.86 | 76.75% |

#### 5-year (Apr 2021 – Apr 2026), fee=4 bps, slippage=2 bps per side:

| Strategy | Trades | Win rate | Net PnL | Profit factor | Max drawdown | Avg conf | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 67 | 59.70% | $40.42 | 2.40 | $15.58 | 0.80 | 17.96% |
| v2 | 117 | 54.70% | $77.34 | 2.24 | $25.32 | 0.86 | 22.90% |

### 12b) Out-of-sample walk-forward benchmarks (honest forward estimates)

✅ **These use clean train/test splits — no overlap between coin selection and measurement.** Methodology: screen top-100 by market cap on the training window only, apply the same tp_rate ≥ 25% / entries ≥ 50 filter, rank by composite score, take the top 10. Backtest those picks on the test window with the current v2 strategy.

#### Walk-forward #1 (train 2021-2023, test 2024-2026) — **FAILED**

| Picks | Trades | Win rate | Net PnL | PF | Max DD | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|
| INJ, ETC, BTC, SAND, FIL, APT, ADA, BNB, NEAR, DOGE | 72 | 44.44% | $6.90 | 1.17 | $11.79 | **4.04%** ❌ |

Only 2/10 picks profitable OOS (DOGE +$12.94 carried the portfolio; ADA +$4.01 marginal). The 1-year gap between training and measurement breaks the methodology.

#### Walk-forward #2 (train 2021-2024, test 2025-2026) — **PASSED**

| Picks | Trades | Win rate | Net PnL | PF | Max DD | Annual ROI |
|---|---:|---:|---:|---:|---:|---:|
| SEI, INJ, BTC, DOGE, ETC, SAND, PYTH, FIL, IOTA, TIA | 36 | 63.89% | $21.21 | 2.45 | $9.01 | **22.19%** ✅ |

7/10 picks profitable OOS. Continuous training (0-day gap) works; 1-year gap did not. The methodology is **regime-dependent**, not robust.

#### The 41pp overfit premium

Running the current 9 coins on the exact same 2025-2026 window gives **62.97%** annual ROI. The 41pp gap between 62.97% and 22.19% is the cost of selection-window overlap. Forward deployment should plan around ~22%, not ~63%.

### Forward-looking estimate

| Estimate | Annual ROI | Derivation |
|---|---:|---|
| **Honest forward estimate** | **~22%** | WF#2 OOS 2025-2026 |
| With expected drift | 15–20% | WF#2 less a drift haircut — training-test gap widens in forward deployment |
| Pessimistic (severe overfit) | 5–10% | Midpoint of WF#1 (4%) and WF#2 (22%) |
| In-sample ceiling | 63–77% | §12a numbers, NOT a forecast |

**Use 15–22% annual as the planning range.** All live risk-sizing, capital allocation, and emotional expectations should be calibrated to this range, not to the §12a numbers.

### Per-coin walk-forward robustness

| Coin | Walk-forward survival | Notes |
|---|---|---|
| DOGE | ✅ Passed WF#1 + WF#2 | Only current coin robust across all tests |
| IOTA | ✅ Passed WF#2 | Also in current set |
| RENDER | ⚠ Insufficient training data | Can't be evaluated via walk-forward |
| BSV | ⚠ Low rank in WF#2 (rank 45) | Passed marginally |
| RUNE | ⚠ Not in top-100 universe | Cannot be reproduced by the screener |
| 1000SHIB | ⚠ Not in top-100 universe | Cannot be reproduced by the screener |
| 1000FLOKI | ⚠ Not in top-100 universe | Cannot be reproduced by the screener |
| TURBO | ⚠ Not in top-100 universe | Cannot be reproduced by the screener |
| IP | ⚠ Not in top-100 universe | Cannot be reproduced by the screener |

**5 of 9 current coins are not in the top-100 universe the screener fetches today** (1000SHIB, RUNE, 1000FLOKI, TURBO, IP). They were picked via a process we cannot reproduce — either a different universe fetcher in April 2026 or manual selection. This is a transparency flag, not a removal recommendation.

**The edge is strongest on DOGE + IOTA.** Both survived every walk-forward test. The other 7 coins are speculative — in-sample they look great, but we have limited out-of-sample validation.

## 13) Previous benchmarks (old 9-coin set, archived)

The old 9-coin set (`BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, SUI`) was net negative over 5 years. The coin selection was the primary issue — BTC/ETH/AVAX/XRP dragged performance. After screening and re-selection, the new 10-coin set is consistently profitable.
