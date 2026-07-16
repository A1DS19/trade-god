# Intraday Paper-First Engine (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `app/intraday/` — a keyless paper-trading engine running the frozen mr_vwap maker variant with full fill telemetry — and retire both legacy bots, per spec `docs/superpowers/specs/2026-07-15-intraday-engine-design.md`.

**Architecture:** The pure strategy core (z-score + batch weights builder) re-homes from `research/` into `app/intraday/strategy.py`; research imports it back (research → app, never the reverse). The live twin of the batch builder is `PaperBook` — an incremental state machine whose transition rules are mapped 1:1 to `build_weights` semantics and pinned by a replay-parity test. Everything persists to Postgres each cycle (restart-safe); Telegram carries events, daily summaries, and weekly fill-telemetry reports.

**Tech Stack:** Python 3.12, pandas (joins prod requirements), python-binance unsigned market-data client (NO API keys in paper mode), SQLAlchemy + Alembic (migration 006), docker compose on the Lightsail box, pytest.

## Global Constraints

- **Frozen strategy params (never searched):** `Z_ENTRY = -3.0`, z window 96 bars (24h of 15m), `HORIZON_BARS = 32`, `MAX_K = 10`, maker-limit fill = STRICT trade-through (`bar_low < limit`); costs 2bps entry / 8bps exit of slot notional; real funding applied (long pays positive rates).
- **Paper mode is keyless:** no `BINANCE_API_KEY*` needed or read by `app/intraday/`; all endpoints unsigned. `EXECUTION_MODE=live` raises `NotImplementedError` in this phase.
- **Paper equity $100, K=10 slots of $10** (`slot_usd = PAPER_EQUITY / MAX_K`).
- **Kill-switches armed in paper:** daily paper loss > 5% of paper equity or drawdown > 20% from peak → halt new entries + Telegram page; halt persists in DB; resume only via `INTRADAY_RESUME=1` at startup (clears once, alerts).
- **Error isolation:** one symbol's exception never kills a cycle; 3 consecutive failures on a symbol → Telegram alert.
- **Universe:** top-30 by 30-day median daily quote volume among the top-100 USDT perps by 24h volume; refreshed weekly; dropped symbols take no new entries, open positions run to exit.
- **Import direction:** `research/` may import `app/`; `app/` must never import `research/`.
- **Telegram discipline:** all dynamic text through `html.escape()` (parse_mode=HTML).
- Run `python -m pytest` before every commit. Until Task 7 the only allowed failure is the known pre-existing `tests/swing/test_reconcile.py::test_stale_row_closed_from_fills`; after Task 7 (legacy tests moved) the suite must be fully green.
- Commits go directly to `main`. Don't add comments/docstrings/type annotations to code you didn't change.
- Task 8 (deploy) touches the production box — it requires the user's explicit go-ahead before executing.

---

### Task 1: Re-home the strategy core into `app/intraday/strategy.py`

**Files:**
- Create: `app/intraday/__init__.py` (empty), `app/intraday/strategy.py`
- Modify: `research/signals/intraday/families.py` (mr_vwap_z delegates), `research/signals/intraday/mr_vwap_strategy.py` (re-export), `requirements.txt` (pandas)
- Test: `tests/intraday/test_strategy_core.py` (create; also create empty `tests/intraday/` dir)

**Interfaces:**
- Produces: `app.intraday.strategy.Z_ENTRY = -3.0`, `Z_RECOVER = -1.0`, `Z_WINDOW = 96`, `zscore(close, volume, quote_volume, window=Z_WINDOW) -> pd.DataFrame` (panels in/out), and `build_weights(z, close, low, elig, params, fill) -> pd.DataFrame` — moved VERBATIM from `research/signals/intraday/mr_vwap_strategy.py:46-96` (the loop body must not change by one character; it is pre-registered, review-verified code). Existing research tests become the regression pins via re-export.

- [ ] **Step 1: Write the failing test**

Create `tests/intraday/test_strategy_core.py`:

```python
"""The re-homed strategy core: z math identical to research, constants pinned,
research modules re-export from app (import direction: research -> app)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.intraday import strategy

BAR_MS = 900_000


def _panels(n=300, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.Index(np.arange(n) * BAR_MS, name="open_time")
    close = pd.DataFrame({"AAAUSDT": 100.0 + rng.normal(0, 0.05, n)}, index=idx)
    volume = pd.DataFrame({"AAAUSDT": np.full(n, 10.0)}, index=idx)
    qv = close * volume
    return close, volume, qv


def test_constants_frozen():
    assert strategy.Z_ENTRY == -3.0
    assert strategy.Z_RECOVER == -1.0
    assert strategy.Z_WINDOW == 96


def test_zscore_matches_research_mr_vwap_z():
    close, volume, qv = _panels()
    z_app = strategy.zscore(close, volume, qv)

    n = len(close)
    df = pd.DataFrame({
        "symbol": "AAAUSDT", "open_time": np.arange(n) * BAR_MS,
        "open": close["AAAUSDT"].to_numpy(), "high": close["AAAUSDT"].to_numpy(),
        "low": close["AAAUSDT"].to_numpy(), "close": close["AAAUSDT"].to_numpy(),
        "volume": 10.0, "quote_volume": (close["AAAUSDT"] * 10.0).to_numpy(),
        "taker_buy_volume": 5.0, "trades": 1,
    })
    from research.signals.intraday.families import mr_vwap_z
    z_research = mr_vwap_z({"klines_15m": df})
    pd.testing.assert_frame_equal(z_app, z_research, check_dtype=False)


def test_research_reexports_are_the_same_objects():
    from research.signals.intraday import mr_vwap_strategy as rs
    assert rs.build_weights is strategy.build_weights
    assert rs.Z_ENTRY is strategy.Z_ENTRY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/intraday/test_strategy_core.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'app.intraday'`.

- [ ] **Step 3: Implement**

Create `app/intraday/strategy.py`. The module docstring, `Z_ENTRY`/`Z_RECOVER` constants, and the ENTIRE `build_weights` function move verbatim from `research/signals/intraday/mr_vwap_strategy.py` (copy lines 1–21 and 46–96 exactly, dropping the `from research import config` import and the `pit_top30_mask` function, which stays research-side). Add the z math as a new pure function:

```python
Z_WINDOW = 96   # 24h of 15m bars — the pre-registered mr_vwap window


def zscore(close: pd.DataFrame, volume: pd.DataFrame, quote_volume: pd.DataFrame,
           window: int = Z_WINDOW) -> pd.DataFrame:
    vsum = volume.rolling(window, min_periods=window).sum()
    vwap = quote_volume.rolling(window, min_periods=window).sum() / vsum.where(vsum > 0)
    sd = close.rolling(window, min_periods=window).std()
    return (close - vwap) / sd.where(sd > 0)
```

Modify `research/signals/intraday/families.py` — `mr_vwap_z` delegates (bucket edges/labels in `mr_vwap_buckets` unchanged):

```python
def mr_vwap_z(data: dict) -> pd.DataFrame:
    from app.intraday.strategy import zscore
    close = _close(data)
    v = sdata.to_panel(data["klines_15m"], "volume")
    qv = sdata.to_panel(data["klines_15m"], "quote_volume")
    return zscore(close, v, qv)
```

Modify `research/signals/intraday/mr_vwap_strategy.py` — delete the moved code and re-export (keep `pit_top30_mask`, its imports, and `PIT_TOP_N`/`PIT_WINDOW_DAYS` exactly as they are):

```python
from app.intraday.strategy import Z_ENTRY, Z_RECOVER, build_weights  # noqa: F401
```

Add `pandas==2.2.3` to `requirements.txt` (alongside the existing pins; this is the version already installed in the dev venv — verify with `python -c "import pandas; print(pandas.__version__)"` and pin whatever it prints).

- [ ] **Step 4: Run tests to verify they pass — including every existing research pin**

Run: `python -m pytest tests/intraday/ tests/research/test_mr_vwap_strategy.py tests/research/test_intraday_families.py tests/research/test_mr_vwap_train.py -v`
Expected: all pass — the 2b strategy/families/train tests are the proof the re-home changed nothing.

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add app/intraday/ research/signals/intraday/families.py research/signals/intraday/mr_vwap_strategy.py requirements.txt tests/intraday/
git commit -m "feat(intraday): re-home strategy core to app/ — research imports it back"
```

---

### Task 2: DB models + migration 006 + state helpers

**Files:**
- Modify: `app/db/models.py` (three models + helpers, appended)
- Create: `alembic/versions/006_add_intraday_tables.py`
- Test: `tests/intraday/test_db_models.py` (create)

**Interfaces:**
- Produces: models `IntradayTrade` (table `intraday_trades`: id, symbol String(20), direction String(5) default "long", mode String(5), limit_price Float, entry_price Float, exit_price Float nullable, slot_usd Float, entry_time String(50), exit_time String(50) nullable, hold_bars Integer nullable, pnl_pct Float nullable, pnl_usd Float nullable, fill_type String(15), exit_reason String(30) nullable, status String(6) default "open"), `IntradayLimit` (table `intraday_limits`: id, symbol String(20), limit_price Float, placed_at String(50), resolved_at String(50) nullable, outcome String(15) nullable, bar_low Float nullable, admitted Boolean nullable), `IntradayState` (table `intraday_state`: key String(40) PK, value JSON, updated String(50)). Helpers: `intraday_state_get(key: str) -> dict | None`, `intraday_state_set(key: str, value: dict)`, `log_intraday_trade(**fields) -> int`, `close_intraday_trade(trade_id, exit_price, exit_time, hold_bars, pnl_pct, pnl_usd, exit_reason)`, `log_intraday_limit(**fields)`. All later tasks call exactly these.

- [ ] **Step 1: Write the failing test**

Create `tests/intraday/test_db_models.py`:

```python
"""Intraday persistence helpers against an in-memory SQLite engine."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.db import models


@pytest.fixture
def mem_db(monkeypatch):
    eng = create_engine("sqlite://")
    monkeypatch.setattr(models, "engine", eng)
    models.Base.metadata.create_all(eng)
    return eng


def test_state_roundtrip_and_overwrite(mem_db):
    assert models.intraday_state_get("paper_book") is None
    models.intraday_state_set("paper_book", {"equity": 100.0})
    assert models.intraday_state_get("paper_book") == {"equity": 100.0}
    models.intraday_state_set("paper_book", {"equity": 99.5})
    assert models.intraday_state_get("paper_book") == {"equity": 99.5}


def test_trade_open_close_roundtrip(mem_db):
    tid = models.log_intraday_trade(
        symbol="DOGEUSDT", mode="paper", limit_price=0.1, entry_price=0.1,
        slot_usd=10.0, entry_time="2026-07-16T00:00:00+00:00",
        fill_type="trade_through",
    )
    models.close_intraday_trade(
        tid, exit_price=0.11, exit_time="2026-07-16T08:00:00+00:00",
        hold_bars=32, pnl_pct=0.1, pnl_usd=1.0, exit_reason="horizon",
    )
    from sqlalchemy.orm import Session
    with Session(mem_db) as s:
        row = s.get(models.IntradayTrade, tid)
        assert row.status == "closed" and row.pnl_usd == 1.0
        assert row.direction == "long"


def test_limit_telemetry_row(mem_db):
    models.log_intraday_limit(
        symbol="DOGEUSDT", limit_price=0.1, placed_at="2026-07-16T00:00:00+00:00",
        resolved_at="2026-07-16T00:15:00+00:00", outcome="touch_only",
        bar_low=0.1, admitted=False,
    )
    from sqlalchemy.orm import Session
    with Session(mem_db) as s:
        row = s.query(models.IntradayLimit).one()
        assert row.outcome == "touch_only" and row.admitted is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/intraday/test_db_models.py -v`
Expected: FAIL — `AttributeError: module 'app.db.models' has no attribute 'intraday_state_get'`.

- [ ] **Step 3: Implement**

Append to `app/db/models.py` (models after `CoinList`, helpers at the end; `Session` is already imported):

```python
class IntradayTrade(Base):
    __tablename__ = "intraday_trades"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    direction   = Column(String(5), nullable=False, default="long")
    mode        = Column(String(5), nullable=False)          # paper | live
    limit_price = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price  = Column(Float, nullable=True)
    slot_usd    = Column(Float, nullable=False)
    entry_time  = Column(String(50), nullable=False)
    exit_time   = Column(String(50), nullable=True)
    hold_bars   = Column(Integer, nullable=True)
    pnl_pct     = Column(Float, nullable=True)
    pnl_usd     = Column(Float, nullable=True)
    fill_type   = Column(String(15), nullable=False)         # trade_through
    exit_reason = Column(String(30), nullable=True)
    status      = Column(String(6), nullable=False, default="open")


class IntradayLimit(Base):
    __tablename__ = "intraday_limits"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    limit_price = Column(Float, nullable=False)
    placed_at   = Column(String(50), nullable=False)
    resolved_at = Column(String(50), nullable=True)
    outcome     = Column(String(15), nullable=True)   # trade_through|touch_only|miss|no_data
    bar_low     = Column(Float, nullable=True)
    admitted    = Column(Boolean, nullable=True)


class IntradayState(Base):
    __tablename__ = "intraday_state"

    key     = Column(String(40), primary_key=True)
    value   = Column(JSON, nullable=False)
    updated = Column(String(50), nullable=False)
```

```python
def intraday_state_get(key: str) -> dict | None:
    with Session(engine) as session:
        row = session.get(IntradayState, key)
        return dict(row.value) if row else None


def intraday_state_set(key: str, value: dict):
    with Session(engine) as session:
        session.merge(IntradayState(
            key=key, value=value,
            updated=datetime.now(timezone.utc).isoformat(),
        ))
        session.commit()


def log_intraday_trade(**fields) -> int:
    with Session(engine) as session:
        row = IntradayTrade(**fields)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def close_intraday_trade(trade_id: int, exit_price: float, exit_time: str,
                         hold_bars: int, pnl_pct: float, pnl_usd: float,
                         exit_reason: str):
    with Session(engine) as session:
        row = session.get(IntradayTrade, trade_id)
        if row:
            row.exit_price = exit_price
            row.exit_time = exit_time
            row.hold_bars = hold_bars
            row.pnl_pct = pnl_pct
            row.pnl_usd = pnl_usd
            row.exit_reason = exit_reason
            row.status = "closed"
            session.commit()


def log_intraday_limit(**fields):
    with Session(engine) as session:
        session.add(IntradayLimit(**fields))
        session.commit()
```

Create `alembic/versions/006_add_intraday_tables.py`: first `cat alembic/versions/005_normalize_swing_sl_tp_units.py` to copy its header conventions exactly (revision id format, imports). The migration:

```python
"""add intraday paper-engine tables

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "intraday_trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(5), nullable=False, server_default="long"),
        sa.Column("mode", sa.String(5), nullable=False),
        sa.Column("limit_price", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("slot_usd", sa.Float, nullable=False),
        sa.Column("entry_time", sa.String(50), nullable=False),
        sa.Column("exit_time", sa.String(50), nullable=True),
        sa.Column("hold_bars", sa.Integer, nullable=True),
        sa.Column("pnl_pct", sa.Float, nullable=True),
        sa.Column("pnl_usd", sa.Float, nullable=True),
        sa.Column("fill_type", sa.String(15), nullable=False),
        sa.Column("exit_reason", sa.String(30), nullable=True),
        sa.Column("status", sa.String(6), nullable=False, server_default="open"),
    )
    op.create_table(
        "intraday_limits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("limit_price", sa.Float, nullable=False),
        sa.Column("placed_at", sa.String(50), nullable=False),
        sa.Column("resolved_at", sa.String(50), nullable=True),
        sa.Column("outcome", sa.String(15), nullable=True),
        sa.Column("bar_low", sa.Float, nullable=True),
        sa.Column("admitted", sa.Boolean, nullable=True),
    )
    op.create_table(
        "intraday_state",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated", sa.String(50), nullable=False),
    )


def downgrade():
    op.drop_table("intraday_state")
    op.drop_table("intraday_limits")
    op.drop_table("intraday_trades")
```

(If 005's actual revision ids are long hashes rather than "005"-style, mirror that format and set `down_revision` to 005's real id.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intraday/test_db_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite, then commit**

```bash
git add app/db/models.py alembic/versions/006_add_intraday_tables.py tests/intraday/test_db_models.py
git commit -m "feat(intraday): DB models, state helpers, migration 006"
```

---

### Task 3: PaperBook — the incremental twin of build_weights

**Files:**
- Create: `app/intraday/paper.py`
- Test: `tests/intraday/test_paper_book.py` (create)

**Interfaces:**
- Consumes: `strategy.Z_ENTRY`, `strategy.build_weights` (parity test only).
- Produces: `paper.Bar = namedtuple("Bar", "open_time close low")`; `class PaperBook` with:
  - `PaperBook(equity: float, max_k: int, horizon_bars: int, entry_cost: float = 0.0002, exit_cost: float = 0.0008)`
  - `.on_bar(bars: dict[str, Bar], z: dict[str, float], universe: set[str]) -> CycleResult` — the full per-cycle transition (semantics below)
  - `.apply_funding(symbol: str, rate: float)` — held positions only; long pays positive: `position.funding_usd -= slot_usd * rate`
  - `.mark_equity(closes: dict[str, float]) -> float` — realized equity + unrealized on open positions
  - `.to_dict() -> dict` / `PaperBook.from_dict(d) -> PaperBook` — JSON-safe round trip
  - `CycleResult` dataclass: `placements: list[dict]`, `resolutions: list[dict]` (each: symbol, limit_price, outcome, bar_low, admitted), `exits: list[dict]` (symbol, entry_price, exit_price, hold_bars, pnl_usd, pnl_pct), `entries: list[dict]` (symbol, entry_price, z)
- **Transition semantics (the 1:1 map to `build_weights(fill="maker_limit", exit="horizon")` — deviation here is a correctness bug):**
  1. Resolve limits placed on the PREVIOUS bar against this bar: `bar.low < limit` → `trade_through`; `== limit` → `touch_only` (NOT filled); `> limit` → `miss`; symbol absent from `bars` → `no_data` (not filled). Limits live exactly one bar.
  2. Age positions: every position open before this bar gets `bars_held += 1`.
  3. Exits: positions with `bars_held >= horizon_bars` exit at `bar.close`; `pnl_usd = slot_usd * (exit/entry - 1) - slot_usd * (entry_cost + exit_cost) + funding_usd`; realized into equity.
  4. Admissions: `trade_through` fills sorted by their signal z ascending, admitted up to
     `min(free_at_placement, max_k - open_count)` with `bars_held = 1` and `entry_price = limit`;
     excess fills get `admitted=False`. **`free_at_placement` is recorded on each pending limit
     when placed** (= `max_k - open_count` at the placement bar, after that bar's exits and
     admissions). This is the load-bearing subtlety: the batch builder allocates slots at the
     SIGNAL bar with fill foreknowledge, so a slot freed by a horizon exit one bar after the
     signal must NOT admit a fill the batch would have blocked. The replay-parity test is the
     arbiter.
  5. Placements: for symbols in `universe`, with a finite z from this bar, `z < Z_ENTRY`, not held, not already pending: place a limit at `bar.close` carrying `free_at_placement` (no hard cap at placement — the cap binds at admission via the recorded value, exactly matching the batch builder's signal-bar slot check).
  - Known intentional limitations (document in the module docstring): `horizon_bars == 1` diverges from batch slot timing (fill and exit share a cycle; the frozen strategy uses 32), and universe drops do NOT force-exit live positions (spec decision: run to exit) whereas the batch builder's eligibility mask exits immediately.

- [ ] **Step 1: Write the failing tests**

Create `tests/intraday/test_paper_book.py`:

```python
"""PaperBook money-path goldens + replay parity against the batch builder."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.intraday import strategy
from app.intraday.paper import Bar, PaperBook

BAR_MS = 900_000


def _bar(t, close, low=None):
    return Bar(open_time=t * BAR_MS, close=close, low=close if low is None else low)


def _book(k=2, horizon=4):
    return PaperBook(equity=100.0, max_k=k, horizon_bars=horizon)


def test_signal_places_limit_then_trade_through_fills():
    book = _book()
    r1 = book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    assert [p["symbol"] for p in r1.placements] == ["A"]
    r2 = book.on_bar({"A": _bar(1, 101.0, low=99.9)}, {"A": 0.0}, {"A"})
    assert r2.resolutions[0]["outcome"] == "trade_through"
    assert r2.entries[0]["entry_price"] == 100.0


def test_touch_only_does_not_fill():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    r2 = book.on_bar({"A": _bar(1, 101.0, low=100.0)}, {"A": 0.0}, {"A"})
    assert r2.resolutions[0]["outcome"] == "touch_only"
    assert not r2.entries


def test_missing_bar_resolves_no_data():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    r2 = book.on_bar({}, {}, {"A"})
    assert r2.resolutions[0]["outcome"] == "no_data"


def test_horizon_exit_pnl_and_costs():
    book = _book(k=1, horizon=2)
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    book.on_bar({"A": _bar(1, 100.0, low=99.0)}, {"A": 0.0}, {"A"})   # fill @100, held 1
    r3 = book.on_bar({"A": _bar(2, 102.0)}, {"A": 0.0}, {"A"})        # held 2 == H -> exit
    assert len(r3.exits) == 1
    e = r3.exits[0]
    slot = 100.0
    expected = slot * 0.02 - slot * (0.0002 + 0.0008)
    assert e["pnl_usd"] == pytest.approx(expected)
    assert book.equity == pytest.approx(100.0 + expected)


def test_slot_cap_admits_lowest_z_first():
    book = _book(k=1, horizon=4)
    bars0 = {s: _bar(0, 100.0) for s in ("A", "B")}
    book.on_bar(bars0, {"A": -4.0, "B": -6.0}, {"A", "B"})
    bars1 = {s: _bar(1, 100.0, low=99.0) for s in ("A", "B")}
    r = book.on_bar(bars1, {"A": 0.0, "B": 0.0}, {"A", "B"})
    admitted = {x["symbol"]: x["admitted"] for x in r.resolutions}
    assert admitted == {"B": True, "A": False}


def test_funding_applied_to_realized_pnl():
    book = _book(k=1, horizon=2)
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    book.on_bar({"A": _bar(1, 100.0, low=99.0)}, {"A": 0.0}, {"A"})
    book.apply_funding("A", 0.0001)     # long pays positive funding
    r = book.on_bar({"A": _bar(2, 100.0)}, {"A": 0.0}, {"A"})
    assert r.exits[0]["pnl_usd"] == pytest.approx(
        -100.0 * (0.0002 + 0.0008) - 100.0 * 0.0001)


def test_serialization_roundtrip_preserves_behavior():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    clone = PaperBook.from_dict(book.to_dict())
    r_orig = book.on_bar({"A": _bar(1, 101.0, low=99.0)}, {"A": 0.0}, {"A"})
    r_clone = clone.on_bar({"A": _bar(1, 101.0, low=99.0)}, {"A": 0.0}, {"A"})
    assert r_orig.entries == r_clone.entries
    assert book.to_dict() == clone.to_dict()


def test_replay_parity_with_batch_builder():
    rng = np.random.default_rng(42)
    n, syms, k, horizon = 400, ["A", "B", "C"], 2, 4
    idx = pd.Index(np.arange(n) * BAR_MS, name="open_time")
    close = pd.DataFrame(
        {s: 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)) for s in syms}, index=idx)
    low = close * (1 - rng.uniform(0, 0.02, (n, len(syms))))
    z = pd.DataFrame(rng.normal(0, 2.0, (n, len(syms))), index=idx, columns=syms)
    elig = pd.DataFrame(True, index=idx, columns=syms)

    w_batch = strategy.build_weights(
        z, close, low, elig,
        {"horizon_bars": horizon, "exit": "horizon", "max_k": k}, "maker_limit")

    book = PaperBook(equity=100.0, max_k=k, horizon_bars=horizon)
    spans = []   # (symbol, fill_bar_index)
    for t in range(n):
        bars = {s: Bar(open_time=int(idx[t]), close=float(close.iloc[t][s]),
                       low=float(low.iloc[t][s])) for s in syms}
        zrow = {s: float(z.iloc[t][s]) for s in syms}
        res = book.on_bar(bars, zrow, set(syms))
        for e in res.entries:
            spans.append((e["symbol"], t))

    # reconstruct exposure: a fill confirmed at bar t earned from bar t-1
    # (batch w[signal] with signal = t-1) for `horizon` bars
    w_live = pd.DataFrame(0.0, index=idx, columns=syms)
    for sym, fill_bar in spans:
        start = fill_bar - 1
        w_live.iloc[start:start + horizon,
                    w_live.columns.get_loc(sym)] = 1.0 / k
    # the batch builder needs t+1 in range; the live book can't know the last
    # bar's future either — compare on the interior
    pd.testing.assert_frame_equal(
        w_live.iloc[: n - 1], w_batch.iloc[: n - 1], check_dtype=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/intraday/test_paper_book.py -v`
Expected: collection error — no module `app.intraday.paper`.

- [ ] **Step 3: Implement `app/intraday/paper.py`**

```python
"""Paper book: the incremental live twin of strategy.build_weights
(fill="maker_limit", exit="horizon"). The transition rules map 1:1 to the
batch builder and are pinned by the replay-parity test; change them only
with that test in front of you. Slot allocation matches the batch builder's
SIGNAL-bar semantics: each limit carries free_at_placement and admissions
are capped by it, so a slot freed after the signal never admits a fill the
batch would have blocked.

Known intentional limitations: horizon_bars == 1 diverges from batch slot
timing (fill and exit share a cycle; the frozen strategy uses 32), and
universe drops do NOT force-exit live positions (spec: run to exit) whereas
the batch eligibility mask exits immediately.
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field

import math

from app.intraday.strategy import Z_ENTRY

Bar = namedtuple("Bar", "open_time close low")


@dataclass
class CycleResult:
    placements: list = field(default_factory=list)
    resolutions: list = field(default_factory=list)
    exits: list = field(default_factory=list)
    entries: list = field(default_factory=list)


class PaperBook:
    def __init__(self, equity: float, max_k: int, horizon_bars: int,
                 entry_cost: float = 0.0002, exit_cost: float = 0.0008):
        self.equity = equity
        self.max_k = max_k
        self.horizon_bars = horizon_bars
        self.entry_cost = entry_cost
        self.exit_cost = exit_cost
        self.slot_usd = equity / max_k
        self.pending: dict[str, dict] = {}    # symbol -> {limit, z, placed_ms}
        self.positions: dict[str, dict] = {}  # symbol -> {entry, bars_held, funding_usd, entry_ms}

    # ── transitions ─────────────────────────────────────────
    def on_bar(self, bars: dict, z: dict, universe: set) -> CycleResult:
        res = CycleResult()

        # 1. resolve limits placed on the previous bar
        fills = []
        for sym, lim in list(self.pending.items()):
            bar = bars.get(sym)
            if bar is None:
                outcome, bar_low = "no_data", None
            elif bar.low < lim["limit"]:
                outcome, bar_low = "trade_through", bar.low
            elif bar.low == lim["limit"]:
                outcome, bar_low = "touch_only", bar.low
            else:
                outcome, bar_low = "miss", bar.low
            rec = {"symbol": sym, "limit_price": lim["limit"], "outcome": outcome,
                   "bar_low": bar_low, "admitted": False, "z": lim["z"],
                   "placed_ms": lim["placed_ms"],
                   "free_at_placement": lim["free_at_placement"]}
            res.resolutions.append(rec)
            if outcome == "trade_through":
                fills.append(rec)
            del self.pending[sym]

        # 2. age positions that existed before this bar
        for pos in self.positions.values():
            pos["bars_held"] += 1

        # 3. exits at horizon
        for sym in list(self.positions):
            pos = self.positions[sym]
            if pos["bars_held"] >= self.horizon_bars:
                bar = bars.get(sym)
                if bar is None:
                    continue   # no price this bar; exit on the next bar we see one
                gross = self.slot_usd * (bar.close / pos["entry"] - 1.0)
                pnl = (gross - self.slot_usd * (self.entry_cost + self.exit_cost)
                       + pos["funding_usd"])
                self.equity += pnl
                res.exits.append({
                    "symbol": sym, "entry_price": pos["entry"],
                    "exit_price": bar.close, "hold_bars": pos["bars_held"],
                    "pnl_usd": pnl,
                    "pnl_pct": bar.close / pos["entry"] - 1.0,
                })
                del self.positions[sym]

        # 4. admissions: lowest signal z first, capped by the SIGNAL-bar slot
        # count (batch builder allocates at the signal bar — see docstring)
        fills.sort(key=lambda r: r["z"])
        free = 0
        if fills:
            free = min(fills[0]["free_at_placement"],
                       self.max_k - len(self.positions))
        for rec in fills[:free]:
            rec["admitted"] = True
            self.positions[rec["symbol"]] = {
                "entry": rec["limit_price"], "bars_held": 1,
                "funding_usd": 0.0, "entry_ms": rec["placed_ms"],
            }
            res.entries.append({"symbol": rec["symbol"],
                                "entry_price": rec["limit_price"], "z": rec["z"]})

        # 5. new placements at this bar's close (record the signal-bar slot
        # count — admissions next bar are capped by it)
        free_now = self.max_k - len(self.positions)
        for sym in sorted(universe):
            zv = z.get(sym)
            bar = bars.get(sym)
            if (bar is None or zv is None or not math.isfinite(zv)
                    or zv >= Z_ENTRY or sym in self.positions
                    or sym in self.pending):
                continue
            self.pending[sym] = {"limit": bar.close, "z": zv,
                                 "placed_ms": bar.open_time,
                                 "free_at_placement": free_now}
            res.placements.append({"symbol": sym, "limit_price": bar.close,
                                   "z": zv, "placed_ms": bar.open_time})
        return res

    # ── accounting ──────────────────────────────────────────
    def apply_funding(self, symbol: str, rate: float):
        pos = self.positions.get(symbol)
        if pos is not None:
            pos["funding_usd"] -= self.slot_usd * rate

    def mark_equity(self, closes: dict) -> float:
        unrealized = 0.0
        for sym, pos in self.positions.items():
            px = closes.get(sym)
            if px is not None:
                unrealized += (self.slot_usd * (px / pos["entry"] - 1.0)
                               + pos["funding_usd"])
        return self.equity + unrealized

    # ── persistence ─────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "equity": self.equity, "max_k": self.max_k,
            "horizon_bars": self.horizon_bars,
            "entry_cost": self.entry_cost, "exit_cost": self.exit_cost,
            "pending": self.pending, "positions": self.positions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperBook":
        book = cls(d["equity"], d["max_k"], d["horizon_bars"],
                   d["entry_cost"], d["exit_cost"])
        book.pending = {k: dict(v) for k, v in d["pending"].items()}
        book.positions = {k: dict(v) for k, v in d["positions"].items()}
        return book
```

Note on step 2/3 ordering vs the batch builder: aging before the exit check makes `bars_held` count COMPLETED earning intervals — fill bar = 1 — so exit lands at the close of bar `signal + horizon`, exactly the batch's last earning interval boundary. The parity test is the arbiter.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intraday/test_paper_book.py -v`
Expected: 8 passed. If `test_replay_parity_with_batch_builder` fails, the transition rules diverge from the batch builder — debug the book against the semantics block in this task, not the test.

- [ ] **Step 5: Run the full suite, then commit**

```bash
git add app/intraday/paper.py tests/intraday/test_paper_book.py
git commit -m "feat(intraday): PaperBook — incremental twin of build_weights, replay-parity pinned"
```

---

### Task 4: Market data + universe refresh

**Files:**
- Create: `app/intraday/data.py`, `app/intraday/universe.py`
- Test: `tests/intraday/test_data_universe.py` (create)

**Interfaces:**
- Consumes: python-binance `Client` (unsigned: `Client("", "")`), `strategy.zscore`.
- Produces:
  - `data.fetch_panels(client, symbols: list[str], bars: int = 200) -> tuple[dict, dict]` — returns `(panels, errors)`; `panels` is `{"close": DataFrame, "low": DataFrame, "volume": DataFrame, "quote_volume": DataFrame}` indexed by open_time ms with one column per successful symbol, CLOSED bars only (drop any kline whose close_time > now); `errors` is `{symbol: str(exception)}` for failed symbols (per-symbol isolation — one failure never raises).
  - `data.latest_bars(panels) -> dict[str, Bar]` — last row per symbol as `paper.Bar`.
  - `data.fetch_funding_since(client, symbols: list[str], since_ms: int) -> list[dict]` — funding events (`symbol, funding_time, funding_rate`) after `since_ms`; per-symbol isolation, failures skipped silently (funding is an accounting refinement, not a trading decision).
  - `universe.resolve_top30(client) -> list[str]` — top-100 USDT perps by 24h quote volume (exchange_info TRADING PERPETUAL filter + ticker sort — same filter logic as `research/universe.py:resolve_top`), then for each fetch 31 daily klines and rank by median of the last 30 `quote_volume` values; require 30 full days; return top `UNIVERSE_SIZE`. Constants `UNIVERSE_SIZE = 30`, `POOL_SIZE = 100`.

- [ ] **Step 1: Write the failing tests**

Create `tests/intraday/test_data_universe.py`:

```python
"""REST fetchers: closed-bar discipline, per-symbol isolation, universe rule."""

from __future__ import annotations

import time

import pytest

from app.intraday import data as idata
from app.intraday import universe as iuni

BAR_MS = 900_000
DAY_MS = 86_400_000


def _kline(open_ms, close=100.0, low=99.0, closed=True):
    close_time = open_ms + BAR_MS - 1 if closed else int(time.time() * 1000) + BAR_MS
    return [open_ms, "100", "101", str(low), str(close), "10",
            close_time, "1000", 5, "5", "500", "0"]


class FakeClient:
    def __init__(self, klines_by_symbol=None, fail=(), funding=None,
                 daily=None, tickers=None, info_symbols=None):
        self.klines_by_symbol = klines_by_symbol or {}
        self.fail = set(fail)
        self.funding = funding or {}
        self.daily = daily or {}
        self.tickers = tickers or []
        self.info_symbols = info_symbols or []

    def futures_klines(self, symbol, interval, limit):
        if symbol in self.fail:
            raise RuntimeError("boom")
        if interval == "1d":
            return self.daily[symbol]
        return self.klines_by_symbol[symbol]

    def futures_funding_rate(self, symbol, startTime, limit):
        return [e for e in self.funding.get(symbol, [])
                if e["fundingTime"] > startTime]

    def futures_exchange_info(self):
        return {"symbols": self.info_symbols}

    def futures_ticker(self):
        return self.tickers


def test_fetch_panels_drops_forming_bar_and_isolates_errors():
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    klines = [_kline(now_open - 2 * BAR_MS), _kline(now_open - BAR_MS),
              _kline(now_open, closed=False)]
    client = FakeClient(klines_by_symbol={"A": klines, "B": klines}, fail=["B"])

    panels, errors = idata.fetch_panels(client, ["A", "B"], bars=10)

    assert list(panels["close"].columns) == ["A"]
    assert len(panels["close"]) == 2            # forming bar dropped
    assert "B" in errors


def test_latest_bars_shape():
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    klines = [_kline(now_open - 2 * BAR_MS, close=50.0, low=49.5),
              _kline(now_open - BAR_MS, close=51.0, low=50.5)]
    client = FakeClient(klines_by_symbol={"A": klines})
    panels, _ = idata.fetch_panels(client, ["A"], bars=10)

    bars = idata.latest_bars(panels)

    assert bars["A"].close == 51.0 and bars["A"].low == 50.5
    assert bars["A"].open_time == now_open - BAR_MS


def test_fetch_funding_since_filters_and_isolates():
    client = FakeClient(funding={
        "A": [{"symbol": "A", "fundingTime": 100, "fundingRate": "0.0001"},
              {"symbol": "A", "fundingTime": 200, "fundingRate": "0.0002"}],
    }, fail=["B"])

    events = idata.fetch_funding_since(client, ["A", "B"], since_ms=100)

    assert events == [{"symbol": "A", "funding_time": 200, "funding_rate": 0.0002}]


def test_resolve_top30_ranks_by_30d_median():
    def daily(qv, days=31):
        return [[d * DAY_MS, "1", "1", "1", "1", "1",
                 d * DAY_MS + DAY_MS - 1, str(qv), 1, "0", "0", "0"]
                for d in range(days)]
    info = [{"symbol": s, "contractType": "PERPETUAL", "quoteAsset": "USDT",
             "status": "TRADING"} for s in ("BIGUSDT", "MIDUSDT", "FRESHUSDT")]
    tickers = [{"symbol": "BIGUSDT", "quoteVolume": "3000"},
               {"symbol": "MIDUSDT", "quoteVolume": "2000"},
               {"symbol": "FRESHUSDT", "quoteVolume": "9999"}]
    client = FakeClient(info_symbols=info, tickers=tickers, daily={
        "BIGUSDT": daily(3000.0), "MIDUSDT": daily(2000.0),
        "FRESHUSDT": daily(9999.0, days=10),      # too young: <30 full days
    })

    top = iuni.resolve_top30(client)

    assert top == ["BIGUSDT", "MIDUSDT"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/intraday/test_data_universe.py -v`
Expected: collection error — no module `app.intraday.data`.

- [ ] **Step 3: Implement**

`app/intraday/data.py`:

```python
"""Unsigned REST market data -> pandas panels. Closed bars only; one symbol's
failure never breaks the cycle (per-symbol isolation is a hard requirement —
see the TON/IP silent-crash postmortem in CLAUDE.md)."""

from __future__ import annotations

import time

import pandas as pd

from app.intraday.paper import Bar

COLS = {"close": 4, "low": 3, "volume": 5, "quote_volume": 7}


def fetch_panels(client, symbols: list[str], bars: int = 200):
    now_ms = int(time.time() * 1000)
    frames = {name: {} for name in COLS}
    errors: dict[str, str] = {}
    for sym in symbols:
        try:
            raw = client.futures_klines(symbol=sym, interval="15m", limit=bars)
            closed = [k for k in raw if int(k[6]) <= now_ms]
            if not closed:
                continue
            idx = [int(k[0]) for k in closed]
            for name, col in COLS.items():
                frames[name][sym] = pd.Series(
                    [float(k[col]) for k in closed], index=idx)
        except Exception as e:
            errors[sym] = str(e)
    panels = {
        name: pd.DataFrame(series).sort_index().rename_axis("open_time")
        for name, series in frames.items()
    }
    return panels, errors


def latest_bars(panels: dict) -> dict[str, Bar]:
    close, low = panels["close"], panels["low"]
    out: dict[str, Bar] = {}
    for sym in close.columns:
        c = close[sym].dropna()
        if c.empty:
            continue
        t = c.index[-1]
        out[sym] = Bar(open_time=int(t), close=float(c.loc[t]),
                       low=float(low[sym].loc[t]))
    return out


def fetch_funding_since(client, symbols: list[str], since_ms: int) -> list[dict]:
    events: list[dict] = []
    for sym in symbols:
        try:
            raw = client.futures_funding_rate(symbol=sym, startTime=since_ms + 1,
                                              limit=100)
            for r in raw:
                if int(r["fundingTime"]) > since_ms:
                    events.append({"symbol": sym,
                                   "funding_time": int(r["fundingTime"]),
                                   "funding_rate": float(r["fundingRate"])})
        except Exception:
            continue
    return events
```

`app/intraday/universe.py`:

```python
"""Weekly universe: top-30 by 30-day median daily quote volume among the
top-100 USDT perps by 24h volume (live twin of the research PIT rule)."""

from __future__ import annotations

import statistics

UNIVERSE_SIZE = 30
POOL_SIZE = 100
MEDIAN_DAYS = 30


def resolve_top30(client) -> list[str]:
    info = client.futures_exchange_info()
    perps = {
        s["symbol"]
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }
    tickers = [t for t in client.futures_ticker() if t["symbol"] in perps]
    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    pool = [t["symbol"] for t in tickers[:POOL_SIZE]]

    ranked = []
    for sym in pool:
        try:
            daily = client.futures_klines(symbol=sym, interval="1d",
                                          limit=MEDIAN_DAYS + 1)
        except Exception:
            continue
        closed = daily[:-1] if len(daily) > MEDIAN_DAYS else daily
        if len(closed) < MEDIAN_DAYS:
            continue
        qv = [float(k[7]) for k in closed[-MEDIAN_DAYS:]]
        ranked.append((statistics.median(qv), sym))
    ranked.sort(reverse=True)
    return [sym for _, sym in ranked[:UNIVERSE_SIZE]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intraday/test_data_universe.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite, then commit**

```bash
git add app/intraday/data.py app/intraday/universe.py tests/intraday/test_data_universe.py
git commit -m "feat(intraday): REST panels with closed-bar discipline + weekly top-30 universe"
```

---

### Task 5: Risk (kill-switches, error tracker), notifier, config

**Files:**
- Create: `app/intraday/risk.py`, `app/intraday/notifier.py`, `app/intraday/config.py`
- Test: `tests/intraday/test_risk.py` (create)

**Interfaces:**
- Consumes: nothing app-internal beyond stdlib (notifier mirrors `app/swing/notifier.py`, importing `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` from `app.config`).
- Produces:
  - `config.py` constants: `HORIZON_BARS = 32`, `MAX_K = 10`, `PAPER_EQUITY = 100.0`, `CHECK_INTERVAL = 900`, `DAILY_LOSS_HALT = 0.05`, `MAX_DD_HALT = 0.20`, `UNIVERSE_REFRESH_DAYS = 7`, `ERROR_ALERT_STRIKES = 3`, `EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "paper")`, `RESUME = os.environ.get("INTRADAY_RESUME") == "1"`.
  - `risk.ErrorTracker(strikes: int = 3)` — `.record(symbol, ok: bool) -> bool` returns True exactly once when a symbol hits `strikes` consecutive failures (alert edge; resets on success, does not re-alert until a success intervenes).
  - `risk.KillSwitch(daily_loss_pct, max_dd_pct)` — `.check(equity_mark: float, utc_date: str) -> str | None` returns `"daily_loss"` / `"drawdown"` on the trip edge else None; tracks `day_anchor` (date, equity at day start) and `peak`; `.halted: bool`; `.resume()`; `.to_dict()` / `KillSwitch.from_dict(d)` JSON round trip.
  - `notifier.send(msg)`, `notifier.notify_fill(symbol, entry_price, z)`, `notifier.notify_exit(symbol, pnl_usd, pnl_pct, hold_bars)`, `notifier.notify_halt(reason, equity)`, `notifier.notify_error_strikes(symbol, n)`, `notifier.notify_daily_summary(text)` — mirror the swing notifier's requests-based `send` with `html.escape` on all dynamic strings.

- [ ] **Step 1: Write the failing tests**

Create `tests/intraday/test_risk.py`:

```python
"""Kill-switch trip edges, resume, error-strike alert edge, serialization."""

from __future__ import annotations

from app.intraday.risk import ErrorTracker, KillSwitch


def test_error_tracker_alerts_once_at_three_strikes():
    t = ErrorTracker(strikes=3)
    assert not t.record("A", ok=False)
    assert not t.record("A", ok=False)
    assert t.record("A", ok=False)          # third consecutive: alert edge
    assert not t.record("A", ok=False)      # no re-alert while still failing
    t.record("A", ok=True)
    assert not t.record("A", ok=False)      # counter reset by the success


def test_daily_loss_halts_on_edge():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.99)
    assert ks.check(100.0, "2026-07-16") is None      # anchors the day
    assert ks.check(96.0, "2026-07-16") is None       # -4%
    assert ks.check(94.9, "2026-07-16") == "daily_loss"
    assert ks.halted
    assert ks.check(94.9, "2026-07-16") is None       # no re-trip while halted


def test_daily_anchor_resets_next_day():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.99)
    ks.check(100.0, "2026-07-16")
    ks.check(97.0, "2026-07-16")
    # the 17th anchors at its first mark (93.0); no trip on the anchor itself
    assert ks.check(93.0, "2026-07-17") is None
    # 88.3 < 93 * 0.95 = 88.35 -> daily-loss trip against the NEW anchor
    assert ks.check(88.3, "2026-07-17") == "daily_loss"


def test_drawdown_halts_from_peak():
    ks = KillSwitch(daily_loss_pct=0.99, max_dd_pct=0.20)
    ks.check(100.0, "2026-07-16")
    ks.check(110.0, "2026-07-16")                     # peak 110
    assert ks.check(88.1, "2026-07-16") is None       # -19.9% from peak
    assert ks.check(87.9, "2026-07-16") == "drawdown"


def test_resume_and_serialization():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.20)
    ks.check(100.0, "2026-07-16")
    ks.check(94.0, "2026-07-16")
    assert ks.halted
    clone = KillSwitch.from_dict(ks.to_dict())
    assert clone.halted
    clone.resume()
    assert not clone.halted
    assert clone.check(93.0, "2026-07-16") is None    # resumed; re-anchor guards re-trip
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/intraday/test_risk.py -v`
Expected: collection error — no module `app.intraday.risk`.

- [ ] **Step 3: Implement**

`app/intraday/config.py`:

```python
"""Frozen strategy + engine settings. Strategy params are pre-registered
(2b findings) — do not tune them here; a new value requires a new research
phase."""

import os

HORIZON_BARS = 32
MAX_K = 10
PAPER_EQUITY = 100.0
CHECK_INTERVAL = 900
DAILY_LOSS_HALT = 0.05
MAX_DD_HALT = 0.20
UNIVERSE_REFRESH_DAYS = 7
ERROR_ALERT_STRIKES = 3
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "paper")
RESUME = os.environ.get("INTRADAY_RESUME") == "1"
```

`app/intraday/risk.py`:

```python
"""Kill-switches (armed in paper — proving them is part of the phase) and
the consecutive-error tracker."""

from __future__ import annotations


class ErrorTracker:
    def __init__(self, strikes: int = 3):
        self.strikes = strikes
        self._counts: dict[str, int] = {}

    def record(self, symbol: str, ok: bool) -> bool:
        if ok:
            self._counts[symbol] = 0
            return False
        self._counts[symbol] = self._counts.get(symbol, 0) + 1
        return self._counts[symbol] == self.strikes


class KillSwitch:
    def __init__(self, daily_loss_pct: float, max_dd_pct: float):
        self.daily_loss_pct = daily_loss_pct
        self.max_dd_pct = max_dd_pct
        self.halted = False
        self.day = None
        self.day_anchor = None
        self.peak = None

    def check(self, equity_mark: float, utc_date: str) -> str | None:
        if self.day != utc_date:
            self.day = utc_date
            self.day_anchor = equity_mark
        if self.peak is None or equity_mark > self.peak:
            self.peak = equity_mark
        if self.halted:
            return None
        if equity_mark < self.day_anchor * (1.0 - self.daily_loss_pct):
            self.halted = True
            return "daily_loss"
        if equity_mark < self.peak * (1.0 - self.max_dd_pct):
            self.halted = True
            return "drawdown"
        return None

    def resume(self):
        self.halted = False
        self.day = None       # re-anchor on the next check

    def to_dict(self) -> dict:
        return {"daily_loss_pct": self.daily_loss_pct,
                "max_dd_pct": self.max_dd_pct, "halted": self.halted,
                "day": self.day, "day_anchor": self.day_anchor,
                "peak": self.peak}

    @classmethod
    def from_dict(cls, d: dict) -> "KillSwitch":
        ks = cls(d["daily_loss_pct"], d["max_dd_pct"])
        ks.halted = d["halted"]
        ks.day = d["day"]
        ks.day_anchor = d["day_anchor"]
        ks.peak = d["peak"]
        return ks
```

`app/intraday/notifier.py`:

```python
"""Telegram notifications for the intraday paper engine."""

import html
import logging

import requests

from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send(msg: str):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram rejected message: %s", data)
    except Exception as e:
        log.error("Telegram error: %s", e)


def notify_fill(symbol: str, entry_price: float, z: float):
    send(f"📥 <b>PAPER FILL {html.escape(symbol)}</b>\n"
         f"Entry: ${entry_price:,.6g}  (z={z:.2f})")


def notify_exit(symbol: str, pnl_usd: float, pnl_pct: float, hold_bars: int):
    emoji = "✅" if pnl_usd >= 0 else "🛑"
    send(f"{emoji} <b>PAPER EXIT {html.escape(symbol)}</b>\n"
         f"PnL: <b>{pnl_usd:+.2f} USDT</b> ({pnl_pct * 100:+.2f}%) "
         f"over {hold_bars} bars")


def notify_halt(reason: str, equity: float):
    send(f"⛔ <b>KILL-SWITCH: {html.escape(reason)}</b>\n"
         f"Paper equity: ${equity:,.2f}\n"
         f"Trading halted. Resume with INTRADAY_RESUME=1.")


def notify_error_strikes(symbol: str, n: int):
    send(f"⚠️ <b>{html.escape(symbol)}</b> failed {n} consecutive cycles")


def notify_daily_summary(text: str):
    send(f"📊 <b>Intraday daily summary</b>\n{text}")
```

(`notify_daily_summary` callers pre-escape: the engine builds `text` exclusively from numbers it formats itself.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intraday/test_risk.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite, then commit**

```bash
git add app/intraday/config.py app/intraday/risk.py app/intraday/notifier.py tests/intraday/test_risk.py
git commit -m "feat(intraday): kill-switches, error tracker, Telegram notifier, frozen config"
```

---

### Task 6: Engine cycle + entrypoint

**Files:**
- Create: `app/intraday/engine.py`, `app/intraday/main.py`, `intraday_main.py` (repo root)
- Test: `tests/intraday/test_engine.py` (create)

**Interfaces:**
- Consumes: every prior task's interface exactly as specified.
- Produces: `engine.Context` (dataclass: client, book: PaperBook, killswitch: KillSwitch, tracker: ErrorTracker, universe: list[str], universe_refreshed_ms: int, last_funding_ms: int, notify: module-like, state_get/state_set callables) and `engine.run_cycle(ctx) -> dict` (summary). `main.main()` builds the Context (restoring book/killswitch/universe from `intraday_state`, honoring `config.RESUME`), then loops: `run_cycle`, persist, sleep to the next 15m boundary + 20s. `intraday_main.py` at repo root mirrors `swing_main.py`'s pattern (logging setup + `app.intraday.main.main()`).

`run_cycle` order (each numbered part wrapped so a failure alerts and skips forward, never crashes the loop):
1. Weekly universe refresh if `now - universe_refreshed_ms > UNIVERSE_REFRESH_DAYS days` (failure: keep the old universe, alert once via tracker key `"__universe__"`).
2. `fetch_panels` for universe + symbols still held/pending (so dropped symbols keep getting exit prices); feed `tracker.record(sym, ok)` per symbol; alert on strike edges.
3. Compute `z = strategy.zscore(close, volume, quote_volume)`; take the last row as `{symbol: float}`.
4. Funding: `fetch_funding_since(client, held_symbols, ctx.last_funding_ms)` → `book.apply_funding` per event; advance `last_funding_ms` to the max seen funding_time.
5. If killswitch halted: call `book.on_bar(bars, z={}, universe=set())` — empty z and universe mean NO new placements while pending limits resolve and open positions age/exit normally.
   Else: `book.on_bar(bars, z_last_row, set(universe))`.
6. Persist DB records: `log_intraday_limit` for every resolution (outcome, bar_low, admitted, resolved_at=now ISO); `log_intraday_trade` for every entry (fill_type="trade_through", mode=config.EXECUTION_MODE); `close_intraday_trade` for every exit (matching the open row by symbol+status="open" → the engine keeps `{symbol: trade_id}` in state).
7. Kill-switch check on `book.mark_equity(last closes)` with today's UTC date; on trip: `notify_halt`.
8. Notifications: fills, exits; once per UTC day (state key `last_summary_date`): daily summary (equity, open positions, fills/misses/touches today from the DB); once per 7 days: weekly telemetry report (trade-through/touch/miss/no_data counts and rates from `intraday_limits`).
9. Persist state: `paper_book`, `killswitch`, `universe` (+refreshed ms), `trade_ids`, `last_funding_ms`.

- [ ] **Step 1: Write the failing tests**

Create `tests/intraday/test_engine.py`:

```python
"""Engine cycle wiring: halt semantics, per-symbol error strikes, state
persistence, restart recovery. DB helpers and notifier are recorded fakes —
the cycle's observable behavior is what's pinned."""

from __future__ import annotations

import time
import types

import numpy as np
import pytest

from app.intraday import engine
from app.intraday.paper import PaperBook
from app.intraday.risk import ErrorTracker, KillSwitch

BAR_MS = 900_000


def _klines(n=120, close=100.0, low=99.0, last_closed=True):
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    out = []
    for i in range(n):
        t = now_open - (n - i) * BAR_MS
        out.append([t, "100", "101", str(low), str(close), "10",
                    t + BAR_MS - 1, "1000", 5, "5", "500", "0"])
    return out


class FakeClient:
    def __init__(self, symbols, fail=()):
        self.symbols = symbols
        self.fail = set(fail)

    def futures_klines(self, symbol, interval, limit):
        if symbol in self.fail:
            raise RuntimeError("boom")
        return _klines()

    def futures_funding_rate(self, symbol, startTime, limit):
        return []


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _f(*a, **k):
            self.calls.append((name, a, k))
        return _f


@pytest.fixture
def ctx(monkeypatch):
    state = {}
    notify = Recorder()
    db = Recorder()
    monkeypatch.setattr(engine, "models", db)
    db.log_intraday_trade = lambda **k: len(db.calls)   # returns fake id
    c = engine.Context(
        client=FakeClient(["AAAUSDT", "BBBUSDT"]),
        book=PaperBook(equity=100.0, max_k=10, horizon_bars=32),
        killswitch=KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.20),
        tracker=ErrorTracker(strikes=3),
        universe=["AAAUSDT", "BBBUSDT"],
        universe_refreshed_ms=int(time.time() * 1000),
        last_funding_ms=0,
        notify=notify,
        state_get=state.get,
        state_set=lambda k, v: state.__setitem__(k, v),
    )
    c._state = state
    return c


def test_cycle_runs_and_persists_state(ctx):
    summary = engine.run_cycle(ctx)
    assert summary["symbols_ok"] == 2
    assert "paper_book" in ctx._state and "killswitch" in ctx._state


def test_error_strikes_alert_once(ctx):
    ctx.client.fail = {"BBBUSDT"}
    engine.run_cycle(ctx)
    engine.run_cycle(ctx)
    engine.run_cycle(ctx)
    strikes = [c for c in ctx.notify.calls if c[0] == "notify_error_strikes"]
    assert len(strikes) == 1
    assert strikes[0][1][0] == "BBBUSDT"


def test_halted_killswitch_blocks_new_placements(ctx, monkeypatch):
    ctx.killswitch.halted = True
    # force a deep-oversold z so a placement WOULD happen if not halted
    monkeypatch.setattr(engine.strategy, "zscore",
                        lambda c, v, q: c * 0.0 - 5.0)
    engine.run_cycle(ctx)
    assert not ctx.book.pending


def test_restart_recovers_book_from_state(ctx):
    ctx.book.pending["AAAUSDT"] = {"limit": 99.0, "z": -4.0, "placed_ms": 0,
                                   "free_at_placement": 10}
    engine.persist(ctx)
    restored = PaperBook.from_dict(ctx._state["paper_book"])
    assert restored.pending["AAAUSDT"]["free_at_placement"] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/intraday/test_engine.py -v`
Expected: collection error — no module `app.intraday.engine`.

- [ ] **Step 3: Implement**

`app/intraday/engine.py`:

```python
"""The 15m cycle: data -> z -> paper book -> risk -> persistence -> Telegram.
Every stage is isolated; a failure alerts and the loop continues (the
TON/IP postmortem is the design constraint here)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import models
from app.intraday import config, strategy
from app.intraday import universe as iuniverse
from app.intraday.data import fetch_funding_since, fetch_panels, latest_bars

log = logging.getLogger(__name__)

DAY_MS = 86_400_000


@dataclass
class Context:
    client: object
    book: object
    killswitch: object
    tracker: object
    universe: list
    universe_refreshed_ms: int
    last_funding_ms: int
    notify: object
    state_get: object
    state_set: object


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def refresh_universe(ctx: Context):
    now_ms = int(time.time() * 1000)
    if now_ms - ctx.universe_refreshed_ms < config.UNIVERSE_REFRESH_DAYS * DAY_MS:
        return
    try:
        new = iuniverse.resolve_top30(ctx.client)
        if new and new != ctx.universe:
            added = sorted(set(new) - set(ctx.universe))
            dropped = sorted(set(ctx.universe) - set(new))
            ctx.notify.send(f"🔄 Universe refreshed: +{added} -{dropped}")
        if new:
            ctx.universe = new
        ctx.universe_refreshed_ms = now_ms
        ctx.tracker.record("__universe__", ok=True)
    except Exception as e:
        log.error("universe refresh failed: %s", e)
        if ctx.tracker.record("__universe__", ok=False):
            ctx.notify.notify_error_strikes("__universe__", config.ERROR_ALERT_STRIKES)


def run_cycle(ctx: Context) -> dict:
    refresh_universe(ctx)

    watch = sorted(set(ctx.universe)
                   | set(ctx.book.positions) | set(ctx.book.pending))
    panels, errors = fetch_panels(ctx.client, watch)
    for sym in watch:
        ok = sym not in errors
        if ctx.tracker.record(sym, ok) and not ok:
            ctx.notify.notify_error_strikes(sym, config.ERROR_ALERT_STRIKES)

    bars = latest_bars(panels)
    z_row: dict = {}
    if not ctx.killswitch.halted and len(panels["close"]):
        z = strategy.zscore(panels["close"], panels["volume"],
                            panels["quote_volume"])
        z_row = {s: float(z[s].iloc[-1]) for s in z.columns}

    try:
        if ctx.book.positions:
            events = fetch_funding_since(ctx.client, sorted(ctx.book.positions),
                                         ctx.last_funding_ms)
            for ev in events:
                ctx.book.apply_funding(ev["symbol"], ev["funding_rate"])
                ctx.last_funding_ms = max(ctx.last_funding_ms, ev["funding_time"])
    except Exception as e:
        log.error("funding failed: %s", e)

    active_universe = set() if ctx.killswitch.halted else set(ctx.universe)
    res = ctx.book.on_bar(bars, z_row, active_universe)

    trade_ids = ctx.state_get("trade_ids") or {}
    now = _now_iso()
    for r in res.resolutions:
        try:
            models.log_intraday_limit(
                symbol=r["symbol"], limit_price=r["limit_price"],
                placed_at=datetime.fromtimestamp(
                    r["placed_ms"] / 1000, tz=timezone.utc).isoformat(),
                resolved_at=now, outcome=r["outcome"], bar_low=r["bar_low"],
                admitted=r["admitted"])
        except Exception as e:
            log.error("limit log failed: %s", e)
    for e_ in res.entries:
        try:
            trade_ids[e_["symbol"]] = models.log_intraday_trade(
                symbol=e_["symbol"], mode=config.EXECUTION_MODE,
                limit_price=e_["entry_price"], entry_price=e_["entry_price"],
                slot_usd=ctx.book.slot_usd, entry_time=now,
                fill_type="trade_through")
            ctx.notify.notify_fill(e_["symbol"], e_["entry_price"], e_["z"])
        except Exception as ex:
            log.error("trade open log failed: %s", ex)
    for x in res.exits:
        try:
            tid = trade_ids.pop(x["symbol"], None)
            if tid is not None:
                models.close_intraday_trade(
                    tid, exit_price=x["exit_price"], exit_time=now,
                    hold_bars=x["hold_bars"], pnl_pct=x["pnl_pct"],
                    pnl_usd=x["pnl_usd"], exit_reason="horizon")
            ctx.notify.notify_exit(x["symbol"], x["pnl_usd"], x["pnl_pct"],
                                   x["hold_bars"])
        except Exception as ex:
            log.error("trade close log failed: %s", ex)

    closes = {s: b.close for s, b in bars.items()}
    mark = ctx.book.mark_equity(closes)
    reason = ctx.killswitch.check(mark, _utc_date())
    if reason:
        ctx.notify.notify_halt(reason, mark)

    maybe_send_summaries(ctx, mark)
    ctx.state_set("trade_ids", trade_ids)
    persist(ctx)
    summary = {"symbols_ok": len(bars), "errors": len(errors),
               "placements": len(res.placements), "entries": len(res.entries),
               "exits": len(res.exits), "equity_mark": mark,
               "halted": ctx.killswitch.halted}
    log.info("cycle done: %s", summary)
    return summary


def maybe_send_summaries(ctx: Context, mark: float):
    """Daily equity summary + weekly fill-telemetry report (spec §3)."""
    try:
        today = _utc_date()
        if (ctx.state_get("last_summary_date") or {}).get("date") != today:
            ctx.notify.notify_daily_summary(
                f"equity mark: ${mark:,.2f}\n"
                f"open positions: {len(ctx.book.positions)}\n"
                f"pending limits: {len(ctx.book.pending)}\n"
                f"halted: {ctx.killswitch.halted}")
            ctx.state_set("last_summary_date", {"date": today})

        now_ms = int(time.time() * 1000)
        last_weekly = (ctx.state_get("last_weekly_ms") or {}).get("ms", 0)
        if now_ms - last_weekly > 7 * DAY_MS:
            from sqlalchemy import func
            from sqlalchemy.orm import Session
            with Session(models.engine) as s:
                counts = dict(
                    s.query(models.IntradayLimit.outcome, func.count())
                    .group_by(models.IntradayLimit.outcome).all())
            total = sum(counts.values()) or 1
            lines = [f"{k}: {v} ({v / total:.0%})"
                     for k, v in sorted(counts.items())]
            ctx.notify.send("📈 <b>Weekly fill telemetry</b>\n"
                            + ("\n".join(lines) if counts else "no limits yet"))
            ctx.state_set("last_weekly_ms", {"ms": now_ms})
    except Exception as e:
        log.error("summary failed: %s", e)


def persist(ctx: Context):
    ctx.state_set("paper_book", ctx.book.to_dict())
    ctx.state_set("killswitch", ctx.killswitch.to_dict())
    ctx.state_set("universe", {"symbols": ctx.universe,
                               "refreshed_ms": ctx.universe_refreshed_ms})
    ctx.state_set("last_funding_ms", {"ms": ctx.last_funding_ms})
```

`app/intraday/main.py`:

```python
"""Entrypoint wiring: restore state, honor INTRADAY_RESUME, loop aligned to
15m closes."""

from __future__ import annotations

import logging
import time

from binance.client import Client

from app.db import models
from app.intraday import config, notifier
from app.intraday import universe as iuniverse
from app.intraday.engine import Context, persist, run_cycle
from app.intraday.paper import PaperBook
from app.intraday.risk import ErrorTracker, KillSwitch

log = logging.getLogger(__name__)


def build_context() -> Context:
    if config.EXECUTION_MODE != "paper":
        raise NotImplementedError("live mode is not implemented in Phase 3")
    client = Client("", "")   # unsigned market data only — keyless by design

    saved_book = models.intraday_state_get("paper_book")
    book = (PaperBook.from_dict(saved_book) if saved_book
            else PaperBook(equity=config.PAPER_EQUITY, max_k=config.MAX_K,
                           horizon_bars=config.HORIZON_BARS))
    saved_ks = models.intraday_state_get("killswitch")
    ks = (KillSwitch.from_dict(saved_ks) if saved_ks
          else KillSwitch(daily_loss_pct=config.DAILY_LOSS_HALT,
                          max_dd_pct=config.MAX_DD_HALT))
    if config.RESUME and ks.halted:
        ks.resume()
        notifier.send("▶️ Kill-switch cleared via INTRADAY_RESUME — trading resumed")

    saved_uni = models.intraday_state_get("universe")
    if saved_uni:
        universe, refreshed = saved_uni["symbols"], saved_uni["refreshed_ms"]
    else:
        universe, refreshed = iuniverse.resolve_top30(client), int(time.time() * 1000)
    saved_f = models.intraday_state_get("last_funding_ms")

    return Context(
        client=client, book=book, killswitch=ks,
        tracker=ErrorTracker(strikes=config.ERROR_ALERT_STRIKES),
        universe=universe, universe_refreshed_ms=refreshed,
        last_funding_ms=(saved_f or {}).get("ms", int(time.time() * 1000)),
        notify=notifier,
        state_get=models.intraday_state_get, state_set=models.intraday_state_set,
    )


def main():
    ctx = build_context()
    notifier.send(f"🚀 Intraday engine up — mode={config.EXECUTION_MODE}, "
                  f"universe={len(ctx.universe)}, "
                  f"equity=${ctx.book.equity:,.2f}"
                  f"{' [HALTED]' if ctx.killswitch.halted else ''}")
    persist(ctx)
    while True:
        try:
            run_cycle(ctx)
        except Exception as e:
            log.exception("cycle crashed: %s", e)
            notifier.send(f"💥 Intraday cycle crashed: {type(e).__name__}")
        now = time.time()
        next_close = (int(now) // config.CHECK_INTERVAL + 1) * config.CHECK_INTERVAL
        time.sleep(max(next_close + 20 - now, 5))
```

`intraday_main.py` (repo root — first `cat swing_main.py` and mirror its logging/bootstrap exactly, swapping the import to `from app.intraday.main import main`):

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app.intraday.main import main

if __name__ == "__main__":
    main()
```

(If `swing_main.py` differs from this shape, follow `swing_main.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intraday/test_engine.py -v`
Expected: 4 passed. (`maybe_send_summaries` swallows its own errors, so the fake `models` object in the fixture — whose `engine` attribute isn't a real SQLAlchemy engine — must not break the cycle tests; the daily-summary branch will fire once via the Recorder, which is harmless. The weekly query's live behavior is verified during the Task 8 deploy watch.)

- [ ] **Step 5: Run the full suite, then commit**

```bash
git add app/intraday/engine.py app/intraday/main.py intraday_main.py tests/intraday/test_engine.py
git commit -m "feat(intraday): engine cycle, entrypoint, restart recovery"
```

---

### Task 7: Teardown — legacy moves, compose, docs

**Files:**
- Move: `app/bot/ → legacy/app/bot/`, `app/swing/ → legacy/app/swing/`, `tests/bot/ → legacy/tests/bot/`, `tests/swing/ → legacy/tests/swing/`, `main.py → legacy/main.py`, `swing_main.py → legacy/swing_main.py`
- Modify: `docker-compose.yml` (remove `bot`, `swing`, `rebalance`; add `intraday`), `.dockerignore` (add `legacy/`), `tests/conftest.py` (remove doubles used only by moved tests, keep the env stub), `CLAUDE.md` (services + sections)
- Test: the full suite — now expected FULLY green

- [ ] **Step 1: Move the legacy code with git mv**

```bash
mkdir -p legacy/app legacy/tests
git mv app/bot legacy/app/bot
git mv app/swing legacy/app/swing
git mv tests/bot legacy/tests/bot
git mv tests/swing legacy/tests/swing
git mv main.py legacy/main.py
git mv swing_main.py legacy/swing_main.py
```

- [ ] **Step 2: Fix collateral references**

- `tests/conftest.py`: keep the `_STUB_ENV` block and any fixtures used by remaining tests (`grep -rl "fake_client\|snapshot" tests/` to check); delete fixtures used only by the moved swing/bot tests. `tests/backtest/`, `tests/property/`, `tests/integration/` may import `app.swing.*` — check with `grep -rl "app.swing\|app.bot" tests/ research/`; any remaining test that imports moved modules moves to `legacy/tests/` as well (same `git mv`).
- `app/api/main.py`: `grep -n "app.swing\|app.bot" app/api/main.py` — if the API imports moved modules, replace those endpoints' imports with direct DB queries (the tables still exist) or delete the specific endpoint if it is swing-runtime-only; the API service must still boot.
- `research/`: `grep -rn "app.swing\|app.bot" research/` — expected none.

- [ ] **Step 3: docker-compose.yml — remove `bot`, `swing`, `rebalance` service blocks; add:**

```yaml
  intraday:
    build: .
    restart: unless-stopped
    env_file: .env
    command: python intraday_main.py
    depends_on:
      db:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    mem_limit: 250m
```

Add `legacy/` to `.dockerignore`.

- [ ] **Step 4: CLAUDE.md** — replace the Docker services table rows `bot`/`swing` with one `intraday` row ("Intraday paper engine — keyless"); add after the table: a short "Intraday Engine (`app/intraday/`)" section (frozen params, paper semantics, kill-switches, INTRADAY_RESUME, universe rule, telemetry tables — 10 lines max, pointing at the Phase 3 spec for detail); replace the "Swing Agent" and "DCA Bot" section bodies with two lines each: retired 2026-07-16 to `legacy/` (code + tests), tables kept as history, DCA spot holdings managed manually.

- [ ] **Step 5: Run the FULL suite — now fully green**

Run: `python -m pytest`
Expected: **0 failures** (the date-sensitive reconcile test moved to legacy/ with its module). Also: `docker compose config -q` (validates the yaml) and `python -c "import app.api.main"` must succeed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(intraday): retire legacy bots to legacy/ — intraday service replaces bot+swing+rebalance"
```

---

### Task 8: Deploy (ops — REQUIRES USER GO-AHEAD; touches the production box)

**Files:** none (operational).

- [ ] **Step 1: Confirm with the user before touching prod.** The deploy stops the DCA bot and swing agent permanently and starts the paper engine. DCA spot holdings on Binance are NOT touched (user decision). Get an explicit yes.

- [ ] **Step 2: Push and deploy** (deploy = push to the box per the established pattern — see memory `project_phase_a_live_money_fixes_2026-07-13`: SSH push to the deploy branch):

```bash
git push production main:deploy     # or the box's actual remote/branch — check .git/config
ssh <lightsail> "cd /srv/trade-god && git pull && docker compose up -d --build && docker compose ps"
```

- [ ] **Step 3: Verify**

```bash
ssh <lightsail> "cd /srv/trade-god && docker compose ps"          # db, migrate(done), api, intraday — NO bot/swing
ssh <lightsail> "cd /srv/trade-god && docker compose logs --tail 50 intraday"
```
Expected: migration 006 applied; startup Telegram message received ("🚀 Intraday engine up — mode=paper..."); first cycle logs `cycle done: {...}` within 15 minutes; no API-key errors (there are none to have).

- [ ] **Step 4: Watch two full cycles** (30 min): confirm `symbols_ok` ≈ 30, zero crashes, state rows appearing in `intraday_state`.

- [ ] **Step 5: Record**: append deploy date + observed first-cycle summary to the Phase 3 spec's Success Criteria section; commit.

---

## Verification (whole phase)

- `python -m pytest` — fully green, no excepted failures.
- Replay-parity test green — PaperBook is provably the batch builder's twin.
- On the box: `intraday` service running keyless; both legacy services gone; Telegram startup + cycle messages flowing.
- `research/` still imports the strategy from `app/` (2b tests green) — one strategy implementation in the whole repo.
