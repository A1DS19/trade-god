# Where we left off
_2026-09-21_

## This session
- **AWS closed the account** hosting the Lightsail box. The intraday paper telemetry DB is gone
  permanently — no backup, no Telegram trail. Confirmed the host is dark (ICMP + :22 dead).
- Reassessed instead of rebuilding. `research/signals/intraday/output/2b/oos_results.csv` shows
  OOS_FULL at **−15.19%, PF 0.986, Sharpe −0.29 over 2,791 trades**. Decision: stop trading, don't
  redeploy, don't reconstruct the lost telemetry. The closure was the occasion, not the cause.
- **Pivoted to the CoinPicks research platform** — and then pivoted the *implementation* a second
  time the same day. Morning: a local Electron + SQLite app (design spec + Plan 1 written and
  approved). Afternoon: replaced with **pnpm workspace / TanStack Start + Hono + Postgres**, after
  checking the stack rather than copying the sibling repo's.
- **Executed the archive** (Plan 1 Task 1). `app/{intraday,api,db,config.py,__init__.py}`,
  `alembic/` (**six** migrations, 001–006), `alembic.ini`, the two root entrypoints `api_main.py`
  and `intraday_main.py` (`main.py` and `swing_main.py` were archived back in July),
  `docker-compose.yml`, `Dockerfile`, `tests/{intraday,api}/` and `research/v2_eval/` → `legacy/`.
  `app/intraday/strategy.py` → `research/signals/intraday/strategy_core.py` (the one module
  `research/` needs), with its test → `tests/research/test_strategy_core.py`;
  `mr_vwap_strategy.py:18` and `families.py:45` repointed. Deleted `swing-logs.txt`, `bot.log`,
  24 tracked `charts_out/` PNGs. **111 passed** after the move (was 182, of which 108 were
  `tests/research`).
  - `research/v2_eval/` was *already* broken: `run.py:53-64` imports `app.swing.backtest_replay`,
    archived 2026-07-16. Nothing tested it, so the suite stayed green over a dead module for two
    months. Worth remembering as a shape, not a one-off.
- **Rewrote the repo's self-description** — Plan 1 Task 2, in its new-stack form rather than the
  Electron text the plan carries. `CLAUDE.md` and `README.md` are now CoinPicks documents; the
  approved spec was revised **in place**; `docker-compose.yml`, `.env.example` and
  `.github/workflows/ci.yml` were written for the new stack; `docs/intraday_operations.md` and
  `docs/testing.md` moved to `legacy/docs/`.
- **The LLM's role changed from the Electron-era drafter to the EvidenceFinder.** It proposes
  `{url, quote, why}` candidates, verified before display; it never proposes a number; every
  `*_draft` / `*_draft_reason` column is deleted. The Claude Code CLI drafter is dropped — see Open
  items, the question about it is *answered*, not abandoned.
- Verified live, today, rather than assumed: npm versions for the whole stack; Node v26.8.1 runs a
  `.ts` file directly with no flag or loader; the DashScope international key returns HTTP 200
  across 172 models; psycopg 3.2.13 imports on system Python 3.14.7; port 5432 is already held by
  an unrelated `medi-pal-db-1` (postgres:17.2), hence **5433**.
- Seeded the `agents/` paper trail: `CONTEXT.md`, `decisions.md`, `roadmap.md`, and this file.

## State
- Branch `main`; last commit is `f273421` (the Electron-era spec + Plan 1). **Everything this
  session produced — the archive moves and the whole doc pass — is in the working tree / index and
  not yet committed.** Commits land on `main` directly here.
- On disk from the new stack, right now: **`docker-compose.yml`** (one `postgres:16-alpine`
  service, bound `127.0.0.1:5433:5432`, fresh volume `coinpicks_data`), **`.env.example`**,
  **`.github/workflows/ci.yml`**. Not on disk yet: `apps/`, `framework/`, `pnpm-workspace.yaml`,
  `package.json`, `research/forward_returns.py`. Every npm version recorded in `CLAUDE.md` and the
  plan is still a decision, not an install.
  - **5433, not 5432**: 5432 is held by an unrelated `medi-pal-db-1` (`postgres:17.2`) on this
    machine. Verified — state it as fact, never as an assumption.
  - `typescript 5.9.3` (latest 7.0.2) and `vitest 4.1.11` (latest 5.0.1) are **deliberate catalog
    pins** against the standing "always latest" rule. Annotate them as such wherever versions get
    listed.
  - ci.yml's TypeScript job is gated on `pnpm-workspace.yaml` existing, so today it skips and
    starts running by itself the moment the workspace lands. The Python job is live and green.
- `CLAUDE.md` and `README.md` are **rewritten**: both describe CoinPicks, neither describes the
  intraday paper engine. `docs/` now contains only `superpowers/{plans,specs}/`.
- The approved spec `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` was
  **revised in place**, not superseded: **§3.2** is the `apps/` tree, **§4** is "Data model
  (PostgreSQL 16)", **§8** is "The EvidenceFinder", and a Revision history at the top records both
  of the day's pivots. Its **"Normative formulas (frozen)"** section has been verified
  byte-identical across the rewrite — **never edit it**.
- `docs/superpowers/plans/2026-09-21-coin-research-foundation.md`: Task 1 **done**; Task 2 **done**
  (the rewrite happened — only the Electron-era replacement *text* pasted inside that task is
  superseded); Tasks 3–4 **discarded** (Electron scaffold, SQLite schema) and must not be executed;
  **Tasks 5–6 are the next work** and are already rewritten against `apps/api/src/scoring/` with
  vitest — execute those two as written.
- `research/` untouched and green: **111 passed**. `tests/` holds `tests/research/` and
  `conftest.py` and nothing else, so `pytest` and `pytest tests/research` are now the same command.
  `pyproject.toml` declares exactly **one** marker, `testnet`; `slow`/`property`/`integration` went
  to `legacy/` with the suites that used them.
- Warehouse is stale since 2026-07-15 (harmless for now). **No refresh cron is installed** —
  `crontab -l` says "no crontab for dev". The weekly line quoted in `CLAUDE.md` is a *recommended*
  entry, not an installed one.

## Next session
1. **Commit** the archive and the doc pass. Don't start new work on top of an uncommitted rewrite.
2. **Vendor the framework markdown** into `framework/`. It exists only under
   `~/Downloads/Altcoin-Trading-System-STANDARD-2026-08-07/Altcoin-Trading-System/Research/framework/`
   (seven files, `00-how-we-think` … `06-one-page-report-template`). It is one copy command and it
   is the provenance the frozen formulas are supposed to be checked against. Do it before writing
   the formulas, not after.
3. **Build order step 2 — the frozen scoring core**, which is Plan 1 Tasks 5 and 6 executed as
   written: a bare `typescript` + `vitest` package at `apps/api/`, no Hono, no Drizzle, no Postgres
   and no React near it. Start with `ranges.ts` and its `SCORING_VERSION` constant, because every
   other file depends on both. Reject out of range, never clamp. Narrative sub-scores may be
   whole numbers. The one genuine framework worked example is the acceptance test: team → 7.25 (the ARB
   narrative → 26.5.
4. **Step 3 — schema, migrations, and the trigger**, and write the trigger in the *same* sitting.
   `drizzle-kit generate --custom`, hand-written `BEFORE UPDATE OR DELETE` on `reports`,
   `report_scores`, `report_team`, `citations`. `schema.ts` will never re-emit it, so it is exactly
   the kind of thing that gets deferred forever. Bring the container up first
   (`docker compose up -d db`) and confirm it lands on 5433 against the `coinpicks_data` volume.
5. When `pnpm-workspace.yaml` lands, name the package scripts `dev`, `build`, `test`, `typecheck`,
   `check`. Biome's script is **`check`** everywhere in this repo — never `lint`.

## Open items
- **`DEFAULT_PROVIDER` is deliberately unpinned.** It is the in-code constant in
  `apps/api/src/evidence/providers.ts`; `COINPICKS_MODEL_PROVIDER` is its environment override, and
  it already sits blank on purpose in `.env.example`. The value gets decided at build-order step 7
  by running one real coin section through `kimi-k3`, `deepseek-v4.1-flash` and `qwen3.8-max` and
  recording the result. Not on price, not on brand.
- **Claude Code CLI subscription auth from a spawned process: ANSWERED — it works.** It was dropped
  anyway, because a bare spawn inherits the operator's global `CLAUDE.md`, skills and MCP config
  (~27k cache-creation tokens on a trivial prompt) and runs whatever model their settings name.
  That is an uncontrolled variable inside an experiment about prediction. Don't re-litigate this as
  if it were a capability question.
- **Framework vendoring is pending**, not done. See Next session #2.
- **Warehouse refresh before the ledger's forward-return join.** The OI and long/short datasets are
  trailing-30-day only; the window from 2026-07-15 onward is already lost and cannot be recovered.
  Nothing in the scoring core, the schema or the commit gate needs it — the join at build-order
  step 6 does. (There is no separate "Phase A.3": `roadmap.md` folds the join, the `research` GRANT
  and `rescore.ts` back into A.1's ledger step, which is what the spec scopes.)
