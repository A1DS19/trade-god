# Intraday Edge-Hunt (Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run pre-registered, cost-aware event studies for six intraday signal families on the 15m warehouse data (train window only) and produce a mechanical SURVIVOR/REJECTED verdict per family — the input to Phase 2b (strategy backtests for survivors), per spec `docs/superpowers/specs/2026-07-15-intraday-remake-design.md` §3.

**Architecture:** One shared harness (`research/signals/intraday/harness.py`) owns the pre-registered survivor rule and evaluation loop; each family is a pure builder function (`families.py`) from warehouse long-frames to a bucket-label panel; a CLI (`study.py`) loads train data once, runs all families, and writes stats + verdicts. Reuses `siglib` (`data` loaders, `events.event_study`, `costs.CostModel`) with two small extensions. No new PnL code — event studies only; the verified backtest engine enters in Phase 2b.

**Tech Stack:** Python 3.12, pandas/pyarrow (already in `requirements-research.txt` — no new dependencies), pytest. No network access needed anywhere (warehouse-only).

## Global Constraints

- **Pre-registration ordering:** Task 6 (the real-data run) MUST NOT start until Tasks 1–5 are committed. The rule, bucket edges, horizons, and hypotheses in this plan are the pre-registration; changing them after seeing real-data results is a protocol violation and must be recorded as such in the report.
- **Train cutoff:** `TRAIN_END = "2025-07-01"`. No data on/after this date is loaded anywhere in Phase 2a. OOS (2025-07-01 → 2026-07-15, three windows) is reserved for Phase 2b final evaluation.
- **Timeframe:** `klines_15m` only. (5m has ~5.5 months of pre-OOS history — too thin to train on; reserved for survivor robustness checks in 2b.)
- **Cost hurdle:** `ROUND_TRIP = 0.0016` — taker 5 bps + slippage 3 bps per side (spec §3). The spec's cost model differs from siglib's 5+5 default; Task 1 adds the spec variant as `INTRADAY` in `research/siglib/costs.py`.
- **Survivor rule (mechanical, per family):** SURVIVOR iff for at least one pre-declared (extreme bucket, horizon) pair ALL hold: (1) edge in the hypothesized direction > `ROUND_TRIP`, where edge = bucket mean forward return − pooled middle-bucket mean (abs-mode families use mean |forward return|); (2) descriptive |t| ≥ 3.0 (overlap-inflated, hence 3 not 2); (3) bucket count ≥ 500; (4) split-half: the edge has the hypothesized sign in BOTH halves of the train window. Families whose hypothesized sign is data-determined (sign 0, time-of-day) take the full-train edge sign as direction and must still pass all four.
- Eligibility: `siglib.data.eligible_mask` (60-day rule) applied to every bucket panel before evaluation.
- Run `python -m pytest` before every commit; the only allowed failure is the known pre-existing `tests/swing/test_reconcile.py::test_stale_row_closed_from_fills` (date-sensitive swing test, unrelated).
- Commits go directly to `main` (user-approved for this repo).
- Don't add comments, docstrings, or type annotations to code you didn't change.
- **Known caveat to carry into the report (not fixable in 2a):** the top-30 universe was selected on 2026-07-15 volume — survivorship bias inflates long-side momentum results. Phase 2b gates survivors on point-in-time universe snapshots where possible.

---

### Task 1: siglib extensions — taker columns, absolute-mode event study, spec cost model

**Files:**
- Modify: `research/siglib/data.py:18` (KLINE_COLS)
- Modify: `research/siglib/events.py` (absolute param)
- Modify: `research/siglib/costs.py` (INTRADAY model)
- Test: `tests/research/test_intraday_siglib_ext.py` (create)

**Interfaces:**
- Consumes: existing `siglib` modules.
- Produces: `data.KLINE_COLS` includes `"taker_buy_volume"` and `"trades"` (so `load_klines` returns them); `events.event_study(..., absolute: bool = False)` — when True, forward returns are replaced by their absolute values before bucketing stats; `costs.INTRADAY = CostModel(taker_bps=5.0, slippage_bps=3.0)`. Tasks 2–5 rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_intraday_siglib_ext.py`:

```python
"""siglib extensions for the intraday edge-hunt: taker columns, abs-mode
event study, spec cost model (5 bps taker + 3 bps slippage per side)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import store
from research.siglib import costs
from research.siglib import data as sdata
from research.siglib.events import event_study


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def test_intraday_cost_model():
    assert costs.INTRADAY.taker_bps == 5.0
    assert costs.INTRADAY.slippage_bps == 3.0
    assert costs.INTRADAY.cost_per_side == pytest.approx(0.0008)


def test_load_klines_returns_taker_columns(warehouse):
    rows = [{
        "open_time": i * 900_000, "open": 1.0, "high": 1.0, "low": 1.0,
        "close": 1.0, "volume": 10.0, "quote_volume": 10.0,
        "taker_buy_volume": 6.0, "trades": 3,
    } for i in range(4)]
    store.upsert("klines_15m", "AAAUSDT", rows, "open_time")

    df = sdata.load_klines("AAAUSDT", interval="15m")

    assert "taker_buy_volume" in df.columns
    assert "trades" in df.columns
    assert df["taker_buy_volume"].iloc[0] == 6.0


def test_event_study_absolute_mode():
    idx = pd.Index(range(0, 10_000, 100), name="open_time")
    up = 1.02 ** np.arange(len(idx))
    down = 0.98 ** np.arange(len(idx))
    close = pd.DataFrame({"UP": up, "DOWN": down}, index=idx)
    buckets = pd.DataFrame("all", index=idx, columns=close.columns)

    signed = event_study(close, buckets, horizons_hours=(1,))
    absolute = event_study(close, buckets, horizons_hours=(1,), absolute=True)

    # signed: +2% and -2% average out near zero; absolute: mean ~2%
    assert abs(signed["mean"].iloc[0]) < 0.005
    assert absolute["mean"].iloc[0] == pytest.approx(0.02, abs=0.001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_siglib_ext.py -v`
Expected: `test_intraday_cost_model` FAILS (`AttributeError: ... no attribute 'INTRADAY'`); `test_load_klines_returns_taker_columns` FAILS (column missing); `test_event_study_absolute_mode` FAILS (`TypeError: ... unexpected keyword argument 'absolute'`).

- [ ] **Step 3: Implement**

`research/siglib/costs.py` — append:

```python
# Spec 2026-07-15 §3 intraday model: 5 bps taker + 3 bps slippage per side.
INTRADAY = CostModel(taker_bps=5.0, slippage_bps=3.0)
```

`research/siglib/data.py:18` — extend the column list:

```python
KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "quote_volume", "taker_buy_volume", "trades"]
```

`research/siglib/events.py` — add the parameter and one line; the signature and loop become:

```python
def event_study(
    panel_close: pd.DataFrame,
    signal_panel: pd.DataFrame,
    horizons_hours=DEFAULT_HORIZONS,
    absolute: bool = False,
) -> pd.DataFrame:
```

and inside the loop, right after `fwd` is built:

```python
    for h in horizons_hours:
        fwd = (panel_close.shift(-h) / panel_close - 1.0).stack().dropna()
        if absolute:
            fwd = fwd.abs()
        fwd.name = "fwd"
```

Also update the docstring's Returns line to mention: `absolute=True studies |forward return| (movement magnitude, direction-free)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_siglib_ext.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite (KLINE_COLS widening must not break existing siglib/signal tests)**

Run: `python -m pytest`
Expected: all pass except the known pre-existing reconcile failure.

- [ ] **Step 6: Commit**

```bash
git add research/siglib/costs.py research/siglib/data.py research/siglib/events.py tests/research/test_intraday_siglib_ext.py
git commit -m "feat(research): siglib intraday extensions — taker cols, abs event study, spec cost model"
```

---

### Task 2: Edge-hunt harness — pre-registered survivor rule + evaluation loop

**Files:**
- Create: `research/signals/intraday/__init__.py` (empty)
- Create: `research/signals/intraday/harness.py`
- Test: `tests/research/test_intraday_harness.py` (create)

**Interfaces:**
- Consumes: `events.event_study(..., absolute=)` from Task 1.
- Produces (Tasks 3–5 rely on these exact names):
  - `harness.ROUND_TRIP = 0.0016`, `harness.MIN_T = 3.0`, `harness.MIN_COUNT = 500`
  - `harness.cut_panel(panel, edges, labels) -> pd.DataFrame` (bucket-label panel)
  - `@dataclass(frozen=True) FamilySpec`: fields `name: str`, `build` (callable `data: dict -> bucket panel`), `extreme: dict` (bucket label -> hypothesized sign +1/-1/0; 0 = data-determined), `middle: list | None` (baseline bucket labels; None = all-other-buckets baseline), `horizons_bars: tuple`, `abs_mode: bool = False`
  - `harness.evaluate_family(spec, close_panel, bucket_panel) -> tuple[pd.DataFrame, pd.DataFrame, str]` returning (full event-study stats, per-(bucket,horizon) checks table, verdict "SURVIVOR"|"REJECTED"). Checks table columns: `family, bucket, horizon_bars, count, t_stat, edge, edge_h1, edge_h2, direction, passes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_intraday_harness.py`:

```python
"""Pre-registered survivor rule: planted edges pass, null noise fails,
split-half sign flips fail, thin buckets fail."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import harness
from research.signals.intraday.harness import FamilySpec

N_BARS = 3000
BAR_MS = 900_000
IDX = pd.Index(np.arange(N_BARS) * BAR_MS, name="open_time")
SYMS = ["AAAUSDT", "BBBUSDT"]


def _spec(extreme_sign=1, middle=("M",), abs_mode=False):
    return FamilySpec(
        name="synthetic", build=lambda data: None,
        extreme={"X": extreme_sign}, middle=list(middle),
        horizons_bars=(4,), abs_mode=abs_mode,
    )


def _panels(drift_after_x: float, flip_second_half: bool = False, n_x: int = 300):
    """Close panel + bucket panel: bucket X fires n_x times per symbol (spaced
    ~10 bars so 4-bar drift windows never overlap adjacent events); each firing
    is followed by `drift_after_x` return over the next 4 bars."""
    rng = np.random.default_rng(7)
    close = pd.DataFrame(100.0, index=IDX, columns=SYMS)
    buckets = pd.DataFrame("M", index=IDX, columns=SYMS)
    x_bars = np.linspace(10, N_BARS - 10, n_x, dtype=int)
    for sym in SYMS:
        prices = np.full(N_BARS, 100.0)
        noise = rng.normal(0, 1e-5, N_BARS)
        step = np.zeros(N_BARS)
        for t in x_bars:
            d = drift_after_x
            if flip_second_half and t > N_BARS // 2:
                d = -drift_after_x
            step[t + 1: t + 5] += d / 4.0
        prices = 100.0 * np.cumprod(1.0 + step + noise)
        close[sym] = prices
        buckets.loc[IDX[x_bars], sym] = "X"
    return close, buckets


def test_planted_edge_survives():
    close, buckets = _panels(drift_after_x=0.01)
    stats, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "SURVIVOR"
    row = checks.iloc[0]
    assert row["passes"]
    assert row["edge"] > harness.ROUND_TRIP
    assert row["count"] >= harness.MIN_COUNT


def test_null_noise_rejected():
    close, buckets = _panels(drift_after_x=0.0)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"
    assert not checks["passes"].any()


def test_split_half_sign_flip_rejected():
    close, buckets = _panels(drift_after_x=0.02, flip_second_half=True)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"


def test_thin_bucket_rejected():
    close, buckets = _panels(drift_after_x=0.01, n_x=100)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"
    assert (checks["count"] < harness.MIN_COUNT).all()


def test_wrong_direction_rejected():
    close, buckets = _panels(drift_after_x=0.01)
    _, _, verdict = harness.evaluate_family(_spec(extreme_sign=-1), close, buckets)
    assert verdict == "REJECTED"


def test_data_determined_sign_passes_either_direction():
    close, buckets = _panels(drift_after_x=-0.01)
    _, checks, verdict = harness.evaluate_family(_spec(extreme_sign=0), close, buckets)
    assert verdict == "SURVIVOR"
    assert checks.iloc[0]["direction"] == -1


def test_abs_mode_detects_movement_without_direction():
    close, buckets = _panels(drift_after_x=0.01, flip_second_half=True)
    _, _, verdict = harness.evaluate_family(
        _spec(abs_mode=True), close, buckets
    )
    assert verdict == "SURVIVOR"


def test_none_middle_uses_all_other_buckets():
    close, buckets = _panels(drift_after_x=0.01)
    spec = FamilySpec(
        name="synthetic", build=lambda data: None,
        extreme={"X": 1}, middle=None, horizons_bars=(4,),
    )
    _, checks, verdict = harness.evaluate_family(spec, close, buckets)
    assert verdict == "SURVIVOR"


def test_cut_panel_labels_and_shape():
    panel = pd.DataFrame({"AAAUSDT": [0.05, 0.5, 0.95, np.nan]},
                         index=pd.Index([0, 1, 2, 3], name="open_time"))
    out = harness.cut_panel(panel, [0.0, 0.1, 0.9, 1.0001], ["lo", "mid", "hi"])
    assert list(out["AAAUSDT"][:3]) == ["lo", "mid", "hi"]
    assert pd.isna(out["AAAUSDT"].iloc[3])
    assert out.shape == panel.shape
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_harness.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'research.signals.intraday'`.

- [ ] **Step 3: Implement**

Create empty `research/signals/intraday/__init__.py`, then `research/signals/intraday/harness.py`:

```python
"""Shared event-study harness for the intraday edge-hunt (Phase 2a).

PRE-REGISTERED PROTOCOL (2026-07-15, committed before any real-data run —
see docs/superpowers/plans/2026-07-15-intraday-edge-hunt.md):
- Data: klines_15m only, strictly before TRAIN_END (study.py). OOS data
  (>= 2025-07-01) is never loaded in Phase 2a.
- Survivor rule per family: SURVIVOR iff for >= one pre-declared
  (extreme bucket, horizon) pair ALL of:
    1. edge in the hypothesized direction > ROUND_TRIP, where
       edge = bucket mean forward return - pooled middle-bucket mean
       (abs_mode families use mean |forward return| instead);
    2. descriptive |t| of the bucket >= MIN_T (forward returns overlap
       across adjacent bars, inflating t — hence 3.0, and treat as a
       ranking device, not a hypothesis test);
    3. bucket count >= MIN_COUNT;
    4. split-half: the edge has the hypothesized sign in BOTH halves of
       the train window.
  Hypothesized sign 0 = data-determined: the full-train edge sign is the
  direction, and all four conditions still bind (used by time-of-day).
- Multiple testing: 6 families x <=5 horizons x <=24 extreme buckets; the
  t>=3 + cost hurdle + split-half stack is the guard, and EVERY tested
  pair is reported in checks.csv, not only the passes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.siglib.events import event_study

ROUND_TRIP = 0.0016
MIN_T = 3.0
MIN_COUNT = 500


@dataclass(frozen=True)
class FamilySpec:
    name: str
    build: object                      # callable: data dict -> bucket panel
    extreme: dict                      # bucket label -> hypothesized sign (+1/-1/0)
    middle: list | None                # baseline buckets; None = all others
    horizons_bars: tuple
    abs_mode: bool = False


def cut_panel(panel: pd.DataFrame, edges: list, labels: list) -> pd.DataFrame:
    stacked = panel.stack()
    buckets = pd.cut(stacked, bins=edges, labels=labels,
                     include_lowest=True).astype(object)
    return buckets.unstack().reindex(index=panel.index, columns=panel.columns)


def _bucket_means(stats: pd.DataFrame, horizon: int) -> pd.DataFrame:
    return stats[stats["horizon_hours"] == horizon].set_index("bucket")


def _edge(rows: pd.DataFrame, bucket: str, middle: list | None) -> float | None:
    if bucket not in rows.index:
        return None
    base_labels = (middle if middle is not None
                   else [b for b in rows.index if b != bucket])
    base = rows.loc[[b for b in base_labels if b in rows.index]]
    if base.empty or float(base["count"].sum()) == 0:
        return None
    base_mean = float((base["mean"] * base["count"]).sum() / base["count"].sum())
    return float(rows.loc[bucket, "mean"]) - base_mean


def evaluate_family(
    spec: FamilySpec,
    close_panel: pd.DataFrame,
    bucket_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Full-train event study + split-half check per (extreme bucket, horizon)."""
    mid = len(close_panel.index) // 2
    halves = (close_panel.index[:mid], close_panel.index[mid:])

    stats = event_study(close_panel, bucket_panel,
                        horizons_hours=spec.horizons_bars, absolute=spec.abs_mode)
    half_stats = [
        event_study(close_panel.loc[ix], bucket_panel.loc[ix],
                    horizons_hours=spec.horizons_bars, absolute=spec.abs_mode)
        for ix in halves
    ]

    rows = []
    for h in spec.horizons_bars:
        full = _bucket_means(stats, h)
        h1, h2 = (_bucket_means(hs, h) for hs in half_stats)
        for bucket, hyp in spec.extreme.items():
            edge = _edge(full, bucket, spec.middle)
            if edge is None:
                continue
            e1 = _edge(h1, bucket, spec.middle)
            e2 = _edge(h2, bucket, spec.middle)
            count = int(full.loc[bucket, "count"])
            t = float(full.loc[bucket, "t_stat"])
            direction = int(hyp) if hyp != 0 else int(np.sign(edge) or 1)
            passes = (
                edge * direction > ROUND_TRIP
                and abs(t) >= MIN_T
                and count >= MIN_COUNT
                and e1 is not None and e1 * direction > 0
                and e2 is not None and e2 * direction > 0
            )
            rows.append({
                "family": spec.name, "bucket": bucket, "horizon_bars": h,
                "count": count, "t_stat": t, "edge": edge,
                "edge_h1": e1, "edge_h2": e2,
                "direction": direction, "passes": bool(passes),
            })
    checks = pd.DataFrame(rows, columns=[
        "family", "bucket", "horizon_bars", "count", "t_stat", "edge",
        "edge_h1", "edge_h2", "direction", "passes",
    ])
    verdict = "SURVIVOR" if bool(checks["passes"].any()) else "REJECTED"
    return stats, checks, verdict
```

Note on abs_mode: the middle-bucket baseline subtracts typical movement, so `edge` is *extra* |move| beyond baseline; the same `> ROUND_TRIP` hurdle applies.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_harness.py -v`
Expected: 9 passed. If `test_planted_edge_survives` fails on the t-stat or hurdle, the planted drift/noise magnitudes above are chosen with wide margins (1% drift vs 0.16% hurdle; 1e-5 noise) — debug the harness, not the fixture.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: all pass except the known reconcile failure.

- [ ] **Step 6: Commit**

```bash
git add research/signals/intraday/ tests/research/test_intraday_harness.py
git commit -m "feat(research): intraday edge-hunt harness — pre-registered survivor rule"
```

---

### Task 3: Signal families 1–3 — breakout, mean-reversion vs VWAP, squeeze

**Files:**
- Create: `research/signals/intraday/families.py`
- Test: `tests/research/test_intraday_families.py` (create)

**Interfaces:**
- Consumes: `harness.cut_panel`, `harness.FamilySpec`; `siglib.data.to_panel`.
- Produces: `families.breakout_buckets(data)`, `families.mr_vwap_buckets(data)`, `families.squeeze_buckets(data)` — each takes `data: dict` with key `"klines_15m"` (long frame) and returns a bucket-label panel; and the start of `families.FAMILIES: list[FamilySpec]` (first three entries). `data` may also carry `"funding"` (used by Task 4). Constants `BARS_1H = 4`, `BARS_24H = 96`, `BARS_7D = 672`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_intraday_families.py`:

```python
"""Golden bucket tests per family + a shared no-lookahead (truncation
invariance) test: the bucket at bar t must not change when future bars are
removed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import families

BAR_MS = 900_000


def _frame(closes, symbol="AAAUSDT", volume=None, taker=None, quote=None):
    n = len(closes)
    volume = volume if volume is not None else [10.0] * n
    return pd.DataFrame({
        "symbol": symbol,
        "open_time": np.arange(n) * BAR_MS,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": volume,
        "quote_volume": quote if quote is not None else list(np.asarray(closes) * np.asarray(volume)),
        "taker_buy_volume": taker if taker is not None else [5.0] * n,
        "trades": 1,
    })


def test_breakout_flags_new_high():
    # oscillating prior range (100..101) so the Donchian width is non-zero
    closes = [100.0 + (i % 2) for i in range(200)] + [110.0]
    data = {"klines_15m": _frame(closes)}
    b = families.breakout_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "break_up"


def test_breakout_flags_new_low():
    closes = [100.0 + (i % 2) for i in range(200)] + [90.0]
    data = {"klines_15m": _frame(closes)}
    b = families.breakout_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "break_down"


def test_mr_vwap_flags_positive_spike():
    rng = np.random.default_rng(3)
    closes = list(100.0 + rng.normal(0, 0.05, 300))
    closes.append(103.0)
    data = {"klines_15m": _frame(closes)}
    b = families.mr_vwap_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "z>3"


def test_squeeze_flags_compression():
    rng = np.random.default_rng(4)
    wild = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, 700))
    quiet = wild[-1] * np.cumprod(1 + rng.normal(0, 0.0005, 200))
    data = {"klines_15m": _frame(list(wild) + list(quiet))}
    b = families.squeeze_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "r<.4"


def _synthetic_data(n=900, seed=11):
    rng = np.random.default_rng(seed)
    frames = []
    for sym in ("AAAUSDT", "BBBUSDT"):
        closes = list(100.0 * np.cumprod(1 + rng.normal(0, 0.004, n)))
        vol = list(rng.uniform(5, 50, n))
        taker = [v * r for v, r in zip(vol, rng.uniform(0.2, 0.8, n))]
        frames.append(_frame(closes, symbol=sym, volume=vol, taker=taker))
    df = pd.concat(frames, ignore_index=True)
    funding = pd.DataFrame({
        "symbol": "AAAUSDT",
        "funding_time": np.arange(0, n * BAR_MS, 32 * BAR_MS),
        "funding_rate": rng.normal(0, 3e-4, len(np.arange(0, n * BAR_MS, 32 * BAR_MS))),
        "mark_price": 100.0,
    })
    return {"klines_15m": df, "funding": funding}


@pytest.mark.parametrize("spec", families.FAMILIES, ids=lambda s: s.name)
def test_no_lookahead_truncation_invariance(spec):
    data = _synthetic_data()
    full = spec.build(data)

    cut = 700
    cut_ms = cut * BAR_MS
    data_trunc = {
        "klines_15m": data["klines_15m"][data["klines_15m"]["open_time"] < cut_ms],
        "funding": data["funding"][data["funding"]["funding_time"] < cut_ms],
    }
    trunc = spec.build(data_trunc)

    common = trunc.index
    a = full.loc[common].fillna("~nan~")
    b = trunc.fillna("~nan~")
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
```

(The truncation test parametrizes over ALL `FAMILIES` — after Task 4 lands the remaining three, they're covered automatically.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_families.py -v`
Expected: collection error — `ImportError: cannot import name 'families'`.

- [ ] **Step 3: Implement `research/signals/intraday/families.py`**

```python
"""The six pre-registered intraday signal families (Phase 2a).

Each builder: data dict (long warehouse frames) -> bucket-label panel
(index=open_time, columns=symbol). Bucket edges, horizons, and hypotheses
are pre-registered in docs/superpowers/plans/2026-07-15-intraday-edge-hunt.md
and MUST NOT change after the real-data run.

Family 5 note: the spec's "volume/OI impulse" runs as volume/taker-flow only —
Binance serves ~30 trailing days of OI, so no OI history exists in the train
window. Recorded as a known limitation in the Phase 2a report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.signals.intraday.harness import FamilySpec, cut_panel

BARS_1H = 4
BARS_24H = 96
BARS_7D = 672


def _close(data):
    return sdata.to_panel(data["klines_15m"], "close")


def breakout_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    hi = close.rolling(BARS_24H, min_periods=BARS_24H).max().shift(1)
    lo = close.rolling(BARS_24H, min_periods=BARS_24H).min().shift(1)
    rng = hi - lo
    pos = (close - lo) / rng.where(rng > 0)
    return cut_panel(
        pos,
        [-np.inf, 0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0, np.inf],
        ["break_down", "0-.1", ".1-.25", ".25-.5", ".5-.75", ".75-.9",
         ".9-1", "break_up"],
    )


def mr_vwap_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    v = sdata.to_panel(data["klines_15m"], "volume")
    qv = sdata.to_panel(data["klines_15m"], "quote_volume")
    vsum = v.rolling(BARS_24H, min_periods=BARS_24H).sum()
    vwap = qv.rolling(BARS_24H, min_periods=BARS_24H).sum() / vsum.where(vsum > 0)
    sd = close.rolling(BARS_24H, min_periods=BARS_24H).std()
    z = (close - vwap) / sd.where(sd > 0)
    return cut_panel(
        z,
        [-np.inf, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, np.inf],
        ["z<-3", "z-3..-2", "z-2..-1", "z-1..1", "z1..2", "z2..3", "z>3"],
    )


def squeeze_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    ret = close.pct_change()
    short_vol = ret.rolling(BARS_24H, min_periods=BARS_24H).std()
    long_vol = ret.rolling(BARS_7D, min_periods=BARS_7D).std()
    ratio = short_vol / long_vol.where(long_vol > 0)
    return cut_panel(
        ratio,
        [0.0, 0.4, 0.6, 0.8, 1.0, 1.25, np.inf],
        ["r<.4", ".4-.6", ".6-.8", ".8-1", "1-1.25", ">1.25"],
    )


FAMILIES: list[FamilySpec] = [
    FamilySpec(
        name="breakout", build=breakout_buckets,
        extreme={"break_up": 1, "break_down": -1},
        middle=[".25-.5", ".5-.75"],
        horizons_bars=(4, 16, 32, 96),
    ),
    FamilySpec(
        name="mr_vwap", build=mr_vwap_buckets,
        extreme={"z<-3": 1, "z>3": -1},
        middle=["z-1..1"],
        horizons_bars=(1, 4, 16, 32),
    ),
    FamilySpec(
        name="squeeze", build=squeeze_buckets,
        extreme={"r<.4": 1, ".4-.6": 1},
        middle=[".8-1", "1-1.25"],
        horizons_bars=(16, 32, 96),
        abs_mode=True,
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_families.py -v`
Expected: 4 golden tests + 3 truncation-invariance instances pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/families.py tests/research/test_intraday_families.py
git commit -m "feat(research): intraday families 1-3 — breakout, MR-vs-VWAP, squeeze"
```

---

### Task 4: Signal families 4–6 — funding-window, volume impulse, time-of-day

**Files:**
- Modify: `research/signals/intraday/families.py`
- Test: `tests/research/test_intraday_families.py` (append golden tests)

**Interfaces:**
- Consumes: Task 3's module layout; `data["funding"]` long frame `[symbol, funding_time, funding_rate, mark_price]`.
- Produces: `families.funding_buckets(data)`, `families.vol_impulse_buckets(data)`, `families.tod_buckets(data)`; `FAMILIES` grows to 6 entries. The existing truncation-invariance parametrization covers the new families automatically.

- [ ] **Step 1: Append the failing golden tests to `tests/research/test_intraday_families.py`**

```python
def test_funding_buckets_use_last_known_rate_no_lookahead():
    n = 200
    data = {"klines_15m": _frame([100.0] * n)}
    data["funding"] = pd.DataFrame({
        "symbol": "AAAUSDT",
        "funding_time": [50 * BAR_MS, 120 * BAR_MS],
        "funding_rate": [2e-3, -2e-3],
        "mark_price": 100.0,
    })
    b = families.funding_buckets(data)
    assert pd.isna(b["AAAUSDT"].iloc[10])          # before first event: unknown
    assert b["AAAUSDT"].iloc[60] == "f>+.1%"       # after +0.2% event
    assert b["AAAUSDT"].iloc[119] == "f>+.1%"      # event at bar 120 not yet known at 119
    assert b["AAAUSDT"].iloc[125] == "f<-.1%"      # after -0.2% event


def test_vol_impulse_flags_buy_surge():
    n = 200
    vol = [10.0] * n
    taker = [5.0] * n
    vol[-1] = 100.0       # 10x surge
    taker[-1] = 90.0      # 90% taker-buy
    data = {"klines_15m": _frame([100.0] * n, volume=vol, taker=taker)}
    b = families.vol_impulse_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "i>1.5"


def test_tod_buckets_are_utc_hour():
    data = {"klines_15m": _frame([100.0] * 8)}   # bars at 00:00..01:45 UTC
    b = families.tod_buckets(data)
    assert b["AAAUSDT"].iloc[0] == "h00"
    assert b["AAAUSDT"].iloc[4] == "h01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_intraday_families.py -v`
Expected: the 3 new tests FAIL (`AttributeError: ... no attribute 'funding_buckets'`); existing tests still pass.

- [ ] **Step 3: Implement — append to `research/signals/intraday/families.py`**

```python
def funding_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    f = data["funding"].pivot(index="funding_time", columns="symbol",
                              values="funding_rate")
    f = f.reindex(columns=close.columns)
    rate = (
        f.reindex(f.index.union(close.index)).sort_index().ffill()
        .loc[close.index]
    )
    rate = rate.where(close.notna())
    return cut_panel(
        rate,
        [-np.inf, -1e-3, -3e-4, -1e-4, 1e-4, 3e-4, 1e-3, np.inf],
        ["f<-.1%", "-.1..-.03%", "-.03..-.01%", "-.01..+.01%",
         "+.01..+.03%", "+.03..+.1%", "f>+.1%"],
    )


def vol_impulse_buckets(data: dict) -> pd.DataFrame:
    v = sdata.to_panel(data["klines_15m"], "volume")
    tb = sdata.to_panel(data["klines_15m"], "taker_buy_volume")
    imb = (tb / v.where(v > 0)) - 0.5
    base = v.rolling(BARS_24H, min_periods=BARS_24H).mean().shift(1)
    surge = (v / base.where(base > 0)).clip(upper=10.0)
    impulse = imb * surge
    return cut_panel(
        impulse,
        [-np.inf, -1.5, -0.75, -0.25, 0.25, 0.75, 1.5, np.inf],
        ["i<-1.5", "-1.5..-.75", "-.75..-.25", "-.25...25",
         ".25..0.75", ".75..1.5", "i>1.5"],
    )


def tod_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    hours = (close.index.to_numpy() // 3_600_000) % 24
    labels = pd.Series([f"h{h:02d}" for h in hours], index=close.index)
    panel = pd.DataFrame(
        np.broadcast_to(labels.to_numpy()[:, None], close.shape).copy(),
        index=close.index, columns=close.columns,
    )
    return panel.where(close.notna())


FAMILIES.extend([
    FamilySpec(
        name="funding_window", build=funding_buckets,
        extreme={"f<-.1%": 1, "f>+.1%": -1},
        middle=["-.01..+.01%"],
        horizons_bars=(16, 32, 96),
    ),
    FamilySpec(
        name="vol_impulse", build=vol_impulse_buckets,
        extreme={"i>1.5": 1, "i<-1.5": -1},
        middle=["-.25...25"],
        horizons_bars=(1, 4, 16, 32),
    ),
    FamilySpec(
        name="time_of_day", build=tod_buckets,
        extreme={f"h{h:02d}": 0 for h in range(24)},
        middle=None,
        horizons_bars=(4,),
    ),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_intraday_families.py -v`
Expected: all pass, including 6 truncation-invariance instances (the parametrization picked up the new families).

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/families.py tests/research/test_intraday_families.py
git commit -m "feat(research): intraday families 4-6 — funding window, volume impulse, time-of-day"
```

---

### Task 5: Study CLI — run all families on train data, write stats + verdicts

**Files:**
- Create: `research/signals/intraday/study.py`
- Test: `tests/research/test_intraday_study_cli.py` (create)

**Interfaces:**
- Consumes: `families.FAMILIES`, `harness.evaluate_family`, `siglib.data` loaders, `eligible_mask`.
- Produces: CLI `python -m research.signals.intraday.study [--out DIR]` writing to DIR (default `research/signals/intraday/output/`): `<family>_event_study.csv` per family, `checks.csv` (all tested pairs, all families), `verdicts.json` (`{family: "SURVIVOR"|"REJECTED"}`), and printing a verdict table. `study.TRAIN_END = "2025-07-01"`.

- [ ] **Step 1: Write the failing test**

Create `tests/research/test_intraday_study_cli.py`:

```python
"""End-to-end smoke test on a tiny synthetic warehouse: the CLI runs all six
families, writes per-family stats, one checks.csv, and verdicts.json."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research import store
from research.signals.intraday import study

BAR_MS = 900_000
N = 1200


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _seed_warehouse():
    rng = np.random.default_rng(21)
    for sym in ("AAAUSDT", "BBBUSDT", "CCCUSDT"):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.004, N))
        vol = rng.uniform(5, 50, N)
        rows = [{
            "open_time": i * BAR_MS, "open": float(closes[i]),
            "high": float(closes[i]), "low": float(closes[i]),
            "close": float(closes[i]), "volume": float(vol[i]),
            "close_time": i * BAR_MS + BAR_MS - 1,
            "quote_volume": float(closes[i] * vol[i]), "trades": 5,
            "taker_buy_volume": float(vol[i] * rng.uniform(0.3, 0.7)),
            "taker_buy_quote_volume": 0.0,
        } for i in range(N)]
        store.upsert("klines_15m", sym, rows, "open_time")
        frows = [{"funding_time": t, "funding_rate": float(rng.normal(0, 2e-4)),
                  "mark_price": 100.0}
                 for t in range(0, N * BAR_MS, 32 * BAR_MS)]
        store.upsert("funding", sym, frows, "funding_time")


def test_study_cli_end_to_end(warehouse, tmp_path, monkeypatch):
    _seed_warehouse()
    out = tmp_path / "out"
    monkeypatch.setattr(study.sdata, "ELIGIBILITY_DAYS", 0)
    monkeypatch.setattr("sys.argv", ["study", "--out", str(out)])

    study.main()

    verdicts = json.loads((out / "verdicts.json").read_text())
    assert set(verdicts) == {
        "breakout", "mr_vwap", "squeeze", "funding_window",
        "vol_impulse", "time_of_day",
    }
    assert set(verdicts.values()) <= {"SURVIVOR", "REJECTED"}
    checks = pd.read_csv(out / "checks.csv")
    # extreme buckets may simply never fire in a small random panel, so a
    # family can legitimately contribute zero check rows — subset, not equality
    assert set(checks["family"]) <= set(verdicts)
    assert len(checks) > 0          # time_of_day alone guarantees rows
    for fam in verdicts:
        assert (out / f"{fam}_event_study.csv").exists()
```

(`ELIGIBILITY_DAYS` is patched to 0 because the synthetic history is only ~12 days; the real run keeps the 60-day rule.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/research/test_intraday_study_cli.py -v`
Expected: collection error — no module `research.signals.intraday.study`.

- [ ] **Step 3: Implement `research/signals/intraday/study.py`**

```python
"""Phase 2a edge-hunt runner: all six families, 15m train data only.

PRE-REGISTERED (2026-07-15): TRAIN_END = 2025-07-01 — nothing on/after this
date is loaded here. OOS (3 windows over 2025-07-01..2026-07-15) is reserved
for Phase 2b. Survivor rule and family definitions: see harness.py and
families.py; every tested pair lands in checks.csv.

Run:  python -m research.signals.intraday.study
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.siglib import data as sdata
from research.signals.intraday.families import FAMILIES
from research.signals.intraday.harness import evaluate_family

TRAIN_END = "2025-07-01"
DEFAULT_OUT = Path(__file__).parent / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df15 = sdata.load_klines("all", interval="15m", end=TRAIN_END)
    if df15.empty:
        raise SystemExit("no klines_15m data in the warehouse before TRAIN_END")
    funding = sdata.load_funding("all", end=TRAIN_END)
    data = {"klines_15m": df15, "funding": funding}

    close = sdata.to_panel(df15, "close")
    elig = (
        sdata.eligible_mask(df15)
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
    )
    print(f"train: {df15['symbol'].nunique()} symbols, "
          f"{len(close.index)} bars < {TRAIN_END}")

    verdicts, all_checks = {}, []
    for spec in FAMILIES:
        buckets = spec.build(data).where(elig)
        stats, checks, verdict = evaluate_family(spec, close, buckets)
        stats.to_csv(out / f"{spec.name}_event_study.csv", index=False)
        all_checks.append(checks)
        verdicts[spec.name] = verdict
        n_pass = int(checks["passes"].sum())
        print(f"{spec.name:<16} {verdict:<9} "
              f"({n_pass}/{len(checks)} bucket x horizon pairs pass)")

    pd.concat(all_checks, ignore_index=True).to_csv(out / "checks.csv", index=False)
    (out / "verdicts.json").write_text(json.dumps(verdicts, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/research/test_intraday_study_cli.py -v`
Expected: 1 passed (runtime under ~30s — synthetic panel is small).

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/study.py tests/research/test_intraday_study_cli.py
git commit -m "feat(research): intraday edge-hunt study CLI (pre-registered, train-only)"
```

---

### Task 6: Run the edge-hunt on real data and write the findings report (ops)

**Files:**
- Create: `research/signals/intraday/output/*.csv`, `verdicts.json` (committed — they are the pre-registration evidence)
- Create: `docs/superpowers/specs/2026-07-XX-intraday-edge-hunt-findings.md` (dated the day it runs)

**Interfaces:**
- Consumes: the CLI from Task 5, real `klines_15m`/`funding` warehouse data.
- Produces: the survivor list that scopes Phase 2b.

- [ ] **Step 1: Confirm pre-registration is committed, then run**

```bash
git log --oneline -1   # must show Task 5's commit (or later)
python -m research.signals.intraday.study 2>&1 | tee /tmp/edge-hunt-run.log
```
Expected: `train: 30 symbols, ~87k bars < 2025-07-01` (symbols listed after ~2025-05 contribute little/nothing to train — that's correct, not a bug), six verdict lines, outputs written. Runtime: minutes.

- [ ] **Step 2: Sanity-check the outputs before reading results as findings**

```bash
python - <<'EOF'
import pandas as pd
c = pd.read_csv("research/signals/intraday/output/checks.csv")
print(c.groupby("family").agg(pairs=("passes", "size"), passes=("passes", "sum")))
print("\ntotal events by family/bucket (min):")
print(c.groupby("family")["count"].min())
EOF
```
Check: every family present; counts plausible (thousands+, not tens — if a family's counts are tiny, suspect a bucketing bug and STOP before interpreting).

- [ ] **Step 3: Write the findings report**

Create `docs/superpowers/specs/2026-07-XX-intraday-edge-hunt-findings.md` with these required sections (content comes from the run):
1. **Protocol** — link to this plan; state the rule was committed before the run (cite the two commit SHAs).
2. **Verdict table** — per family: verdict, best (bucket, horizon) pair with edge/t/count/split-half values.
3. **Per-family notes** — for survivors: which buckets/horizons passed and the shape of the bucket curve (monotone? cliff?); for rejects: how far from the bar they fell.
4. **Known caveats** — survivorship-biased universe (top-30 chosen 2026-07-15); overlap-inflated t-stats; volume-only family 5 (no historical OI); funding staleness (rate known at bar open, conservative by ≤1 bar).
5. **Phase 2b scope** — which survivors proceed to strategy backtests; if ZERO survive, the pre-agreed fallback applies (build the engine anyway, paper-trade the least-bad candidate — user decision 2026-07-15).

- [ ] **Step 4: Commit outputs + report**

```bash
git add research/signals/intraday/output/ docs/superpowers/specs/
git commit -m "research: intraday edge-hunt results — verdicts + findings report"
```

---

## Verification (whole phase)

- `python -m pytest` — green (except the known pre-existing reconcile failure).
- `research/signals/intraday/output/verdicts.json` exists with all six families and is committed AFTER the code that produced it (pre-registration order provable from `git log`).
- The findings report names the Phase 2b survivors (possibly none) and carries all four caveats.
- No file under `research/` loads data ≥ 2025-07-01 in this phase (grep for `TRAIN_END` usage: only `study.py` calls the loaders).
