# Testing Guide

How the trade-god test suite is organized, how to run it, and how to add to it.
Covers the post-2026-07-16 layout (intraday engine + research warehouse); the
retired bot/swing suites live in `legacy/tests/` and are not collected.

## Running

```bash
python -m pytest                   # full suite (fast, fully green — no excepted failures)
python -m pytest tests/intraday    # one area
python -m pytest -k paper_book     # by name
```

Config lives in `pyproject.toml` (`[tool.pytest.ini_options]`): `testpaths = ["tests"]`,
`pythonpath = ["."]` (so `import app...` works with no `sys.path` hacks), and
`--import-mode=importlib`.

## Layout

```
tests/
  conftest.py      env stub (import-time) + the testnet skip-hook
  intraday/        the paper engine: strategy core, paper book, engine cycle, risk, data, DB
  research/        warehouse fetchers/store/checks + the 2a/2b backtest harness
```

- **`tests/intraday/`** — the money paths:
  - `test_strategy_core.py` — z math identical to research, frozen constants pinned,
    import direction enforced (research → app, never the reverse).
  - `test_paper_book.py` — PaperBook money-path goldens **and the keystone test**,
    `test_replay_parity_with_batch_builder`: the live incremental book must match
    `strategy.build_weights` bar-for-bar. Any transition-rule change must keep this green.
  - `test_engine.py` — cycle wiring: halt semantics, per-symbol error strikes, state
    persistence, restart recovery (DB helpers and notifier are recorded fakes).
  - `test_risk.py` — kill-switch trip edges, resume, serialization.
  - `test_data_universe.py` — closed-bar discipline, per-symbol isolation, top-30 rule.
  - `test_db_models.py` — persistence helpers against in-memory SQLite.
- **`tests/research/`** — gated by `pytest.importorskip("pandas"/"pyarrow")` in its own
  conftest, so the suite passes on machines without `requirements-research.txt`
  (e.g. the prod box).

## conftest rules

`tests/conftest.py` sets the credential env vars (incl. a valid-looking
`DATABASE_URL`) **at import time**, because `app.config` reads them on import.
**Do not re-add env or `sys.path` boilerplate to individual test files** — conftest
loads before any test module is collected.

## Markers

Declared in `pyproject.toml`: `property`, `integration`, `testnet`, `slow`.
`testnet` tests auto-skip unless `RUN_TESTNET=1` (network + creds); the others are
descriptive filters (`-m property`).

## Philosophy

Money-paths first. The strategy lives **once** in `app/intraday/strategy.py` — research
imports it — and the replay-parity test is what makes "the backtest and the live engine
agree" a pinned invariant instead of a hope. When adding engine behavior, pin the
observable effect (notifications sent, rows written, state persisted), not internals.
