# Intraday Remake — Design

**Date:** 2026-07-15
**Status:** Approved by user (direction, capital, teardown, fallback, approach, all 4 design sections)

## Context — why we're remaking

Log analysis of `swing-logs.txt` (2026-06-12 → 2026-07-15, 791 hourly cycles):

- **Zero live trades in 33 days.** Every cycle reported `Open positions: none`.
- Dominant blockers: ~6,650 HOLDs cite `ADX < 28`, ~5,800 cite `ADX < 20 (ranging)`.
  Best setup all month: TURBO at confidence 0.71 vs the 0.80 bar.
- **TON and IP crashed every cycle** (`float division by zero`) since ~2026-06-24 —
  908 swallowed errors, no alert, 2 of 13 coins silently dead for ~3 weeks.
- Shadow tracker: 4 blocked shorts netting −1.8% (the RSI gate + shorts-off saved money).

Combined with prior research: v2 OOS evaluation (2026-06-12) found the long-only strategy
has **no edge** (−0.74% pooled, underperforms a plain basket); Phase C rejected carry,
XS momentum, and basis MR against pre-registered criteria. The project is a strategy with
no demonstrated edge, making zero trades, with 15% of its universe crashing every cycle.

## Goal

Replace both existing bots with **one intraday futures system** (5m–15m decision cadence)
whose strategy is chosen by evidence: a fee-aware, pre-registered edge-hunt on warehouse
data, then a paper-first live engine. Real money only after live shadow validation.

**Explicitly out of scope:** true HFT (co-location, microsecond latency, maker-rebate
market making) — not achievable from retail infrastructure; websocket streaming engine —
deferred unless research finds an edge that decays in seconds.

## Decisions (user-approved)

| Decision | Choice |
|----------|--------|
| Direction | Intraday system, 5m–1h cycles, research-first |
| Capital | Same as now (~$50–100) — proving-ground scale |
| Existing bots | Retire **both** (DCA spot bot + swing agent) |
| If no edge passes OOS | Build the engine anyway; run best candidate in **paper mode**; real money gates on ~4 weeks positive shadow PnL |
| Approach | A: Research pipeline → paper-first engine |

## 1. Architecture & teardown

- Remove `bot` and `swing` services from `docker-compose.yml`.
- Archive `app/bot/` and `app/swing/` (move, don't delete — history and reusable parts
  stay reachable). DB keeps `trades` / `swing_trades` tables as history.
- New package `app/intraday/`:
  - `engine.py` — cycle loop, aligned to candle close
  - `strategy.py` — **pure function**: market snapshot → decision. The only place
    strategy logic lives; the backtest imports this same function, so live/backtest
    parity is structural rather than test-enforced.
  - `execution.py` — order placement behind one interface with `paper` / `live` modes
  - `risk.py` — kill-switches and limits
- Reused from the old system: futures exchange wrapper (incl. the 2026-06-05
  `/fapi/v1/algoOrder` SL/TP fix), reconciler, Telegram notifier, Alembic + Postgres.

## 2. Data (research prerequisite)

- Extend `research/` warehouse with intraday klines for a **liquid top-30 subset**
  selected by 30-day median daily quote volume (thin coins have untradeable spreads at
  this frequency):
  - `klines_15m` — from 2023-01-01 or listing date, whichever is later
  - `klines_5m` — most recent ~18 months
- Reuse the existing resumable backfill machinery (per symbol×dataset high-water mark).
- Backfills run from the DEV machine only (prod IP stays clean — 2026-06-05 ban).
- Estimated volume: ~10–15M new rows; parquet + duckdb handle this fine.

## 3. Research protocol (pre-registered)

**Cost model in every result:** 0.05% taker fee + 0.03% modeled slippage per side
(~0.16% round trip). Gross-of-fees numbers are never reported.

**Signal families** (each gets a cheap event study first — does the raw signal predict
forward returns net of costs? — and only survivors get full strategy backtests):

1. Intraday breakout (range/Donchian break with volatility filter)
2. Short-horizon mean reversion (return z-score vs VWAP)
3. Volatility compression → expansion (squeeze)
4. Funding-window effects (8h funding cycle; funding data already in warehouse)
5. Volume / OI impulse
6. Time-of-day seasonality

**Pass bar — fixed now, before any backtest runs. OOS windows untouched until final eval:**

- Net (after costs) profit factor ≥ 1.15
- ≥ 100 OOS trades
- Positive in ≥ 2 of 3 walk-forward OOS windows
- Max drawdown ≤ 20%

Built on the existing `siglib` verified backtest library. Output: a research report per
family and a ranked candidate list.

## 4. Engine, risk, go-live gate

- **Cadence/transport:** REST polling of closed candles (5m or 15m per research winner).
  Well within rate limits for 30 symbols; no websockets in v1.
- **Paper mode is first-class and the default.** Identical decision path to live;
  simulated fills at next-candle open + modeled slippage; every trade recorded in a new
  `intraday_trades` table with a `mode` column (`paper` / `live`).
- **Error isolation with alerting** (fixes the TON/IP failure mode): a per-symbol
  exception never kills the loop, and 3 consecutive failures on a symbol fires a
  Telegram alert.
- **Kill-switches:** daily-loss halt and max-drawdown halt — both stop trading and page
  via Telegram. Hard caps on concurrent positions and per-trade risk.
- **Go-live gate:** top 2–3 candidates run in paper mode simultaneously. Real $50–100
  turns on for one candidate only after ~4 weeks of net-positive shadow PnL and zero
  kill-switch trips.
- **Weekly automated report:** live/paper performance vs backtest expectation.

## Testing

Same philosophy as the existing suite: money-path tests first, Hypothesis invariants,
indicator golden tests. The structural live/backtest parity (shared `strategy.py`)
replaces the old parity test's job; a smoke parity test remains as a regression tripwire.

## Phases (each gated on the one before)

1. **Data** — backfill 15m/5m klines, gap-check.
2. **Edge-hunt** — event studies → strategy backtests → OOS eval against the pass bar.
3. **Engine** — build `app/intraday/`, retire old bots, deploy in paper mode.
4. **Shadow → live** — ≥4 weeks paper validation, then live at $50–100.
