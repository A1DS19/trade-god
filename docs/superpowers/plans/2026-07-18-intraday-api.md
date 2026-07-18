# Intraday API & Status Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JSON endpoints over the intraday telemetry tables plus a server-rendered HTML status page, with the retired DCA/swing endpoints relocated under `/legacy/*`.

**Architecture:** `app/api/` splits into `main.py` (assembly), `queries.py` (shared read-only aggregation helpers returning plain dicts), `routers/intraday.py`, `routers/legacy.py`, and `status_page.py` (HTML built from the same `queries.py` dicts the JSON routes return). Spec: `docs/superpowers/specs/2026-07-18-intraday-api-design.md`.

**Tech Stack:** FastAPI 0.115.6, SQLAlchemy 2.0.40, pytest + `fastapi.testclient` (httpx installed on the dev box). **No new runtime dependencies** — `requirements.txt` is not touched.

## Global Constraints

- DB access in ALL new/moved API code goes through the module attribute — `from app.db import models` then `Session(models.engine)` — never `from app.db.models import engine`. Tests swap the engine by monkeypatching `models.engine`; a direct import freezes the real engine at import time and breaks every test.
- `GET /health` keeps its exact path and response `{"status": "ok"}` — the compose healthcheck (fixed in `c03c0ba`) probes it.
- `pnl_pct` in API responses is a percentage: DB fraction × 100 (swing-endpoint convention).
- All dynamic text on the HTML page goes through `html.escape()`.
- Query params use the existing `Query(default=...)` style, not `Annotated`.
- Read-only: no endpoint mutates state.
- Commits go directly to `main` (established user preference for this repo). No AI attribution in commit messages.
- Test runner: `python -m pytest` from the repo root; `tests/api/` is auto-collected via `testpaths = ["tests"]`.

---

### Task 1: Router scaffold, legacy relocation, API test fixtures

**Files:**
- Create: `app/api/routers/__init__.py` (empty)
- Create: `app/api/routers/legacy.py`
- Create: `tests/api/__init__.py` (empty)
- Create: `tests/api/conftest.py`
- Modify: `app/api/main.py` (gutted to assembly only)
- Test: `tests/api/test_app_assembly.py`

**Interfaces:**
- Consumes: existing endpoint bodies in `app/api/main.py` (portfolio `:20-41`, pnl `:45-70`, trades `:74-108`, stats `:112-162`, swing_trades `:166-216`, swing_stats `:220-310`).
- Produces: `app.api.main.app` (FastAPI instance; `api_main.py` keeps working unchanged), `legacy.dca_router` / `legacy.swing_router`, and test fixtures `mem_db`, `client`, `seed` (factory) used by every later task.

- [ ] **Step 1: Write the failing tests**

`tests/api/__init__.py`: empty file.

`tests/api/conftest.py`:

```python
"""API test fixtures: in-memory SQLite behind the real app + TestClient.

StaticPool + check_same_thread=False are load-bearing: TestClient runs sync
endpoints in a worker thread, and without a shared single connection each
thread would see its own EMPTY in-memory database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import models


@pytest.fixture
def mem_db(monkeypatch):
    eng = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(models, "engine", eng)
    models.Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(mem_db):
    from app.api.main import app

    return TestClient(app)


@pytest.fixture
def seed(mem_db):
    """Factory: seed(model_attr, **fields) inserts a row, returns its PK id (or None)."""

    def _seed(model_attr: str, **fields):
        with Session(mem_db) as s:
            row = getattr(models, model_attr)(**fields)
            s.add(row)
            s.commit()
            return getattr(row, "id", None)

    return _seed


CLOSED_TRADE = dict(
    symbol="DOGEUSDT", mode="paper", limit_price=0.10, entry_price=0.10,
    exit_price=0.11, slot_usd=10.0,
    entry_time="2026-07-16T17:00:22+00:00", exit_time="2026-07-17T00:45:22+00:00",
    hold_bars=32, pnl_pct=0.0892, pnl_usd=0.8811, fill_type="trade_through",
    exit_reason="horizon", status="closed",
)
```

`tests/api/test_app_assembly.py`:

```python
"""App assembly: /health frozen, legacy endpoints relocated, old paths gone."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def test_health_unchanged(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_legacy_dca_portfolio_relocated(client, seed):
    seed("Position", coin="BTC", avg_buy=50000.0, qty=0.01)
    r = client.get("/legacy/dca/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["positions"][0]["coin"] == "BTC"
    assert body["total_cost_usd"] == 500.0


def test_legacy_swing_stats_relocated(client):
    r = client.get("/legacy/swing/stats")
    assert r.status_code == 200
    assert r.json()["trades"] == 0


def test_all_six_legacy_paths_respond(client):
    for path in (
        "/legacy/dca/portfolio", "/legacy/dca/pnl", "/legacy/dca/trades",
        "/legacy/dca/stats", "/legacy/swing/trades", "/legacy/swing/stats",
    ):
        assert client.get(path).status_code == 200, path


def test_old_paths_are_gone(client):
    for path in ("/portfolio", "/pnl", "/trades", "/stats", "/swing/trades", "/swing/stats"):
        assert client.get(path).status_code == 404, path
```

(`CLOSED_TRADE` is imported here so the shared seed payload is exercised from Task 2 on; the import also pins that conftest constants are importable under `--import-mode=importlib`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/ -v`
Expected: FAIL — `/legacy/*` paths return 404 (routers don't exist yet), old paths return 200.

- [ ] **Step 3: Create `app/api/routers/legacy.py`**

Create `app/api/routers/__init__.py` (empty file), then `app/api/routers/legacy.py` with this skeleton:

```python
"""Retired DCA + swing endpoints, relocated verbatim under /legacy/*.

Bodies are the pre-2.0 app/api/main.py functions, unchanged except the
session line (module-attribute engine access — see Global Constraints).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session as SASession

from app.db import models
from app.db.models import Position, SwingTrade, Trade

dca_router = APIRouter(prefix="/legacy/dca", tags=["legacy-dca"])
swing_router = APIRouter(prefix="/legacy/swing", tags=["legacy-swing"])
```

Then move the six functions from the current `app/api/main.py` into it, verbatim, with ONLY these mechanical changes:

| Function (current lines) | New decorator |
|---|---|
| `portfolio` (`main.py:20-41`) | `@dca_router.get("/portfolio")` |
| `pnl` (`main.py:45-70`) | `@dca_router.get("/pnl")` |
| `trades` (`main.py:74-108`) | `@dca_router.get("/trades")` |
| `stats` (`main.py:112-162`) | `@dca_router.get("/stats")` |
| `swing_trades` (`main.py:166-216`) | `@swing_router.get("/trades")` |
| `swing_stats` (`main.py:220-310`) | `@swing_router.get("/stats")` |

In every moved body replace `with SASession(engine) as session:` with `with SASession(models.engine) as session:` (one occurrence per function). No other edits.

- [ ] **Step 4: Rewrite `app/api/main.py` as assembly only**

Replace the whole file with:

```python
"""FastAPI app assembly — routers only, no business logic."""

from fastapi import FastAPI

from app.api.routers.legacy import dca_router, swing_router

app = FastAPI(title="Trade-God API", version="2.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(dca_router)
app.include_router(swing_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: 5 PASS.

- [ ] **Step 6: Run the full suite (nothing else broke)**

Run: `python -m pytest`
Expected: 147 passed (142 existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add app/api/ tests/api/
git commit -m "refactor(api): split into routers, move retired DCA/swing endpoints under /legacy"
```

---

### Task 2: `queries.list_trades` + `GET /intraday/trades`

**Files:**
- Create: `app/api/queries.py`
- Create: `app/api/routers/intraday.py`
- Modify: `app/api/main.py` (include intraday router)
- Test: `tests/api/test_intraday_trades.py`

**Interfaces:**
- Consumes: fixtures from Task 1 (`client`, `seed`, `CLOSED_TRADE`); `models.IntradayTrade`.
- Produces: `queries.list_trades(limit: int = 50, symbol: str | None = None, status: str | None = None, since: str | None = None) -> list[dict]` and `queries._trade_dict(t) -> dict` (reused by nothing outside queries.py); route `GET /intraday/trades`.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_intraday_trades.py`:

```python
"""GET /intraday/trades — columns, pct scaling, filters, ordering."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def test_empty_db_returns_empty_list(client):
    r = client.get("/intraday/trades")
    assert r.status_code == 200
    assert r.json() == []


def test_columns_and_pct_scaling(client, seed):
    seed("IntradayTrade", **CLOSED_TRADE)
    row = client.get("/intraday/trades").json()[0]
    assert row["symbol"] == "DOGEUSDT"
    assert row["pnl_pct"] == 8.92          # 0.0892 fraction -> percent
    assert row["pnl_usd"] == 0.8811
    assert row["hold_bars"] == 32
    assert row["status"] == "closed"
    assert row["fill_type"] == "trade_through"
    assert set(row) == {
        "id", "symbol", "limit_price", "entry_price", "exit_price", "slot_usd",
        "entry_time", "exit_time", "hold_bars", "pnl_pct", "pnl_usd",
        "fill_type", "exit_reason", "status",
    }


def test_open_trade_has_null_exit_fields(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "exit_price": None, "exit_time": None,
                             "hold_bars": None, "pnl_pct": None, "pnl_usd": None,
                             "exit_reason": None, "status": "open"})
    row = client.get("/intraday/trades").json()[0]
    assert row["status"] == "open"
    assert row["pnl_pct"] is None and row["exit_time"] is None


def test_filters_and_ordering(client, seed):
    seed("IntradayTrade", **CLOSED_TRADE)  # DOGEUSDT, entry 07-16
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT",
                             "entry_time": "2026-07-18T01:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT", "status": "open",
                             "entry_time": "2026-07-18T02:00:00+00:00"})

    assert [t["symbol"] for t in client.get("/intraday/trades").json()] == \
        ["XRPUSDT", "XRPUSDT", "DOGEUSDT"]          # newest first (id desc)
    assert len(client.get("/intraday/trades?symbol=xrpusdt").json()) == 2  # upcased
    assert len(client.get("/intraday/trades?status=open").json()) == 1
    assert len(client.get("/intraday/trades?since=2026-07-18T00:00:00").json()) == 2
    assert len(client.get("/intraday/trades?limit=1").json()) == 1


def test_limit_over_500_rejected(client):
    assert client.get("/intraday/trades?limit=501").status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_intraday_trades.py -v`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Create `app/api/queries.py`**

```python
"""Read-only aggregation helpers shared by the JSON routes and the status page.

Every function returns plain dicts/lists so both consumers share one code path.
Engine access is via the models module attribute (see tests/api/conftest.py).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import models


def list_trades(limit: int = 50, symbol: str | None = None,
                status: str | None = None, since: str | None = None) -> list[dict]:
    with Session(models.engine) as session:
        q = session.query(models.IntradayTrade)
        if symbol:
            q = q.filter(models.IntradayTrade.symbol == symbol.upper())
        if status:
            q = q.filter(models.IntradayTrade.status == status.lower())
        if since:
            q = q.filter(models.IntradayTrade.entry_time >= since)
        rows = q.order_by(models.IntradayTrade.id.desc()).limit(limit).all()
    return [_trade_dict(t) for t in rows]


def _trade_dict(t: models.IntradayTrade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "limit_price": t.limit_price,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "slot_usd": t.slot_usd,
        "entry_time": t.entry_time,
        "exit_time": t.exit_time,
        "hold_bars": t.hold_bars,
        "pnl_pct": round(t.pnl_pct * 100, 4) if t.pnl_pct is not None else None,
        "pnl_usd": t.pnl_usd,
        "fill_type": t.fill_type,
        "exit_reason": t.exit_reason,
        "status": t.status,
    }
```

- [ ] **Step 4: Create `app/api/routers/intraday.py` and include it**

```python
"""JSON endpoints over the intraday telemetry tables."""

from fastapi import APIRouter, Query

from app.api import queries

router = APIRouter(prefix="/intraday", tags=["intraday"])


@router.get("/trades")
def trades(
    limit: int = Query(default=50, le=500),
    symbol: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
):
    """Intraday paper trades, newest first."""
    return queries.list_trades(limit=limit, symbol=symbol, status=status, since=since)
```

In `app/api/main.py` add below the existing legacy import:

```python
from app.api.routers.intraday import router as intraday_router
```

and above the legacy includes:

```python
app.include_router(intraday_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/queries.py app/api/routers/intraday.py app/api/main.py tests/api/test_intraday_trades.py
git commit -m "feat(api): GET /intraday/trades"
```

---

### Task 3: `queries.trade_stats` + `GET /intraday/stats`

**Files:**
- Modify: `app/api/queries.py`, `app/api/routers/intraday.py`
- Test: `tests/api/test_intraday_stats.py`

**Interfaces:**
- Consumes: Task 1 fixtures, Task 2 module layout.
- Produces: `queries.trade_stats(since: str | None = None) -> dict` (keys: `trades, win_rate_pct, net_pnl_usd, gross_win_usd, gross_loss_usd, profit_factor, avg_pnl_pct, median_pnl_pct, best_trade, worst_trade, period, by_symbol`; empty → `{"trades": 0, "message": ...}`). Task 6 and Task 7 call this.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_intraday_stats.py`:

```python
"""GET /intraday/stats — hand-computed aggregates over closed trades."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def _seed_three(seed):
    # +1.00 (DOGE), -0.50 (XRP), +0.50 (DOGE) -> net +1.00
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0, "pnl_pct": 0.10,
                             "exit_time": "2026-07-17T00:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT", "pnl_usd": -0.5,
                             "pnl_pct": -0.05, "entry_time": "2026-07-17T05:00:00+00:00",
                             "exit_time": "2026-07-17T12:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 0.5, "pnl_pct": 0.05,
                             "entry_time": "2026-07-18T01:00:00+00:00",
                             "exit_time": "2026-07-18T08:00:00+00:00"})


def test_hand_computed_aggregates(client, seed):
    _seed_three(seed)
    s = client.get("/intraday/stats").json()
    assert s["trades"] == 3
    assert s["win_rate_pct"] == 66.67
    assert s["net_pnl_usd"] == 1.0
    assert s["gross_win_usd"] == 1.5
    assert s["gross_loss_usd"] == 0.5
    assert s["profit_factor"] == 3.0
    assert s["avg_pnl_pct"] == round((10 - 5 + 5) / 3, 4)
    assert s["median_pnl_pct"] == 5.0
    assert s["best_trade"] == {"symbol": "DOGEUSDT", "pnl_usd": 1.0,
                               "exit_time": "2026-07-17T00:00:00+00:00"}
    assert s["worst_trade"]["symbol"] == "XRPUSDT"
    assert s["period"] == {"first_entry": "2026-07-16T17:00:22+00:00",
                           "last_exit": "2026-07-18T08:00:00+00:00"}
    assert s["by_symbol"]["DOGEUSDT"] == {"trades": 2, "wins": 2,
                                          "win_rate_pct": 100.0, "net_pnl": 1.5}
    assert s["by_symbol"]["XRPUSDT"]["win_rate_pct"] == 0.0


def test_open_trades_excluded(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "status": "open", "pnl_usd": None,
                             "pnl_pct": None, "exit_time": None})
    assert client.get("/intraday/stats").json()["trades"] == 0


def test_since_filters_on_entry_time(client, seed):
    _seed_three(seed)
    s = client.get("/intraday/stats?since=2026-07-18T00:00:00").json()
    assert s["trades"] == 1 and s["net_pnl_usd"] == 0.5


def test_empty_shape(client):
    s = client.get("/intraday/stats").json()
    assert s == {"trades": 0, "message": "No closed intraday trades in window."}


def test_all_wins_profit_factor_capped(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    assert client.get("/intraday/stats").json()["profit_factor"] == 999.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_intraday_stats.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement**

Append to `app/api/queries.py` (add `import statistics` to the imports):

```python
def trade_stats(since: str | None = None) -> dict:
    with Session(models.engine) as session:
        q = session.query(models.IntradayTrade).filter(
            models.IntradayTrade.status == "closed")
        if since:
            q = q.filter(models.IntradayTrade.entry_time >= since)
        closed = q.order_by(models.IntradayTrade.exit_time.asc()).all()

    if not closed:
        return {"trades": 0, "message": "No closed intraday trades in window."}

    pnls = [t.pnl_usd or 0.0 for t in closed]
    pcts = [(t.pnl_pct or 0.0) * 100 for t in closed]
    wins = [p for p in pnls if p > 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    else:
        profit_factor = 999.0 if gross_win > 0 else 0.0

    best = max(closed, key=lambda t: t.pnl_usd or 0.0)
    worst = min(closed, key=lambda t: t.pnl_usd or 0.0)

    by_symbol: dict[str, dict] = {}
    for t in closed:
        s = by_symbol.setdefault(t.symbol, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        s["trades"] += 1
        if (t.pnl_usd or 0) > 0:
            s["wins"] += 1
        s["net_pnl"] += t.pnl_usd or 0.0
    for s in by_symbol.values():
        s["win_rate_pct"] = round(s["wins"] / s["trades"] * 100, 2)
        s["net_pnl"] = round(s["net_pnl"], 4)

    return {
        "trades": len(closed),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 2),
        "net_pnl_usd": round(sum(pnls), 4),
        "gross_win_usd": round(gross_win, 4),
        "gross_loss_usd": round(gross_loss, 4),
        "profit_factor": profit_factor,
        "avg_pnl_pct": round(sum(pcts) / len(pcts), 4),
        "median_pnl_pct": round(statistics.median(pcts), 4),
        "best_trade": {"symbol": best.symbol, "pnl_usd": round(best.pnl_usd or 0, 4),
                       "exit_time": best.exit_time},
        "worst_trade": {"symbol": worst.symbol, "pnl_usd": round(worst.pnl_usd or 0, 4),
                        "exit_time": worst.exit_time},
        "period": {"first_entry": min(t.entry_time for t in closed),
                   "last_exit": max((t.exit_time for t in closed if t.exit_time),
                                    default=None)},
        "by_symbol": by_symbol,
    }
```

Append to `app/api/routers/intraday.py`:

```python
@router.get("/stats")
def stats(since: str | None = Query(default=None)):
    """Aggregate performance over closed trades (field names mirror /legacy/swing/stats)."""
    return queries.trade_stats(since=since)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/queries.py app/api/routers/intraday.py tests/api/test_intraday_stats.py
git commit -m "feat(api): GET /intraday/stats"
```

---

### Task 4: `queries.fill_stats` + `GET /intraday/fills`

**Files:**
- Modify: `app/api/queries.py`, `app/api/routers/intraday.py`
- Test: `tests/api/test_intraday_fills.py`

**Interfaces:**
- Consumes: Task 1 fixtures; `models.IntradayLimit`.
- Produces: `queries.fill_stats() -> dict` with keys `total_placed, pending, admitted, by_outcome` where `by_outcome` maps each of `trade_through/touch_only/miss/no_data` to `{"count": int, "pct": float}` (pct of RESOLVED limits, cumulative since inception — Telegram weekly-report semantics). Task 6 and Task 7 call this.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_intraday_fills.py`:

```python
"""GET /intraday/fills — outcome distribution over intraday_limits."""

from __future__ import annotations

LIMIT = dict(symbol="DOGEUSDT", limit_price=0.1,
             placed_at="2026-07-16T17:00:00+00:00",
             resolved_at="2026-07-16T17:15:00+00:00")


def test_distribution(client, seed):
    seed("IntradayLimit", **LIMIT, outcome="trade_through", bar_low=0.09, admitted=True)
    seed("IntradayLimit", **LIMIT, outcome="trade_through", bar_low=0.09, admitted=False)
    seed("IntradayLimit", **LIMIT, outcome="touch_only", bar_low=0.1, admitted=False)
    seed("IntradayLimit", **LIMIT, outcome="miss", bar_low=0.11, admitted=False)
    seed("IntradayLimit", symbol="DOGEUSDT", limit_price=0.1,
         placed_at="2026-07-18T20:45:00+00:00")   # unresolved: outcome NULL

    f = client.get("/intraday/fills").json()
    assert f["total_placed"] == 5
    assert f["pending"] == 1
    assert f["admitted"] == 1
    assert f["by_outcome"]["trade_through"] == {"count": 2, "pct": 50.0}
    assert f["by_outcome"]["touch_only"] == {"count": 1, "pct": 25.0}
    assert f["by_outcome"]["miss"] == {"count": 1, "pct": 25.0}
    assert f["by_outcome"]["no_data"] == {"count": 0, "pct": 0.0}


def test_empty_db(client):
    f = client.get("/intraday/fills").json()
    assert f["total_placed"] == 0 and f["pending"] == 0
    assert f["by_outcome"]["trade_through"] == {"count": 0, "pct": 0.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_intraday_fills.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement**

Append to `app/api/queries.py`:

```python
OUTCOMES = ("trade_through", "touch_only", "miss", "no_data")


def fill_stats() -> dict:
    with Session(models.engine) as session:
        rows = session.query(models.IntradayLimit).all()

    resolved = [r for r in rows if r.outcome is not None]
    by_outcome = {}
    for name in OUTCOMES:
        count = sum(1 for r in resolved if r.outcome == name)
        by_outcome[name] = {
            "count": count,
            "pct": round(count / len(resolved) * 100, 2) if resolved else 0.0,
        }
    return {
        "total_placed": len(rows),
        "pending": len(rows) - len(resolved),
        "admitted": sum(1 for r in resolved if r.admitted),
        "by_outcome": by_outcome,
    }
```

Append to `app/api/routers/intraday.py`:

```python
@router.get("/fills")
def fills():
    """Cumulative limit-outcome telemetry — the measurement that decides go-live."""
    return queries.fill_stats()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/queries.py app/api/routers/intraday.py tests/api/test_intraday_fills.py
git commit -m "feat(api): GET /intraday/fills"
```

---

### Task 5: `queries.engine_state` + `GET /intraday/state`

**Files:**
- Modify: `app/api/queries.py`, `app/api/routers/intraday.py`
- Test: `tests/api/test_intraday_state.py`

**Interfaces:**
- Consumes: Task 1 fixtures; `models.IntradayState` (`key`, JSON `value`, `updated`); state keys `paper_book`, `killswitch`, `universe` written by the engine.
- Produces: `queries.engine_state(now: datetime | None = None) -> dict` with keys `equity, slot_usd, positions, pending, killswitch, universe, updated` (+ optional `warning`). `killswitch` includes derived `day_pnl_pct` and `drawdown_from_peak_pct` (percent, 4dp). Task 6 and Task 7 call this.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_intraday_state.py`:

```python
"""GET /intraday/state — deserialized engine state with derived percentages."""

from __future__ import annotations

BOOK = {"equity": 101.9396, "max_k": 10, "horizon_bars": 32, "entry_cost": 0.0002,
        "exit_cost": 0.0008, "slot_usd": 10.0, "pending": {},
        "positions": {"WLDUSDT": {"entry": 0.3599, "bars": 5}}}
KS = {"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": False,
      "day": "2026-07-18", "day_anchor": 100.2878, "peak": 102.0052}
UNI = {"symbols": ["BTCUSDT", "ETHUSDT"], "refreshed_ms": 1784219517039}


def _seed_state(seed, book=BOOK, ks=KS, uni=UNI):
    seed("IntradayState", key="paper_book", value=book,
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="killswitch", value=ks,
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="universe", value=uni,
         updated="2026-07-18T20:30:23+00:00")


def test_state_deserialized_with_derived_pcts(client, seed):
    _seed_state(seed)
    s = client.get("/intraday/state").json()
    assert s["equity"] == 101.9396
    assert s["slot_usd"] == 10.0
    assert "WLDUSDT" in s["positions"]
    assert s["killswitch"]["halted"] is False
    # 101.9396/100.2878 - 1 = +1.64706% ; 101.9396/102.0052 - 1 = -0.06431%
    assert s["killswitch"]["day_pnl_pct"] == 1.6471
    assert s["killswitch"]["drawdown_from_peak_pct"] == -0.0643
    assert s["universe"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert s["universe"]["age_days"] is not None
    assert s["updated"]["paper_book"] == "2026-07-18T20:30:23+00:00"
    assert "warning" not in s


def test_missing_rows_yield_nulls_not_500(client):
    s_resp = client.get("/intraday/state")
    assert s_resp.status_code == 200
    s = s_resp.json()
    assert s["equity"] is None
    assert s["positions"] == {} and s["pending"] == {}
    assert s["killswitch"]["halted"] is None
    assert s["universe"]["symbols"] == []


def test_unreadable_state_row_warns_not_500(client, seed):
    seed("IntradayState", key="paper_book", value=["not", "a", "dict"],
         updated="2026-07-18T20:30:23+00:00")
    s = client.get("/intraday/state").json()
    assert s["equity"] is None
    assert "paper_book" in s["warning"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_intraday_state.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement**

Append to `app/api/queries.py` (add `from datetime import datetime, timezone` to the imports):

```python
_STATE_KEYS = ("paper_book", "killswitch", "universe")


def engine_state(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    raw: dict[str, dict | None] = {}
    updated: dict[str, str] = {}
    warnings: list[str] = []
    with Session(models.engine) as session:
        for key in _STATE_KEYS:
            row = session.get(models.IntradayState, key)
            if row is None:
                raw[key] = None
                continue
            updated[key] = row.updated
            try:
                raw[key] = dict(row.value)
            except (TypeError, ValueError):
                raw[key] = None
                warnings.append(f"state row '{key}' unreadable")

    book = raw["paper_book"] or {}
    ks = raw["killswitch"] or {}
    uni = raw["universe"] or {}
    equity = book.get("equity")

    out = {
        "equity": equity,
        "slot_usd": book.get("slot_usd"),
        "positions": book.get("positions", {}),
        "pending": book.get("pending", {}),
        "killswitch": {
            "halted": ks.get("halted"),
            "day": ks.get("day"),
            "day_anchor": ks.get("day_anchor"),
            "peak": ks.get("peak"),
            "daily_loss_pct": ks.get("daily_loss_pct"),
            "max_dd_pct": ks.get("max_dd_pct"),
            "day_pnl_pct": _pct_change(equity, ks.get("day_anchor")),
            "drawdown_from_peak_pct": _pct_change(equity, ks.get("peak")),
        },
        "universe": {
            "symbols": uni.get("symbols", []),
            "refreshed_ms": uni.get("refreshed_ms"),
            "age_days": _age_days(uni.get("refreshed_ms"), now),
        },
        "updated": updated,
    }
    if warnings:
        out["warning"] = "; ".join(warnings)
    return out


def _pct_change(value: float | None, base: float | None) -> float | None:
    if value is None or not base:
        return None
    return round((value / base - 1) * 100, 4)


def _age_days(refreshed_ms: int | None, now: datetime) -> float | None:
    if refreshed_ms is None:
        return None
    then = datetime.fromtimestamp(refreshed_ms / 1000, tz=timezone.utc)
    return round((now - then).total_seconds() / 86400, 1)
```

Append to `app/api/routers/intraday.py`:

```python
@router.get("/state")
def state():
    """Engine state: equity, open book, kill-switch latch, universe."""
    return queries.engine_state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS. (If `day_pnl_pct` rounds differently, recompute by hand — `round((101.9396 / 100.2878 - 1) * 100, 4)` — and fix the TEST, not the rounding rule.)

- [ ] **Step 5: Commit**

```bash
git add app/api/queries.py app/api/routers/intraday.py tests/api/test_intraday_state.py
git commit -m "feat(api): GET /intraday/state"
```

---

### Task 6: `queries.gate_progress` + `GET /intraday/gate`

**Files:**
- Modify: `app/api/queries.py`, `app/api/routers/intraday.py`
- Test: `tests/api/test_intraday_gate.py`

**Interfaces:**
- Consumes: `trade_stats()` (Task 3), `fill_stats()` (Task 4), `engine_state()` (Task 5).
- Produces: `queries.gate_progress(today: date | None = None) -> dict` with keys `window {start, end, days_elapsed, days_remaining}`, `criteria {cumulative_pnl, kill_switch, trade_through_rate_pct}`, `on_track: bool`; module constants `GATE_START`, `GATE_END`. Task 7 calls this.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_intraday_gate.py`:

```python
"""GET /intraday/gate — 4-week go-live gate tracker.

Date arithmetic is tested through gate_progress(today=...) so tests never
depend on the wall clock; the endpoint test asserts shape only.
"""

from __future__ import annotations

from datetime import date

from app.api import queries
from tests.api.conftest import CLOSED_TRADE


def test_window_math_mid_window(mem_db):
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["window"] == {"start": "2026-07-16", "end": "2026-08-13",
                           "days_elapsed": 2, "days_remaining": 26}


def test_window_clamps_before_and_after(mem_db):
    assert queries.gate_progress(today=date(2026, 7, 10))["window"]["days_elapsed"] == 0
    late = queries.gate_progress(today=date(2026, 9, 1))["window"]
    assert late["days_elapsed"] == 28 and late["days_remaining"] == 0


def test_pnl_criterion_edges(mem_db, seed):
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["cumulative_pnl"] == {"value_usd": 0.0, "pass": True}  # no trades: 0 >= 0

    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": -0.01})
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["cumulative_pnl"]["pass"] is False
    assert g["on_track"] is False


def test_halt_latch_blocks_on_track(mem_db, seed):
    seed("IntradayState", key="killswitch",
         value={"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": True,
                "day": "2026-07-18", "day_anchor": 100.0, "peak": 100.0},
         updated="2026-07-18T00:00:00+00:00")
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["kill_switch"]["halted_now"] is True
    assert g["criteria"]["kill_switch"]["daily_halt_at_pct"] == -5.0
    assert g["criteria"]["kill_switch"]["drawdown_halt_at_pct"] == -20.0
    assert "Telegram" in g["criteria"]["kill_switch"]["note"]
    assert g["on_track"] is False


def test_trade_through_rate_from_fills(mem_db, seed):
    seed("IntradayLimit", symbol="A", limit_price=1.0, placed_at="t",
         resolved_at="t", outcome="trade_through", admitted=True)
    seed("IntradayLimit", symbol="A", limit_price=1.0, placed_at="t",
         resolved_at="t", outcome="miss", admitted=False)
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["trade_through_rate_pct"] == 50.0


def test_no_resolved_limits_rate_is_null(mem_db):
    assert queries.gate_progress(today=date(2026, 7, 18))["criteria"]["trade_through_rate_pct"] is None


def test_endpoint_shape(client):
    g = client.get("/intraday/gate").json()
    assert set(g) == {"window", "criteria", "on_track"}
    assert set(g["criteria"]) == {"cumulative_pnl", "kill_switch", "trade_through_rate_pct"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_intraday_gate.py -v`
Expected: FAIL — `gate_progress` not defined.

- [ ] **Step 3: Implement**

Append to `app/api/queries.py` (add `date` to the datetime import):

```python
# 4-week telemetry window — docs/intraday_operations.md "Go-live gate (manual only)".
GATE_START = date(2026, 7, 16)
GATE_END = date(2026, 8, 13)


def gate_progress(today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    stats = trade_stats()
    ks = engine_state()["killswitch"]
    fills = fill_stats()

    net_pnl = stats["net_pnl_usd"] if stats["trades"] else 0.0
    resolved = fills["total_placed"] - fills["pending"]
    tt_pct = fills["by_outcome"]["trade_through"]["pct"] if resolved else None
    halted = bool(ks["halted"])
    window_days = (GATE_END - GATE_START).days

    return {
        "window": {
            "start": GATE_START.isoformat(),
            "end": GATE_END.isoformat(),
            "days_elapsed": min(max((today - GATE_START).days, 0), window_days),
            "days_remaining": max((GATE_END - today).days, 0),
        },
        "criteria": {
            "cumulative_pnl": {"value_usd": net_pnl, "pass": net_pnl >= 0},
            "kill_switch": {
                "halted_now": halted,
                "day_pnl_pct": ks["day_pnl_pct"],
                "daily_halt_at_pct": _halt_threshold_pct(ks["daily_loss_pct"]),
                "drawdown_from_peak_pct": ks["drawdown_from_peak_pct"],
                "drawdown_halt_at_pct": _halt_threshold_pct(ks["max_dd_pct"]),
                "note": "current latch only; trip history lives in Telegram",
            },
            "trade_through_rate_pct": tt_pct,
        },
        "on_track": net_pnl >= 0 and not halted,
    }


def _halt_threshold_pct(fraction: float | None) -> float | None:
    return None if fraction is None else -round(fraction * 100, 2)
```

Append to `app/api/routers/intraday.py`:

```python
@router.get("/gate")
def gate():
    """Progress against the 4-week go-live gate (ends 2026-08-13)."""
    return queries.gate_progress()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/queries.py app/api/routers/intraday.py tests/api/test_intraday_gate.py
git commit -m "feat(api): GET /intraday/gate — go-live gate tracker"
```

---

### Task 7: Status page with sparkline (`GET /`)

**Files:**
- Create: `app/api/status_page.py`
- Modify: `app/api/queries.py` (add `realized_equity_curve`), `app/api/main.py` (include page router)
- Test: `tests/api/test_status_page.py`

**Interfaces:**
- Consumes: `engine_state()`, `gate_progress()`, `trade_stats()`, `fill_stats()`, `list_trades()`; `PAPER_EQUITY` from `app/intraday/config.py:9`.
- Produces: `queries.realized_equity_curve() -> list[float]` (starts at `PAPER_EQUITY`, one point per closed trade by exit_time); `status_page.render_sparkline(points: list[float]) -> str` (empty string for <2 points); `status_page.router` serving `GET /` as HTML.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_status_page.py`:

```python
"""GET / — self-contained HTML status page."""

from __future__ import annotations

from app.api import queries
from app.api.status_page import render_sparkline
from tests.api.conftest import CLOSED_TRADE

KS = {"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": False,
      "day": "2026-07-18", "day_anchor": 100.0, "peak": 102.0}


def _seed_full(seed, halted=False):
    seed("IntradayState", key="paper_book",
         value={"equity": 101.94, "slot_usd": 10.0, "pending": {},
                "positions": {"WLDUSDT": {"entry": 0.3599}}},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="killswitch", value={**KS, "halted": halted},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="universe",
         value={"symbols": ["WLDUSDT"], "refreshed_ms": 1784219517039},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "WLDUSDT", "pnl_usd": -0.25,
                             "exit_time": "2026-07-18T08:00:00+00:00"})


def test_realized_equity_curve(mem_db, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": -0.25,
                             "exit_time": "2026-07-18T08:00:00+00:00"})
    assert queries.realized_equity_curve() == [100.0, 101.0, 100.75]


def test_sparkline_svg():
    svg = render_sparkline([100.0, 101.0, 100.75])
    assert svg.startswith("<svg") and "polyline" in svg


def test_sparkline_needs_two_points():
    assert render_sparkline([100.0]) == ""


def test_page_renders_seeded_data(client, seed):
    _seed_full(seed)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "101.94" in body            # equity headline
    assert "WLDUSDT" in body           # open position + trade row
    assert "<svg" in body              # sparkline (3-point curve)
    assert "HALTED" not in body


def test_halted_badge(client, seed):
    _seed_full(seed, halted=True)
    assert "HALTED" in client.get("/").text


def test_empty_db_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "no data yet" in r.text.lower()
    assert "<svg" not in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_status_page.py -v`
Expected: FAIL — `app.api.status_page` does not exist.

- [ ] **Step 3: Add `realized_equity_curve` to `app/api/queries.py`**

Add `from app.intraday.config import PAPER_EQUITY` to the imports, then append:

```python
def realized_equity_curve() -> list[float]:
    """Equity after each closed trade (realized only — blind to open-position drift)."""
    with Session(models.engine) as session:
        closed = (
            session.query(models.IntradayTrade)
            .filter(models.IntradayTrade.status == "closed")
            .order_by(models.IntradayTrade.exit_time.asc())
            .all()
        )
    points = [PAPER_EQUITY]
    for t in closed:
        points.append(round(points[-1] + (t.pnl_usd or 0.0), 4))
    return points
```

- [ ] **Step 4: Create `app/api/status_page.py`**

```python
"""GET / — self-contained HTML status page built from queries.py dicts.

No external assets, no JS: inline CSS and a meta-refresh. The page is only
reachable through the SSH tunnel (port 8000 is closed at the firewall).
"""

from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api import queries

router = APIRouter()


def render_sparkline(points: list[float], width: int = 560, height: int = 80) -> str:
    if len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    step = width / (len(points) - 1)
    coords = " ".join(
        f"{i * step:.1f},{height - 4 - (p - lo) / span * (height - 8):.1f}"
        for i, p in enumerate(points)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="spark" role="img">'
        f'<polyline points="{coords}" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/></svg>'
    )


def _fmt(v, digits: int = 2, suffix: str = "") -> str:
    return "—" if v is None else f"{v:.{digits}f}{suffix}"


def _tick(ok: bool | None) -> str:
    return {True: "✅", False: "❌"}.get(ok, "—")


def build_page() -> str:
    state = queries.engine_state()
    gate = queries.gate_progress()
    stats = queries.trade_stats()
    fills = queries.fill_stats()
    trades = queries.list_trades(limit=10)
    curve = queries.realized_equity_curve()

    ks = state["killswitch"]
    halted_badge = '<span class="badge">HALTED</span>' if ks["halted"] else ""
    net_pnl = stats["net_pnl_usd"] if stats["trades"] else 0.0

    headline = (
        '<div class="cards">'
        f'<div class="card"><div class="k">Equity</div><div class="v">${_fmt(state["equity"])}</div></div>'
        f'<div class="card"><div class="k">Net realized</div><div class="v">${_fmt(net_pnl)}</div></div>'
        f'<div class="card"><div class="k">Today</div><div class="v">{_fmt(ks["day_pnl_pct"], suffix="%")}</div></div>'
        f'<div class="card"><div class="k">From peak</div><div class="v">{_fmt(ks["drawdown_from_peak_pct"], suffix="%")}</div></div>'
        f"{halted_badge}</div>"
    )

    w = gate["window"]
    c = gate["criteria"]
    gate_html = (
        f'<h2>Go-live gate <small>day {w["days_elapsed"]} of 28 · ends {w["end"]}</small></h2>'
        "<ul>"
        f'<li>{_tick(c["cumulative_pnl"]["pass"])} cumulative PnL ${_fmt(c["cumulative_pnl"]["value_usd"])}</li>'
        f'<li>{_tick(not c["kill_switch"]["halted_now"])} kill-switch clear '
        f'(today {_fmt(c["kill_switch"]["day_pnl_pct"], suffix="%")} vs {_fmt(c["kill_switch"]["daily_halt_at_pct"], suffix="%")}, '
        f'peak {_fmt(c["kill_switch"]["drawdown_from_peak_pct"], suffix="%")} vs {_fmt(c["kill_switch"]["drawdown_halt_at_pct"], suffix="%")}; '
        f'{html.escape(c["kill_switch"]["note"])})</li>'
        f'<li>trade-through rate: {_fmt(c["trade_through_rate_pct"], suffix="%")}</li>'
        "</ul>"
    )

    spark = render_sparkline(curve)
    spark_html = (
        f"<h2>Realized equity</h2>{spark}" if spark
        else "<h2>Realized equity</h2><p>no data yet — fewer than 2 closed trades</p>"
    )

    def dict_table(title: str, d: dict) -> str:
        if not d:
            return f"<h2>{title}</h2><p>none</p>"
        rows = "".join(
            f"<tr><td>{html.escape(str(sym))}</td><td>{html.escape(str(v))}</td></tr>"
            for sym, v in d.items()
        )
        return f"<h2>{title}</h2><table><tr><th>symbol</th><th>detail</th></tr>{rows}</table>"

    if trades:
        trade_rows = "".join(
            f"<tr><td>{html.escape(t['symbol'])}</td><td>{html.escape(t['entry_time'][:16])}</td>"
            f"<td>{_fmt(t['pnl_pct'], suffix='%')}</td><td>{_fmt(t['pnl_usd'], 4)}</td>"
            f"<td>{html.escape(t['status'])}</td></tr>"
            for t in trades
        )
        trades_html = ("<h2>Recent trades</h2><table>"
                       "<tr><th>symbol</th><th>entry</th><th>gross %</th><th>net USDT</th><th>status</th></tr>"
                       f"{trade_rows}</table>")
    else:
        trades_html = "<h2>Recent trades</h2><p>no data yet</p>"

    fills_html = (
        "<h2>Fill telemetry</h2><table><tr><th>outcome</th><th>count</th><th>pct</th></tr>"
        + "".join(
            f"<tr><td>{name}</td><td>{fills['by_outcome'][name]['count']}</td>"
            f"<td>{fills['by_outcome'][name]['pct']}%</td></tr>"
            for name in queries.OUTCOMES
        )
        + f"<tr><td>pending</td><td>{fills['pending']}</td><td>—</td></tr></table>"
    )

    warning = (f'<p class="warn">{html.escape(state["warning"])}</p>'
               if state.get("warning") else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>Trade-God — Intraday</title>
<style>
 body {{ font: 14px/1.5 monospace; margin: 2rem auto; max-width: 640px;
        background: #101418; color: #d8dee9; }}
 h2 {{ font-size: 1rem; border-bottom: 1px solid #2e3440; padding-bottom: .2rem; }}
 small {{ color: #7b88a1; font-weight: normal; }}
 table {{ border-collapse: collapse; width: 100%; }}
 td, th {{ text-align: left; padding: .15rem .6rem .15rem 0; }}
 th {{ color: #7b88a1; }}
 .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }}
 .card .k {{ color: #7b88a1; font-size: .8rem; }}
 .card .v {{ font-size: 1.3rem; }}
 .badge {{ background: #bf616a; color: #fff; padding: .2rem .6rem; border-radius: 4px; }}
 .spark {{ width: 100%; height: 80px; color: #88c0d0; }}
 .warn {{ color: #ebcb8b; }}
</style></head><body>
<h1>Intraday paper engine</h1>
{warning}
{headline}
{gate_html}
{spark_html}
{dict_table("Open positions", state["positions"])}
{dict_table("Pending limits", state["pending"])}
{trades_html}
{fills_html}
</body></html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def status_page():
    return build_page()
```

- [ ] **Step 5: Include the router in `app/api/main.py`**

Add the import:

```python
from app.api.status_page import router as status_router
```

and, above the other includes:

```python
app.include_router(status_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/api/ -v`
Expected: all PASS.

- [ ] **Step 7: Eyeball the page locally**

```bash
DATABASE_URL="sqlite:///$(mktemp -d)/page.db" python - <<'EOF'
from app.db import models
models.init_db()
from sqlalchemy.orm import Session
with Session(models.engine) as s:
    s.add(models.IntradayTrade(symbol="WLDUSDT", mode="paper", limit_price=0.36,
        entry_price=0.36, exit_price=0.37, slot_usd=10.0,
        entry_time="2026-07-18T12:45:00+00:00", exit_time="2026-07-18T20:30:00+00:00",
        hold_bars=32, pnl_pct=0.0303, pnl_usd=0.2955, fill_type="trade_through",
        exit_reason="horizon", status="closed"))
    s.commit()
from app.api.status_page import build_page
print(build_page())
EOF
```

Expected: full HTML document printed, containing the equity card, gate list, and trade row. (Optional: redirect to a file and open in a browser.)

- [ ] **Step 8: Commit**

```bash
git add app/api/status_page.py app/api/queries.py app/api/main.py tests/api/test_status_page.py
git commit -m "feat(api): HTML status page with realized-equity sparkline at /"
```

---

### Task 8: Docs, full verification, deploy

**Files:**
- Modify: `CLAUDE.md` (FastAPI endpoints line), `docs/intraday_operations.md` (Monitoring section)
- No code changes.

**Interfaces:**
- Consumes: everything above, deployed via the standard Lightsail flow (memory: `project_phase3_deploy_2026-07-16`).
- Produces: live API on the box; docs matching reality.

- [ ] **Step 1: Update `CLAUDE.md`**

Replace the line:

```markdown
## FastAPI Endpoints (port 8000)
`GET /health` `/portfolio` `/pnl` `/trades` `/stats` `/docs`
```

with:

```markdown
## FastAPI Endpoints (port 8000, tunnel-only)
`GET /` (HTML status page) `/health` `/intraday/{trades,stats,fills,state,gate}`
`/legacy/dca/{portfolio,pnl,trades,stats}` `/legacy/swing/{trades,stats}` `/docs`
```

- [ ] **Step 2: Update `docs/intraday_operations.md`**

In the **Monitoring** section, replace the closing paragraph
("The FastAPI service (port 8000) is unchanged and serves only legacy-table history; there are deliberately no intraday REST endpoints in Phase 3.")
with:

```markdown
**API** — since 2026-07-18 the FastAPI service also serves the intraday telemetry
(design: `docs/superpowers/specs/2026-07-18-intraday-api-design.md`). Port 8000 stays
closed at the firewall; tunnel in with `ssh -L 8000:localhost:8000 <lightsail-host>`, then:

- `http://localhost:8000/` — HTML status page (equity, gate progress, sparkline, open book)
- `GET /intraday/trades|stats|fills|state|gate` — JSON telemetry
- `GET /legacy/dca/*`, `/legacy/swing/*` — retired-bot history (old root paths removed)

The gate endpoint reports the CURRENT kill-switch latch only — past trips leave no DB
trace, so "zero trips" is still verified from Telegram ⛔ history.
```

- [ ] **Step 3: Full suite + compose sanity**

Run: `python -m pytest && docker compose config --quiet && echo OK`
Expected: all tests pass, `OK`.

- [ ] **Step 4: Commit and push to GitHub**

```bash
git add CLAUDE.md docs/intraday_operations.md
git commit -m "docs: record intraday API endpoints and tunnel access"
git push origin main
```

- [ ] **Step 5: Deploy to Lightsail**

```bash
GIT_SSH_COMMAND="ssh -i LightsailDefaultKey-ap-southeast-1.pem" \
  git push ssh://ubuntu@54.169.100.56/home/ubuntu/trade-god main:refs/heads/deploy
ssh -i LightsailDefaultKey-ap-southeast-1.pem ubuntu@54.169.100.56 \
  "cd ~/trade-god && git merge --ff-only deploy && git log -1 --oneline && \
   docker compose up -d --build api"
```

Expected: fast-forward merge, `git log -1` shows the docs commit, api container rebuilt and started. `intraday` and `db` must NOT be recreated.

- [ ] **Step 6: Verify live**

```bash
ssh -i LightsailDefaultKey-ap-southeast-1.pem ubuntu@54.169.100.56 \
  "sleep 70; docker inspect -f '{{.State.Health.Status}}' trade-god-api-1; \
   docker exec trade-god-api-1 python -c \"import urllib.request; \
print(urllib.request.urlopen('http://localhost:8000/intraday/gate').read().decode()[:300])\""
```

Expected: `healthy`, then gate JSON with `days_elapsed` matching today. Finally, tunnel in (`ssh -i <key> -L 8000:localhost:8000 ubuntu@54.169.100.56`) and load `http://localhost:8000/` in a browser — status page renders with live numbers.

- [ ] **Step 7: Save project memory**

Write a `project` memory (per global CLAUDE.md memory rules) covering: intraday API + status page shipped, router split with `/legacy/*` relocation, the `models.engine` monkeypatch-compatibility constraint, the StaticPool SQLite TestClient gotcha, and the gate endpoint's kill-switch-history limitation.
