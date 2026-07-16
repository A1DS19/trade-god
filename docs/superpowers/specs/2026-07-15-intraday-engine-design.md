# Intraday Paper-First Engine — Design (Phase 3)

**Date:** 2026-07-15
**Status:** Approved by user (candidates, universe policy, DCA-holdings disposition, approach, all 4 design sections)

## Context

Phases C, 2a, and 2b rejected every strategy candidate under honest evaluation
(`2026-07-15-intraday-edge-hunt-findings.md`, `2026-07-15-mr-vwap-2b-findings.md`). Per the
pre-agreed decision tree, Phase 3 builds the paper-first engine anyway: shadow trading is the one
validation that cannot be overfit, and it measures the one number no backtest can supply — real
maker fill behavior. Both legacy bots retire in this phase.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Launch candidate | mr_vwap maker-limit variant (frozen 2b params: H=32 bars, horizon exit, K=10, z<−3) in paper mode, with full fill telemetry |
| Universe | Weekly auto-refresh: top-30 by 30-day median quote volume from REST daily klines (same rule as the backtest PIT gate) |
| DCA spot holdings | Left held, managed manually — the deploy touches nothing on Binance |
| Approach | A: shared strategy core re-homed into `app/` |
| Go-live | Manual only: ≥4 weeks positive shadow PnL + zero kill-switch trips makes live *eligible*; a human flips `EXECUTION_MODE=live` |

## 1. Architecture & teardown

New package `app/intraday/`:

- `config.py` — frozen strategy params (H=32, K=10, Z_ENTRY=−3.0), cadence 900s, paper equity $100, risk thresholds, universe settings, `EXECUTION_MODE` (only `paper` implemented in this phase; `live` raises NotImplementedError)
- `strategy.py` — **the shared pure core**, re-homed from `research/signals/intraday/mr_vwap_strategy.py`: z computation (from `families.mr_vwap_z` math), `build_weights`, `Z_ENTRY`/`Z_RECOVER`, the strict trade-through fill rule. `research/signals/intraday/mr_vwap_strategy.py` becomes a thin re-export so all 2b research code and tests keep working. Import direction: research → app, never app → research.
- `data.py` — unsigned REST 15m/1d kline fetch (python-binance public client, no keys) → pandas panels; drops the still-forming bar; per-symbol error isolation
- `paper.py` — the paper book: virtual limits, fill resolution, positions, PnL accounting, telemetry
- `engine.py` — the 15m cycle loop, candle-close aligned (~20s after close)
- `risk.py` — kill-switches + consecutive-error tracker
- `universe.py` — weekly top-30 refresh
- `notifier.py` — Telegram (same html.escape discipline as legacy)
- `main.py` — entrypoint + wiring

**pandas joins prod `requirements.txt`** (matplotlib already ships; 2GB box is fine).

**Teardown (same phase):** `bot` and `swing` services removed from docker-compose; `intraday`
service added (no API keys in its environment while paper). `app/bot/` and `app/swing/` move to
`legacy/` together with `tests/bot/` and `tests/swing/` (excluded from pytest — this also removes
the known date-sensitive `test_stale_row_closed_from_fills` failure). DB tables `positions`,
`trades`, `swing_trades` remain as history. The `api` service is unchanged. DCA spot holdings on
Binance are not touched.

## 2. Cycle & paper execution with fill telemetry

Each cycle (900s, aligned after 15m close):

1. Fetch closed 15m klines for the universe (~120 bars/symbol; ~30 unsigned requests — far inside rate limits).
2. Compute z with the shared core (identical math to the 2a/2b research).
3. **Resolve pending virtual limits** against the just-closed bar: `low < limit` → filled at the
   limit price (`trade_through`); `low == limit` → `touch_only`, NOT filled; `low > limit` →
   `miss`. Every placed limit writes a telemetry row regardless of outcome — this measurement is
   the phase's primary deliverable (real fill rates vs the backtest's strict-trade-through
   assumption, and the PnL sitting in the touch-only gap).
4. **Exits:** positions at horizon (32 bars) exit at the closed bar's close.
5. **Entries:** z<−3 signals place new virtual limits at the signal close, lowest z first, capped
   by free slots (K=10 slots of 1/10 of paper equity). Limits expire after one bar.
6. Apply real funding events to held positions; charge modeled costs identically to 2b
   (`MAKER_ENTRY` 2bps entry, `INTRADAY` 8bps exit) so paper PnL is accounting-compatible with the
   backtest.

The paper book persists to the DB every cycle (restart-safe; a restart resumes limits, positions,
and kill-switch state).

## 3. Risk, ops, reporting

- **Error isolation:** one symbol's exception never kills the cycle; 3 consecutive failures on a
  symbol → Telegram alert (the TON/IP lesson, structural).
- **Kill-switches, armed in paper:** daily paper loss > 5% of paper equity, or drawdown > 20%
  from peak paper equity → halt paper trading + Telegram page. The halt persists in
  `intraday_state` across restarts; resume is explicit: operator starts the service with
  `INTRADAY_RESUME=1`, which clears the halt once and alerts that trading resumed. Proving this
  machinery is part of the phase's purpose.
- **Universe refresh:** weekly; top-30 by 30d median quote volume among the top-100 by 24h volume
  (REST daily klines). Dropped symbols take no new entries; open positions run to exit. Changes
  are alerted.
- **Telegram:** entry/exit/miss events (compact), daily paper summary (PnL, fill stats), weekly
  report: paper PnL vs backtest expectation + telemetry aggregates (trade-through %, touch %,
  miss %).
- **Go-live gate:** manual only, as decided. Nothing in this phase implements live order routing.

## 4. Data, persistence, testing

Alembic migration 006:

- `intraday_trades` — id, symbol, direction, mode, limit_price, entry_price, exit_price,
  slot_fraction, entry_time, exit_time, hold_bars, pnl_pct, pnl_usd, fill_type, exit_reason, status
- `intraday_limits` — id, symbol, limit_price, placed_at, resolved_at, outcome
  (trade_through | touch_only | miss), bar_low (telemetry)
- `intraday_state` — key/value JSON (paper book snapshot, kill-switch state, universe snapshot)

Tests (money-path first, established style): fill golden tests (trade-through / touch / miss /
expiry), horizon exit, slot cap + lowest-z tie-break, kill-switch trips, restart recovery,
universe rule, error-isolation 3-strike alert — plus the **structural parity test**: engine
decisions on fixture panels must equal `strategy.build_weights` output exactly.

## Protocol notes carried from the 2b final review

Applied to any future research phase run from this codebase: two-commit freeze-then-unseal
evidence pattern; a pre-registered stop condition (never unseal a variant whose train metrics
already violate an OOS gate); flag grid-corner winners; commit every diagnostic artifact.

## Success criteria for Phase 3

1. Both legacy bots retired; one `intraday` service running keyless paper mode on the Lightsail box.
2. Four weeks of unattended operation producing daily summaries and weekly fill-telemetry reports
   without silent failures.
3. The fill-telemetry dataset answers: how optimistic was the strict trade-through model, and is
   there any maker-execution path worth a future pre-registered study?

### Deploy record (2026-07-16)

Deployed to the Lightsail box at 16:31 UTC (`b1fdd76`): legacy `bot`/`swing`/`rebalance`
containers removed, migration 006 applied, engine up keyless. First cycle 16:32 UTC:
`symbols_ok=30, errors=0, equity_mark=100.0, halted=False`; all 7 state keys persisted;
startup/daily/weekly Telegram messages received. Three clean cycles observed (16:32, 16:45,
17:00). First live telemetry within the watch window: ALLOUSDT limit 0.37888 (z=−3.58) placed
at 16:45, resolved `trade_through` at 17:00 (bar low 0.37627) → trade id=1 open, $10 slot.
Criterion 1 met; criterion 2 window runs through 2026-08-13.
