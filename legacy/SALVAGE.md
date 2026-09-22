# What is worth taking out of `legacy/`, and what is not

_Assessed 2026-09-21, after the archive (`86ad438`)._

97 Python files, **11,334 lines**. Almost all of it is the trading era and dies with it: strategy,
exchange clients, backtest engines, grid searches, the DCA and swing bots, the intraday paper
engine, the Alembic chain. None of that has a use in a fundamental-research tool.

Three things are worth taking — as **patterns**, not as code. CoinPicks is TypeScript; nothing here
gets imported.

## 1. The status page — `legacy/app/api/status_page.py`

159 lines producing a **self-contained HTML page with no external assets and no JavaScript**:
inline CSS, a meta-refresh, and a sparkline drawn as an inline `<svg><polyline>` computed from a
list of floats (`render_sparkline`, lines 20–33).

Relevant to spec §9's ledger view. A page with no build step and no asset pipeline is readable in a
browser in three years, which is the same property the ledger itself is supposed to have. Worth
copying the approach when the ledger view is built; the sparkline is ~12 lines of arithmetic.

## 2. Vendor fetching with a fallback — `legacy/app/bot/universe.py`

CoinGecko primary, CoinPaprika fallback, and — the part that matters — it **logs which source
answered** (lines 54, 59). That is provenance in embryo, and spec §6 formalises it: every adapter
returns `{ value, provenance }` carrying `source`, `url`, `fetched_at` and a
`verified | vendor_claim` label.

Also worth keeping: the 429 handling at lines 29–33 — escalating backoff of `30 * (attempt + 1)`
seconds, three attempts, then raise rather than return a partial list. CoinPicks hits CoinGecko for
±2% depth and will meet the same limiter on the same free tier.

## 3. The `research/` warehouse is NOT here

It never moved. `research/` is alive, green (111 tests), and is what `forward_returns.py` will read
at build-order step 6. Its loaders are in `research/store.py`. Nothing needs rescuing from it.

## What was deliberately left to rot

- `legacy/app/swing/`, `legacy/app/bot/`, `legacy/app/intraday/` — every strategy, indicator,
  exchange client and reconciler. The OOS run said the edge was not there.
- `legacy/app/db/models.py` — superseded by `apps/api/src/db/schema.ts`. Note its habit of storing
  every timestamp as `String(50)`; the new schema uses `timestamptz` precisely because of it.
- `legacy/alembic/` — six migrations, 001–006. Drizzle is the only DDL author now.
- `legacy/research/v2_eval/` — broken since 2026-07-16 and untested, so the suite stayed green over
  it for two months. The shape of that failure is worth more than the code.
