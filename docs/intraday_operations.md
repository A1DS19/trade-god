# Intraday Paper Engine — Operations Guide

Living ops reference for `app/intraday/` (deployed 2026-07-16). Design rationale lives in
[the Phase 3 spec](superpowers/specs/2026-07-15-intraday-engine-design.md); this doc covers
what the running system does, what its Telegram messages mean, and how to monitor and
operate it.

Research chain that led here: [remake design](superpowers/specs/2026-07-15-intraday-remake-design.md)
→ Phase 1 data backfill → [Phase 2a edge hunt](superpowers/specs/2026-07-15-intraday-edge-hunt-findings.md)
(mr_vwap sole survivor) → [Phase 2b backtest](superpowers/specs/2026-07-15-mr-vwap-2b-findings.md)
(REJECTED at retail costs) → Phase 3 paper-first engine (this system).

---

## What's running

- **Strategy:** `mr_vwap` — long-only mean reversion on deep oversold vs 24h VWAP
  (`app/intraday/strategy.py`, shared verbatim with research backtests).
- **Execution:** paper only. `EXECUTION_MODE=live` raises `NotImplementedError`
  (`app/intraday/main.py`). Virtual maker limits, no orders touch the exchange.
- **Keyless:** `Client("", "")` — unsigned market-data endpoints only. No Binance API keys
  in the container.
- **Cycle:** every 900s, aligned to 15m candle close +20s (`main.py`). Each cycle:
  fetch klines → compute z → resolve pending limits → age/exit positions → admit fills →
  place new limits → apply funding → mark equity → check kill-switches → persist.
- **Universe:** weekly top-30 USDT perps by 30-day median quote volume; ~24h backoff on
  refresh failure (the 2026-06-05 -1003 ban is the design constraint).

## Frozen parameters

Pre-registered from 2b research — **do not tune without a new research phase**
(`app/intraday/config.py`, `strategy.py`, `paper.py`).

| Param | Value | Notes |
|---|---|---|
| `HORIZON_BARS` (H) | 32 | 15m bars; entry bar counts as bar 1 |
| `MAX_K` (slots) | 10 | $10/slot at $100 equity |
| `Z_ENTRY` | −3.0 | strict `<`; z = (close − 24h-VWAP) / 96-bar σ |
| `Z_WINDOW` | 96 | 24h of 15m bars |
| `PAPER_EQUITY` | $100 | slot size is **fixed** at equity/K — does not drift with realized PnL across restarts |
| Costs | 2 bps entry / 8 bps exit | modeled maker entry + taker-ish exit, deducted from `pnl_usd` |
| `DAILY_LOSS_HALT` | 5% | vs first equity mark of the UTC day |
| `MAX_DD_HALT` | 20% | vs all-time equity peak |
| `UNIVERSE_REFRESH_DAYS` | 7 | |
| `ERROR_ALERT_STRIKES` | 3 | consecutive per-symbol failures → alert |

## Telegram message reference

All messages come from `app/intraday/notifier.py` (events wired in `engine.py`/`main.py`).

| Message | Meaning |
|---|---|
| 🚀 `Intraday engine up — mode=…, universe=…, equity=…` | Service (re)start. Suffix `[HALTED]` if the kill-switch is still latched. |
| 📥 `PAPER FILL <SYM> / Entry: $… (z=…)` | A virtual limit filled and was **admitted** to a slot. Only strict trade-through fills (bar low **below** the limit price) ever fill — a bar that merely touches the limit is logged `touch_only` and does **not** fill. This is deliberately conservative, and why `intraday_trades.fill_type` is always `trade_through`. |
| ✅ / 🛑 `PAPER EXIT <SYM> / PnL: ±x.xx USDT (±x.xx%) over N bars` | Horizon exit at the N-th bar close. **The % is gross** (`close/entry − 1`); **the USDT figure is net** of the 10 bps round-trip cost and accrued funding — so on a $10 slot the USDT number is ~$0.01 lower than the gross % implies. Entry bar counts as bar 1, so a 32-bar exit lands 31 × 15m (7h45m) after the fill message. |
| 📊 `Intraday daily summary` | Equity mark, open positions, pending limits, halted flag. Keyed to the **UTC date**: fires on the first cycle after 00:00 UTC (observed ~6:00 PM local), and also on the first cycle after a fresh boot — hence two on deploy day. |
| 📈 `Weekly fill telemetry` | `trade_through` / `touch_only` / `miss` / `no_data` counts. Sent every 7 days from the last send (first one fires at boot). **Percentages are cumulative since inception**, not per-week (`engine.py` counts the whole `intraday_limits` table). |
| 🔄 `Universe refreshed: +[…] -[…]` | Weekly top-30 changed. Dropped symbols do **not** force-exit open positions — they run to their horizon exit. |
| ⚠️ `<SYM> failed N consecutive cycles` | Per-symbol data failures hit the strike limit (also used for `__data__` = whole fetch stage and `__universe__` = refresh). |
| ⛔ `KILL-SWITCH: daily_loss` / `drawdown` | Trading halted; positions stop being opened (existing book still marks). Persisted — survives restarts. |
| ▶️ `Kill-switch cleared via INTRADAY_RESUME` | Operator resume acknowledged (see runbook below). |
| 💥 `Intraday cycle crashed: <Error>` | Unhandled cycle exception; loop continues next cycle. |
| ⚠️ `state persist failed` / `trade open log failed` | DB write failed; state self-heals next cycle (full-snapshot writes), trade-close ids are kept for retry. |

## Day-1 verification (2026-07-16 log audit)

The first day's Telegram stream was reconciled against the code, line by line:

- 6 fills (ALLO, HYPE, XRP, NEAR, UNI, XLM), all z ∈ [−3.58, −3.00] — consistent with the
  strict `Z_ENTRY=−3.0` gate.
- ALLOUSDT +$0.88 (+8.92% gross) and HYPEUSDT −$0.22 (−2.13%) both exited at exactly
  32 bars: fill 11:00 → exit 18:45, fill 11:30 → exit 19:15. PnL math reconciles:
  gross% × $10 − $0.01 costs ± funding = the USDT figure.
- The 18:00 daily summary (4 open, 1 pending) matches the fill timeline exactly; the
  10:32 summary + "no limits yet" weekly report were the expected boot-time sends.
- **Caveat to watch, not a bug:** a broad market dip fills many slots at once (6 fills in
  8h on day 1), so the book concentrates in correlated longs. That is by design with
  K=10 — but it is exactly the regime where the 2b out-of-sample maker-fill concern
  lives. The fill telemetry exists to measure it.

## Kill-switch & resume runbook

Two latches (`app/intraday/risk.py`), both persisted in `intraday_state`:

- **daily_loss** — equity mark < 95% of the first mark of the current UTC day.
- **drawdown** — equity mark < 80% of the all-time peak.

When latched: ⛔ alert, no new placements/admissions (`active_universe` empties), book
still marks and horizon exits still fire. The halt survives restarts.

**To resume** (operator decision only — investigate first):

```bash
# on the Lightsail box
cd ~/trade-god
INTRADAY_RESUME=1 docker compose up -d intraday   # or set it in .env, then remove it
docker compose logs -f intraday                   # expect ▶️ resume + 🚀 startup
```

`INTRADAY_RESUME=1` clears the latch **once** at boot and re-anchors the daily baseline
on the next cycle. Remove the variable afterwards so a later halt isn't auto-cleared by
a routine restart.

## Monitoring

**Logs** (every cycle ends with a one-line summary):

```bash
docker compose logs -f intraday
docker compose logs --timestamps intraday | grep "cycle done"
# cycle done: {'symbols_ok': 30, 'errors': 0, 'placements': 2, 'entries': 1,
#              'exits': 0, 'equity_mark': 100.3, 'halted': False}
```

**Database** — Postgres is loopback-bound (since `29c4976`); tunnel in first:

```bash
ssh -L 5433:localhost:5432 <lightsail-host>
psql postgresql://tradegod:tradegod@localhost:5433/tradegod
```

```sql
-- fill-outcome distribution (the telemetry that decides go-live)
SELECT outcome, admitted, COUNT(*) FROM intraday_limits
GROUP BY outcome, admitted ORDER BY outcome;

-- realized trades, newest first
SELECT id, symbol, entry_time, exit_time, hold_bars, pnl_pct, pnl_usd, status
FROM intraday_trades ORDER BY id DESC LIMIT 20;

-- realized PnL + open book
SELECT status, COUNT(*), COALESCE(SUM(pnl_usd), 0) AS pnl
FROM intraday_trades GROUP BY status;

-- engine state (paper_book, killswitch, universe, trade_ids, summary timers)
SELECT key, updated, value FROM intraday_state;
```

**API** — since 2026-07-18 the FastAPI service also serves the intraday telemetry
(design: `docs/superpowers/specs/2026-07-18-intraday-api-design.md`). Port 8000 stays
closed at the firewall; tunnel in with `ssh -L 8000:localhost:8000 <lightsail-host>`, then:

- `http://localhost:8000/` — HTML status page (equity, gate progress, sparkline, open book)
- `GET /intraday/trades|stats|fills|state|gate` — JSON telemetry
- `GET /legacy/dca/*`, `/legacy/swing/*` — retired-bot history (old root paths removed)

The gate endpoint reports the CURRENT kill-switch latch only — past trips leave no DB
trace, so "zero trips" is still verified from Telegram ⛔ history.

## Go-live gate (manual only)

The 4-week telemetry window ends **2026-08-13**. Go-live requires ALL of:

1. ≥4 weeks of positive cumulative paper PnL,
2. zero kill-switch trips,
3. fill telemetry consistent with the 2b maker-fill assumptions
   (trade-through rate not materially worse than backtest).

Then — and only by a human — `EXECUTION_MODE=live`, which today raises
`NotImplementedError` on purpose: live execution is a separate, future implementation
phase, not a config flip.
