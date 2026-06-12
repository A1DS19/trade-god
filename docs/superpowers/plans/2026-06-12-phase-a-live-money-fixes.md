# Phase A: Live-Money Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four live-money gaps in the swing bot: silent exchange-side fills, the flat 3%/8% client safety net overriding ATR stops, algo orders never being cancelled, and indicators computed on still-forming candles.

**Architecture:** All changes live in `app/swing/` plus one DB helper in `app/db/models.py`. A new `app/swing/reconcile.py` module diffs DB open rows against exchange positions each cycle and backfills closes from account fills (`GET /fapi/v1/userTrades` via `client.futures_account_trades`). Cancellation gains a second call to the Algo service (`DELETE /fapi/v1/algoOpenOrders` — verified against Binance docs 2026-06-12; the existing placement already uses `POST /fapi/v1/algoOrder`). The safety net reads per-trade `entry_sl_pct`/`entry_tp_pct` from the DB row. Indicators drop the unclosed last kline and use full warmup windows.

**Tech Stack:** Python 3.12 stdlib + python-binance 1.0.19 + SQLAlchemy. Tests: pytest with `tests/conftest.py`'s `FakeBinanceClient` (env stubs are set there at import — do NOT re-add env boilerplate in test files).

**Context for the engineer:**
- Spec: `docs/superpowers/specs/2026-06-12-quant-strategy-overhaul-design.md` (Phase A section).
- The bot loops hourly in `app/swing/main.py:run()`. Positions come from the exchange every cycle (`get_open_positions`), DB rows in `swing_trades` track trades for PnL/cooldown.
- Live incident this plan fixes: DOGE trade id=71 was closed by its exchange-side algo SL on 2026-06-11 but its DB row is still `status='open'` — the reconciler must repair it automatically on first deployed cycle.
- Run tests with `python -m pytest` from the repo root (fast, ~1s; testnet tests auto-skip).

---

### Task 0: Branch

- [ ] **Step 0.1: Create the feature branch**

```bash
cd /home/dev/projects/trade-god
git checkout -b fix/swing-live-money-batch
```

---

### Task 1: Cancel algo orders too (`cancel_open_orders`)

The 2026-06-05 fix moved SL/TP *placement* to the Algo service but left *cancellation* on the legacy endpoint, which does not cover algo orders. Every bot-initiated close leaves the SL+TP pair armed with `closePosition="true"` — a stale trigger can market-close a future position.

**Files:**
- Modify: `app/swing/exchange.py:108-112` (`cancel_open_orders`)
- Modify: `tests/conftest.py` (FakeBinanceClient already records `_request_futures_api` calls — no change needed for this task)
- Test: `tests/swing/test_exchange_cancel.py` (create)

- [ ] **Step 1.1: Write the failing test**

Create `tests/swing/test_exchange_cancel.py`:

```python
"""Cancellation must clear BOTH order layers.

Legacy /fapi/v1/allOpenOrders does not cancel Algo-service conditional orders
(the same 2025-12-09 migration that caused -4120 on placement). A close that
only cancels the legacy layer leaves SL/TP triggers armed with
closePosition="true" — they can market-close a future position in the symbol.
"""

from __future__ import annotations

from app.swing import exchange


def test_cancel_open_orders_cancels_both_layers(fake_client) -> None:
    exchange.cancel_open_orders(fake_client, "IOTA")

    # Legacy layer (regular orders)
    assert fake_client.cancelled == [{"symbol": "IOTAUSDT"}]

    # Algo layer (conditional SL/TP orders)
    deletes = [c for c in fake_client.algo_calls if c["method"] == "delete"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "algoOpenOrders"
    assert deletes[0]["signed"] is True
    assert deletes[0]["data"] == {"symbol": "IOTAUSDT"}


def test_cancel_algo_failure_does_not_raise(fake_client, monkeypatch) -> None:
    """A failed algo cancel must not abort the close path — log and continue."""
    from binance.exceptions import BinanceAPIException

    def _raise(*args, **kwargs):
        raise BinanceAPIException(object(), 400, '{"code":-1102,"msg":"bad"}')

    monkeypatch.setattr(fake_client, "_request_futures_api", _raise)
    exchange.cancel_open_orders(fake_client, "IOTA")  # must not raise
    assert fake_client.cancelled == [{"symbol": "IOTAUSDT"}]
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `python -m pytest tests/swing/test_exchange_cancel.py -v`
Expected: FAIL — `test_cancel_open_orders_cancels_both_layers` fails on `len(deletes) == 1` (no delete call is made by current code).

- [ ] **Step 1.3: Implement**

In `app/swing/exchange.py`, replace the current `cancel_open_orders` (lines 108–112):

```python
def cancel_open_orders(client: Client, coin: str):
    """Cancel BOTH order layers for a symbol.

    Regular orders live on /fapi/v1/allOpenOrders; conditional SL/TP orders
    live on the Algo service since 2025-12-09 and need their own cancel
    (DELETE /fapi/v1/algoOpenOrders) — the legacy call does not touch them.
    """
    symbol = f"{coin}USDT"
    try:
        client.futures_cancel_all_open_orders(symbol=symbol)
    except BinanceAPIException as e:
        log.warning("Could not cancel open orders for %s: %s", coin, e)
    try:
        client._request_futures_api("delete", "algoOpenOrders", True, data={"symbol": symbol})
    except BinanceAPIException as e:
        log.warning("Could not cancel algo orders for %s: %s", coin, e)
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `python -m pytest tests/swing/test_exchange_cancel.py tests/swing/test_exchange_sltp.py -v`
Expected: all PASS (the sltp tests guard against regressions in the shared fake).

- [ ] **Step 1.5: Commit**

```bash
git add app/swing/exchange.py tests/swing/test_exchange_cancel.py
git commit -m "fix(swing): cancel Algo-service conditional orders on close (placement was fixed 2026-06-05, cancellation was not)"
```

---

### Task 2: Account-fills accessor + fake-client support

**Files:**
- Modify: `app/swing/exchange.py` (add `get_recent_fills` after `get_open_positions`, line ~44)
- Modify: `tests/conftest.py` (extend `FakeBinanceClient`)
- Test: covered by Task 3's reconcile tests (the accessor is a one-line passthrough)

- [ ] **Step 2.1: Add the accessor to `app/swing/exchange.py`** (after `get_open_positions`):

```python
def get_recent_fills(client: Client, coin: str, start_ms: int) -> list[dict]:
    """Account trade fills for a symbol since ``start_ms`` (GET /fapi/v1/userTrades)."""
    return client.futures_account_trades(symbol=f"{coin}USDT", startTime=start_ms, limit=100)
```

- [ ] **Step 2.2: Extend `FakeBinanceClient` in `tests/conftest.py`**

Add to `__init__` (after `self.cancelled = ...`):

```python
        self.fills: list[dict] = []           # seed for futures_account_trades
        self.fills_requests: list[dict] = []  # records requests for assertions
```

Add a method in the "market data / account" section:

```python
    def futures_account_trades(self, **params):
        self.fills_requests.append(params)
        return list(self.fills)
```

- [ ] **Step 2.3: Run the full suite to confirm nothing broke**

Run: `python -m pytest -q`
Expected: 87 passed (85 existing + 2 from Task 1), 1 skipped.

- [ ] **Step 2.4: Commit**

```bash
git add app/swing/exchange.py tests/conftest.py
git commit -m "feat(swing): account-fills accessor for reconciliation + fake-client support"
```

---

### Task 3: DB helper — all open swing trades

**Files:**
- Modify: `app/db/models.py` (add after `get_open_swing_trade`, line ~235)

Note: DB helpers in this repo are not unit-tested directly (tests never connect to Postgres; the fake `DATABASE_URL` in conftest exists only so `create_engine` doesn't choke at import). The helper mirrors `get_open_swing_trade` exactly; reconcile tests monkeypatch it.

- [ ] **Step 3.1: Add the helper to `app/db/models.py`**:

```python
def get_all_open_swing_trades() -> list[SwingTrade]:
    with Session(engine) as session:
        return (
            session.query(SwingTrade)
            .filter(SwingTrade.status == "open")
            .order_by(SwingTrade.id.asc())
            .all()
        )
```

- [ ] **Step 3.2: Sanity-check import and commit**

Run: `python -c "from app import db; print(callable(db.get_all_open_swing_trades))"`
Expected: `True`
(If `app/db/__init__.py` re-exports names explicitly rather than `from .models import *`, add `get_all_open_swing_trades` to that re-export — check with `grep -n "import" app/db/__init__.py`.)

```bash
git add app/db/models.py
git commit -m "feat(db): get_all_open_swing_trades helper for reconciliation"
```

---

### Task 4: Reconciliation module

The core fix. When an exchange-side algo SL/TP fires between cycles, the bot currently never notices: the DB row stays `open`, no Telegram is sent, and the loss cooldown (which filters `status='closed'`) is bypassed.

**Files:**
- Create: `app/swing/reconcile.py`
- Test: `tests/swing/test_reconcile.py` (create)

- [ ] **Step 4.1: Write the failing tests**

Create `tests/swing/test_reconcile.py`:

```python
"""Tests for app.swing.reconcile — closing stale DB rows after exchange-side fills.

The live incident this pins: DOGE id=71's algo SL fired 2026-06-11 ~17:45 UTC;
the position vanished between hourly cycles and the DB row stayed status='open'
with no alert and no cooldown. reconcile() must detect DB-open/exchange-absent
trades, backfill the close from account fills, alert, and mark them closed so
the loss cooldown can see them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.swing import reconcile


def _row(**kw):
    """A SwingTrade-shaped stand-in (only the fields reconcile reads)."""
    defaults = dict(
        id=71,
        coin="DOGE",
        direction="short",
        entry_price=0.0834,
        qty=499.0,
        notional_usdt=41.62,
        entry_time="2026-06-10T08:54:16+00:00",
        status="open",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


@pytest.fixture
def capture(monkeypatch):
    """Patch db + notifier seams; return the capture dict."""
    cap = {"closes": [], "alerts": [], "rows": []}
    monkeypatch.setattr(reconcile.db, "get_all_open_swing_trades", lambda: cap["rows"])
    monkeypatch.setattr(
        reconcile.db, "log_swing_close", lambda **kw: cap["closes"].append(kw)
    )
    monkeypatch.setattr(
        reconcile.notifier, "notify_close",
        lambda coin, pos, pnl, reason: cap["alerts"].append((coin, pnl, reason)),
    )
    return cap


def test_stale_row_closed_from_fills(fake_client, capture) -> None:
    capture["rows"] = [_row()]
    # Position absent from exchange; the short was closed by two BUY fills.
    fake_client.fills = [
        {"side": "SELL", "price": "0.0834", "qty": "499", "realizedPnl": "0", "time": 1781100856000},
        {"side": "BUY", "price": "0.0863", "qty": "300", "realizedPnl": "-0.87", "time": 1781199900000},
        {"side": "BUY", "price": "0.0863", "qty": "199", "realizedPnl": "-0.58", "time": 1781199901000},
    ]

    results = reconcile.reconcile(fake_client, positions={})

    assert len(capture["closes"]) == 1
    close = capture["closes"][0]
    assert close["trade_id"] == 71
    assert close["exit_price"] == pytest.approx(0.0863)
    assert close["realized_pnl_usd"] == pytest.approx(-1.45)
    assert close["realized_pnl_pct"] == pytest.approx(-1.45 / 41.62)
    assert "SL" in close["exit_reason"] and "reconciled" in close["exit_reason"]
    assert capture["alerts"] and capture["alerts"][0][0] == "DOGE"
    assert results[0]["coin"] == "DOGE"
    # Fills were requested from the trade's entry time onward
    assert fake_client.fills_requests[0]["symbol"] == "DOGEUSDT"
    assert fake_client.fills_requests[0]["startTime"] == 1781081656000  # 2026-06-10T08:54:16Z in ms


def test_winning_fill_labelled_tp(fake_client, capture) -> None:
    capture["rows"] = [_row()]
    fake_client.fills = [
        {"side": "BUY", "price": "0.0776", "qty": "499", "realizedPnl": "2.89", "time": 1781199900000},
    ]

    reconcile.reconcile(fake_client, positions={})

    assert "TP" in capture["closes"][0]["exit_reason"]


def test_open_position_left_alone(fake_client, capture) -> None:
    capture["rows"] = [_row(coin="BSV")]
    results = reconcile.reconcile(fake_client, positions={"BSV": {"side": "short"}})
    assert capture["closes"] == [] and capture["alerts"] == [] and results == []


def test_no_fills_falls_back_to_current_price(fake_client, capture) -> None:
    capture["rows"] = [_row()]
    fake_client.fills = []
    fake_client.price = 0.0850

    reconcile.reconcile(fake_client, positions={})

    close = capture["closes"][0]
    assert close["exit_price"] == pytest.approx(0.0850)
    # short from 0.0834 to 0.0850 = a loss of (0.0834-0.0850)*499
    assert close["realized_pnl_usd"] == pytest.approx((0.0834 - 0.0850) * 499)
    assert "no fills" in close["exit_reason"]


def test_per_row_errors_isolated(fake_client, capture, monkeypatch) -> None:
    """One bad row must not stop the others from reconciling."""
    capture["rows"] = [_row(id=1, coin="AAA", entry_time="not-a-timestamp"), _row(id=2)]
    fake_client.fills = [
        {"side": "BUY", "price": "0.0863", "qty": "499", "realizedPnl": "-1.45", "time": 1781199900000},
    ]

    results = reconcile.reconcile(fake_client, positions={})

    assert [c["trade_id"] for c in capture["closes"]] == [2]
    assert len(results) == 1
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `python -m pytest tests/swing/test_reconcile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.swing.reconcile'`

- [ ] **Step 4.3: Implement `app/swing/reconcile.py`**

```python
"""Reconcile DB open swing trades against live exchange positions.

When an exchange-side algo SL/TP fires between cycles, the bot never performs
the close itself: the next cycle just sees the position gone. Without this
module the swing_trades row stays 'open' forever, no Telegram alert is sent,
and the loss cooldown — which only looks at status='closed' rows — is silently
bypassed (live incident: DOGE id=71, 2026-06-11).

Called once per cycle, right after positions are fetched.
"""

import logging
from datetime import datetime, timezone

from app import db
from app.swing import notifier
from app.swing.exchange import get_price, get_recent_fills

log = logging.getLogger(__name__)


def _entry_ms(entry_time: str) -> int:
    dt = datetime.fromisoformat(entry_time)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _close_from_fills(row, fills: list[dict]) -> tuple[float, float, str] | None:
    """(exit_price, pnl_usd, reason) from closing-side fills, or None if absent."""
    closing_side = "SELL" if row.direction == "long" else "BUY"
    closing = [f for f in fills if f["side"] == closing_side]
    if not closing:
        return None
    qty_total = sum(float(f["qty"]) for f in closing)
    if qty_total <= 0:
        return None
    exit_price = sum(float(f["price"]) * float(f["qty"]) for f in closing) / qty_total
    pnl = sum(float(f["realizedPnl"]) for f in closing)
    label = "SL" if pnl < 0 else "TP"
    return exit_price, pnl, f"exchange-side {label} fill (reconciled)"


def reconcile(client, positions: dict) -> list[dict]:
    """Close DB rows whose position no longer exists on the exchange.

    Returns one dict per reconciled trade (coin, pnl, reason) for cycle logging.
    Per-row failures are logged and skipped so one bad row can't block the rest.
    """
    results: list[dict] = []
    for row in db.get_all_open_swing_trades():
        if row.coin in positions:
            continue
        try:
            fills = get_recent_fills(client, row.coin, _entry_ms(row.entry_time))
            closed = _close_from_fills(row, fills)
            if closed is None:
                # Fills unavailable (pruned history / data gap): close at the
                # current price so the row can't stay stale forever, but say so.
                exit_price = get_price(client, row.coin)
                if row.direction == "long":
                    pnl = (exit_price - row.entry_price) * row.qty
                else:
                    pnl = (row.entry_price - exit_price) * row.qty
                reason = "reconciled (no fills found)"
            else:
                exit_price, pnl, reason = closed
            pnl_pct = pnl / row.notional_usdt if row.notional_usdt else 0.0
            db.log_swing_close(
                trade_id=row.id,
                exit_price=exit_price,
                realized_pnl_usd=pnl,
                realized_pnl_pct=pnl_pct,
                exit_reason=reason,
            )
            notifier.notify_close(row.coin, {"entry": row.entry_price}, pnl, reason)
            results.append({"coin": row.coin, "pnl": pnl, "reason": reason})
        except Exception as e:
            log.error("Reconcile failed for %s (id=%s): %s", row.coin, row.id, e)
    return results
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `python -m pytest tests/swing/test_reconcile.py -v`
Expected: 5 PASS. If the `startTime` assertion fails, check the ms math, not the test: `datetime.fromisoformat("2026-06-10T08:54:16+00:00").timestamp() * 1000 == 1781081656000`.

- [ ] **Step 4.5: Commit**

```bash
git add app/swing/reconcile.py tests/swing/test_reconcile.py
git commit -m "feat(swing): reconcile exchange-side fills into DB closes (fixes silent stop-outs, restores loss cooldown)"
```

---

### Task 5: Wire reconciliation into the main loop

**Files:**
- Modify: `app/swing/main.py:8-13` (imports) and `:107-108` (cycle start)

- [ ] **Step 5.1: Add the import**

In `app/swing/main.py`, change line 9 from:

```python
from app.swing import config, agent, notifier, shadow, snapshot
```

to:

```python
from app.swing import config, agent, notifier, reconcile, shadow, snapshot
```

- [ ] **Step 5.2: Call it at cycle start**

After `log.info("Open positions: %s", ...)` (line 108), insert:

```python
            for rec in reconcile.reconcile(client, positions):
                log.info("RECONCILED %s — %s pnl=%.4f", rec["coin"], rec["reason"], rec["pnl"])
```

(No extra try/except: `reconcile()` already isolates per-row errors, and a total failure of `db.get_all_open_swing_trades()` is caught by the loop's outer handler, same as any other cycle error.)

- [ ] **Step 5.3: Run the full suite**

Run: `python -m pytest -q`
Expected: 92 passed, 1 skipped. Also: `python -c "import app.swing.main"` → no import errors.

- [ ] **Step 5.4: Commit**

```bash
git add app/swing/main.py
git commit -m "feat(swing): run fill reconciliation each cycle (repairs DOGE id=71 on first deploy)"
```

---

### Task 6: Safety net uses per-trade stops

The hourly client-side net currently compares against flat `DEFAULT_SL_PCT=3%` / `DEFAULT_TP_PCT=8%`, which is tighter than every recent ATR-sized stop (3.45–6.82%) — so the carefully sized exchange stop never fires and the de-facto risk model is "3%, checked hourly". The net must use the trade's own stored `entry_sl_pct`/`entry_tp_pct`, with the defaults only as fallback.

**Files:**
- Modify: `app/swing/main.py` (add `_net_thresholds` helper after `_safety_net_label`, line ~89; rewire lines 111–137)
- Test: `tests/swing/test_safety_net_thresholds.py` (create)

- [ ] **Step 6.1: Write the failing test**

Create `tests/swing/test_safety_net_thresholds.py`:

```python
"""The client-side net must back up the trade's OWN ATR-sized stops, not
override them with the flat defaults (live incident: IOTA's 4.69% stop was
preempted by the 3% default at 3.77% on 2026-06-12)."""

from __future__ import annotations

from types import SimpleNamespace

from app.swing import config
from app.swing.main import _net_thresholds


def test_uses_trade_row_stops() -> None:
    row = SimpleNamespace(entry_sl_pct=0.0469, entry_tp_pct=0.0938)
    assert _net_thresholds(row) == (0.0469, 0.0938)


def test_falls_back_to_defaults_when_no_row() -> None:
    assert _net_thresholds(None) == (config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT)


def test_falls_back_per_field_when_zero_or_none() -> None:
    row = SimpleNamespace(entry_sl_pct=0.0, entry_tp_pct=None)
    assert _net_thresholds(row) == (config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT)
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `python -m pytest tests/swing/test_safety_net_thresholds.py -v`
Expected: FAIL with `ImportError: cannot import name '_net_thresholds'`

- [ ] **Step 6.3: Implement**

In `app/swing/main.py`, add after `_safety_net_label` (after line 88):

```python
def _net_thresholds(db_trade) -> tuple[float, float]:
    """Per-trade SL/TP for the client-side net, falling back to the defaults.

    The net exists to back up the exchange-side ATR-sized stops, so it must use
    the same percentages — a flat default tighter than the ATR stop would
    preempt the exchange order and become the de-facto (wrong) stop.
    """
    sl = getattr(db_trade, "entry_sl_pct", None) or config.DEFAULT_SL_PCT
    tp = getattr(db_trade, "entry_tp_pct", None) or config.DEFAULT_TP_PCT
    return sl, tp
```

Then rewire the safety-net block. Replace lines 111–137 (the `for coin, pos in list(positions.items()):` block) so the DB row is fetched once and feeds both the thresholds and the close logging:

```python
            for coin, pos in list(positions.items()):
                if coin not in config.COINS:
                    continue
                price_now = get_price(client, coin)
                chg = (price_now - pos["entry"]) / pos["entry"]
                db_trade = db.get_open_swing_trade(coin)
                sl_pct, tp_pct = _net_thresholds(db_trade)
                label = _safety_net_label(
                    pos["side"], pos["entry"], price_now, sl_pct, tp_pct,
                )
                if label:
                    exit_reason = f"client-side {label} ({chg*100:+.1f}%)"
                    log.info("CLIENT %s %s chg=%.2f%%", label, coin, chg * 100)
                    cancel_open_orders(client, coin)
                    close_order = close_position(client, coin, positions)
                    exit_price = _extract_exit_price(close_order, price_now)
                    pnl, pnl_pct = _calc_realized_pnl(pos, exit_price)
                    log.info("NOTIFY client-%s %s pnl=%.4f", label, coin, pnl)
                    notifier.notify_close(coin, pos, pnl, exit_reason)
                    if db_trade:
                        db.log_swing_close(
                            trade_id=db_trade.id,
                            exit_price=exit_price,
                            realized_pnl_usd=pnl,
                            realized_pnl_pct=pnl_pct,
                            exit_reason=exit_reason,
                        )
                    positions = get_open_positions(client)
```

(The only changes vs the current block: `db_trade` is fetched before the check instead of after, and `_net_thresholds(db_trade)` replaces `config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT`.)

- [ ] **Step 6.4: Run tests**

Run: `python -m pytest tests/swing/test_safety_net_thresholds.py -v && python -m pytest -q`
Expected: 3 new PASS; full suite green (95 passed, 1 skipped).

- [ ] **Step 6.5: Commit**

```bash
git add app/swing/main.py tests/swing/test_safety_net_thresholds.py
git commit -m "fix(swing): client safety net backs up per-trade ATR stops instead of overriding them with flat 3%/8%"
```

---

### Task 7: Closed-candle indicators, full RSI warmup, converged daily EMA200

Binance includes the still-forming candle as the last kline; every indicator currently reads it, so signals repaint intra-bar and `vol_ratio` compares a partial candle against 20 full ones. Additionally RSI warms up on only 30 bars (1–3 pt error vs converged Wilder RSI, with hard gates at exactly 32/68) and `ema200_daily` is seeded ~11% on a 220-day-old price.

**Files:**
- Modify: `app/swing/indicators.py` (add `_drop_unclosed`; modify `get_indicators` lines 177, 186, 205)
- Test: `tests/swing/test_indicators_closed_candle.py` (create)

- [ ] **Step 7.1: Write the failing tests**

Create `tests/swing/test_indicators_closed_candle.py`:

```python
"""Indicators must be computed on CLOSED candles only.

Binance returns the still-forming candle as the last kline. Using it makes
every signal repaint intra-bar and structurally deflates vol_ratio (a partial
candle's volume vs 20 full ones). get_indicators must drop it.
"""

from __future__ import annotations

import time

from app.swing.indicators import _drop_unclosed, calc_rsi, get_indicators


def _kline(open_time_ms: int, close: float, vol: float, close_time_ms: int) -> list:
    # Binance kline: [open_time, open, high, low, close, volume, close_time, ...]
    return [open_time_ms, close, close * 1.01, close * 0.99, close, vol, close_time_ms, 0, 0, 0, 0, 0]


def _series(n: int, *, last_unclosed: bool, interval_ms: int = 4 * 3600 * 1000) -> list:
    now_ms = int(time.time() * 1000)
    out = []
    for i in range(n):
        open_t = now_ms - (n - i) * interval_ms
        close_t = open_t + interval_ms - 1
        out.append(_kline(open_t, 100.0 + i * 0.1, 1000.0, close_t))
    if last_unclosed:
        out[-1][6] = now_ms + interval_ms  # close_time in the future = forming
    return out


def test_drop_unclosed_removes_forming_candle() -> None:
    kl = _series(50, last_unclosed=True)
    assert len(_drop_unclosed(kl)) == 49


def test_drop_unclosed_keeps_closed_series_intact() -> None:
    kl = _series(50, last_unclosed=False)
    assert len(_drop_unclosed(kl)) == 50


def test_drop_unclosed_empty() -> None:
    assert _drop_unclosed([]) == []


class _KlineClient:
    """Fake client for get_indicators: serves controlled klines, benign rest."""

    KLINE_INTERVAL_4HOUR = "4h"
    KLINE_INTERVAL_1DAY = "1d"

    def __init__(self) -> None:
        self.kl4 = _series(200, last_unclosed=True)
        self.kl1d = _series(601, last_unclosed=True, interval_ms=24 * 3600 * 1000)
        self.requested_limits: dict[str, int] = {}

    def futures_klines(self, *, symbol, interval, limit):
        self.requested_limits[interval] = limit
        return list(self.kl4 if interval == "4h" else self.kl1d)

    def futures_open_interest_hist(self, **kw):
        return []

    def futures_global_longshort_ratio(self, **kw):
        return []

    def _request_futures_data_api(self, *a, **kw):
        return []


def test_get_indicators_uses_closed_candles_and_full_rsi_warmup() -> None:
    client = _KlineClient()
    ind = get_indicators(client, "DOGE")

    closed_closes = [float(k[4]) for k in client.kl4[:-1]]
    # price = last CLOSED close, not the forming candle
    assert ind["price"] == closed_closes[-1]
    # RSI computed over the full closed series, not a 30-bar tail
    assert ind["rsi14_4h"] == calc_rsi(closed_closes, 14)
    assert ind["rsi14_4h"] != calc_rsi(closed_closes[-30:], 14) or len(closed_closes) <= 30
    # daily fetch is deep enough for a converged EMA200 after dropping the forming bar
    assert client.requested_limits["1d"] >= 601
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `python -m pytest tests/swing/test_indicators_closed_candle.py -v`
Expected: FAIL with `ImportError: cannot import name '_drop_unclosed'`

- [ ] **Step 7.3: Implement in `app/swing/indicators.py`**

Add near the top of the file (after the imports — check `import time` is present; add it if not):

```python
def _drop_unclosed(klines: list, now_ms: int | None = None) -> list:
    """Drop the still-forming last candle (close_time in the future).

    Binance always includes the current candle; every indicator here must see
    closed bars only, or signals repaint intra-bar and vol_ratio compares a
    partial candle against full ones.
    """
    if not klines:
        return klines
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if int(klines[-1][6]) > now_ms:
        return klines[:-1]
    return klines
```

In `get_indicators`:

Line 177, wrap the 4h fetch:

```python
    klines_4h = _drop_unclosed(
        client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_4HOUR, limit=200)
    )
```

Line 186, full RSI warmup:

```python
    rsi14 = calc_rsi(closes_4h, 14)
```

Line 205, deeper daily fetch + drop forming bar:

```python
    klines_1d = _drop_unclosed(
        client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1DAY, limit=601)
    )
```

- [ ] **Step 7.4: Run the new tests and the full suite**

Run: `python -m pytest tests/swing/test_indicators_closed_candle.py -v && python -m pytest -q`
Expected: new tests PASS; full suite green (99 passed, 1 skipped). If an existing indicator golden test fails, it is asserting on the OLD 30-bar RSI value through `get_indicators` — update that test's expectation to `calc_rsi(full_closed_series, 14)`; do NOT revert the warmup. (Golden tests that call `calc_rsi` directly are unaffected.)

- [ ] **Step 7.5: Commit**

```bash
git add app/swing/indicators.py tests/swing/test_indicators_closed_candle.py
git commit -m "fix(swing): compute indicators on closed candles only; full RSI warmup; converged daily EMA200"
```

---

### Task 8: Orphan algo-order cleanup script (one-off operational tool)

IOTA was client-side closed on 2026-06-12 with the old cancel code — its SL @ 0.0472 / TP @ 0.0409 algo orders are likely still armed (price is ~1.7% below that stale SL trigger). DOGE's TP twin may also linger. This script lists and cancels algo orders on symbols with no open position.

**Files:**
- Create: `scripts/cleanup_orphan_algo_orders.py`

- [ ] **Step 8.1: Write the script**

```python
"""One-off: list/cancel orphaned Algo-service conditional orders.

An algo SL/TP with closePosition="true" left armed after its position is gone
will market-close any FUTURE position in that symbol when the stale trigger
hits. Dry-run by default; pass --execute to actually cancel.

Usage (needs BINANCE_API_KEY_FUTURES / BINANCE_SECRET_KEY_FUTURES in env or .env):
    python scripts/cleanup_orphan_algo_orders.py            # report only
    python scripts/cleanup_orphan_algo_orders.py --execute  # cancel orphans
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from binance.client import Client  # noqa: E402

from app.swing import config  # noqa: E402
from app.swing.exchange import get_open_positions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="actually cancel (default: dry run)")
    args = parser.parse_args()

    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
    positions = get_open_positions(client)
    print(f"Open positions: {sorted(positions) or 'none'}")

    resp = client._request_futures_api("get", "openAlgoOrders", True, data={})
    orders = resp.get("orders", resp) if isinstance(resp, dict) else resp
    if not orders:
        print("No open algo orders. Nothing to do.")
        return

    orphans: dict[str, list] = {}
    for o in orders:
        coin = o["symbol"][:-4] if o["symbol"].endswith("USDT") else o["symbol"]
        status = "HELD" if coin in positions else "ORPHAN"
        print(f"[{status}] {o['symbol']} {o.get('orderType', o.get('type'))} "
              f"trigger={o.get('triggerPrice')} algoId={o.get('algoId')}")
        if status == "ORPHAN":
            orphans.setdefault(o["symbol"], []).append(o)

    if not orphans:
        print("No orphans found.")
        return
    if not args.execute:
        print(f"\nDRY RUN — would cancel all algo orders on: {sorted(orphans)}. Re-run with --execute.")
        return
    for symbol in sorted(orphans):
        client._request_futures_api("delete", "algoOpenOrders", True, data={"symbol": symbol})
        print(f"Cancelled all algo orders on {symbol}")


if __name__ == "__main__":
    main()
```

Note: `python-dotenv` — check it is in `requirements.txt` (`grep dotenv requirements.txt`); `main.py`/`api_main.py` already use `load_dotenv`, so it should be. If the GET response shape differs in practice (dict vs list), the `resp.get("orders", resp)` normalization covers both documented variants.

- [ ] **Step 8.2: Dry-run against production**

Run (from the repo root, with the prod futures keys in `.env`):
`python scripts/cleanup_orphan_algo_orders.py`
Expected: a listing that shows whether IOTAUSDT / DOGEUSDT algo orders are still armed. **Paste the output into the session before proceeding** — this answers the open question from the 2026-06-12 analysis.

- [ ] **Step 8.3: Execute if orphans exist**

Run: `python scripts/cleanup_orphan_algo_orders.py --execute`
Then re-run the dry-run to confirm zero orphans remain.

- [ ] **Step 8.4: Commit**

```bash
git add scripts/cleanup_orphan_algo_orders.py
git commit -m "chore(swing): orphan algo-order cleanup script (dry-run by default)"
```

---

### Task 9: Full verification, merge, deploy

- [ ] **Step 9.1: Full suite + import smoke**

```bash
python -m pytest -q
python -c "import app.swing.main, app.swing.reconcile, app.swing.indicators, app.swing.exchange"
```

Expected: ~99 passed, 1 skipped; no import errors.

- [ ] **Step 9.2: Merge to main**

```bash
git checkout main && git merge --no-ff fix/swing-live-money-batch -m "fix(swing): live-money batch — fill reconciliation, per-trade safety net, algo cancel, closed-candle indicators"
```

- [ ] **Step 9.3: Deploy to Lightsail**

```bash
ssh -i LightsailDefaultKey-ap-southeast-1.pem ubuntu@54.169.100.56 \
  "cd trade-god && git pull && docker compose up -d --build swing"
```

(Adjust the remote repo dir if different — `scripts/export_swing_logs.sh` uses `REMOTE_DIR`; check its default.)

- [ ] **Step 9.4: Verify the first live cycle**

```bash
ssh -i LightsailDefaultKey-ap-southeast-1.pem ubuntu@54.169.100.56 \
  "cd trade-god && docker compose logs --since 15m swing"
```

Expected within the first cycle:
1. `RECONCILED DOGE — exchange-side SL fill (reconciled) pnl=-1.4...` (repairs id=71) + a Telegram close alert.
2. No `Error processing` / `Main loop error` lines.
3. On the next bot-initiated close (whenever it happens): no warnings from the algo-cancel call.

Then confirm in the DB (id=71 closed, exit fields populated):

```bash
docker run --rm postgres:16-alpine psql "postgresql://tradegod:tradegod@54.169.100.56:5432/tradegod" \
  -c "SELECT id, coin, status, exit_price, realized_pnl_usd, exit_reason FROM swing_trades WHERE id IN (71, 72);"
```

Expected: id=71 `closed` with a negative `realized_pnl_usd` (~-1.45) and reason `exchange-side SL fill (reconciled)`; id=72 (BSV) still `open` only if the position is still live on the exchange.

- [ ] **Step 9.5: Update CLAUDE.md known-issues section**

Add under "Known Issues & Fixes" in `CLAUDE.md`:

```markdown
### Fixed (2026-06-12): silent exchange-side fills + safety-net override + algo cancel + forming-candle indicators
- `app/swing/reconcile.py` diffs DB open rows vs exchange positions each cycle; backfills closes
  from `futures_account_trades` (exit price = fill VWAP, PnL = summed realizedPnl), alerts, and
  feeds the loss cooldown. Repaired DOGE id=71 (silent algo-SL fill 2026-06-11).
- Client safety net now uses per-trade `entry_sl_pct`/`entry_tp_pct` (fallback: DEFAULT_*).
- `cancel_open_orders` also DELETEs `/fapi/v1/algoOpenOrders` (placement was fixed 2026-06-05;
  cancellation wasn't — stale closePosition triggers could close future positions).
- Indicators drop the still-forming last kline (4h + 1d), RSI warms up on the full 200-bar
  series, daily fetch deepened to 601 for a converged EMA200.
```

```bash
git add CLAUDE.md && git commit -m "docs: record 2026-06-12 live-money fixes in CLAUDE.md"
git push
```

---

## Self-review notes (already applied)

- **Spec coverage:** Phase A items 1–4 map to Tasks 4–5 (reconciliation), 6 (safety net), 1+8 (algo cancel + orphan cleanup), 7 (closed candles). DOGE id=71 repair is automated via Task 4/5 and verified in 9.4.
- **Type consistency:** `reconcile.reconcile(client, positions) -> list[dict]` matches the Task 5 call site; `_net_thresholds(db_trade) -> tuple[float, float]` matches Task 6's call; `_drop_unclosed(klines, now_ms=None)` matches Task 7's tests.
- **Endpoint verification:** `GET /fapi/v1/openAlgoOrders` and `DELETE /fapi/v1/algoOpenOrders` confirmed against the Binance USDS-M docs on 2026-06-12. `futures_account_trades` is python-binance's wrapper for `GET /fapi/v1/userTrades`; if it's absent in 1.0.19, substitute `client._request_futures_api("get", "userTrades", True, data={"symbol": ..., "startTime": ..., "limit": 100})` in `get_recent_fills` — the tests only exercise the fake.
- **Test-count expectations** (87/92/95/99) assume the current 85+1; if the baseline differs, the deltas (+2, +5, +3, +4) are what matter.
