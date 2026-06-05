# Testing Guide

How the trade-god test suite is organized, how to run it, and how to add to it.
The historical build plan is in [testing_plan.md](testing_plan.md); this is the
living reference.

## Running

```bash
python -m pytest                 # full suite (fast; testnet tests auto-skip)
python -m pytest tests/swing     # one area
python -m pytest -m property     # only Hypothesis property tests
python -m pytest -k safety_net   # by name
```

Config lives in `pyproject.toml` (`[tool.pytest.ini_options]`): `testpaths`,
`pythonpath = ["."]` (so `import app...` works with no `sys.path` hacks), and
`--import-mode=importlib` (lets the same filename — e.g. `test_indicators.py` —
exist under both `tests/bot/` and `tests/swing/`).

Dev deps: `pytest`, `hypothesis` (pinned in `requirements.txt`).

## Layout

```
tests/
  conftest.py      shared fixtures + the testnet skip-hook
  swing/           swing agent: gates, SL/TP sizing & orders, position math, safety net, indicators
  bot/             DCA bot: position-state helpers, indicators
  backtest/        replay profitability + live↔backtest parity
  property/        Hypothesis invariants
  integration/     Binance testnet round-trip (opt-in)
```

Mirror `app/` for component tests; `property/` and `integration/` are
cross-cutting.

## Fixtures (`tests/conftest.py`)

- **Env stub** — credential env vars (incl. `DATABASE_URL`) are set at *import
  time*, because `app.config` / `app.db` read them when imported. Don't re-set
  them in test files.
- **`fake_client`** — a `FakeBinanceClient` that records order calls
  (`algo_calls`, `created_orders`) and returns benign market-data defaults. Use
  it instead of touching the network.
- **`snapshot`** — a factory producing a valid swing snapshot dict; override any
  field by kwarg, e.g. `snapshot(adx=33.0, daily_ema_alignment="bearish")`.

## Markers

| marker | meaning |
|---|---|
| `property` | Hypothesis property-based test |
| `integration` | crosses a component / external boundary |
| `testnet` | hits Binance testnet — **skipped unless `RUN_TESTNET=1`** |
| `slow` | long-running |

## Test categories (and why)

- **Unit / money-path** — the load-bearing math: SL/TP sizing, position sizing,
  realized PnL, the expected-move cost filter, and the client-side safety net
  (`_safety_net_label`). A bug here mis-sizes or fails to stop a real position.
- **Property (Hypothesis)** — invariants that must hold for *all* inputs: size
  stays in `[MIN, MAX]` and rises with confidence; long/short PnL are mirror
  images; the safety net never triggers inside the band.
- **Indicator golden tests** — verified against analytically-known answers (EMA
  of a constant is the constant; RSI of a monotonic series is 0/100; ATR of a
  constant range is that range; ADX picks the trend direction). They check the
  math, not just freeze current output.
- **Live↔backtest parity** (`tests/backtest/test_live_backtest_parity.py`) — the
  most important one. `agent.decide()` (live) and `decide_v2()` (backtest) are
  *separate implementations of the same strategy*. This feeds both identical
  snapshots and fails if they disagree — catching the drift class that once let
  the backtest run `MIN_CONFIDENCE=0.85` while live ran `0.80`.
- **Integration (testnet)** — the only test that exercises the live
  `/fapi/v1/algoOrder` contract (the `-4120` fix). Opt-in:
  ```bash
  RUN_TESTNET=1 BINANCE_TESTNET_KEY=... BINANCE_TESTNET_SECRET=... \
      python -m pytest -m testnet
  ```

## Adding a test

1. Put it under the matching component dir (`tests/swing`, `tests/bot`, …).
2. Use `snapshot` / `fake_client` from conftest — no env or `sys.path` boilerplate.
3. Prefer behavior on a money path over a getter. If the rule should hold for any
   input, add a Hypothesis property in `tests/property/`.
4. Network / credential tests get `@pytest.mark.testnet` and skip by default.

## What's covered — and what isn't (scope C)

Covered: swing decision gates & scoring (via `agent.decide`), SL/TP sizing &
order placement, position/PnL math, the client-side safety net, both indicator
modules, and live↔backtest parity.

**Not yet unit-tested** (needs refactoring — tracked as **scope C**):
- **DCA buy/sell gates are inline in `app/bot/trader.run()`** — only the state
  helpers and indicators are unit-tested; the buy *decision* needs extraction
  into a pure function first.
- **Live and backtest duplicate strategy code** (`agent.py` vs
  `backtest_replay/strategy.py`, and the two `indicators.py`). The parity test
  guards them; unifying into one strategy core is the scope-C goal.
