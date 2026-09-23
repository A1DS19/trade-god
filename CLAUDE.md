# Trade-God — Project Context for Claude

> The repo name is historical. What lives in it now is **CoinPicks**, a personal crypto
> research platform. The automated trading system is archived under `legacy/` and is not
> imported, collected by tests, or deployed anywhere.

## What this is

A personal research platform implementing the **CoinPicks** fundamental framework. The owner
researches a token, scores it against **frozen** rubric formulas, attaches citations whose quotes
are **mechanically verified** to appear at their source URL, and commits an immutable
point-in-time report.

Committed reports accumulate into a **ledger**, later joined against forward returns computed from
the existing Python parquet warehouse, to answer whether any of these scores predict anything.
The answer may be no. That is a result worth having.

## Why the trading era ended (2026-09-21)

`research/signals/intraday/output/2b/oos_results.csv` measured the surviving strategy at
**−15.19% return, profit factor 0.986, Sharpe −0.29 over 2,791 trades** (−25.2% under stress).
Training-set PF was 1.021. The 66-day paper run that looked positive was ~1.8 months drawn from a
~6%-monthly-volatility distribution, checked at three sequential gates, with the entire gain
concentrated in ~10 of 312 trades. Separately, AWS closed the account holding the Lightsail box,
destroying the paper telemetry. The closure is the occasion for the pivot, not its cause.

State this once when it is relevant. Do not re-litigate it and do not dramatise it.

---

## THE FROZEN FORMULAS — the rule that outranks every other rule here

The CoinPicks formulas are **normative**. Implement them exactly. Never adjust a weight, a
threshold, or a rounding rule because an alternative looks better calibrated. A modified formula
tests a *different* framework and makes every previously committed report non-comparable — which
makes the ledger's eventual verdict meaningless. Raise discrepancies with the owner; do not patch
them.

- They live in `apps/api/src/scoring/{ranges,product,narrative,team,accrual}.ts` — pure functions,
  no imports from the rest of the app.
- **ONE copy**, enforced by the module resolver: `apps/api/package.json` declares
  `exports "." -> "./src/app.ts"`, so `apps/web` *cannot* import `narrativeTotal()`.
- They are evaluated at **exactly one moment**: inside `POST /reports/:id/commit`, in the same
  transaction that writes `report_scores` and flips `reports.status`. Every downstream consumer
  reads the stored number, never recomputes it.
- Out-of-range values are **REJECTED, never clamped**.
- Rubric sub-scores are **whole numbers**. The lessons state their scales as integer-contiguous
  bands, and the product gate partitions into "16+" / "0–15" — a partition that only covers
  integers. Derived values (the team weighted score, a mean) are not integers.
- `report_scores.scoring_version` is written by the commit route from a constant in
  `scoring/ranges.ts`. The ledger's fatal failure mode is silently comparing rows scored under two
  framework versions.

**Vendored:** the framework's seven source lessons live in `framework/` (`00-how-we-think` … `06-one-page-report-template`), copied in on 2026-09-21 from the
Skool transcription. They are evidence, not code — never edit them. If an implementation
disagrees with a lesson, the implementation is wrong.

---

## Directory structure

```
apps/
├── api/              # Hono + Drizzle (Node). Owns all DDL, scoring, the commit gate.
│   ├── src/scoring/  # the frozen formulas — pure, no app imports
│   ├── src/db/       # schema.ts (every column declared here)
│   ├── src/chain/    # viem layer — Phase A.2, same Node process, no sidecar
│   ├── drizzle/      # generated .sql + meta/_journal.json, both COMMITTED
│   └── scripts/      # rescore.ts — the only re-derivation path
└── web/              # TanStack Start + React 19
framework/            # vendored CoinPicks source lessons — evidence, never edit
research/             # Python parquet warehouse + signal research (dev machine only)
agents/               # paper trail: handoff.md, CONTEXT.md, decisions.md, roadmap.md
docs/superpowers/     # specs/ and plans/ — the only thing left under docs/
tests/research/       # the surviving Python suite
legacy/               # every retired system. Not imported, not collected, not deployed.
docker-compose.yml    # the single postgres:16-alpine service
.env.example
.github/workflows/ci.yml
```

`apps/` and `pnpm-workspace.yaml` are the build ahead. On disk **today**: `legacy/`,
`research/`, `tests/research/`, `agents/`, `docs/superpowers/`, and — already written for the new
stack — `docker-compose.yml`, `.env.example` and `.github/workflows/ci.yml`. There is no `app/`
package any more — do not go looking in it.

---

## Stack

pnpm workspace, `packages: ["apps/*"]`. Runtime **Node v26.8.1, not Bun** — verified that Node
executes a `.ts` file directly with no flag and no loader. (`~/projects/profe` needs Bun only
because one of its workspace packages publishes raw `.ts` with no build step; nothing here does.)

| Where | Packages |
|---|---|
| `apps/api` | hono 4.13.8 · @hono/zod-validator 0.9.1 · drizzle-orm 0.45.3 · drizzle-kit 0.31.11 (dev) · pg 8.23.0 via `drizzle-orm/node-postgres` · zod 4.6.5 · openai 7.20.0 · viem 2.56.8 (Phase A.2) |
| `apps/web` | @tanstack/react-start 1.168.57 · @tanstack/react-router 1.170.38 · react/react-dom 19.3.0 · vite 8.3.0 · tailwindcss + @tailwindcss/vite 4.3.3 |
| shared | @biomejs/biome 2.5.14 · pnpm 10.33.0 |

**Two deliberate deviations from "always latest", pinned in `pnpm-workspace.yaml` catalog:**
`typescript 5.9.3` (latest is 7.0.2, the Go-native compiler, a fresh major) and `vitest 4.1.11`
(latest is 5.0.1, days old). Reason: `hc<AppType>` plus Drizzle's `$inferSelect` are two of the
heaviest type-level workloads in the ecosystem, and the sibling repo's decisions log records that
unpinned TypeScript across workspaces is what produces Hono's *"Type instantiation is excessively
deep"* across an RPC boundary. Revisit the week after report #1 commits. State this as a
deliberate pin wherever versions are listed.

**Node 26 strips types; it does not transform them.** `--experimental-transform-types` no
longer exists on v26.8.1 — `node --help` lists only `--experimental-strip-types`. So no
parameter properties, no `enum`, no `namespace`, no decorators anywhere under `apps/`, and
every relative import carries an explicit `.ts`. `tsconfig.base.json` sets
`erasableSyntaxOnly` and `moduleResolution: "nodenext"` so either slip is a compile error
rather than a green typecheck over code that cannot boot.

**Not in this project:** no shadcn or any component library, no Better Auth, no Redis, no S3, no
BullMQ, no git-hook gate, no jscpd, no fallow. Those belong to a deployed product with customers.

---

## Postgres

**ONE** docker compose service, `postgres:16-alpine`, bound `127.0.0.1:5433:5432` — **not 5432**,
which is already held by an unrelated container (`medi-pal-db-1`, postgres:17.2) on this machine.
A **fresh** named volume `coinpicks_data` — never reuse `trade-god_postgres_data`, which still
holds the dead trading database and an `alembic_version` row at revision 006.

**THREE roles, two DSNs, one process.** `coinpicks_owner` owns every table and is used only
by the boot migrator, which closes its pool before the port is taken; `coinpicks_app` is
`LOGIN NOSUPERUSER`, owns nothing, and holds only `SELECT/INSERT/UPDATE/DELETE` on the seven
tables; `research` reads five tables and writes only the outcome columns of
`forward_returns`. The split exists because a session owning the tables can
`SET session_replication_role = replica` and edit a committed report with every trigger
installed and silent — confirmed live, then confirmed refused for a NOSUPERUSER non-owner.
Roles are created once by `pnpm --filter @coinpicks/api run db:bootstrap`; grants live in
`apps/api/drizzle/0002_role_grants.sql`, because grants die with the table they were granted
on.

```
DATABASE_URL_OWNER=postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks
DATABASE_URL=postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks
```

**Drizzle is the ONLY DDL author.** `apps/api/src/db/schema.ts` declares every column;
`drizzle-kit generate` writes plain `.sql` under `apps/api/drizzle/` plus `meta/_journal.json`,
both committed; the API applies them at boot from `server.ts` **before the port is taken**.
Alembic is no longer this repo's migration tool — two DDL authors against one database is exactly
the silent drift this repo's standing lesson is about.

**Five schema rules that are not negotiable:**

1. **`pgEnum`, never `text().$type<>()`** — for `reports.status` ∈ {draft, committed} and
   `citations.status` ∈ {unverified, verified, near_miss, failed, unverifiable_js, waived}.
   `$type<T>()` is a TypeScript fiction, not a database constraint.

2. **Immutability triggers on `reports`, `report_scores`, `report_team` and `citations`**,
   raising when the parent report's status = `'committed'`. The children fire on
   **INSERT OR UPDATE OR DELETE**, not just UPDATE OR DELETE — under the older wording,
   `INSERT INTO citations ... WHERE report_id = <a committed one>` returned `INSERT 0 1`, and
   adding a citation to a committed report is editing it. Statement-level `BEFORE TRUNCATE`
   triggers cover `forward_returns` as well, because TRUNCATE fires no row triggers at all.
   Every trigger is `ENABLE ALWAYS`: the default is silenced by
   `SET session_replication_role = replica`. A child row's `report_id` is immutable
   unconditionally — re-parenting a committed report's children onto a draft was reproduced
   live and gutted the committed row. Amended 2026-09-21 after the adversarial review; the
   originals are in `agents/decisions.md`.
   Drizzle's DSL cannot express a trigger: `apps/api/drizzle/0001_immutability_triggers.sql`
   is hand-written and `schema.ts` never re-emits it. **Never run `drizzle-kit push`** — it
   diffs `schema.ts` against the live database, knows nothing about the hand-written
   migrations, and would leave the ledger unguarded without saying so.

3. **`report_scores.scoring_version`**, written by the commit route from `SCORING_VERSION` in
   `scoring/ranges.ts` (`'coinpicks-2026-09-21'`; bump only when a frozen formula, range,
   weight or threshold changes). Nullable at column level and NOT NULL **by trigger** at the
   moment of commit — a draft has not been scored under any framework version, and
   `coinpicks_assert_commitable()` refuses a commit without one.
   `apps/api/src/scoring/frozen-surface.test.ts` fails if a frozen number moves without a
   deliberate bump, and pins the CHECK constraints against the same numbers.
```
4. **`reports.version` integer NOT NULL with compare-and-swap writes** —
   `UPDATE ... WHERE id=$1 AND version=$2`, 409 on zero rows. Two browser tabs on one draft would
   otherwise be silent last-write-wins, a hole Electron's single-instance lock used to cover for
   free.
5. **`timestamptz` for every timestamp, `jsonb` for `coins.address_sources` and
   `chain_facts.payload`.** The archived `app/db/models.py` stored every timestamp as
   `String(50)`. The ledger join is a date join. Do not inherit that habit.

Seven tables, no `user_id` in any of them: `coins`, `reports`, `report_scores`, `report_team`,
`citations`, `chain_facts`, `forward_returns`.

---

## The LLM is an EvidenceFinder, not a drafter

The model proposes candidate `{url, quote, why}` for a claim. Every candidate runs through the
deterministic citation verifier **before it is displayed**. It never proposes a number. Every
`*_draft` / `*_draft_reason` column pair is **deleted** from `report_scores`. **The human types
every score.**

The old containment guarantee ("the LLM writes only to `*_draft` columns, enforced by schema") is
gone, and its replacement is explicit: the `citations` table has **no column for the model's "why"
prose**, so the model's reasoning has nowhere to persist; and a test asserts that **no
LLM-reachable code path writes to `report_scores`**.

`citations` gains `origin` ∈ {human, model}, `finder_provider`, `finder_model`, and a nullable
`selected_at` — a row with `selected_at IS NULL` is an unselected candidate, the commit gate counts
only selected ones, and that also makes "did the finder actually help?" answerable later for free.

The provider seam is lifted near-verbatim from `/home/dev/projects/profe/apps/api/src/providers.ts`
(275 lines, zero imports) and `model.ts` (313 lines), and lands here as
`apps/api/src/evidence/{providers.ts,model.ts}` — never `apps/api/src/providers.ts`: a table of
providers over one
OpenAI-compatible client, strict `json_schema`, answers re-parsed through the caller's own zod
schema, 90s timeout, and `origin: "model" | "fixture"` so a keyless run can never be mistaken for a
model draft. One funded DashScope international key serves 172 models across Qwen, Kimi, DeepSeek
and GLM (verified HTTP 200 against `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`).

**`DEFAULT_PROVIDER` — the in-code constant in `evidence/providers.ts`, overridden per run by the
`COINPICKS_MODEL_PROVIDER` environment variable — is deliberately unpinned until the bench runs.**
The sibling repo's recorded blind bench put
qwen3.8-flash last on 5/5 ballots (overall 2.0 vs deepseek-v4-flash 4.6 and kimi-k3 4.4), both Qwen
tiers slowest. The default gets decided by running one real coin section through **kimi-k3,
deepseek-v4.1-flash and qwen3.8-max** and recording the result. Never pin a default on price or on
vibes.

**The Claude Code CLI drafter is dropped.** Its subscription auth from a spawned process *was*
verified to work — that open item is **answered, not mooted** — but a bare spawn inherits the
operator's global `CLAUDE.md`, skills and MCP config into the drafter's context (~27k
cache-creation tokens on a trivial prompt) and runs whatever model the operator's settings name.
For a ledger testing whether a score predicts returns, a drafter that changes when an unrelated
config file is edited is an uncontrolled variable.

---

## Python's role

`research/` is unchanged and stays. **`research/forward_returns.py` does not exist yet** — it is
build-order step 6 (the ledger), and nothing in the tree imports psycopg today (psycopg 3.2.13 *is* importable on
this machine's system Python 3.14.7, which is why the plan is viable). When written it will select
committed reports, compute 30/90/180/365-day returns from the parquet warehouse, and
`INSERT ... ON CONFLICT (report_id, horizon_days) DO UPDATE`. Horizons are **frozen at
30/90/180/365** as of 2026-09-21 — retrofitting horizons onto existing commits is fine, comparing
across changed horizons is not.

Python owns no table's shape, enforced by a **GRANT rather than a convention**: a `research` role
with `SELECT` on `coins`/`reports`/`report_scores`/`report_team`/`citations` and
`INSERT, UPDATE` on `forward_returns`. Nothing else.

**Python never recomputes a score.** Auditing a committed number reads the stored row;
re-derivation runs the authoritative TypeScript via `node apps/api/scripts/rescore.ts`.

---

## Research Warehouse (`research/`, dev machine only)

Point-in-time market data for signal research/backtests — parquet per dataset per symbol under
gitignored `research/warehouse/` (~360MB, 6M+ rows, top-100 USDT perps since listing).
**Never ships anywhere** — there is no deployment target any more; deps in
`requirements-research.txt` (pandas/pyarrow/duckdb) are dev-machine only. This warehouse is what
the ledger's forward returns are computed from, which is why it survived the pivot.

Datasets: `klines_1h/4h/1d`, `funding` (full history), `premium_index_1h` (basis),
`oi_1h` + `long_short_1h` (Binance serves trailing 30d only — refresh ≥ monthly or history is lost),
`universe` (top-N snapshots with onboard dates), `klines_5m/15m` (intraday top-30 subset only —
5m trailing ~18 months, 15m since 2023-01-01; **excluded from the default dataset list** so the
weekly `--top 100` cron never fetches minute data for 100 symbols), `intraday_universe`
(top-30-by-30d-median-quote-volume snapshots).

```bash
python -m research.backfill --top 100          # resumable (per symbol×dataset high-water mark)
python -m research.backfill --symbols DOGEUSDT --datasets funding
python -m research.check                       # gap/staleness report
python -m research.intraday_universe --top 30 --save   # print + snapshot intraday top-30
```

**Rules:** run backfills from the DEV machine only — never a hosted IP (2026-06-05 -1003 ban).
All endpoints are unsigned (no API keys).

**A daily refresh cron is installed** (2026-09-22; the warehouse had silently stopped in mid-July
with no cron): `crontab -l` shows
`30 5 * * * cd /home/dev/projects/trade-god && /usr/bin/python -m research.backfill --top 100 >> /tmp/research-backfill.log 2>&1`.
Each run resolves the day's top-100 USDT perps, saves that universe snapshot, and resumes every
dataset from its high-water mark, so it also keeps stitching the trailing-30d OI / long-short
window. Check `/tmp/research-backfill.log` when data looks stale.

**Known data quirks:** Binance funding timestamps carry ms jitter (gap checker tolerates 1.5×);
ICPUSDT premium index has a genuine 77-day hole (2022-07-12 → 2022-09-27); OI/L-S endpoints are
END-anchored (`startTime`-only returns newest rows — fetchers paginate with explicit windows).

**Signal code:** `research/signals/` keeps the finished studies (carry, xs_momentum, basis_mr,
intraday). The one module the intraday study still needs is
`research/signals/intraday/strategy_core.py` — moved out of the archived `app/intraday/strategy.py`
and kept under test at `tests/research/test_strategy_core.py`.
`research/signals/intraday/{mr_vwap_strategy.py,families.py}` import it from there.

---

## The archive map (`legacy/`)

Moved 2026-09-21, unchanged: dead code kept for provenance. Nothing in the live tree imports it and
pytest does not collect it.

| Was | Now |
|---|---|
| `app/{intraday,api,db,config.py,__init__.py}` | `legacy/app/` |
| `app/intraday/strategy.py` | `research/signals/intraday/strategy_core.py` (kept alive) |
| `tests/intraday/test_strategy_core.py` | `tests/research/test_strategy_core.py` (repointed) |
| `alembic/`, `alembic.ini`, `api_main.py`, `intraday_main.py`, `docker-compose.yml`, `Dockerfile` | `legacy/` |
| `tests/{intraday,api}/` | `legacy/tests/` |
| `research/v2_eval/` | `legacy/research/v2_eval/` |
| DCA bot + swing agent (retired 2026-07-16) | `legacy/app/{bot,swing}/`, `legacy/tests/`, `legacy/docs/` |
| `docs/intraday_operations.md`, `docs/testing.md` | `legacy/docs/` — `docs/` now holds only `superpowers/` |
| `swing-logs.txt`, `bot.log`, 24 tracked `charts_out/` PNGs | deleted |

`research/v2_eval/` was **already broken** when archived: `run.py:53-64` imports
`app.swing.backtest_replay`, archived on 2026-07-16. Nothing tested it, so the suite stayed green
over a dead module for two months — which is why the surviving strategy module kept its test when
it moved. `alembic/versions/` held **six** migrations (001–006); earlier docs said five.

---

## How to run

```bash
docker compose up -d db     # postgres:16-alpine on 127.0.0.1:5433, volume coinpicks_data
pnpm dev                    # api on :8789, web on :5173 proxying /api
pnpm test                   # Vitest
pnpm check                  # Biome
python -m pytest -q         # the Python research suite (111 tests)
```

**Deployment: loopback only, one user, no auth.** This is *re-decided, not inherited* — the old
reason ("so drafting can use the Claude Code subscription") died with the CLI drafter. The
surviving reasons are the ledger's integrity, a single writer, no `user_id` in any of the seven
tables, and no egress surface for a verifier that fetches arbitrary third-party URLs.

---

## Build order

1. archive (**done**) · 2. frozen scoring core · 3. schema + migrations + the trigger · 4. minimal
editor · 5. citation verifier · 6. commit gate + ledger view · 7. bench the three models on one
real coin · 8. wire the EvidenceFinder.

**Phase A.2** = the viem chain layer (pools / safety / issuance / holders / accrual, Multicall3,
the >5%-from-TVL-weighted-median poison-pair drop) in `apps/api/src/chain/`, same Node process, no
sidecar. Honest sizing: **9–10 working days to report #1**, chain layer excluded.

---

## Testing

Money-paths first — here that means the **scoring and gating paths**, not I/O breadth.

- The commit gate's e2e gets **real Postgres or it does not run.** Memory stores have no
  transactions, no CHECK constraints and no triggers, so a green e2e against them proves nothing
  about atomicity or immutability.
- Python: `python -m pytest -q`, config in `pyproject.toml`. `tests/conftest.py` holds the testnet
  skip hook — it skips anything marked `@pytest.mark.testnet` unless `RUN_TESTNET=1`. That hook is
  live infrastructure; don't duplicate it per test file.
- `pyproject.toml` declares **exactly one marker: `testnet`.** `property`, `integration` and `slow`
  left with the suites that used them and now live under `legacy/` — do not cite them as available.
- `tests/` now contains only `tests/research/` and `conftest.py`, so `pytest` and
  `pytest tests/research` are the same command.
- 111 tests pass after the archive (was 182, of which 108 were `tests/research`).

---

## Known issues & fixes

Every entry that used to live here described the DCA bot, the swing agent or the intraday paper
engine — all archived, gotchas moved with them to `legacy/` and `legacy/docs/`. The live gotchas
are stated in place above: port **5433** (5432 is taken by `medi-pal-db-1`), the **fresh**
`coinpicks_data` volume, the Drizzle-only DDL rule, and the Binance data quirks in the warehouse
section.

---

## Session convention

`agents/handoff.md` is read first at session start. When a session ends with "let's continue
tomorrow" (or similar), overwrite it: what was done, current state, next session's plan. Record
hard decisions in `agents/decisions.md` and completed milestones in `agents/roadmap.md` **as they
happen**, not at the end. `agents/CONTEXT.md` holds the canonical vocabulary — use its words.

## Git

- Commits land on `main` directly. Personal repo; the owner has said branch ceremony is
  unnecessary here.
- **Never add AI attribution** — no `Co-Authored-By: Claude …` trailers, no generated-with footers.
  The owner is the sole author.
- Concise commit messages focused on *why*.
- Run the touched suite before calling anything done.
