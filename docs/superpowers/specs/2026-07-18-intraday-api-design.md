# Intraday API & Status Page — Design

**Date:** 2026-07-18
**Status:** Approved by user (approach A + sparkline; all design sections)

## Context

Phase 3 deliberately shipped with no intraday REST endpoints — telemetry lives in Telegram and
raw SQL over the tunnel (`docs/intraday_operations.md`). Two days in, the daily check is
"SSH + psql + mental math". This design gives the `api` service a live purpose: JSON endpoints
over the intraday tables plus one human-glanceable HTML status page, and reorganizes the retired
DCA/swing endpoints under `/legacy/*` so the live system is the headline.

The API stays private: port 8000 remains closed in the Lightsail firewall; access is
`ssh -L 8000:localhost:8000` (or curl on the box). No auth, read-only GETs only.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Consumption | JSON endpoints for curl/scripts + one server-rendered HTML status page at `/` |
| Legacy endpoints | Kept, moved verbatim to `/legacy/dca/*` and `/legacy/swing/*` (old paths gone; nothing consumes them) |
| Approach | A ("mirror + gate") plus the realized-PnL sparkline from C — no engine changes |
| Dependencies | None added: HTML is a Python-rendered string, inline CSS, `<meta http-equiv="refresh" content="60">`; no Jinja2, no JS |

## 1. Structure

```
app/api/
├── main.py              # app assembly only: create app, include routers, GET /health
├── queries.py           # intraday query/aggregation helpers returning plain dicts
├── status_page.py       # GET / — renders HTML from the same queries.py helpers
└── routers/
    ├── __init__.py
    ├── intraday.py      # /intraday/* JSON (thin wrappers over queries.py)
    └── legacy.py        # existing 6 endpoints under /legacy/* (bodies untouched)
```

- `GET /health` keeps its exact path — the compose healthcheck (fixed `c03c0ba`) probes it.
- Legacy moves: `/portfolio` → `/legacy/dca/portfolio`, `/pnl` → `/legacy/dca/pnl`,
  `/trades` → `/legacy/dca/trades`, `/stats` → `/legacy/dca/stats`,
  `/swing/trades` → `/legacy/swing/trades`, `/swing/stats` → `/legacy/swing/stats`.
  Function bodies are relocated, not rewritten. Swagger tags: `intraday`, `legacy-dca`,
  `legacy-swing`.
- JSON routes and the HTML page share `queries.py` — no duplicated SQL/aggregation.
- App title stays "Trade-God API", version bumps to 2.0.0.

## 2. Intraday endpoints

All read from the existing tables (`intraday_trades`, `intraday_limits`, `intraday_state`)
via the ORM models already in `app/db/models.py`.

### `GET /intraday/trades`

Query params: `limit` (default 50, max 500), `symbol`, `status` (`open|closed`), `since`
(ISO datetime, `entry_time >= since` lexicographically — timestamps are ISO varchars, same
convention as the swing endpoints). Newest first. Returns the table columns per row:
`id, symbol, limit_price, entry_price, exit_price, slot_usd, entry_time, exit_time,
hold_bars, pnl_pct, pnl_usd, fill_type, exit_reason, status` — `pnl_pct` reported as a
percentage (×100, rounded 4dp) like `/legacy/swing/trades`.

### `GET /intraday/stats`

Over closed trades, optional `since` (entry_time). Field names mirror `/legacy/swing/stats`:
`trades, win_rate_pct, net_pnl_usd, gross_win_usd, gross_loss_usd, profit_factor,
avg_pnl_pct, median_pnl_pct, best_trade {symbol, pnl_usd, exit_time},
worst_trade {…}, by_symbol {trades, wins, win_rate_pct, net_pnl}, period {first_entry,
last_exit}`. Empty window → `{"trades": 0, "message": …}` like the swing endpoint.

### `GET /intraday/fills`

The go-live telemetry, computed over all of `intraday_limits`:
`total_placed, pending` (outcome NULL), `by_outcome` — count and pct of resolved for each of
`trade_through / touch_only / miss / no_data` — and `admitted` count (fills that got a slot).
Percentages are cumulative since inception, matching the weekly Telegram report semantics.

### `GET /intraday/state`

Deserialized `intraday_state` (each row's JSON `value` is stored whole; this endpoint is a
tidy view, not a schema change):

- `equity`, `slot_usd`, `positions` (dict), `pending` (dict) — from `paper_book`
- `killswitch` — `halted, day, day_anchor, peak, daily_loss_pct, max_dd_pct` plus derived
  `day_pnl_pct` (equity vs day_anchor) and `drawdown_from_peak_pct` (equity vs peak)
- `universe` — `symbols`, `refreshed_ms`, derived `age_days`
- `updated` timestamps per key

Missing rows (fresh DB) → nulls, HTTP 200.

### `GET /intraday/gate`

The 4-week go-live gate tracker. Window constants live in `queries.py` with a comment
pointing at `docs/intraday_operations.md`: `GATE_START = 2026-07-16`, `GATE_END = 2026-08-13`
(28 days). Response:

- `window` — `start, end, days_elapsed, days_remaining` (computed against the current UTC
  date, matching the engine's UTC day convention)
- `criteria`:
  1. `cumulative_pnl` — net closed PnL, `pass` = ≥ 0
  2. `kill_switch` — **current** latch state plus proximity: `day_pnl_pct` vs the −5% halt,
     `drawdown_from_peak_pct` vs the −20% halt. *Known limitation, by design:* past trips are
     not persisted (a resumed latch leaves no DB trace), so "zero trips ever" remains verified
     by Telegram ⛔ history, not this endpoint. The response carries
     `note: "current latch only; trip history lives in Telegram"`.
  3. `trade_through_rate_pct` — from the fills query; the "not materially worse than backtest"
     judgement stays human.
- `on_track` — boolean AND of criterion 1 and current-latch-clear.

## 3. Status page (`GET /`)

One self-contained HTML page (inline CSS, no external assets — the box serves nothing
public), auto-refreshing every 60s. Sections top to bottom:

1. **Headline row** — equity, net realized PnL, today's PnL %, drawdown from peak %, and a
   red `HALTED` badge when the latch is set.
2. **Gate progress** — "day N of 28", end date, and per-criterion tick/cross from
   `/intraday/gate`'s logic.
3. **Sparkline** — inline SVG, realized equity curve: `100 + cumsum(pnl_usd)` over closed
   trades ordered by `exit_time`. Realized-only by design: blind to open-position drift, no
   engine changes to persist per-cycle marks. Fewer than 2 closed trades → placeholder text.
4. **Open book** — open positions and pending limits tables (from `paper_book` state).
5. **Recent trades** — last 10, with symbol, entry/exit, hold, gross %, net USDT.
6. **Fill telemetry** — outcome counts + rates.

All dynamic text goes through `html.escape()` (project-wide Telegram discipline applies to
HTML pages equally). The page renders from the same `queries.py` dicts the JSON routes
return — one code path for the numbers.

## 4. Errors & behavior

- Read-only; no state mutation anywhere in the API.
- Empty/fresh DB: every endpoint returns a valid empty shape (`trades: 0`, empty lists,
  null state), page renders "no data yet" — no 500s on missing rows.
- DB down: FastAPI's default 500 is acceptable (the operator is the only consumer).
- Malformed `since`/params: FastAPI validation 422s as today.
- `intraday_state.value` JSON that fails to parse → that section null + `warning` field,
  page shows "state unreadable" (defensive because the engine rewrites these rows every
  900s mid-read).

## 5. Testing

New `tests/api/` package (currently zero API coverage), using the existing conftest env-stub
pattern and FastAPI `TestClient` over SQLite:

- **stats math** — seeded closed trades with hand-computed win rate / PF / net PnL / median
- **trades filters** — symbol/status/since/limit each pin behavior
- **fills distribution** — mixed outcomes + pending rows → counts and rates
- **state** — seeded `intraday_state` JSON round-trips; missing rows → nulls; corrupt JSON →
  warning not 500
- **gate** — pass/fail edges for cumulative PnL and latch; days arithmetic pinned to fixed
  dates (no wall-clock dependence in tests)
- **status page** — 200, contains seeded equity figure and symbols, HALTED badge appears when
  latched, sparkline SVG present with ≥2 closed trades
- **legacy relocation** — all six respond at `/legacy/*` paths; old paths 404

Runs inside the normal `python -m pytest` suite.

## 6. Deploy

Standard flow: commit → push origin main → push to Lightsail `deploy` → `git merge --ff-only`
→ `docker compose up -d --build api` (code change, image rebuild required — unlike the
healthcheck fix). `intraday` and `db` services untouched. Verify: healthcheck stays green,
`curl localhost:8000/intraday/gate` on the box, page loads through the tunnel.

## Out of scope

- Per-cycle equity persistence (mark-to-market curve) — would touch the live engine; a
  future engine change can add it and the page picks it up for free.
- Auth / opening port 8000 — tunnel-only stays the access model.
- Any write/operational endpoints (resume, halt) — operator actions stay on the box.
- New intraday REST consumers (alerts, dashboards) — nothing else may depend on these
  endpoints during the telemetry window.
