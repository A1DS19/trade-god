# Swing Tuning Notes (April 3, 2026)

## Context
- Project: `trade-god`
- Service: Swing futures agent (`app/swing`)
- Goal: reduce frequent close-at-loss behavior caused by overly sensitive exit logic and fix SL/TP unit bugs.

## Observed Symptoms
- Logs repeatedly showed: `EXIT ... 4h EMA turned mixed` followed by closes at a loss.
- Logs showed signals like `sl=3.176 tp=6.352` (wrong units for internal fractional fields).
- Exchange warnings: `APIError(code=-4120)` on SL/TP placement.

## Root Causes Identified
1. SL/TP unit mismatch in snapshot generation:
- Expected internal units: fractions (e.g. `0.03176` for 3.176%).
- Produced values: whole percent numbers (e.g. `3.176`).

2. Exit strategy too aggressive on noise:
- Mixed EMA state was enough to exit, which caused frequent early exits near local chop.

3. Close PnL recording used pre-close snapshot PnL in some paths:
- Could diverge from true realized result at fill.

4. Historical DB rows (`swing_trades`) contain bad `entry_sl_pct`/`entry_tp_pct` units for newer rows.

## Code Changes Applied

### 1) SL/TP and Signal Logging
- File: `app/swing/snapshot.py`
  - `suggested_sl_pct` and `suggested_tp_pct` now computed as fractions.
- File: `app/swing/agent.py`
  - Signal logs now render `sl/tp` in human-readable `%` while keeping fractional internals.

### 2) Realized PnL Accuracy
- File: `app/swing/main.py`
  - Added close fill extraction helper (`avgPrice` fallback handling).
  - Realized PnL now calculated from entry/exit price for close, flip-close, and client-side SL/TP close paths.

### 3) Exit Strategy Revision (sell strategy)
- File: `app/swing/agent.py`
  - Hard exit still on full invalidation:
    - `4h EMA turned bullish` (for shorts) / `bearish` (for longs)
    - daily EMA flip
    - ADX collapse
  - Mixed EMA now exits only with additional weakening confirmation:
    - mixed EMA + MACD weakening + `ADX < 25`
  - Deeper RSI exit thresholds (moved into config constants).

- File: `app/swing/main.py`
  - Added soft-exit loss guard:
    - for non-hard exit reasons, if unrealized loss is small, hold and delay close.
  - Added `CLOSE-CHECK` log line with reason + unrealized PnL%.

### 4) Tuned Parameters (current)
- File: `app/swing/config.py`
  - `SHORT_EXIT_RSI_FLOOR = 32.0`
  - `LONG_EXIT_RSI_CEIL = 68.0`
  - `SOFT_EXIT_MAX_LOSS_PCT = 0.020`

### 5) Historical Data Normalization Migration
- New file: `alembic/versions/005_normalize_swing_sl_tp_units.py`
  - Divides `entry_sl_pct` and `entry_tp_pct` by `100` where values are `> 1`.
  - Purpose: normalize historical percent-unit rows to fractional units.

## Verified Historical Bad Rows
From `/home/dev/swing_trades.json`:
- `id=60`: `entry_sl_pct=2.4`, `entry_tp_pct=4.801`
- `id=61`: `entry_sl_pct=3.176`, `entry_tp_pct=6.352`
- `id=62`: `entry_sl_pct=3.258`, `entry_tp_pct=6.516`

These are now handled by migration `005`.

## Deploy Checklist
```bash
cd ~/trade-god
git pull
docker compose run --rm migrate
docker compose up -d --build swing
docker compose logs -f swing
```

## Post-Deploy Monitoring (24h)
Collect:
```bash
docker compose logs --since 24h swing | rg "CLOSE-CHECK|HOLD .*soft exit delayed|NOTIFY close|CLIENT SL|CLIENT TP|SIGNAL"
```

Then export and review `swing_trades` for:
- reduced count of small-loss exits on mixed EMA reasons
- no new `entry_sl_pct`/`entry_tp_pct` rows with values `> 1`
- expected distribution of realized loss vs wins.

## Notes
- Losses are still expected; objective is to cut avoidable noise exits, not eliminate losing trades.
- DB exposure decision was explicitly left unchanged by user request.
