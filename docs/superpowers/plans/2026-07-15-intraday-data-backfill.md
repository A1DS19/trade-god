# Intraday Data Backfill (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the research warehouse with `klines_15m` (from 2023-01-01 or listing) and `klines_5m` (trailing ~18 months) for a liquid top-30 subset selected by 30-day median daily quote volume, per the approved spec `docs/superpowers/specs/2026-07-15-intraday-remake-design.md` §2.

**Architecture:** The existing `research/` backfill machinery (`backfill.py` orchestrator, `binance_source.py` fetchers, `store.py` parquet upserts, `check.py` gap scanner) is dataset-generic — new datasets are registered in `research/config.py:DATASETS` and `research/backfill.py:FETCHERS` and everything else (resume from high-water mark, gap checking) works unchanged. Two new pieces: a per-dataset **start floor** so minute-level klines don't backfill to 2020, and a **top-30 selector** ranking warehouse symbols by 30-day median daily quote volume.

**Tech Stack:** Python 3.12, pandas + pyarrow (already in `requirements-research.txt` — no new dependencies), python-binance unsigned market-data endpoints, pytest.

## Global Constraints

- Backfills run from the DEV machine only — never the prod IP (2026-06-05 -1003 ban). All endpoints unsigned; no API keys.
- Rate limit: keep the default `--delay 0.5` (seconds between REST requests).
- The weekly refresh cron runs `python -m research.backfill --top 100` with the **default** dataset list — intraday datasets MUST NOT join that default (minute-level klines for 100 symbols would balloon the warehouse and the request budget). They are explicit opt-in via `--datasets`.
- `klines_15m` floor: `1_672_531_200_000` (2023-01-01T00:00:00Z). `klines_5m` window: `548 * DAY_MS` (~18 months trailing).
- Run `python -m pytest` before every commit; all tests must pass (testnet tests auto-skip).
- Commits go directly to `main` (user-approved for this repo).
- Don't add comments, docstrings, or type annotations to code you didn't change.

---

### Task 1: Register intraday datasets + start floors in config

**Files:**
- Modify: `research/config.py`
- Test: `tests/research/test_intraday_datasets.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `config.DATASETS` entries `"klines_15m"`, `"klines_5m"`, `"intraday_universe"`; `config.MINUTE_MS: int`; `config.KLINES_15M_FLOOR_MS: int`; `config.KLINES_5M_WINDOW_MS: int`; `config.dataset_start_floor(dataset: str, now_ms: int) -> int` (returns 0 for datasets with no floor). Tasks 2 and 3 rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_intraday_datasets.py`:

```python
"""Intraday dataset registration and backfill start floors."""

from research import config

NOW_MS = 1_752_500_000_000


def test_intraday_datasets_registered():
    assert config.DATASETS["klines_15m"] == ("open_time", 15 * config.MINUTE_MS)
    assert config.DATASETS["klines_5m"] == ("open_time", 5 * config.MINUTE_MS)
    assert config.DATASETS["intraday_universe"] == ("snapshot_key", None)


def test_start_floor_15m_is_2023_01_01():
    assert config.dataset_start_floor("klines_15m", NOW_MS) == 1_672_531_200_000


def test_start_floor_5m_is_trailing_window():
    assert config.dataset_start_floor("klines_5m", NOW_MS) == NOW_MS - config.KLINES_5M_WINDOW_MS
    assert config.KLINES_5M_WINDOW_MS == 548 * config.DAY_MS


def test_no_floor_for_classic_datasets():
    for ds in ("klines_1h", "klines_4h", "klines_1d", "funding",
               "premium_index_1h", "oi_1h", "long_short_1h", "universe"):
        assert config.dataset_start_floor(ds, NOW_MS) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_datasets.py -v`
Expected: 4 FAILED — `AttributeError: module 'research.config' has no attribute 'MINUTE_MS'` (and/or `KeyError: 'klines_15m'`).

- [ ] **Step 3: Implement in `research/config.py`**

Add `MINUTE_MS` next to the existing time constants (after the `DAY_MS` line):

```python
HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
MINUTE_MS = 60_000
```

Add three entries to the `DATASETS` dict (keep existing entries untouched; insert the kline entries before `"klines_1h"` and `"intraday_universe"` after `"universe"`):

```python
DATASETS: dict[str, tuple[str, int | None]] = {
    "klines_5m": ("open_time", 5 * MINUTE_MS),
    "klines_15m": ("open_time", 15 * MINUTE_MS),
    "klines_1h": ("open_time", HOUR_MS),
    "klines_4h": ("open_time", 4 * HOUR_MS),
    "klines_1d": ("open_time", DAY_MS),
    "funding": ("funding_time", 8 * HOUR_MS),
    "premium_index_1h": ("open_time", HOUR_MS),
    "oi_1h": ("timestamp", HOUR_MS),
    "long_short_1h": ("timestamp", HOUR_MS),
    "universe": ("snapshot_key", None),
    "intraday_universe": ("snapshot_key", None),
}
```

Append at the end of the file:

```python
# Minute-level klines are capped so they never backfill to listing:
# 15m from 2023-01-01 (or listing, whichever is later), 5m trailing ~18 months.
KLINES_15M_FLOOR_MS = 1_672_531_200_000  # 2023-01-01T00:00:00Z
KLINES_5M_WINDOW_MS = 548 * DAY_MS


def dataset_start_floor(dataset: str, now_ms: int) -> int:
    """Earliest allowed backfill start for a dataset; 0 = no floor."""
    if dataset == "klines_15m":
        return KLINES_15M_FLOOR_MS
    if dataset == "klines_5m":
        return now_ms - KLINES_5M_WINDOW_MS
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_datasets.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite (the new DATASETS entries must not break check/store tests)**

Run: `python -m pytest`
Expected: all pass, no new failures.

- [ ] **Step 6: Commit**

```bash
git add research/config.py tests/research/test_intraday_datasets.py
git commit -m "feat(research): register 5m/15m kline datasets with backfill start floors"
```

---

### Task 2: Wire intraday klines into the backfill (fetchers, floor clamp, safe defaults)

**Files:**
- Modify: `research/binance_source.py:16` (INTERVAL_MS)
- Modify: `research/backfill.py` (FETCHERS, new DEFAULT_DATASETS, floor clamp in `run()`, argparse default)
- Test: `tests/research/test_backfill.py` (modify existing + add two tests)

**Interfaces:**
- Consumes: `config.dataset_start_floor(dataset, now_ms)`, `config.KLINES_15M_FLOOR_MS`, `config.KLINES_5M_WINDOW_MS` from Task 1.
- Produces: `backfill.FETCHERS` gains `"klines_15m"` / `"klines_5m"` (interval strings `"15m"` / `"5m"`); `backfill.DEFAULT_DATASETS: list[str]` (all fetchable datasets except the two intraday ones) — Task 4's commands and the CLAUDE.md cron note rely on the CLI behavior this creates.

- [ ] **Step 1: Update the existing resume test to pin classic-dataset behavior, and add the two new failing tests**

In `tests/research/test_backfill.py`, inside `test_backfill_starts_from_onboard_then_resumes`, replace both occurrences of

```python
    summary1 = backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
```
and
```python
    backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
```
with
```python
    summary1 = backfill.run(client=None, targets=targets, datasets=list(backfill.DEFAULT_DATASETS), delay=0)
```
and
```python
    backfill.run(client=None, targets=targets, datasets=list(backfill.DEFAULT_DATASETS), delay=0)
```

(The intraday datasets clamp their start to a floor, so the "every dataset starts at onboard=1234" assertion only holds for the classic, unfloored datasets.)

Then append these two tests at the end of the file:

```python
def test_backfill_clamps_intraday_start_to_floor(warehouse, monkeypatch):
    from research import config

    stub = StubSource()
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    before = int(time.time() * 1000)
    backfill.run(client=None, targets=targets, datasets=["klines_15m", "klines_5m"], delay=0)
    after = int(time.time() * 1000)

    starts = {d: a[-1] for d, s, a, k in stub.calls}
    assert starts["klines_15m"] == config.KLINES_15M_FLOOR_MS
    assert (before - config.KLINES_5M_WINDOW_MS
            <= starts["klines_5m"]
            <= after - config.KLINES_5M_WINDOW_MS)


def test_default_datasets_exclude_intraday_klines():
    assert "klines_5m" not in backfill.DEFAULT_DATASETS
    assert "klines_15m" not in backfill.DEFAULT_DATASETS
    assert set(backfill.DEFAULT_DATASETS) < set(backfill.FETCHERS)
    assert backfill.FETCHERS["klines_15m"].needs_interval == "15m"
    assert backfill.FETCHERS["klines_5m"].needs_interval == "5m"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_backfill.py -v`
Expected: `test_backfill_starts_from_onboard_then_resumes` FAILS with `AttributeError: module 'research.backfill' has no attribute 'DEFAULT_DATASETS'`; the two new tests FAIL the same way / with `KeyError: 'klines_15m'`.

- [ ] **Step 3: Implement**

`research/binance_source.py` — extend the interval map (line 16) and import `MINUTE_MS`:

```python
from research.config import HOUR_MS, MINUTE_MS, ROLLING_WINDOW_MS

INTERVAL_MS = {"5m": 5 * MINUTE_MS, "15m": 15 * MINUTE_MS,
               "1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": 24 * HOUR_MS}
```

`research/backfill.py` — extend `FETCHERS` and add `DEFAULT_DATASETS` directly below it:

```python
FETCHERS: dict[str, _FetchSpec] = {
    "klines_5m": _FetchSpec(src.fetch_klines, "5m"),
    "klines_15m": _FetchSpec(src.fetch_klines, "15m"),
    "klines_1h": _FetchSpec(src.fetch_klines, "1h"),
    "klines_4h": _FetchSpec(src.fetch_klines, "4h"),
    "klines_1d": _FetchSpec(src.fetch_klines, "1d"),
    "funding": _FetchSpec(src.fetch_funding),
    "premium_index_1h": _FetchSpec(src.fetch_premium_index),
    "oi_1h": _FetchSpec(src.fetch_open_interest),
    "long_short_1h": _FetchSpec(src.fetch_long_short),
}

# The weekly --top 100 cron uses the default list; minute-level klines for 100
# symbols would blow the request budget, so intraday is explicit opt-in.
DEFAULT_DATASETS = [d for d in FETCHERS if d not in ("klines_5m", "klines_15m")]
```

In `run()`, clamp the start to the dataset floor — compute `now_ms` once at the top of the function, then apply after the existing `start_ms` line:

```python
def run(client, targets: list[dict], datasets: list[str], delay: float) -> Summary:
    summary = Summary()
    now_ms = int(time.time() * 1000)
    for t in targets:
        symbol = t["symbol"]
        for dataset in datasets:
            spec = FETCHERS[dataset]
            time_col, _ = config.DATASETS[dataset]
            hwm = store.high_water_mark(dataset, symbol, time_col)
            start_ms = (hwm + 1) if hwm is not None else int(t.get("onboard_date_ms") or 0)
            start_ms = max(start_ms, config.dataset_start_floor(dataset, now_ms))
```

(The rest of `run()` is unchanged.)

In `main()`, change the argparse default so the cron keeps its old behavior:

```python
    parser.add_argument("--datasets", default=",".join(DEFAULT_DATASETS),
                        help=f"subset of: {','.join(FETCHERS)} (default excludes klines_5m/15m)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_backfill.py -v`
Expected: all pass (2 pre-existing tests + 2 new).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add research/binance_source.py research/backfill.py tests/research/test_backfill.py
git commit -m "feat(research): intraday kline backfill — floor-clamped starts, opt-in datasets"
```

---

### Task 3: Top-30 intraday universe selector

**Files:**
- Create: `research/intraday_universe.py`
- Test: `tests/research/test_intraday_universe.py` (create)

**Interfaces:**
- Consumes: `config.WAREHOUSE_DIR`, `store.load(dataset, symbol)`, `store.upsert(dataset, symbol, rows, time_col)`; the `"intraday_universe"` DATASETS entry from Task 1; warehouse `klines_1d` parquets (column `quote_volume`, time column `open_time`).
- Produces: `intraday_universe.select_top(n: int, now_ms: int | None = None) -> list[dict]` (each dict: `symbol`, `median_quote_volume_30d`, `rank`; symbols whose last daily bar is older than 7 days are excluded — a delisted coin's stale parquet must not rank), `intraday_universe.save_snapshot(rows: list[dict], snapshot_ms: int) -> int`, and CLI `python -m research.intraday_universe [--top N] [--save]` printing a comma-separated symbol list to stdout (exactly the format `backfill --symbols` accepts). Task 4 depends on the CLI.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_intraday_universe.py`:

```python
"""Top-N intraday universe: rank warehouse symbols by 30-day median daily quote volume."""

from __future__ import annotations

import pytest

from research import intraday_universe, store

DAY_MS = 86_400_000


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _write_1d(symbol, quote_volumes):
    rows = [
        {"open_time": i * DAY_MS, "close": 1.0, "quote_volume": qv}
        for i, qv in enumerate(quote_volumes)
    ]
    store.upsert("klines_1d", symbol, rows, "open_time")


NOW_40D = 40 * DAY_MS  # "now" for fixtures whose last bar is day 39 — 1 day fresh


def test_ranks_by_median_quote_volume(warehouse):
    _write_1d("AAAUSDT", [100.0] * 40)
    _write_1d("BBBUSDT", [300.0] * 40)
    _write_1d("CCCUSDT", [200.0] * 40)

    top = intraday_universe.select_top(2, now_ms=NOW_40D)

    assert [r["symbol"] for r in top] == ["BBBUSDT", "CCCUSDT"]
    assert top[0]["rank"] == 1
    assert top[0]["median_quote_volume_30d"] == 300.0


def test_median_uses_last_30_days_only(warehouse):
    _write_1d("OLDUSDT", [9_000.0] * 40 + [10.0] * 30)
    _write_1d("NEWUSDT", [100.0] * 70)

    top = intraday_universe.select_top(2, now_ms=70 * DAY_MS)

    assert [r["symbol"] for r in top] == ["NEWUSDT", "OLDUSDT"]


def test_skips_symbols_with_short_history(warehouse):
    _write_1d("FRESHUSDT", [1_000_000.0] * 10)
    _write_1d("OKUSDT", [50.0] * 35)

    top = intraday_universe.select_top(30, now_ms=35 * DAY_MS)

    assert [r["symbol"] for r in top] == ["OKUSDT"]


def test_skips_stale_symbols(warehouse):
    # DEADUSDT's last bar is day 39; LIVEUSDT's is day 47. At now=day 48,
    # DEAD is 9 days stale (delisted-coin parquet) and must not rank despite volume.
    _write_1d("DEADUSDT", [9_000.0] * 40)
    _write_1d("LIVEUSDT", [50.0] * 48)

    top = intraday_universe.select_top(30, now_ms=48 * DAY_MS)

    assert [r["symbol"] for r in top] == ["LIVEUSDT"]


def test_save_snapshot_writes_keyed_rows(warehouse):
    _write_1d("AAAUSDT", [100.0] * 40)
    rows = intraday_universe.select_top(1)

    n = intraday_universe.save_snapshot(rows, snapshot_ms=1234)

    assert n == 1
    snap = store.load("intraday_universe", "ALL")
    assert snap.iloc[0]["snapshot_key"] == "1234:AAAUSDT"
    assert snap.iloc[0]["symbol"] == "AAAUSDT"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_universe.py -v`
Expected: collection error — `ImportError: cannot import name 'intraday_universe'`.

- [ ] **Step 3: Implement `research/intraday_universe.py`**

```python
"""Select the intraday research universe: top-N warehouse symbols by 30-day
median daily quote volume (spec 2026-07-15 §2 — thin coins have untradeable
spreads at intraday frequency).

    python -m research.intraday_universe                 # print CSV symbol list
    python -m research.intraday_universe --top 30 --save # also snapshot to warehouse

Reads klines_1d already in the warehouse; refresh it first
(python -m research.backfill --top 100 --datasets klines_1d) so medians are current.
Output feeds straight into: python -m research.backfill --symbols "$(...)".
"""

from __future__ import annotations

import argparse
import time

from research import config, store

MIN_DAYS = 30
STALENESS_MS = 7 * config.DAY_MS  # last daily bar older than this = likely delisted


def select_top(n: int, now_ms: int | None = None) -> list[dict]:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    ds_dir = config.WAREHOUSE_DIR / "klines_1d"
    rows = []
    for path in sorted(ds_dir.glob("*.parquet")):
        symbol = path.stem
        df = store.load("klines_1d", symbol)
        if len(df) < MIN_DAYS:
            continue
        window = df.sort_values("open_time").tail(MIN_DAYS)
        if int(window["open_time"].max()) < now_ms - STALENESS_MS:
            continue
        rows.append({
            "symbol": symbol,
            "median_quote_volume_30d": float(window["quote_volume"].median()),
        })
    rows.sort(key=lambda r: r["median_quote_volume_30d"], reverse=True)
    top = rows[:n]
    for rank, r in enumerate(top, start=1):
        r["rank"] = rank
    return top


def save_snapshot(rows: list[dict], snapshot_ms: int) -> int:
    keyed = [
        {**r, "snapshot_ms": snapshot_ms, "snapshot_key": f"{snapshot_ms}:{r['symbol']}"}
        for r in rows
    ]
    return store.upsert("intraday_universe", "ALL", keyed, "snapshot_key")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--save", action="store_true", help="snapshot selection to the warehouse")
    args = parser.parse_args()

    top = select_top(args.top)
    if args.save:
        save_snapshot(top, snapshot_ms=int(time.time() * 1000))
    print(",".join(r["symbol"] for r in top))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_universe.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add research/intraday_universe.py tests/research/test_intraday_universe.py
git commit -m "feat(research): intraday top-30 selector by 30d median quote volume"
```

---

### Task 4: Run the backfill and verify integrity (ops — DEV machine only)

**Files:** none created/modified (warehouse parquets are gitignored).

**Interfaces:**
- Consumes: the CLIs from Tasks 2 and 3.
- Produces: populated `research/warehouse/klines_15m/` and `research/warehouse/klines_5m/` (30 symbols each) plus an `intraday_universe` snapshot — the inputs Phase 2 (edge-hunt) reads.

- [ ] **Step 1: Refresh daily klines so the 30-day medians are current**

```bash
cd /home/dev/projects/trade-god
python -m research.backfill --top 100 --datasets klines_1d
```
Expected: per-symbol `klines_1d +N rows` lines, exit 0. (~2 min.)

- [ ] **Step 2: Resolve and snapshot the top-30, hold it in a shell variable**

```bash
SYMS=$(python -m research.intraday_universe --top 30 --save)
echo "$SYMS" | tr ',' '\n' | wc -l   # expect 30
echo "$SYMS"
```
Expected: 30 comma-separated symbols, majors first (BTCUSDT/ETHUSDT/SOLUSDT-tier names).

- [ ] **Step 3: Dry-run the intraday backfill**

```bash
python -m research.backfill --symbols "$SYMS" --datasets klines_5m,klines_15m --dry-run
```
Expected: 30 symbol lines with onboard dates, then `30 symbols x 2 datasets, delay=0.5s`.

- [ ] **Step 4: Run the real backfill in the background**

```bash
nohup python -m research.backfill --symbols "$SYMS" --datasets klines_5m,klines_15m \
  > /tmp/intraday-backfill.log 2>&1 &
```
Expected wall clock: **1–2 hours** (~5,500 paginated requests at 0.5 s delay: 5m ≈ 105 pages/symbol over 18 months, 15m ≈ 60–85 pages/symbol since 2023). Monitor with `tail -f /tmp/intraday-backfill.log`. If interrupted, re-running the same command resumes from each symbol's high-water mark.

- [ ] **Step 5: Verify completion and row counts**

```bash
tail -5 /tmp/intraday-backfill.log
python - <<'EOF'
import pandas as pd
from research import config
for ds in ("klines_5m", "klines_15m"):
    files = sorted((config.WAREHOUSE_DIR / ds).glob("*.parquet"))
    total = sum(len(pd.read_parquet(f)) for f in files)
    print(f"{ds}: {len(files)} symbols, {total:,} rows")
EOF
```
Expected: `Done: +N rows ... 0 failures` in the log; ~30 files per dataset; roughly 4–5M rows for 5m and 2–4M for 15m (late-listed symbols have less history). If any `FAILED` lines appear, re-run Step 4 — resume is safe — and only investigate fetchers if the same symbol×dataset fails twice.

- [ ] **Step 6: Gap check**

```bash
python -m research.check
```
Expected: the new datasets appear in the scan; no large unexplained gaps in `klines_5m`/`klines_15m`. Known pre-existing quirks (ICPUSDT premium-index 77-day hole, funding ms jitter) are unrelated to the new datasets. Exchange-downtime gaps of a few bars are acceptable; a multi-day gap in a top-30 symbol is not — re-run the backfill for that symbol and re-check before proceeding.

---

### Task 5: Document the new datasets and refresh procedure

**Files:**
- Modify: `CLAUDE.md` (Research Warehouse section)

**Interfaces:**
- Consumes: behavior established in Tasks 2–4.
- Produces: docs only.

- [ ] **Step 1: Update the Research Warehouse section of `CLAUDE.md`**

Replace the `Datasets:` paragraph:

```markdown
Datasets: `klines_1h/4h/1d`, `funding` (full history), `premium_index_1h` (basis),
`oi_1h` + `long_short_1h` (Binance serves trailing 30d only — refresh ≥ monthly or history is lost),
`universe` (top-N snapshots with onboard dates), `klines_5m/15m` (intraday top-30 subset only —
5m trailing ~18 months, 15m since 2023-01-01; **excluded from the default dataset list** so the
weekly `--top 100` cron never fetches minute data for 100 symbols), `intraday_universe`
(top-30-by-30d-median-quote-volume snapshots).
```

And add below the existing command block:

```markdown
python -m research.intraday_universe --top 30 --save   # print + snapshot intraday top-30
# refresh intraday klines (dev machine only):
python -m research.backfill --symbols "$(python -m research.intraday_universe --top 30 --save)" --datasets klines_5m,klines_15m
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: intraday 5m/15m warehouse datasets + refresh procedure"
```

---

## Verification (whole phase)

- `python -m pytest` — green.
- `research/warehouse/klines_5m/` and `klines_15m/` each hold ~30 parquets; `python -m research.check` shows no unexplained gaps.
- `python -m research.backfill --top 100 --dry-run` still lists only the 7 classic datasets (cron safety).
- Phase 2 (edge-hunt) is unblocked: `store.load("klines_5m", "BTCUSDT")` returns a populated DataFrame.
