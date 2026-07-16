# mr_vwap Strategy Backtest (Phase 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtest the Phase 2a survivor (mr_vwap long side: deep oversold vs 24h VWAP on 15m bars) as a real strategy through the verified `siglib` engine, in two pre-registered execution variants — **next-bar taker** (base case: expected to FAIL per findings caveat #6) and **maker-limit entry** (the real question: same signal, ~2bps entry cost instead of 8) — freeze parameters on train, then unseal the OOS year ONCE and judge against the pre-registered pass bar.

**Architecture:** One engine extension (asymmetric buy/sell costs in `siglib.backtest`), one pure strategy module (`mr_vwap_strategy.py`: panels in → weights panel out, both fill models), a train-phase runner (grid + mechanical selection + diagnostics, train-only), and an OOS evaluator (committed before it is ever run; running it IS the unseal). Findings doc `docs/superpowers/specs/2026-07-15-intraday-edge-hunt-findings.md` §5 requirements are all encoded here.

**Tech Stack:** Python 3.12, pandas/pyarrow (no new deps), pytest, `siglib` (verified engine — the ONLY place PnL is computed). Warehouse-only; no network.

## Global Constraints (the Phase 2b pre-registration — frozen once Task 5's run starts)

- **OOS seal:** no code path loads data ≥ `2025-07-01` until Task 5's explicit unseal step, which runs the Task 4 evaluator ONCE per variant. No iteration after unseal — whatever it says is the verdict.
- **Signal (fixed from 2a, not searched):** entry when z < −3.0, where z = (close − VWAP₉₆)/σ₉₆ on 15m bars (exact 2a definition via `families.mr_vwap_z`); long only. `z_recover` exit threshold fixed at −1.0.
- **Entry conventions (findings caveat #6):**
  - `next_bar` (taker, base case): signal at bar t → position earns from close[t+1] (weights shifted one extra bar). Costs: entry+exit at `INTRADAY` (5bps taker + 3bps slippage per side).
  - `maker_limit`: limit bid at close[t] placed at t's close; fills during bar t+1 **only if low[t+1] < close[t]** (strict trade-through ⇒ certain fill; touching doesn't count — queue position is not assumed). Filled position earns from close[t] (= the limit price, matching the engine's w[t] convention). Costs: entry at `MAKER_ENTRY` (2bps fee + 0 slippage), exit at `INTRADAY` taker. Missed fills are skipped — that lost-winner adverse selection is the honest price of maker.
- **Stress costs:** `next_bar` → `STRESS` (5+10) both sides; `maker_limit` → entry `MAKER_ENTRY_STRESS` (2+2), exit `STRESS`.
- **Parameter grid (train-only selection):** H ∈ {8, 16, 32} bars of exposure × exit ∈ {horizon, z_recover} × K ∈ {3, 5, 10} max concurrent positions = 18 combos per fill variant. Sizing: fixed slots of 1/K gross each, idle slots in cash. Tie-break when signals exceed free slots: lowest z first. Exits free slots before entries within a bar.
- **Selection rule (mechanical, per variant, basis_mr precedent):** eligible = n_trades ≥ 100 AND total_return > 0 on train; rank by annualized Sharpe of bar net returns (BARS_PER_YEAR = 4×24×365 = 35040); plateau guard: prefer the best combo whose one-step H/K grid neighbors (same exit) all have Sharpe > 0, else global best flagged `cliff`. If NO combo is eligible for a variant, that variant is NOT VIABLE; if both variants fail, Phase 2b ends REJECTED **without unsealing OOS**.
- **Pass bar (OOS, per variant, from spec §3):** net profit factor ≥ 1.15 on bar returns, ≥ 100 OOS trades (engine `n_trades`), positive total return in ≥ 2 of 3 windows — W1 2025-07-01→2025-11-01, W2 2025-11-01→2026-03-01, W3 2026-03-01→end — max drawdown ≤ 20% on the full OOS slice. Judged mechanically at baseline costs; stress result reported alongside.
- **Point-in-time universe gate:** symbol tradable at bar t only if its trailing 30-day median daily quote volume ranks ≤ 30 among ALL warehouse `klines_1d` symbols, effective from the day AFTER the ranking day closes (no same-day lookahead). Partial mitigation only — the top-100 pool itself was selected on 2026-07-15; carry the caveat.
- **Diagnostics before unseal (findings §5):** per-symbol PnL decomposition, distinct-episode counts (not overlapping bar-events), monthly return table, edge-t of strategy bar returns; descriptive 5m robustness check (z window 288 bars, horizons ×3, train slice 2025-01-13→07-01) — all train-only, none may alter frozen params.
- Run `python -m pytest` before every commit; only allowed failure: pre-existing `tests/swing/test_reconcile.py::test_stale_row_closed_from_fills`.
- Commits go directly to `main`. Don't add comments/docstrings/type annotations to code you didn't change.

---

### Task 1: Engine asymmetric costs + maker cost models + 2a backlog tests

**Files:**
- Modify: `research/siglib/backtest.py` (run_backtest sell-side cost split)
- Modify: `research/siglib/costs.py` (MAKER_ENTRY, MAKER_ENTRY_STRESS)
- Test: `tests/research/test_backtest_asymmetric_costs.py` (create)
- Test: `tests/research/test_intraday_harness.py` (append two 2a-backlog tests)

**Interfaces:**
- Produces: `run_backtest(..., sell_cost_model: CostModel | None = None)` — None keeps exact current behavior; when set, positive executed weight changes (buys) are charged at `cost_model.cost_per_side` and negative ones (sells) at `sell_cost_model.cost_per_side`. For a long-only book buys = entries, sells = exits. `costs.MAKER_ENTRY = CostModel(taker_bps=2.0, slippage_bps=0.0)`; `costs.MAKER_ENTRY_STRESS = CostModel(taker_bps=2.0, slippage_bps=2.0)`. Tasks 3–4 rely on these names.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_backtest_asymmetric_costs.py`:

```python
"""Asymmetric buy/sell costs: default unchanged; long-only entry/exit split."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.siglib.backtest import run_backtest
from research.siglib.costs import CostModel

IDX = pd.Index(np.arange(10) * 900_000, name="open_time")


def _flat_prices():
    return pd.DataFrame({"AAAUSDT": [100.0] * 10}, index=IDX)


def _one_round_trip():
    w = pd.DataFrame(0.0, index=IDX, columns=["AAAUSDT"])
    w.iloc[2:5] = 1.0  # decided on bars 2-4 -> enter at bar 3, exit at bar 5
    return w


def test_none_sell_model_matches_symmetric():
    prices, w = _flat_prices(), _one_round_trip()
    base = run_backtest(prices, w, CostModel())
    explicit = run_backtest(prices, w, CostModel(), sell_cost_model=CostModel())
    pd.testing.assert_series_equal(base.returns, explicit.returns)
    pd.testing.assert_series_equal(base.trade_costs, explicit.trade_costs)


def test_long_only_entry_exit_rates_split():
    prices, w = _flat_prices(), _one_round_trip()
    buy = CostModel(taker_bps=2.0, slippage_bps=0.0)    # 2 bps/side
    sell = CostModel(taker_bps=5.0, slippage_bps=3.0)   # 8 bps/side
    res = run_backtest(prices, w, buy, sell_cost_model=sell)
    # entry decided bar 2 executes bar 3; exit decided bar 5 executes bar 6
    assert res.trade_costs.iloc[3] == pytest.approx(1.0 * 0.0002)
    assert res.trade_costs.iloc[6] == pytest.approx(1.0 * 0.0008)
    assert float(res.trade_costs.sum()) == pytest.approx(0.0010)
    assert res.n_trades == 2
    assert float(res.turnover_per_bar.sum()) == pytest.approx(2.0)


def test_maker_cost_models_registered():
    from research.siglib import costs
    assert costs.MAKER_ENTRY.cost_per_side == pytest.approx(0.0002)
    assert costs.MAKER_ENTRY_STRESS.cost_per_side == pytest.approx(0.0004)
```

Append to `tests/research/test_intraday_harness.py` (2a review backlog):

```python
def test_min_t_gate_binds_independently(monkeypatch):
    close, buckets = _panels(drift_after_x=0.01)
    monkeypatch.setattr(harness, "MIN_T", 1e9)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"
    row = checks.iloc[0]
    assert row["edge"] > harness.ROUND_TRIP and row["count"] >= harness.MIN_COUNT
    assert not row["passes"]


def test_edge_uses_count_weighted_middle_baseline():
    stats = pd.DataFrame({
        "bucket": ["X", "M1", "M2"],
        "count": [50, 100, 300],
        "mean": [0.05, 0.01, 0.02],
    }).set_index("bucket")
    edge = harness._edge(stats, "X", ["M1", "M2"])
    assert edge == pytest.approx(0.05 - (0.01 * 100 + 0.02 * 300) / 400)
```

(`test_intraday_harness.py` already imports `pandas as pd`? It does not — add `import pandas as pd` and `import pytest` to its imports if missing; it currently imports numpy, pandas, and the harness — check the file header and add only what's absent.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_backtest_asymmetric_costs.py tests/research/test_intraday_harness.py -v`
Expected: `test_long_only_entry_exit_rates_split` FAILS (`TypeError: ... unexpected keyword argument 'sell_cost_model'`); `test_maker_cost_models_registered` FAILS (AttributeError); the two harness tests PASS or FAIL depending only on missing imports — if they pass already, they are regression pins, fine.

- [ ] **Step 3: Implement**

`research/siglib/costs.py` — append:

```python
# Phase 2b maker-limit entry model: 2 bps maker fee, no slippage at the limit
# price (the fill IS the quoted price); stress adds 2 bps adverse-fill drift.
MAKER_ENTRY = CostModel(taker_bps=2.0, slippage_bps=0.0)
MAKER_ENTRY_STRESS = CostModel(taker_bps=2.0, slippage_bps=2.0)
```

`research/siglib/backtest.py` — signature gains the parameter:

```python
def run_backtest(
    prices_1h_panel: pd.DataFrame,
    target_weights_panel: pd.DataFrame,
    cost_model: CostModel,
    funding_long: pd.DataFrame | None = None,
    eligibility: pd.DataFrame | None = None,
    sell_cost_model: CostModel | None = None,
) -> BacktestResult:
```

Docstring addition (one line, under the cost_model param docs): `sell_cost_model: optional separate rate for negative executed weight changes (sells); buys stay on cost_model. For long-only books this splits entry/exit costs. None = symmetric (unchanged behavior).`

Replace the turnover/cost block (currently `dw_exec = dw.shift(1).fillna(0.0).abs()` and `trade_costs = turnover_per_bar * cost_model.cost_per_side`) with:

```python
    dw = w - w.shift(1).fillna(0.0)
    dw_exec_signed = dw.shift(1).fillna(0.0)
    dw_exec = dw_exec_signed.abs()
    turnover_per_bar = dw_exec.sum(axis=1)
    trades_per_bar = (dw_exec > _TRADE_TOL).sum(axis=1)
    if sell_cost_model is None:
        trade_costs = turnover_per_bar * cost_model.cost_per_side
    else:
        buy_turnover = dw_exec_signed.clip(lower=0.0).sum(axis=1)
        sell_turnover = (-dw_exec_signed.clip(upper=0.0)).sum(axis=1)
        trade_costs = (buy_turnover * cost_model.cost_per_side
                       + sell_turnover * sell_cost_model.cost_per_side)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_backtest_asymmetric_costs.py tests/research/test_intraday_harness.py -v`
Expected: all pass (3 new cost tests + 12 harness tests).

- [ ] **Step 5: Run the full suite (the engine is shared — its lookahead-pin and v2 tests must stay green), then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/siglib/backtest.py research/siglib/costs.py tests/research/test_backtest_asymmetric_costs.py tests/research/test_intraday_harness.py
git commit -m "feat(research): asymmetric buy/sell costs in engine + maker cost models + 2a backlog tests"
```

---

### Task 2: Strategy module — weights builder with both fill models + PIT universe gate

**Files:**
- Modify: `research/signals/intraday/families.py` (extract public `mr_vwap_z`)
- Create: `research/signals/intraday/mr_vwap_strategy.py`
- Test: `tests/research/test_mr_vwap_strategy.py` (create)

**Interfaces:**
- Produces (Tasks 3–4 rely on these exact names):
  - `families.mr_vwap_z(data) -> pd.DataFrame` — the exact z panel 2a bucketed (`mr_vwap_buckets` refactored to call it; existing golden tests must stay green unchanged).
  - `mr_vwap_strategy.pit_top30_mask(df_1d_long, index_15m, columns) -> pd.DataFrame` — boolean panel, ranking effective from the day after the ranking day closes.
  - `mr_vwap_strategy.build_weights(z, close, low, elig, params, fill) -> pd.DataFrame` — params `{"horizon_bars": int, "exit": "horizon"|"z_recover", "max_k": int}`, fill `"next_bar"|"maker_limit"`; weights ∈ {0, 1/K}. Constants `Z_ENTRY = -3.0`, `Z_RECOVER = -1.0`, `PIT_TOP_N = 30`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_mr_vwap_strategy.py`:

```python
"""Golden money-path tests for the 2b weights builder: entry timing per fill
model, maker fill condition, exits, slot cap, PIT gate timing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import mr_vwap_strategy as strat

BAR_MS = 900_000
DAY_MS = 86_400_000
N = 40
IDX = pd.Index(np.arange(N) * BAR_MS, name="open_time")
SYMS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


def _panels(z_hits: dict, low_offset: float = -1.0):
    """z: -5 at (bar, symbol) per z_hits {sym: [bars]}, else 0.
    low = close + low_offset (negative offset => maker limit trades through)."""
    z = pd.DataFrame(0.0, index=IDX, columns=SYMS)
    for sym, bars in z_hits.items():
        for b in bars:
            z.loc[IDX[b], sym] = -5.0
    close = pd.DataFrame(100.0, index=IDX, columns=SYMS)
    low = close + low_offset
    elig = pd.DataFrame(True, index=IDX, columns=SYMS)
    return z, close, low, elig


PARAMS = {"horizon_bars": 4, "exit": "horizon", "max_k": 2}


def test_next_bar_entry_starts_one_bar_late_and_holds_horizon():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    col = w["AAAUSDT"]
    assert col.iloc[10] == 0.0                       # signal bar: no exposure yet
    assert list(col.iloc[11:15]) == [0.5] * 4        # 4 earning bars from close[11]
    assert col.iloc[15] == 0.0


def test_maker_entry_starts_at_signal_bar_when_filled():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="maker_limit")
    col = w["AAAUSDT"]
    assert list(col.iloc[10:14]) == [0.5] * 4        # fills: low[11] < close[10]
    assert col.iloc[14] == 0.0


def test_maker_miss_when_no_trade_through():
    z, close, low, elig = _panels({"AAAUSDT": [10]}, low_offset=0.0)  # touch only
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="maker_limit")
    assert float(w.abs().sum().sum()) == 0.0


def test_z_recover_exit_cuts_hold_short():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    z.loc[IDX[13], "AAAUSDT"] = 0.0   # already 0, explicit: recovered by bar 13
    params = {"horizon_bars": 20, "exit": "z_recover", "max_k": 2}
    w = strat.build_weights(z, close, low, elig, params, fill="next_bar")
    col = w["AAAUSDT"]
    assert col.iloc[11] == 0.5
    # z > -1 at bar 12 (first held close) -> w goes 0 at bar 12
    assert col.iloc[12] == 0.0


def test_slot_cap_prefers_lowest_z():
    z, close, low, elig = _panels({"AAAUSDT": [10], "BBBUSDT": [10], "CCCUSDT": [10]})
    z.loc[IDX[10], "BBBUSDT"] = -4.0   # least oversold of the three
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    row = w.iloc[11]
    assert row["AAAUSDT"] == 0.5 and row["CCCUSDT"] == 0.5 and row["BBBUSDT"] == 0.0


def test_weights_are_zero_or_slot_size():
    z, close, low, elig = _panels({"AAAUSDT": [5, 20], "BBBUSDT": [12]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    assert set(np.unique(w.to_numpy())) <= {0.0, 0.5}


def test_pit_mask_effective_next_day():
    days = 40
    rows = []
    for sym, qv in (("BIGUSDT", 1000.0), ("SMALLUSDT", 10.0)):
        for i in range(days):
            rows.append({"symbol": sym, "open_time": i * DAY_MS,
                         "close": 1.0, "quote_volume": qv})
    df_1d = pd.DataFrame(rows)
    idx15 = pd.Index([35 * DAY_MS + k * BAR_MS for k in range(4)], name="open_time")
    mask = strat.pit_top30_mask(df_1d, idx15, pd.Index(["BIGUSDT", "SMALLUSDT"]))
    assert bool(mask["BIGUSDT"].all()) and bool(mask["SMALLUSDT"].all())  # both rank <= 30

    # ranking uses data through day d, effective from day d+1: bars before the
    # first ranking day closes must be False
    early = pd.Index([10 * DAY_MS], name="open_time")   # day 10 < 30-day warmup end
    mask_early = strat.pit_top30_mask(df_1d, early, pd.Index(["BIGUSDT"]))
    assert not bool(mask_early["BIGUSDT"].iloc[0])


def test_mr_vwap_z_extracted_and_buckets_unchanged():
    from research.signals.intraday import families
    rng = np.random.default_rng(5)
    n = 300
    closes = list(100.0 + rng.normal(0, 0.05, n))
    df = pd.DataFrame({
        "symbol": "AAAUSDT", "open_time": np.arange(n) * BAR_MS,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [10.0] * n, "quote_volume": [c * 10.0 for c in closes],
        "taker_buy_volume": [5.0] * n, "trades": 1,
    })
    data = {"klines_15m": df}
    z = families.mr_vwap_z(data)
    assert z.shape[1] == 1 and np.isfinite(z.iloc[-1, 0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_mr_vwap_strategy.py -v`
Expected: collection error — no module `mr_vwap_strategy` / no attribute `mr_vwap_z`.

- [ ] **Step 3: Implement**

`research/signals/intraday/families.py` — extract the z computation from `mr_vwap_buckets` into a public function (the bucket function's behavior must not change):

```python
def mr_vwap_z(data: dict) -> pd.DataFrame:
    close = _close(data)
    v = sdata.to_panel(data["klines_15m"], "volume")
    qv = sdata.to_panel(data["klines_15m"], "quote_volume")
    vsum = v.rolling(BARS_24H, min_periods=BARS_24H).sum()
    vwap = qv.rolling(BARS_24H, min_periods=BARS_24H).sum() / vsum.where(vsum > 0)
    sd = close.rolling(BARS_24H, min_periods=BARS_24H).std()
    return (close - vwap) / sd.where(sd > 0)


def mr_vwap_buckets(data: dict) -> pd.DataFrame:
    return cut_panel(
        mr_vwap_z(data),
        [-np.inf, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, np.inf],
        ["z<-3", "z-3..-2", "z-2..-1", "z-1..1", "z1..2", "z2..3", "z>3"],
    )
```

Create `research/signals/intraday/mr_vwap_strategy.py`:

```python
"""Phase 2b strategy: long-only mean reversion on deep oversold vs 24h VWAP.

PRE-REGISTERED (2026-07-16 — docs/superpowers/plans/2026-07-16-mr-vwap-2b-backtest.md):
Z_ENTRY = -3.0 and Z_RECOVER = -1.0 are fixed from Phase 2a, never searched.
Two fill models per findings caveat #6:
- next_bar: signal at t -> exposure starts at close[t+1] (taker base case).
- maker_limit: limit bid at close[t]; fills in bar t+1 only on STRICT
  trade-through (low[t+1] < close[t]); exposure starts at close[t] = the
  limit price, matching the engine's w[t] convention. Missed fills skipped.
Slots: 1/K gross each; exits free slots before entries; lowest z first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research import config

Z_ENTRY = -3.0
Z_RECOVER = -1.0
PIT_TOP_N = 30
PIT_WINDOW_DAYS = 30


def pit_top30_mask(df_1d_long: pd.DataFrame, index_15m: pd.Index,
                   columns: pd.Index) -> pd.DataFrame:
    qv = df_1d_long.pivot(index="open_time", columns="symbol",
                          values="quote_volume").sort_index()
    med = qv.rolling(PIT_WINDOW_DAYS, min_periods=PIT_WINDOW_DAYS).median()
    rank = med.rank(axis=1, ascending=False)
    mask_1d = rank <= PIT_TOP_N
    # a day's bar covers [open, open+1d); its ranking is known at close and
    # applies from the NEXT ms onward — shift the effective index by one day
    mask_1d.index = mask_1d.index + config.DAY_MS
    out = (
        mask_1d.reindex(mask_1d.index.union(index_15m)).sort_index().ffill()
        .loc[index_15m]
        .reindex(columns=columns)
        .fillna(False)
        .astype(bool)
    )
    return out


def build_weights(z: pd.DataFrame, close: pd.DataFrame, low: pd.DataFrame,
                  elig: pd.DataFrame, params: dict, fill: str) -> pd.DataFrame:
    if fill not in ("next_bar", "maker_limit"):
        raise ValueError(f"unknown fill model {fill!r}")
    horizon = int(params["horizon_bars"])
    exit_mode = params["exit"]
    k = int(params["max_k"])
    slot = 1.0 / k

    idx, cols = z.index, z.columns
    n, m = len(idx), len(cols)
    zv = z.to_numpy()
    cv = close.to_numpy()
    lv = low.to_numpy()
    ev = elig.reindex(index=idx, columns=cols).fillna(False).to_numpy()
    signal = (zv < Z_ENTRY) & ev & np.isfinite(cv)

    w = np.zeros((n, m))
    remaining = np.zeros(m, dtype=int)   # earning bars left per symbol (0 = flat)

    for t in range(n):
        # exits first (horizon exhaustion is the age-down at the end of each
        # bar; z is checked from the first held close onward)
        for s in range(m):
            if remaining[s] > 0 and (
                (exit_mode == "z_recover" and zv[t, s] > Z_RECOVER)
                or not ev[t, s]
            ):
                remaining[s] = 0
        # candidate entries effective THIS bar, most-oversold first
        cands = []
        for s in range(m):
            if remaining[s] > 0:
                continue
            if fill == "next_bar":
                if t >= 1 and signal[t - 1, s]:
                    cands.append((zv[t - 1, s], s))
            else:  # maker_limit: signal at t, strict trade-through in t+1
                if t + 1 < n and signal[t, s] and lv[t + 1, s] < cv[t, s]:
                    cands.append((zv[t, s], s))
        cands.sort()
        free = k - int((remaining > 0).sum())
        for _, s in cands[:free]:
            remaining[s] = horizon
        # write weights and age positions
        for s in range(m):
            if remaining[s] > 0:
                w[t, s] = slot
                remaining[s] -= 1

    return pd.DataFrame(w, index=idx, columns=cols)
```

(Engine note: `run_backtest` already forces w to 0 on NaN-price bars, so the builder does not need its own NaN handling beyond the `np.isfinite` guard in `signal`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_mr_vwap_strategy.py tests/research/test_intraday_families.py -v`
Expected: 9 new tests pass AND all existing family tests still pass (the mr_vwap refactor must not change bucket output — `test_mr_vwap_flags_positive_spike` and the truncation-invariance instances are the regression pins).

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/families.py research/signals/intraday/mr_vwap_strategy.py tests/research/test_mr_vwap_strategy.py
git commit -m "feat(research): mr_vwap 2b strategy — next-bar/maker-limit fills, PIT top-30 gate"
```

---

### Task 3: Train-phase runner — grid, mechanical selection, diagnostics

**Files:**
- Create: `research/signals/intraday/mr_vwap_train.py`
- Test: `tests/research/test_mr_vwap_train.py` (create)

**Interfaces:**
- Produces: CLI `python -m research.signals.intraday.mr_vwap_train [--out DIR]` (default `research/signals/intraday/output/2b/`) writing `combo_log.csv` (all 36 runs), `frozen_params.json` (`{variant: params|null}` — null = NOT VIABLE), `diag_per_symbol.csv`, `diag_monthly.csv`, `diag_summary.json` (episode counts, edge-t, 5m descriptive check). `mr_vwap_train.TRAIN_END = "2025-07-01"`, `GRID_H = [8, 16, 32]`, `GRID_EXIT = ["horizon", "z_recover"]`, `GRID_K = [3, 5, 10]`, `BARS_PER_YEAR = 35040`, `VARIANTS` dict mapping variant name → (fill, buy CostModel, sell CostModel). Task 4 reads `frozen_params.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/research/test_mr_vwap_train.py`:

```python
"""Train-runner smoke test on a synthetic warehouse + unit test of the
mechanical selection rule (eligibility, Sharpe ranking, plateau guard)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research import store
from research.signals.intraday import mr_vwap_train as train

BAR_MS = 900_000
DAY_MS = 86_400_000
N = 4000


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _seed(symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT")):
    rng = np.random.default_rng(9)
    for sym in symbols:
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.004, N))
        vol = rng.uniform(5, 50, N)
        rows = [{
            "open_time": i * BAR_MS, "open": float(closes[i]),
            "high": float(closes[i] * 1.001), "low": float(closes[i] * 0.999),
            "close": float(closes[i]), "volume": float(vol[i]),
            "close_time": i * BAR_MS + BAR_MS - 1,
            "quote_volume": float(closes[i] * vol[i]), "trades": 5,
            "taker_buy_volume": float(vol[i] * 0.5), "taker_buy_quote_volume": 0.0,
        } for i in range(N)]
        store.upsert("klines_15m", sym, rows, "open_time")
        days = N * BAR_MS // DAY_MS + 1
        drows = [{"open_time": d * DAY_MS, "close": 100.0,
                  "quote_volume": 1e6} for d in range(days)]
        store.upsert("klines_1d", sym, drows, "open_time")
        frows = [{"funding_time": t, "funding_rate": 0.0001, "mark_price": 100.0}
                 for t in range(0, N * BAR_MS, 32 * BAR_MS)]
        store.upsert("funding", sym, frows, "funding_time")


def test_select_frozen_params_mechanical_rule():
    log = pd.DataFrame([
        {"fill": "next_bar", "horizon_bars": 8, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.10, "sharpe": 2.0},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.20, "sharpe": 3.0},
        {"fill": "next_bar", "horizon_bars": 32, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.05, "sharpe": 1.0},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 5,
         "n_trades": 200, "total_return": 0.15, "sharpe": 2.5},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 10,
         "n_trades": 50, "total_return": 0.30, "sharpe": 9.9},  # ineligible: trades
    ])
    chosen, cliff = train.select_frozen(log[log.fill == "next_bar"])
    assert chosen["horizon_bars"] == 16 and chosen["max_k"] == 3
    assert not cliff

    none_eligible = log.assign(total_return=-1.0)
    assert train.select_frozen(none_eligible) == (None, False)


def test_train_cli_end_to_end(warehouse, tmp_path, monkeypatch):
    _seed()
    out = tmp_path / "2b"
    monkeypatch.setattr(train.sdata, "ELIGIBILITY_DAYS", 0)
    monkeypatch.setattr(train, "GRID_H", [4])
    monkeypatch.setattr(train, "GRID_K", [2])
    monkeypatch.setattr(train, "MIN_TRAIN_TRADES", 1)
    monkeypatch.setattr("sys.argv", ["train", "--out", str(out)])

    train.main()

    log = pd.read_csv(out / "combo_log.csv")
    assert len(log) == 4                      # 1 H x 2 exits x 1 K x 2 variants
    frozen = json.loads((out / "frozen_params.json").read_text())
    assert set(frozen) == {"next_bar", "maker_limit"}
    assert (out / "diag_summary.json").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/research/test_mr_vwap_train.py -v`
Expected: collection error — no module `mr_vwap_train`.

- [ ] **Step 3: Implement `research/signals/intraday/mr_vwap_train.py`**

```python
"""Phase 2b train runner: pre-registered grid, mechanical freeze, diagnostics.

PRE-REGISTERED (2026-07-16): TRAIN_END = 2025-07-01 — nothing on/after is
loaded here. Grid 3H x 2exit x 3K per fill variant; selection = eligible
(n_trades >= 100, total_return > 0) -> max annualized Sharpe with the
basis_mr plateau guard on H/K neighbors (same exit). Diagnostics are
descriptive and must not alter frozen params. OOS stays sealed.

Run:  python -m research.signals.intraday.mr_vwap_train
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.siglib.backtest import run_backtest
from research.siglib.costs import INTRADAY, MAKER_ENTRY
from research.signals.intraday import mr_vwap_strategy as strat
from research.signals.intraday.families import mr_vwap_z

TRAIN_END = "2025-07-01"
DEFAULT_OUT = Path(__file__).parent / "output" / "2b"
GRID_H = [8, 16, 32]
GRID_EXIT = ["horizon", "z_recover"]
GRID_K = [3, 5, 10]
MIN_TRAIN_TRADES = 100
BARS_PER_YEAR = 4 * 24 * 365
VARIANTS = {
    "next_bar": ("next_bar", INTRADAY, INTRADAY),
    "maker_limit": ("maker_limit", MAKER_ENTRY, INTRADAY),
}


def annualized_sharpe(returns: pd.Series) -> float:
    sd = float(returns.std())
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(returns.mean()) / sd * np.sqrt(BARS_PER_YEAR)


def load_panels(end):
    df15 = sdata.load_klines("all", interval="15m", end=end)
    if df15.empty:
        raise SystemExit("no klines_15m data before end")
    df1d = sdata.load_klines("all", interval="1d", end=end)
    funding = sdata.load_funding("all", end=end)
    data = {"klines_15m": df15}
    close = sdata.to_panel(df15, "close")
    low = sdata.to_panel(df15, "low")
    z = mr_vwap_z(data)
    elig = (
        sdata.eligible_mask(df15)
        .reindex(index=close.index, columns=close.columns).fillna(False)
    )
    pit = strat.pit_top30_mask(df1d, close.index, close.columns)
    return z, close, low, elig & pit, funding


def run_combo(panels, params, fill, buy, sell):
    z, close, low, elig, funding = panels
    w = strat.build_weights(z, close, low, elig, params, fill)
    res = run_backtest(close, w, buy, funding_long=funding,
                       eligibility=None, sell_cost_model=sell)
    s = res.summary()
    s["sharpe"] = annualized_sharpe(res.returns)
    s["episodes"] = int(((w > 0) & (w.shift(1).fillna(0.0) == 0)).sum().sum())
    return s, w, res


def select_frozen(log: pd.DataFrame):
    ok = log[(log.n_trades >= MIN_TRAIN_TRADES) & (log.total_return > 0)]
    if ok.empty:
        return None, False
    ok = ok.sort_values("sharpe", ascending=False)

    def neighbors_positive(row) -> bool:
        for col, grid in (("horizon_bars", GRID_H), ("max_k", GRID_K)):
            gi = grid.index(row[col])
            for j in (gi - 1, gi + 1):
                if 0 <= j < len(grid):
                    q = {"horizon_bars": row["horizon_bars"], "max_k": row["max_k"]}
                    q[col] = grid[j]
                    nb = log[(log.horizon_bars == q["horizon_bars"])
                             & (log.max_k == q["max_k"])
                             & (log.exit == row["exit"])]
                    if len(nb) and float(nb.iloc[0].sharpe) <= 0:
                        return False
        return True

    for _, row in ok.iterrows():
        if neighbors_positive(row):
            return row, False
    return ok.iloc[0], True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    panels = load_panels(TRAIN_END)
    rows, best = [], {}
    for vname, (fill, buy, sell) in VARIANTS.items():
        for H, E, K in itertools.product(GRID_H, GRID_EXIT, GRID_K):
            params = {"horizon_bars": H, "exit": E, "max_k": K}
            s, _, _ = run_combo(panels, params, fill, buy, sell)
            rows.append({"fill": vname, **params, **s})
            print(f"{vname:<12} H={H:<3} exit={E:<10} K={K:<3} "
                  f"ret={s['total_return']:+.4f} pf={s['profit_factor']:.3f} "
                  f"sharpe={s['sharpe']:+.2f} trades={s['n_trades']} "
                  f"episodes={s['episodes']}")
    log = pd.DataFrame(rows)
    log.to_csv(out / "combo_log.csv", index=False)

    frozen, diag = {}, {}
    for vname in VARIANTS:
        chosen, cliff = select_frozen(log[log.fill == vname])
        if chosen is None:
            frozen[vname] = None
            print(f"{vname}: NOT VIABLE on train")
            continue
        frozen[vname] = {"horizon_bars": int(chosen.horizon_bars),
                         "exit": str(chosen.exit), "max_k": int(chosen.max_k),
                         "_cliff": bool(cliff)}
        print(f"{vname}: FROZEN {frozen[vname]} sharpe={chosen.sharpe:+.2f}")
    (out / "frozen_params.json").write_text(json.dumps(frozen, indent=2) + "\n")

    # diagnostics on the best viable variant(s), train-only, descriptive
    per_sym_rows, monthly_rows = [], []
    for vname, params in frozen.items():
        if params is None:
            continue
        fill, buy, sell = VARIANTS[vname]
        p = {k: v for k, v in params.items() if not k.startswith("_")}
        s, w, res = run_combo(panels, p, fill, buy, sell)
        z, close, low, elig, funding = panels
        ret = close / close.shift(1) - 1.0
        pnl_sym = (w.shift(1).fillna(0.0) * ret).fillna(0.0)
        for sym in pnl_sym.columns:
            entries = int(((w[sym] > 0) & (w[sym].shift(1).fillna(0.0) == 0)).sum())
            if entries:
                per_sym_rows.append({"variant": vname, "symbol": sym,
                                     "episodes": entries,
                                     "gross_pnl": float(pnl_sym[sym].sum())})
        month = pd.to_datetime(res.returns.index, unit="ms").to_period("M")
        for mth, grp in res.returns.groupby(month):
            monthly_rows.append({"variant": vname, "month": str(mth),
                                 "net_return": float(grp.sum())})
        se = float(res.returns.std()) / np.sqrt(max(len(res.returns), 1))
        diag[vname] = {"edge_t": float(res.returns.mean()) / se if se else float("nan"),
                       "episodes": s["episodes"], **{k: s[k] for k in
                       ("total_return", "profit_factor", "max_drawdown", "n_trades")}}
    pd.DataFrame(per_sym_rows).to_csv(out / "diag_per_symbol.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(out / "diag_monthly.csv", index=False)
    (out / "diag_summary.json").write_text(json.dumps(diag, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
```

(The 5m descriptive robustness check is an ops step in Task 5, not code here — it reruns this CLI's frozen params by hand against 5m panels; see Task 5 Step 2. This keeps the train runner single-purpose.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/research/test_mr_vwap_train.py -v`
Expected: 2 passed (smoke test runtime under ~60s).

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/mr_vwap_train.py tests/research/test_mr_vwap_train.py
git commit -m "feat(research): mr_vwap 2b train runner — grid, mechanical freeze, diagnostics"
```

---

### Task 4: OOS evaluator (committed sealed — running it is the unseal)

**Files:**
- Create: `research/signals/intraday/mr_vwap_oos.py`
- Test: `tests/research/test_mr_vwap_oos.py` (create)

**Interfaces:**
- Produces: CLI `python -m research.signals.intraday.mr_vwap_oos [--out DIR]` (default same `output/2b/`) — reads `frozen_params.json`, loads FULL history (the only module allowed to), runs each viable variant at baseline and stress costs, slices `OOS_WINDOWS`, judges `PASS_BAR` mechanically, writes `oos_results.csv` + `oos_verdicts.json`. `mr_vwap_oos.OOS_START = "2025-07-01"`, `OOS_WINDOWS = [("W1", "2025-07-01", "2025-11-01"), ("W2", "2025-11-01", "2026-03-01"), ("W3", "2026-03-01", None)]`; `judge(full_oos_summary: dict, window_returns: list[float]) -> dict` with keys `pf_ok, trades_ok, windows_ok, dd_ok, passes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_mr_vwap_oos.py`:

```python
"""The OOS judge is mechanical: pin every gate of the pre-registered pass bar."""

from __future__ import annotations

import pytest

from research.signals.intraday import mr_vwap_oos as oos

GOOD = {"profit_factor": 1.30, "n_trades": 250, "max_drawdown": 0.10}


def test_judge_passes_when_all_gates_pass():
    v = oos.judge(GOOD, [0.05, -0.01, 0.04])
    assert v == {"pf_ok": True, "trades_ok": True, "windows_ok": True,
                 "dd_ok": True, "passes": True}


@pytest.mark.parametrize("patch,expect_fail", [
    ({"profit_factor": 1.14}, "pf_ok"),
    ({"n_trades": 99}, "trades_ok"),
    ({"max_drawdown": 0.21}, "dd_ok"),
])
def test_judge_fails_each_gate(patch, expect_fail):
    v = oos.judge({**GOOD, **patch}, [0.05, -0.01, 0.04])
    assert not v[expect_fail] and not v["passes"]


def test_judge_requires_two_of_three_positive_windows():
    assert not oos.judge(GOOD, [0.05, -0.01, -0.04])["windows_ok"]
    assert oos.judge(GOOD, [0.05, 0.01, -0.04])["windows_ok"]


def test_pass_bar_constants():
    assert oos.MIN_PF == 1.15 and oos.MIN_TRADES == 100
    assert oos.MAX_DD == 0.20 and oos.OOS_START == "2025-07-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_mr_vwap_oos.py -v`
Expected: collection error — no module `mr_vwap_oos`.

- [ ] **Step 3: Implement `research/signals/intraday/mr_vwap_oos.py`**

```python
"""Phase 2b OOS evaluator — RUNNING THIS UNSEALS THE OOS YEAR. Run ONCE per
freeze, from Task 5's gated ops step only. No iteration after unseal.

Judges each viable variant against the pre-registered pass bar (spec §3 /
findings §5): net PF >= 1.15 on bar returns, >= 100 OOS trades, positive
total return in >= 2 of 3 windows, max drawdown <= 20% on the full OOS slice.

Run:  python -m research.signals.intraday.mr_vwap_oos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.signals.intraday import mr_vwap_train as train
from research.signals.intraday.mr_vwap_train import VARIANTS, load_panels, run_combo
from research.siglib.costs import INTRADAY, MAKER_ENTRY, MAKER_ENTRY_STRESS, STRESS

DEFAULT_OUT = Path(__file__).parent / "output" / "2b"
OOS_START = "2025-07-01"
OOS_WINDOWS = [("W1", "2025-07-01", "2025-11-01"),
               ("W2", "2025-11-01", "2026-03-01"),
               ("W3", "2026-03-01", None)]
MIN_PF = 1.15
MIN_TRADES = 100
MAX_DD = 0.20
STRESS_COSTS = {"next_bar": (STRESS, STRESS),
                "maker_limit": (MAKER_ENTRY_STRESS, STRESS)}


def judge(full_oos_summary: dict, window_returns: list[float]) -> dict:
    pf_ok = float(full_oos_summary["profit_factor"]) >= MIN_PF
    trades_ok = int(full_oos_summary["n_trades"]) >= MIN_TRADES
    windows_ok = sum(1 for r in window_returns if r > 0) >= 2
    dd_ok = float(full_oos_summary["max_drawdown"]) <= MAX_DD
    return {"pf_ok": pf_ok, "trades_ok": trades_ok, "windows_ok": windows_ok,
            "dd_ok": dd_ok, "passes": pf_ok and trades_ok and windows_ok and dd_ok}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    frozen = json.loads((out / "frozen_params.json").read_text())

    panels = load_panels(end=None)   # FULL history — the unseal
    rows, verdicts = [], {}
    for vname, params in frozen.items():
        if params is None:
            verdicts[vname] = "NOT_VIABLE_ON_TRAIN"
            continue
        p = {k: v for k, v in params.items() if not k.startswith("_")}
        fill = VARIANTS[vname][0]
        for label, (buy, sell) in (
            ("baseline", VARIANTS[vname][1:]),
            ("stress", STRESS_COSTS[vname]),
        ):
            s, w, res = run_combo(panels, p, fill, buy, sell)
            oos_res = res.window(start=OOS_START)
            full = oos_res.summary()
            full["sharpe"] = train.annualized_sharpe(oos_res.returns)
            win_rets = []
            for wname, ws, we in OOS_WINDOWS:
                wr = res.window(start=ws, end=we)
                win_rets.append(wr.total_return)
                rows.append({"variant": vname, "cost": label, "window": wname,
                             **wr.summary()})
            rows.append({"variant": vname, "cost": label, "window": "OOS_FULL",
                         **full})
            if label == "baseline":
                verdicts[vname] = {"judge": judge(full, win_rets),
                                   "params": p, "window_returns": win_rets}
            print(f"{vname}/{label}: PF={full['profit_factor']:.3f} "
                  f"trades={full['n_trades']} dd={full['max_drawdown']:.3f} "
                  f"windows={['%+.4f' % r for r in win_rets]}")
    pd.DataFrame(rows).to_csv(out / "oos_results.csv", index=False)
    (out / "oos_verdicts.json").write_text(json.dumps(verdicts, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_mr_vwap_oos.py -v`
Expected: 6 passed. (The CLI body is exercised for real in Task 5; the judge — the part that decides the verdict — is fully pinned here.)

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest` — all pass except the known reconcile failure.

```bash
git add research/signals/intraday/mr_vwap_oos.py tests/research/test_mr_vwap_oos.py
git commit -m "feat(research): mr_vwap 2b OOS evaluator — sealed until the gated ops run"
```

---

### Task 5: Ops — train run, freeze review, ONE OOS unseal, findings report

**Files:**
- Create: `research/signals/intraday/output/2b/*` (committed evidence)
- Create: `docs/superpowers/specs/2026-07-XX-mr-vwap-2b-findings.md` (dated the run day)

- [ ] **Step 1: Confirm pre-registration is committed, run the train phase**

```bash
git log --oneline -1        # must show Task 4's commit or later
python -m research.signals.intraday.mr_vwap_train 2>&1 | tee /tmp/2b-train.log
```
Expected: 36 combo lines, frozen params (or NOT VIABLE) per variant, diagnostics written. Runtime: tens of minutes (36 stateful weight builds over ~87k bars × 24 symbols).

- [ ] **Step 2: Review diagnostics BEFORE unsealing**

Read `combo_log.csv`, `frozen_params.json`, `diag_*.csv/json` and check, per viable variant: episodes (not bar-events) in the hundreds+, per-symbol PnL not dominated by 1–2 symbols, monthly returns not concentrated in 1–2 months, edge-t sensible. Run the descriptive 5m check (train slice only, non-gating):

```bash
python - <<'EOF'
import json
from research.signals.intraday import mr_vwap_train as train
from research.signals.intraday import mr_vwap_strategy as strat
from research.signals.intraday.families import BARS_24H
import research.signals.intraday.families as fam

fam.BARS_24H = 288            # 24h in 5m bars, descriptive translation
frozen = json.loads(open("research/signals/intraday/output/2b/frozen_params.json").read())
panels = None
import research.siglib.data as sdata
df5 = sdata.load_klines("all", interval="5m", end=train.TRAIN_END)
data = {"klines_15m": df5}    # builder is interval-agnostic; keys reused
z = fam.mr_vwap_z(data)
close = sdata.to_panel(df5, "close"); low = sdata.to_panel(df5, "low")
elig = sdata.eligible_mask(df5).reindex(index=close.index, columns=close.columns).fillna(False)
from research.siglib.backtest import run_backtest
for vname, p in frozen.items():
    if not p: continue
    q = {k: v for k, v in p.items() if not k.startswith("_")}
    q["horizon_bars"] *= 3
    fill, buy, sell = train.VARIANTS[vname]
    w = strat.build_weights(z, close, low, elig, q, fill)
    r = run_backtest(close, w, buy, sell_cost_model=sell)
    print(vname, "5m train slice:", r.summary())
fam.BARS_24H = BARS_24H
EOF
```
Record the output in the findings doc as descriptive only. **STOP CONDITION:** if both variants are NOT VIABLE on train, skip Step 3 — OOS stays sealed; write the findings doc with verdict REJECTED-ON-TRAIN and go to Step 5.

- [ ] **Step 3: Unseal — run the OOS evaluator ONCE**

```bash
python -m research.signals.intraday.mr_vwap_oos 2>&1 | tee /tmp/2b-oos.log
```
This is the single permitted OOS evaluation. No re-runs after parameter or code changes — a re-run for a pure bug fix must be disclosed in the findings doc as a protocol deviation with the bug named.

- [ ] **Step 4: Write the findings doc** `docs/superpowers/specs/2026-07-XX-mr-vwap-2b-findings.md` with required sections: Protocol (commit SHAs proving the evaluator predates the unseal); frozen params + train metrics per variant; OOS verdict table (baseline + stress, per window); the judge's gate-by-gate result; diagnostics summary (episodes, per-symbol/monthly concentration, 5m check); caveats carried forward (survivorship-biased pool, PIT gate partial, maker fill optimism bounds: strict trade-through vs queue reality); decision per the pre-agreed tree — PASS → Phase 3 engine implements the passing variant; FAIL → Phase 3 engine anyway, paper-trade the best candidate, no live money without shadow validation.

- [ ] **Step 5: Commit evidence + report, then final whole-branch review**

```bash
git add research/signals/intraday/output/2b/ docs/superpowers/specs/
git commit -m "research: mr_vwap 2b results — train freeze + OOS verdict"
```
Dispatch the final whole-branch reviewer (most capable model) over the Phase 2b range with the same research-integrity mandate as 2a (lookahead, seal enforcement, judge applied as pre-registered, findings honesty — special attention: the maker fill condition uses bar t+1's low to set w[t], which is an execution model, not signal lookahead; the reviewer should verify the fill price equals the engine's earning base so no free edge is created).

---

## Verification (whole phase)

- `python -m pytest` — green (except the known reconcile failure).
- `git log` proves: strategy + train runner + OOS evaluator all committed before the Task 5 ops run; `output/2b/` evidence committed after.
- `frozen_params.json` selected by the mechanical rule from `combo_log.csv` (re-derivable).
- The findings doc names the verdict per variant and the Phase 3 decision; OOS was evaluated exactly once (or the deviation is disclosed).
