# Test Suite & Structure Overhaul — Plan

Approved 2026-06-05. **Scope B**: meaningful test coverage + light reorg.
Live-vs-backtest strategy de-duplication is deferred (**scope C**); the
live↔backtest parity test (slice 5) is the bridge to it.

Informed by crypto/algo-trading testing practice: no-lookahead assertions,
property/invariant tests, differential (live↔backtest) testing, faked-client +
testnet integration, reconciliation/recovery.

## Principles
- Tests assert **behavior on money paths** (sizing, SL/TP, entry/exit gates,
  safety net, PnL) — not getters.
- Fast & deterministic by default; network/testnet tests gated behind markers.
- One shared `conftest.py` — no per-file env / `sys.path` boilerplate.
- Each slice lands independently on `main`, tests green before commit.

## Target layout
```
tests/
  conftest.py      shared fixtures: env, FakeBinanceClient, snapshot factory
  bot/             DCA: buy/sell gates, dip, caps, cooldowns
  swing/           agent gates, snapshot SL/TP + sizing, exchange, indicators
  backtest/        profitability + no-lookahead + live↔backtest parity
  property/        Hypothesis invariants
  integration/     testnet order round-trip (marker-gated)
pyproject.toml     pytest config: testpaths, pythonpath, markers, coverage
```

## Slices (in order, one commit each)
- [x] 0. **Infra** — `pyproject.toml` (pytest config + markers) + `conftest.py`
      (env autouse, `FakeBinanceClient`, snapshot factory). Migrate existing 3
      tests, drop boilerplate. Green.
- [x] 1. **Swing money math** — `snapshot.py` SL/TP sizing (ATR×1.5 / ATR×3,
      mins) + confidence→size mapping. Property invariants (SL on loss side, TP
      on profit side, notional bounds, conf∈[0,1]).
- [ ] 2. **Client-side safety net** (`swing/main.py`) — the *only* stop
      protection: triggers at thresholds for long/short, no false trigger in band.
- [ ] 3. **DCA bot** (`app/bot/`, currently ZERO) — buy gates (dip, EMA, RSI,
      macro, volume, caps, cooldown), partial-TP + trailing-stop exits.
- [ ] 4. **Indicators** — golden tests (bot + swing) + **no-lookahead** assertion
      (value at bar *t* uses only data ≤ *t*).
- [ ] 5. **Live↔backtest parity** — same snapshot → same decision from
      `agent.decide()` and the backtest strategy. Bridge to scope C.
- [ ] 6. **Integration** — Binance testnet order round-trip (place algoOrder +
      cancel), gated by `@pytest.mark.testnet` (opt-in, not CI).
- [ ] 7. **Tidy-up** — move `grid_search.py`/`wf_grid_search.py` → `scripts/`;
      `ALGO_IMPROVEMENTS.txt` → `docs/`; delete `migrate.sql` if dead; gitignore
      `cache/` + `outputs/`.

## Out of scope (separate project — scope C)
Unify live (`agent.py`, `indicators.py`) and backtest
(`backtest_replay/strategy.py`, `indicators.py`) into one strategy core. Do
**after** slice 5 provides a parity safety net.
