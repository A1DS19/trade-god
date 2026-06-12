# Phase B: Research Data Warehouse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A persistent, point-in-time research data warehouse (parquet + DuckDB) for the top-100 Binance USDT-M perps — klines, funding, premium index (basis), OI, long/short — with a resumable throttled backfill CLI and a gap checker, so signal research and backtests stop re-downloading from Binance (the 2026-06-05 IP-ban cause).

**Architecture:** New top-level `research/` package, excluded from the Docker image; dev-only deps in `requirements-research.txt` (pandas, pyarrow, duckdb) — the live bot stays stdlib-pure. One parquet file per dataset per symbol under gitignored `research/warehouse/`. `store.py` owns parquet I/O (upsert keyed on the dataset's time column, high-water marks); `binance_source.py` owns throttled paginated fetching (normalized list-of-dict rows); `universe.py` resolves the top-N by 24h quote volume; `backfill.py` and `check.py` are the CLIs. All endpoints used are UNSIGNED market data — the backfill needs no API keys (`Client("", "")`).

**Tech Stack:** Python 3.12+ (dev box runs 3.14), python-binance 1.0.19, pandas, pyarrow, duckdb (query layer only — nothing in this phase requires writing duckdb code beyond the dep). Tests: pytest; `tests/research/conftest.py` does `pytest.importorskip("pandas")` so the suite passes on machines without research deps.

**Verified facts (2026-06-12):** python-binance 1.0.19 has `futures_klines`, `futures_funding_rate`, `futures_open_interest_hist`, `futures_global_longshort_ratio`, `futures_ticker`, `futures_exchange_info` — but NO `futures_premium_index_klines`; premium index klines go through `client._request_futures_api("get", "premiumIndexKlines", False, data={...})` (unsigned; same array shape as klines). `futures_exchange_info()` symbols carry `onboardDate` (ms). 527 USDT perps currently TRADING. OI/L-S history endpoints only serve the trailing ~30 days (period="1h", limit max 500). Funding history: limit max 1000. Klines: limit max 1500.

**Context for the engineer:** repo /home/dev/projects/trade-god. Spec: `docs/superpowers/specs/2026-06-12-quant-strategy-overhaul-design.md` (Phase B section). Run tests with `python -m pytest -q` (baseline: 102 passed, 1 skipped). The existing pagination pattern to mirror lives in `app/swing/backtest_replay/engine.py:_fetch_klines` (cursor advance + non-advancing-cursor guard + stop on short batch). Kline array: `[open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_vol, taker_buy_quote_vol, ignore]`.

---

### Task 0: Branch + deps (controller runs this)

- [ ] `git checkout -b feat/research-warehouse`
- [ ] `python -m pip install --user pandas pyarrow duckdb` (versions land in requirements-research.txt in Task 1)

---

### Task 1: Scaffolding — package, config, ignores, test conftest

**Files:**
- Create: `requirements-research.txt`, `research/__init__.py`, `research/config.py`, `tests/research/__init__.py`, `tests/research/conftest.py`
- Modify: `.gitignore`, `.dockerignore`

- [ ] **Step 1.1:** `requirements-research.txt` (pin to the versions just installed — check with `python -m pip show pandas pyarrow duckdb | grep -E "Name|Version"`):

```
# Research-only dependencies (dev machine). NEVER installed in the Docker image —
# the live bot stays stdlib + python-binance. See docs/superpowers/specs/2026-06-12-*.md
pandas==<installed>
pyarrow==<installed>
duckdb==<installed>
```

- [ ] **Step 1.2:** `research/__init__.py`:

```python
"""Research data warehouse + signal research tooling (dev machine only).

Not deployed: excluded from the Docker image via .dockerignore. Uses
requirements-research.txt deps (pandas/pyarrow/duckdb) that prod never installs.
"""
```

- [ ] **Step 1.3:** `research/config.py`:

```python
"""Warehouse layout and dataset definitions."""

import os
from pathlib import Path

# Override in tests / alternate machines via env.
WAREHOUSE_DIR = Path(os.environ.get("RESEARCH_WAREHOUSE_DIR", str(Path(__file__).parent / "warehouse")))

RATE_LIMIT_DELAY = 0.5  # seconds between REST requests; never run from the prod IP

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS

# dataset name -> (time column, expected bar spacing in ms; None = irregular)
DATASETS: dict[str, tuple[str, int | None]] = {
    "klines_1h": ("open_time", HOUR_MS),
    "klines_4h": ("open_time", 4 * HOUR_MS),
    "klines_1d": ("open_time", DAY_MS),
    "funding": ("funding_time", 8 * HOUR_MS),
    "premium_index_1h": ("open_time", HOUR_MS),
    "oi_1h": ("timestamp", HOUR_MS),
    "long_short_1h": ("timestamp", HOUR_MS),
}

# OI / long-short endpoints only serve the trailing ~30 days; clamp with margin.
ROLLING_WINDOW_MS = 29 * DAY_MS
ROLLING_DATASETS = {"oi_1h", "long_short_1h"}
```

- [ ] **Step 1.4:** `tests/research/__init__.py` empty; `tests/research/conftest.py`:

```python
"""Research tests need the dev-only deps; skip the whole directory without them."""

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
```

- [ ] **Step 1.5:** Append to `.gitignore`:

```
# research warehouse data (parquet) — local only
research/warehouse/
```

Append to `.dockerignore`:

```
# research tooling never ships in images (dev-only deps + data)
research/
requirements-research.txt
```

- [ ] **Step 1.6:** Verify + commit. `python -m pytest -q` → 102 passed, 1 skipped (unchanged); `python -c "from research import config; print(config.DATASETS['klines_1h'])"` → `('open_time', 3600000)`.

```bash
git add requirements-research.txt research/__init__.py research/config.py tests/research/ .gitignore .dockerignore
git commit -m "feat(research): warehouse scaffolding — package, dataset config, dev-only deps, ignores"
```

---

### Task 2: store.py — parquet upsert, high-water mark, load

**Files:**
- Create: `research/store.py`
- Test: `tests/research/test_store.py`

- [ ] **Step 2.1: Write the failing tests** — `tests/research/test_store.py`:

```python
"""store.py owns all parquet I/O: idempotent upsert keyed on the dataset's time
column, high-water marks for resumable backfills, atomic writes."""

from __future__ import annotations

import pandas as pd
import pytest

from research import store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _rows(*times):
    return [{"open_time": t, "close": float(t) / 1000} for t in times]


def test_upsert_creates_and_loads(warehouse):
    n = store.upsert("klines_1h", "DOGEUSDT", _rows(1000, 2000), "open_time")
    assert n == 2
    df = store.load("klines_1h", "DOGEUSDT")
    assert list(df["open_time"]) == [1000, 2000]


def test_upsert_dedups_and_sorts(warehouse):
    store.upsert("klines_1h", "DOGEUSDT", _rows(2000, 1000), "open_time")
    n = store.upsert("klines_1h", "DOGEUSDT", _rows(2000, 3000), "open_time")
    assert n == 1  # 2000 already present; only 3000 is new
    df = store.load("klines_1h", "DOGEUSDT")
    assert list(df["open_time"]) == [1000, 2000, 3000]


def test_upsert_newer_row_wins_on_same_time(warehouse):
    store.upsert("oi_1h", "DOGEUSDT", [{"timestamp": 1000, "sum_open_interest": 1.0}], "timestamp")
    store.upsert("oi_1h", "DOGEUSDT", [{"timestamp": 1000, "sum_open_interest": 2.0}], "timestamp")
    df = store.load("oi_1h", "DOGEUSDT")
    assert len(df) == 1 and df.iloc[0]["sum_open_interest"] == 2.0


def test_upsert_empty_rows_noop(warehouse):
    assert store.upsert("klines_1h", "DOGEUSDT", [], "open_time") == 0
    assert store.load("klines_1h", "DOGEUSDT").empty


def test_high_water_mark(warehouse):
    assert store.high_water_mark("klines_1h", "DOGEUSDT", "open_time") is None
    store.upsert("klines_1h", "DOGEUSDT", _rows(1000, 5000, 3000), "open_time")
    assert store.high_water_mark("klines_1h", "DOGEUSDT", "open_time") == 5000


def test_unknown_dataset_rejected(warehouse):
    with pytest.raises(KeyError):
        store.upsert("nope", "DOGEUSDT", _rows(1), "open_time")
```

- [ ] **Step 2.2:** Run `python -m pytest tests/research/test_store.py -v` → ImportError/ModuleNotFoundError.

- [ ] **Step 2.3: Implement** `research/store.py`:

```python
"""Parquet storage: one file per dataset per symbol, idempotent time-keyed upserts.

Files are small (a few MB max), so upsert = read + concat + dedup + atomic
rewrite. Dedup keeps the LAST occurrence so refreshed rows (e.g. a re-fetched
partial period) overwrite older ones.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from research import config


def dataset_path(dataset: str, symbol: str) -> Path:
    if dataset not in config.DATASETS:
        raise KeyError(f"unknown dataset {dataset!r}; add it to research.config.DATASETS")
    return config.WAREHOUSE_DIR / dataset / f"{symbol}.parquet"


def load(dataset: str, symbol: str) -> pd.DataFrame:
    path = dataset_path(dataset, symbol)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def high_water_mark(dataset: str, symbol: str, time_col: str) -> int | None:
    df = load(dataset, symbol)
    if df.empty or time_col not in df.columns:
        return None
    return int(df[time_col].max())


def upsert(dataset: str, symbol: str, rows: list[dict], time_col: str) -> int:
    """Merge rows into the symbol's parquet; returns the count of NEW time keys."""
    path = dataset_path(dataset, symbol)
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    existing = load(dataset, symbol)
    before = set(existing[time_col]) if not existing.empty else set()
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    merged = (
        merged.drop_duplicates(subset=[time_col], keep="last")
        .sort_values(time_col)
        .reset_index(drop=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return len(set(new[time_col]) - before)
```

- [ ] **Step 2.4:** `python -m pytest tests/research/test_store.py -v` → 6 PASS; full suite → 108 passed, 1 skipped.

- [ ] **Step 2.5: Commit** — `git add research/store.py tests/research/test_store.py && git commit -m "feat(research): parquet store — idempotent time-keyed upserts + high-water marks"`

---

### Task 3: binance_source.py — throttled paginated fetchers

**Files:**
- Create: `research/binance_source.py`
- Test: `tests/research/test_binance_source.py`

- [ ] **Step 3.1: Write the failing tests** — `tests/research/test_binance_source.py`:

```python
"""Fetchers must paginate to exhaustion, throttle, normalize rows, drop the
still-forming last candle, and clamp rolling datasets to the 30-day window."""

from __future__ import annotations

import time

from research import binance_source as src


def _kline(open_ms, close_ms):
    return [open_ms, "1.0", "2.0", "0.5", "1.5", "100", close_ms, "150", 7, "60", "90", "0"]


class FakePagedClient:
    """Serves canned pages; records request kwargs."""

    def __init__(self, kline_pages=None, funding_pages=None, oi_pages=None):
        self.kline_pages = list(kline_pages or [])
        self.funding_pages = list(funding_pages or [])
        self.oi_pages = list(oi_pages or [])
        self.kline_calls: list[dict] = []
        self.funding_calls: list[dict] = []
        self.oi_calls: list[dict] = []
        self.premium_calls: list[dict] = []

    def futures_klines(self, **kw):
        self.kline_calls.append(kw)
        return self.kline_pages.pop(0) if self.kline_pages else []

    def futures_funding_rate(self, **kw):
        self.funding_calls.append(kw)
        return self.funding_pages.pop(0) if self.funding_pages else []

    def futures_open_interest_hist(self, **kw):
        self.oi_calls.append(kw)
        return self.oi_pages.pop(0) if self.oi_pages else []

    def futures_global_longshort_ratio(self, **kw):
        self.oi_calls.append(kw)
        return self.oi_pages.pop(0) if self.oi_pages else []

    def _request_futures_api(self, method, path, signed=False, data=None):
        self.premium_calls.append({"method": method, "path": path, "signed": signed, "data": data})
        return self.kline_pages.pop(0) if self.kline_pages else []


def test_klines_paginate_and_normalize():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    base = now - 3000 * h  # all closed
    page1 = [_kline(base + i * h, base + (i + 1) * h - 1) for i in range(1500)]
    page2 = [_kline(base + (1500 + i) * h, base + (1501 + i) * h - 1) for i in range(10)]
    client = FakePagedClient(kline_pages=[page1, page2])

    rows = src.fetch_klines(client, "DOGEUSDT", "1h", base, delay=0)

    assert len(rows) == 1510
    assert client.kline_calls[0]["startTime"] == base
    assert client.kline_calls[0]["limit"] == 1500
    # cursor advanced past page1's last open_time
    assert client.kline_calls[1]["startTime"] == page1[-1][0] + h
    r = rows[0]
    assert r["open_time"] == base and r["close"] == 1.5 and r["volume"] == 100.0
    assert r["quote_volume"] == 150.0 and r["trades"] == 7


def test_klines_drop_forming_last_candle():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    closed = _kline(now - 2 * h, now - h - 1)
    forming = _kline(now - h, now + h)  # close_time in the future
    client = FakePagedClient(kline_pages=[[closed, forming]])

    rows = src.fetch_klines(client, "DOGEUSDT", "1h", now - 2 * h, delay=0)

    assert [r["open_time"] for r in rows] == [now - 2 * h]


def test_funding_pagination_and_normalization():
    pages = [
        [{"fundingTime": 1000 + i, "fundingRate": "0.0001", "markPrice": "1.0"} for i in range(1000)],
        [{"fundingTime": 3000, "fundingRate": "-0.0002", "markPrice": "1.1"}],
    ]
    client = FakePagedClient(funding_pages=pages)

    rows = src.fetch_funding(client, "DOGEUSDT", 1000, delay=0)

    assert len(rows) == 1001
    assert client.funding_calls[0]["limit"] == 1000
    assert client.funding_calls[1]["startTime"] == 1999 + 1  # last fundingTime + 1
    assert rows[-1] == {"funding_time": 3000, "funding_rate": -0.0002, "mark_price": 1.1}


def test_premium_index_uses_unsigned_raw_endpoint():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    client = FakePagedClient(kline_pages=[[_kline(now - 2 * h, now - h - 1)]])

    rows = src.fetch_premium_index(client, "DOGEUSDT", now - 2 * h, delay=0)

    call = client.premium_calls[0]
    assert call["path"] == "premiumIndexKlines" and call["signed"] is False
    assert call["data"]["interval"] == "1h" and call["data"]["symbol"] == "DOGEUSDT"
    assert rows[0]["close"] == 1.5 and "volume" not in rows[0]


def test_open_interest_clamps_to_rolling_window():
    now = int(time.time() * 1000)
    client = FakePagedClient(oi_pages=[[{"timestamp": now - 1000, "sumOpenInterest": "5", "sumOpenInterestValue": "10"}]])

    rows = src.fetch_open_interest(client, "DOGEUSDT", 0, delay=0)  # asks from epoch 0

    requested = client.oi_calls[0]["startTime"]
    assert requested >= now - 30 * 24 * src.HOUR_MS  # clamped
    assert rows == [{"timestamp": now - 1000, "sum_open_interest": 5.0, "sum_open_interest_value": 10.0}]


def test_long_short_normalization():
    now = int(time.time() * 1000)
    client = FakePagedClient(oi_pages=[[{"timestamp": now - 1000, "longShortRatio": "2.5", "longAccount": "0.71", "shortAccount": "0.29"}]])

    rows = src.fetch_long_short(client, "DOGEUSDT", now - 2000, delay=0)

    assert rows == [{"timestamp": now - 1000, "long_short_ratio": 2.5, "long_account": 0.71, "short_account": 0.29}]
```

- [ ] **Step 3.2:** Run → ModuleNotFoundError.

- [ ] **Step 3.3: Implement** `research/binance_source.py`:

```python
"""Throttled, paginated Binance USDT-M market-data fetchers (all UNSIGNED).

Every fetcher: sleeps `delay` before each request (never hammer from one IP —
see the 2026-06-05 -1003 ban), paginates to exhaustion with a non-advancing
cursor guard, and returns normalized list[dict] rows matching research.config
dataset schemas. The still-forming last candle is dropped (close_time in the
future) so the warehouse only ever holds closed bars.
"""

from __future__ import annotations

import time

from research.config import HOUR_MS, ROLLING_WINDOW_MS

INTERVAL_MS = {"1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": 24 * HOUR_MS}

KLINES_PAGE = 1500
FUNDING_PAGE = 1000
ROLLING_PAGE = 500


def _now_ms() -> int:
    return int(time.time() * 1000)


def _drop_unclosed(rows: list[list], now_ms: int) -> list[list]:
    if rows and int(rows[-1][6]) > now_ms:
        return rows[:-1]
    return rows


def _kline_row(k: list) -> dict:
    return {
        "open_time": int(k[0]),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "close_time": int(k[6]),
        "quote_volume": float(k[7]),
        "trades": int(k[8]),
        "taker_buy_volume": float(k[9]),
        "taker_buy_quote_volume": float(k[10]),
    }


def _paginate(fetch_page, start_ms: int, *, step_ms: int, page_size: int, delay: float,
              row_time) -> list:
    """Generic cursor pagination: fetch_page(cursor) -> raw list; row_time(raw_row) -> ms."""
    out: list = []
    cursor = start_ms
    prev_last = -1
    while True:
        if delay > 0:
            time.sleep(delay)
        batch = fetch_page(cursor)
        if not batch:
            break
        out.extend(batch)
        last = row_time(batch[-1])
        if last <= prev_last:
            break
        prev_last = last
        cursor = last + step_ms
        if len(batch) < page_size:
            break
    return out


def fetch_klines(client, symbol: str, interval: str, start_ms: int, *, delay: float) -> list[dict]:
    step = INTERVAL_MS[interval]
    raw = _paginate(
        lambda c: client.futures_klines(symbol=symbol, interval=interval, startTime=c, limit=KLINES_PAGE),
        start_ms, step_ms=step, page_size=KLINES_PAGE, delay=delay, row_time=lambda k: int(k[0]),
    )
    return [_kline_row(k) for k in _drop_unclosed(raw, _now_ms())]


def fetch_premium_index(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client._request_futures_api(
            "get", "premiumIndexKlines", False,
            data={"symbol": symbol, "interval": "1h", "startTime": c, "limit": KLINES_PAGE},
        ),
        start_ms, step_ms=HOUR_MS, page_size=KLINES_PAGE, delay=delay, row_time=lambda k: int(k[0]),
    )
    # Premium-index klines carry no volume/trades data — keep OHLC + times only.
    return [
        {"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
         "low": float(k[3]), "close": float(k[4]), "close_time": int(k[6])}
        for k in _drop_unclosed(raw, _now_ms())
    ]


def fetch_funding(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client.futures_funding_rate(symbol=symbol, startTime=c, limit=FUNDING_PAGE),
        start_ms, step_ms=1, page_size=FUNDING_PAGE, delay=delay,
        row_time=lambda r: int(r["fundingTime"]),
    )
    return [
        {"funding_time": int(r["fundingTime"]), "funding_rate": float(r["fundingRate"]),
         "mark_price": float(r["markPrice"]) if r.get("markPrice") not in (None, "") else None}
        for r in raw
    ]


def _clamp_rolling(start_ms: int) -> int:
    return max(start_ms, _now_ms() - ROLLING_WINDOW_MS)


def fetch_open_interest(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client.futures_open_interest_hist(symbol=symbol, period="1h", startTime=c, limit=ROLLING_PAGE),
        _clamp_rolling(start_ms), step_ms=HOUR_MS, page_size=ROLLING_PAGE, delay=delay,
        row_time=lambda r: int(r["timestamp"]),
    )
    return [
        {"timestamp": int(r["timestamp"]), "sum_open_interest": float(r["sumOpenInterest"]),
         "sum_open_interest_value": float(r["sumOpenInterestValue"])}
        for r in raw
    ]


def fetch_long_short(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client.futures_global_longshort_ratio(symbol=symbol, period="1h", startTime=c, limit=ROLLING_PAGE),
        _clamp_rolling(start_ms), step_ms=HOUR_MS, page_size=ROLLING_PAGE, delay=delay,
        row_time=lambda r: int(r["timestamp"]),
    )
    return [
        {"timestamp": int(r["timestamp"]), "long_short_ratio": float(r["longShortRatio"]),
         "long_account": float(r["longAccount"]), "short_account": float(r["shortAccount"])}
        for r in raw
    ]
```

- [ ] **Step 3.4:** `python -m pytest tests/research/test_binance_source.py -v` → 6 PASS; full suite → 114 passed, 1 skipped.

- [ ] **Step 3.5: Commit** — `git add research/binance_source.py tests/research/test_binance_source.py && git commit -m "feat(research): throttled paginated Binance fetchers (klines/funding/premium/OI/L-S, all unsigned)"`

---

### Task 4: universe.py — top-N resolution + universe.parquet

**Files:**
- Create: `research/universe.py`
- Test: `tests/research/test_universe.py`

- [ ] **Step 4.1: Write the failing tests** — `tests/research/test_universe.py`:

```python
"""Universe resolution: top-N TRADING USDT perps by 24h quote volume, with
exchangeInfo metadata (onboardDate), snapshot-appended to universe.parquet."""

from __future__ import annotations

import pytest

from research import store, universe


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class FakeClient:
    def futures_exchange_info(self):
        def sym(s, status="TRADING", ct="PERPETUAL", quote="USDT", onboard=1567965300000):
            return {"symbol": s, "status": status, "contractType": ct,
                    "quoteAsset": quote, "onboardDate": onboard}
        return {"symbols": [
            sym("DOGEUSDT"),
            sym("BSVUSDT"),
            sym("OLDUSDT", status="SETTLING"),          # not trading -> excluded
            sym("BTCUSDT_240628", ct="CURRENT_QUARTER"),  # not perp -> excluded
            sym("ETHBTC", quote="BTC"),                  # not USDT -> excluded
            sym("PEPEUSDT"),
        ]}

    def futures_ticker(self):
        return [
            {"symbol": "DOGEUSDT", "quoteVolume": "3000"},
            {"symbol": "BSVUSDT", "quoteVolume": "1000"},
            {"symbol": "PEPEUSDT", "quoteVolume": "2000"},
            {"symbol": "OLDUSDT", "quoteVolume": "9999"},   # excluded by exchangeInfo
            {"symbol": "UNLISTEDUSDT", "quoteVolume": "8888"},  # no exchangeInfo entry
        ]


def test_resolve_top_orders_by_quote_volume_and_filters():
    rows = universe.resolve_top(FakeClient(), 2)
    assert [r["symbol"] for r in rows] == ["DOGEUSDT", "PEPEUSDT"]
    assert rows[0]["rank"] == 1 and rows[1]["rank"] == 2
    assert rows[0]["coin"] == "DOGE"
    assert rows[0]["onboard_date_ms"] == 1567965300000


def test_snapshot_appends_to_universe_parquet(warehouse):
    rows = universe.resolve_top(FakeClient(), 2)
    universe.save_snapshot(rows, snapshot_ms=1000)
    universe.save_snapshot(rows, snapshot_ms=2000)  # second day
    df = store.load("universe", "ALL")
    assert len(df) == 4
    assert sorted(set(df["snapshot_ms"])) == [1000, 2000]


def test_snapshot_same_time_idempotent(warehouse):
    rows = universe.resolve_top(FakeClient(), 2)
    universe.save_snapshot(rows, snapshot_ms=1000)
    universe.save_snapshot(rows, snapshot_ms=1000)
    assert len(store.load("universe", "ALL")) == 2
```

Note: this needs a `universe` dataset in `research/config.py` DATASETS. Add `"universe": ("snapshot_key", None),` to the dict (snapshot_key is a synthetic `f"{snapshot_ms}:{symbol}"` string key so upsert's time-keyed dedup gives per-(snapshot,symbol) idempotence).

- [ ] **Step 4.2:** Run → failure (missing module / missing dataset).

- [ ] **Step 4.3: Implement** — add the `"universe"` entry to `config.DATASETS` (as above), then `research/universe.py`:

```python
"""Resolve the research universe: top-N TRADING USDT perpetuals by 24h quote volume."""

from __future__ import annotations

from research import store


def resolve_top(client, n: int) -> list[dict]:
    info = client.futures_exchange_info()
    perps = {
        s["symbol"]: s
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }
    tickers = [t for t in client.futures_ticker() if t["symbol"] in perps]
    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    rows = []
    for rank, t in enumerate(tickers[:n], start=1):
        s = perps[t["symbol"]]
        rows.append({
            "symbol": s["symbol"],
            "coin": s["symbol"][:-4],
            "rank": rank,
            "quote_volume_24h": float(t["quoteVolume"]),
            "onboard_date_ms": int(s.get("onboardDate", 0)),
            "status": s["status"],
        })
    return rows


def save_snapshot(rows: list[dict], snapshot_ms: int) -> int:
    keyed = [
        {**r, "snapshot_ms": snapshot_ms, "snapshot_key": f"{snapshot_ms}:{r['symbol']}"}
        for r in rows
    ]
    return store.upsert("universe", "ALL", keyed, "snapshot_key")
```

Note: `store.high_water_mark` casts to int — universe's string key would break it, but nothing calls high_water_mark on the universe dataset; if you prefer safety, have `high_water_mark` return `None` when the column dtype isn't numeric (one-line guard: `if not pd.api.types.is_numeric_dtype(df[time_col]): return None`). Add that guard.

- [ ] **Step 4.4:** Tests pass; full suite → 117 passed, 1 skipped.

- [ ] **Step 4.5: Commit** — `git add research/universe.py research/config.py research/store.py tests/research/test_universe.py && git commit -m "feat(research): universe resolution (top-N USDT perps by quote volume) + snapshots"`

---

### Task 5: backfill.py — resumable CLI

**Files:**
- Create: `research/backfill.py`
- Test: `tests/research/test_backfill.py`

- [ ] **Step 5.1: Write the failing tests** — `tests/research/test_backfill.py`:

```python
"""Backfill orchestration: per symbol x dataset, fetch from high-water mark
(or onboard date), upsert, isolate per-task errors, report a summary."""

from __future__ import annotations

import time

import pytest

from research import backfill, store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class StubSource:
    """Replaces binance_source fetchers; records (symbol, start_ms) requests."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_on: set = set()

    def make(self, dataset, rows_fn):
        def _fetch(client, symbol, *args, **kwargs):
            key = (dataset, symbol)
            self.calls.append((dataset, symbol, args, kwargs))
            if key in self.fail_on:
                raise RuntimeError("boom")
            return rows_fn(symbol)
        return _fetch


def _wire(monkeypatch, stub, rows_by_dataset):
    monkeypatch.setattr(backfill, "FETCHERS", {
        ds: backfill._FetchSpec(stub.make(ds, rows_by_dataset[ds]), backfill.FETCHERS[ds].needs_interval)
        for ds in backfill.FETCHERS
    })


def test_backfill_starts_from_onboard_then_resumes(warehouse, monkeypatch):
    stub = StubSource()
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    summary1 = backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
    # first run: every dataset starts at onboard date
    starts = {(d, s): a[0] if a else k.get("start_ms") for d, s, a, k in stub.calls}
    assert all(v == 1234 for v in starts.values())
    assert summary1.failures == []

    stub.calls.clear()
    backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
    # second run: resumes from hwm+1
    starts2 = {(d, s): a[0] if a else k.get("start_ms") for d, s, a, k in stub.calls}
    assert all(v == 5001 for v in starts2.values())


def test_backfill_isolates_failures(warehouse, monkeypatch):
    stub = StubSource()
    stub.fail_on.add(("klines_1h", "DOGEUSDT"))
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    summary = backfill.run(client=None, targets=targets, datasets=["klines_1h", "klines_4h"], delay=0)

    assert summary.failures == [("klines_1h", "DOGEUSDT")]
    assert store.load("klines_4h", "DOGEUSDT").shape[0] == 1  # other dataset still landed
```

- [ ] **Step 5.2:** Run → failure.

- [ ] **Step 5.3: Implement** `research/backfill.py`:

```python
"""Resumable warehouse backfill CLI.

    python -m research.backfill --top 100
    python -m research.backfill --symbols DOGEUSDT,BSVUSDT --datasets klines_1h,funding
    python -m research.backfill --top 100 --dry-run

Run from the DEV machine only — never the production IP (2026-06-05 -1003 ban).
All endpoints are unsigned: no API keys required. Re-running resumes from each
symbol x dataset high-water mark, so interrupting is always safe.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

from research import binance_source as src
from research import config, store, universe


@dataclass
class _FetchSpec:
    fn: object
    needs_interval: str | None = None


FETCHERS: dict[str, _FetchSpec] = {
    "klines_1h": _FetchSpec(src.fetch_klines, "1h"),
    "klines_4h": _FetchSpec(src.fetch_klines, "4h"),
    "klines_1d": _FetchSpec(src.fetch_klines, "1d"),
    "funding": _FetchSpec(src.fetch_funding),
    "premium_index_1h": _FetchSpec(src.fetch_premium_index),
    "oi_1h": _FetchSpec(src.fetch_open_interest),
    "long_short_1h": _FetchSpec(src.fetch_long_short),
}


@dataclass
class Summary:
    new_rows: dict = field(default_factory=dict)   # (dataset, symbol) -> int
    failures: list = field(default_factory=list)   # [(dataset, symbol)]


def run(client, targets: list[dict], datasets: list[str], delay: float) -> Summary:
    summary = Summary()
    for t in targets:
        symbol = t["symbol"]
        for dataset in datasets:
            spec = FETCHERS[dataset]
            time_col, _ = config.DATASETS[dataset]
            hwm = store.high_water_mark(dataset, symbol, time_col)
            start_ms = (hwm + 1) if hwm is not None else int(t.get("onboard_date_ms") or 0)
            try:
                if spec.needs_interval:
                    rows = spec.fn(client, symbol, spec.needs_interval, start_ms, delay=delay)
                else:
                    rows = spec.fn(client, symbol, start_ms, delay=delay)
                n = store.upsert(dataset, symbol, rows, time_col)
                summary.new_rows[(dataset, symbol)] = n
                print(f"{symbol:<16} {dataset:<18} +{n} rows")
            except Exception as e:
                summary.failures.append((dataset, symbol))
                print(f"{symbol:<16} {dataset:<18} FAILED: {e}", file=sys.stderr)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--symbols", help="comma-separated symbol override (skips top-N resolution)")
    parser.add_argument("--datasets", default=",".join(FETCHERS), help=f"subset of: {','.join(FETCHERS)}")
    parser.add_argument("--delay", type=float, default=config.RATE_LIMIT_DELAY)
    parser.add_argument("--dry-run", action="store_true", help="list the work, fetch nothing")
    args = parser.parse_args()

    from binance.client import Client
    client = Client("", "")  # unsigned market-data endpoints only

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    unknown = [d for d in datasets if d not in FETCHERS]
    if unknown:
        parser.error(f"unknown datasets: {unknown}")

    if args.symbols:
        targets = [{"symbol": s.strip(), "onboard_date_ms": 0} for s in args.symbols.split(",")]
    else:
        rows = universe.resolve_top(client, args.top)
        universe.save_snapshot(rows, snapshot_ms=int(time.time() * 1000))
        targets = rows
        print(f"Universe: top {len(rows)} USDT perps by 24h quote volume (snapshot saved)")

    if args.dry_run:
        for t in targets:
            print(f"{t['symbol']:<16} onboard={t.get('onboard_date_ms')}")
        print(f"{len(targets)} symbols x {len(datasets)} datasets, delay={args.delay}s")
        return

    summary = run(client, targets, datasets, args.delay)
    total = sum(summary.new_rows.values())
    print(f"\nDone: +{total} rows across {len(summary.new_rows)} tasks; {len(summary.failures)} failures")
    if summary.failures:
        for dataset, symbol in summary.failures:
            print(f"  FAILED {symbol} {dataset}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.4:** Tests pass; full suite → 119 passed, 1 skipped. Also smoke the CLI parser: `python -m research.backfill --help` prints usage (no network — Client is constructed after parse in main(); verify by reading: parse_args runs before Client construction. It does NOT: Client("","") line is before datasets parse? In the code above Client is constructed right after parse_args — --help exits inside parse_args, so safe).

- [ ] **Step 5.5: Commit** — `git add research/backfill.py tests/research/test_backfill.py && git commit -m "feat(research): resumable backfill CLI (top-N universe, per-task isolation, hwm resume)"`

---

### Task 6: check.py — gap and staleness report

**Files:**
- Create: `research/check.py`
- Test: `tests/research/test_check.py`

- [ ] **Step 6.1: Write the failing tests** — `tests/research/test_check.py`:

```python
"""check.py reports per-file row counts, time coverage, internal gaps
(spacing > expected step) and staleness, so backtests can't silently span holes."""

from __future__ import annotations

import pytest

from research import check, store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def test_finds_gaps(warehouse):
    h = 3_600_000
    rows = [{"open_time": i * h, "close": 1.0} for i in (0, 1, 2, 5, 6)]  # gap: 2->5
    store.upsert("klines_1h", "DOGEUSDT", rows, "open_time")

    report = check.scan()

    [entry] = [e for e in report if e["dataset"] == "klines_1h" and e["symbol"] == "DOGEUSDT"]
    assert entry["rows"] == 5
    assert entry["gaps"] == 1
    assert entry["largest_gap_ms"] == 3 * h


def test_no_gaps_clean(warehouse):
    h = 3_600_000
    store.upsert("klines_1h", "DOGEUSDT", [{"open_time": i * h, "close": 1.0} for i in range(4)], "open_time")
    [entry] = check.scan()
    assert entry["gaps"] == 0


def test_irregular_datasets_skip_gap_check(warehouse):
    store.upsert("universe", "ALL", [{"snapshot_key": "1:A", "symbol": "A"}], "snapshot_key")
    [entry] = check.scan()
    assert entry["gaps"] is None
```

- [ ] **Step 6.2:** Run → failure.

- [ ] **Step 6.3: Implement** `research/check.py`:

```python
"""Warehouse integrity report: rows, coverage, internal gaps, staleness.

    python -m research.check
"""

from __future__ import annotations

from research import config, store


def scan() -> list[dict]:
    report = []
    for dataset, (time_col, step_ms) in config.DATASETS.items():
        ds_dir = config.WAREHOUSE_DIR / dataset
        if not ds_dir.exists():
            continue
        for path in sorted(ds_dir.glob("*.parquet")):
            symbol = path.stem
            df = store.load(dataset, symbol)
            entry = {"dataset": dataset, "symbol": symbol, "rows": len(df),
                     "gaps": None, "largest_gap_ms": 0, "first": None, "last": None}
            if step_ms is not None and len(df) > 1:
                times = df[time_col].sort_values()
                diffs = times.diff().dropna()
                gaps = diffs[diffs > step_ms]
                entry["gaps"] = int(len(gaps))
                entry["largest_gap_ms"] = int(gaps.max()) if len(gaps) else 0
                entry["first"] = int(times.iloc[0])
                entry["last"] = int(times.iloc[-1])
            report.append(entry)
    return report


def main() -> None:
    report = scan()
    if not report:
        print("Warehouse is empty.")
        return
    bad = [e for e in report if e["gaps"]]
    print(f"{len(report)} files scanned; {len(bad)} with gaps")
    for e in sorted(bad, key=lambda e: -e["largest_gap_ms"])[:40]:
        print(f"  {e['symbol']:<16} {e['dataset']:<18} rows={e['rows']:<8} "
              f"gaps={e['gaps']:<4} largest={e['largest_gap_ms'] / 3_600_000:.1f}h")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.4:** Tests pass; full suite → 122 passed, 1 skipped.

- [ ] **Step 6.5: Commit** — `git add research/check.py tests/research/test_check.py && git commit -m "feat(research): warehouse gap/staleness checker"`

---

### Task 7: Real backfill run (controller does this — long-running, from the dev machine)

- [ ] **Step 7.1:** `python -m research.backfill --top 100 --dry-run` — sanity-check the universe list (expect ~100 symbols, majors at the top).
- [ ] **Step 7.2:** Small probe first: `python -m research.backfill --symbols DOGEUSDT --delay 0.5` — all 7 datasets land; spot-check row counts and `python -m research.check` is clean.
- [ ] **Step 7.3:** Full run in background: `python -m research.backfill --top 100 --delay 0.5` (expect ~45–90 min). On completion: re-run once more (tests resume + tops up anything that closed during the run), then `python -m research.check`.
- [ ] **Step 7.4:** Spot-validate against known values: DOGE funding rows ≈ 3/day since onboard; 1h kline count ≈ hours since onboard; compare one daily close against the swing bot's view.

### Task 8: Final review, docs, merge (controller)

- [ ] **Step 8.1:** Final code review subagent over the whole branch.
- [ ] **Step 8.2:** Add a short "Research warehouse" section to CLAUDE.md (commands, layout, never-from-prod-IP rule, weekly refresh cron line: `0 6 * * 1 cd /home/dev/projects/trade-god && python -m research.backfill --top 100 >> /tmp/research-backfill.log 2>&1`).
- [ ] **Step 8.3:** `python -m pytest -q` green → merge `feat/research-warehouse` to main (--no-ff), push.

---

## Self-review notes (applied)

- Spec coverage: parquet-per-dataset-per-symbol ✓, BYO-nothing unsigned backfill ✓, resumable hwm ✓, 30-day rolling accumulation for OI/L-S ✓, gap checker ✓, universe snapshots with onboard dates ✓, dev-only deps + dockerignore ✓. DuckDB ships as a dep (query layer for Phase C) — no code needed this phase.
- Type consistency: `store.upsert(dataset, symbol, rows, time_col) -> int`; `high_water_mark -> int | None` (with non-numeric guard); fetchers `(client, symbol[, interval], start_ms, *, delay) -> list[dict]`; `backfill.run(client, targets, datasets, delay) -> Summary`; `check.scan() -> list[dict]`.
- The funding fetcher paginates with `step_ms=1` (funding times are irregular ~8h; cursor = last fundingTime + 1 avoids both overlap and skips).
- `oi_1h`/`long_short_1h` clamp start to now−29d; weekly cron keeps history continuous thereafter.
