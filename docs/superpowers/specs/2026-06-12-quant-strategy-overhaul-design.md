# Quant Strategy Overhaul — Design

**Date:** 2026-06-12
**Status:** Approved by user
**Goal:** Replace the swing bot's rule-based TA strategy with a quant-validated strategy, built on a proper research pipeline. The end product is the same always-on bot trading Binance USDT-M perps — only the brain changes, and only after validation.

## Decisions made (with user)

| Decision | Choice |
|---|---|
| Sequencing | Live-money fixes first, then warehouse → research → new engine |
| Research universe | Top ~100 USDT-M perps by 24h quote volume |
| Integration | New strategy **replaces** the current EMA/RSI/MACD pipeline after validation + shadow period |
| Risk envelope | Same as today: $5–10 margin per trade at 5x ($25–50 notional), max 3 concurrent |
| Architecture | One strategy core, two harnesses (backtest replays the same code live runs) |
| Research stack | pandas + pyarrow + duckdb, **dev machine only**; live bot stays stdlib-pure |

## Why

The current swing agent's signals (EMA/RSI/MACD/ADX) all derive from the same price series — effectively one trend signal. Live result over 70 closed trades: -$3.91, 40% win rate, statistically indistinguishable from zero edge minus costs. The 2026-06-12 deep analysis also found execution leaks (silent exchange-side fills, the flat 3% client net overriding ATR stops, decisions on still-forming candles) that would eat any edge. The repo already has rare strengths — walk-forward discipline, a parity test, live ground truth — but lacks: persistent historical data (the `cache/klines/` dir is empty; every backtest re-downloads, which caused the 2026-06-05 IP ban), orthogonal signals, and statistical sample sizes.

---

## Phase A — Live-money fixes (current bot, ships first)

All in `app/swing/`, each with tests, one batch:

1. **Exchange-fill reconciliation.** Each cycle and at startup: diff DB `status='open'` rows against exchange positions. For vanished positions, backfill exit price/time/PnL/reason from `GET /fapi/v1/userTrades`, mark closed, send the Telegram close alert, feed the loss-cooldown. The stale DOGE id=71 row is repaired by this code path on first deploy (no manual SQL).
2. **Safety net reads per-trade stops.** Client-side hourly check compares against the trade's stored `entry_sl_pct`/`entry_tp_pct` instead of flat `DEFAULT_SL_PCT`/`DEFAULT_TP_PCT`; defaults remain only as fallback when the DB row is missing. Restores the ATR-sized exchange stop as primary exit.
3. **Algo-order cancellation.** Route `cancel_open_orders()` through the Algo service (same migration the placement side got on 2026-06-05), verify against open algo orders, and cancel any currently-orphaned IOTA/DOGE triggers.
4. **Closed candles only.** Drop the forming last kline from 4h/1d indicator inputs; RSI warmup uses all fetched closes (200) instead of 30; fetch ~600 daily candles so EMA200 is converged. Moves live closer to what backtests replay.

Out of scope for A (tracked separately, not blocking): swing watchdog/heartbeat, baseline Alembic migration, .dockerignore additions.

## Phase B — Research data warehouse (dev machine only)

- **New top-level `research/` package**, excluded from the Docker image via `.dockerignore`. Dependencies in `requirements-research.txt` (pandas, pyarrow, duckdb) — never installed on the Lightsail box.
- **Storage: parquet, one file per dataset per symbol**, under gitignored `research/warehouse/`:
  - `klines_1h/`, `klines_4h/`, `klines_1d/` — OHLCV since listing
  - `funding/` — full funding-rate history since listing
  - `premium_index_1h/` — premium-index klines (basis) since listing
  - `oi_1h/`, `long_short_1h/` — Binance serves only the trailing 30 days; the updater accumulates them into continuous history from now on
  - `universe.parquet` — symbol metadata: listing date, status, rank snapshots
- **Backfill CLI:** `python -m research.backfill --top 100`. Resolves top-100 USDT-M perps by 24h quote volume, backfills all datasets since listing. Single-threaded, throttled ~0.5 s/request (≈1–1.5 h total). **Run from the dev machine only — never the production IP** (lesson of the 2026-06-05 -1003 ban).
- **Resumable + idempotent:** per symbol/dataset high-water mark (last stored open time); re-running tops up incrementally. A weekly dev-machine cron keeps data fresh and stitches the 30-day OI/L-S windows together.
- **Gap validation:** `python -m research.check` reports missing bars per symbol/dataset so backtests cannot silently span holes.
- **Query layer:** DuckDB over the parquet tree for research scripts.

## Phase C — Signal research

Reproducible scripts in `research/` (not ad-hoc notebooks), reading the warehouse. Candidates in priority order:

1. **Funding-rate carry** — extreme funding = crowded positioning; test mean-reversion of crowded coins and funding collection vs price drift. Orthogonal to the current momentum stack.
2. **Cross-sectional momentum** — rank top-100 by 7/14/30-day returns; test persistence of relative strength (trade the strongest/weakest few) instead of evaluating each coin in isolation.
3. **Basis/premium mean-reversion** (stretch) — premium-index extremes vs forward returns.

**Method per signal (fixed in advance):**
1. Event study: conditional forward returns after signal fires, with sample sizes and confidence intervals.
2. Portfolio backtest **through the strategy core itself** with taker fees (5 bps/side), slippage, and funding accrual modeled.
3. Walk-forward across ≥3 train/OOS windows (reusing the `wf_grid_search` discipline).
4. Every parameter combination tried is logged to quantify the multiple-testing burden; thresholds chosen on train windows only.

**Pre-registered promotion criteria** (a signal ships only if ALL hold):
- OOS net-positive in ≥2 of 3 walk-forward windows
- OOS profit factor ≥ 1.2
- Still net-positive with 2× slippage

If nothing passes, nothing ships — the current strategy keeps running rather than being replaced by something unvalidated.

## Phase D — Strategy core v3, shadow run, cutover

- **`app/strategy/` (new):** `MarketState` dataclass (per-coin features, cross-sectional ranks, funding, book state) and a pure `decide(state) -> list[Action]`. Stdlib-only, no API calls, no clock reads. The research backtester replays this exact function; the live loop executes it. One implementation, two harnesses — the live/backtest parity-debt class of bugs is eliminated by construction.
- **Live infra unchanged:** `exchange.py` (with Phase A's fixed algo cancel), notifier, DB, cooldowns. Only the brain is swapped behind a config switch: `STRATEGY=v2 | v3-shadow | v3`.
- **Shadow period:** with `v3-shadow`, v3 runs every cycle in the live container, recording would-be trades to a new `shadow_trades` table (paper fills at next-candle prices, fees modeled) while v2 keeps trading real money. Cutover gate: after **≥4 weeks**, shadow net PnL after costs is positive AND max drawdown is within 1.5× the backtest's OOS drawdown for a same-length window; then flip to `STRATEGY=v3`. v2 code stays in the tree for one release as rollback.
- **Live data for cross-sectional inputs:** one batched 24h-ticker call + one batched premium-index call per cycle covers all symbols (well within rate limits).
- **DB migration 006:** `strategy` column on `swing_trades`; new `shadow_trades` table.
- **Sizing:** unchanged — $5–10 margin at 5x, max 3 concurrent; scaling later is a config change.

## Error handling

- Backfill: resumable, throttled, per-symbol error isolation (one bad symbol doesn't kill the run), gap report.
- Live: keep the existing two-tier per-coin / whole-cycle isolation; Phase A adds fill reconciliation so exchange-side events can't silently desync state.
- Shadow mode failures must never affect real trading: shadow errors are logged and skipped.

## Testing

- Phase A: unit tests per fix (reconciliation with fake client + fake DB, safety-net thresholds, algo cancel request shape, closed-candle indicator inputs).
- Warehouse: golden tests for backfill pagination/dedup/high-water-mark logic against fixtures.
- Strategy core: golden tests for feature computations; property tests (never exceeds MAX_OPEN, never sizes above cap, no orders on stale data); replay determinism (same warehouse slice → identical trade list).
- Execution: fake-client tests for order paths.
- The existing 85-test suite stays green throughout.

## Non-goals (YAGNI)

- No ML models in v1 of the new engine — validated rule-based signals only; meta-labeling can come later.
- No new exchanges, no spot changes (DCA bot untouched).
- No web dashboard for research; scripts + parquet are enough.
- No increase in capital at stake until v3 has post-cutover live history.

## Sequencing summary

A (fixes, ~1–2 days) → B (warehouse, ~2–3 days incl. backfill) → C (research, ~1 week first pass, open-ended) → D (engine + 4-week shadow → cutover). Each phase gets its own implementation plan; A starts immediately.
