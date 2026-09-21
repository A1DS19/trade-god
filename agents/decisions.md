# Decisions

Hard, costly-to-reverse decisions only. Dated, newest first, never edited in place — a decision
that stops being true gets a *new* entry above it that says so, and the old entry keeps its
original reasoning so the mistake stays legible.

2026-09-21 holds two pivots. Everything below the "earlier the same day" marker was decided in the
morning, against an Electron design that the afternoon replaced.

---

## 2026-09-21 — Forward-return horizons frozen at 30 / 90 / 180 / 365 days

`research/forward_returns.py` will compute exactly four horizons, and that set does not change.

Retrofitting a new horizon onto already-committed reports is fine — the parquet warehouse holds
the full history, so a backfill is just another `INSERT ... ON CONFLICT DO UPDATE`. What is not
fine is *comparing* a cohort measured at 60 days against a cohort measured at 90 because someone
changed their mind halfway through. The ledger's whole claim is that its rows are comparable. Pick
the horizons once, before there is any temptation to pick the ones that look better.

**Reversal cost:** low to add a horizon, total to change one — a changed horizon retro-invalidates
every comparison already drawn.

## 2026-09-21 — TypeScript and Vitest pinned in the workspace catalog, against the standing "always latest" rule

`pnpm-workspace.yaml` pins `typescript` at 5.9.3 and `vitest` at 4.1.11. Latest today are 7.0.2
(the Go-native compiler, a fresh major) and 5.0.1 (days old). This is a deliberate deviation from
this repo's own "always use the latest stable" rule, and it must be stated as a deviation
wherever the versions are listed — an unexplained old pin is indistinguishable from neglect.

The reason is specific, not general caution. `hc<AppType>` (Hono's RPC client) and Drizzle's
`$inferSelect` are two of the heaviest type-level workloads in the TypeScript ecosystem, and the
sibling repo's decisions log records exactly what breaks: unpinned TypeScript across workspaces
produces "Type instantiation is excessively deep and possibly infinite" across the RPC boundary.
A brand-new compiler implementation plus a brand-new test runner, on day one, on top of that, is
three unknowns at once.

Revisit the week after report #1 commits — by then the stack works and a compiler upgrade is a
contained experiment rather than a confound.

**Reversal cost:** low. Bump the catalog, run the suite, keep or revert.

## 2026-09-21 — Drizzle is the only DDL author; immutability is enforced by a database trigger

`apps/api/src/db/schema.ts` declares every column. `drizzle-kit generate` emits plain `.sql` under
`apps/api/drizzle/` plus `meta/_journal.json`, both committed, and the API applies them at boot
from `server.ts` *before* the port is taken. Alembic stops being this repo's migration tool and
goes to `legacy/` with the rest of the trading stack.

Two DDL authors against one database is precisely the silent-drift failure this repo already
learned once. One author, one journal, applied on a path that cannot be skipped.

Three schema choices are load-bearing and are recorded here rather than left to the schema file to
explain:

- `pgEnum`, never `text().$type<>()`, for `reports.status` and `citations.status`. `$type<T>()` is
  a TypeScript fiction; it constrains nothing in the database, and the ledger's integrity cannot
  rest on a type that disappears at runtime.
- A `BEFORE UPDATE OR DELETE` trigger on `reports`, `report_scores`, `report_team` and `citations`
  that raises when the parent report is `committed`. Drizzle's DSL cannot express a trigger, so it
  needs `drizzle-kit generate --custom` and a hand-written `.sql` that `schema.ts` will never
  re-emit. This is the one piece of SQL that makes "a committed report is never edited" true
  against a stray `psql`, a GUI client, or an agent with shell access. **Write it on day 2 or it
  never gets written.**
- `reports.version` integer with compare-and-swap writes (`UPDATE ... WHERE id=$1 AND version=$2`,
  409 on zero rows). Two browser tabs on one draft is silent last-write-wins otherwise — a hole
  Electron's single-instance lock used to cover for free, and the move to a browser removed the
  cover without removing the hazard.

Also: `timestamptz` for every timestamp, `jsonb` for `coins.address_sources` and
`chain_facts.payload`. The archived `app/db/models.py` stored every timestamp as `String(50)`. The
ledger join is a date join. Do not inherit that habit.

**Reversal cost:** high once reports are committed — the trigger is the guarantee, and data
written without it cannot be retroactively trusted.

## 2026-09-21 — The LLM is an EvidenceFinder, not a drafter

This replaces section 8 of the design spec outright. The model proposes candidate
`{url, quote, why}` for a claim; every candidate runs through the deterministic citation verifier
*before* it is displayed. It never proposes a number. Every `*_draft` / `*_draft_reason` column
pair is deleted from `report_scores`. **The human types every score.**

The old design had a real containment guarantee — "the LLM writes only to `*_draft` columns,
enforced by schema" — and deleting those columns deletes the guarantee, so it needs a written
replacement rather than a vibe:

1. The `citations` table has no column for the model's `why` prose. The model's reasoning has
   nowhere to persist, so it cannot quietly become the analyst's reasoning.
2. A test asserts that no LLM-reachable code path writes to `report_scores`.

`citations` gains `origin` (`human` | `model`), `finder_provider`, `finder_model`, and a nullable
`selected_at`. Unselected candidates stay in the table, which makes the question "did the finder
actually help?" answerable later for free.

The provider seam is lifted near-verbatim from `~/projects/profe/apps/api/src/providers.ts`
(275 lines, zero imports) and `model.ts` (313 lines): a table of providers over one
OpenAI-compatible client, strict `json_schema`, answers re-parsed through the caller's own zod
schema, a 90s timeout, and an `origin: "model" | "fixture"` tag so a keyless run can never be
mistaken for a model draft.

One funded DashScope international key serves 172 models across Qwen, Kimi, DeepSeek and GLM —
verified live today, HTTP 200 against `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.
`DEFAULT_PROVIDER` is deliberately **not** pinned yet. The sibling repo's recorded blind bench put
`qwen3.8-flash` last on 5/5 ballots (overall 2.0, against `deepseek-v4-flash` 4.6 and `kimi-k3`
4.4) with both Qwen tiers slowest, which is enough to know that picking on price or on brand is
picking badly. The default gets decided by running one real coin section through `kimi-k3`,
`deepseek-v4.1-flash` and `qwen3.8-max` and recording the result.

**The Claude Code CLI drafter is dropped, and the open item about it is ANSWERED, not mooted:**
subscription auth from a spawned process *was* verified to work. It was dropped anyway. A bare
spawn inherits the operator's global `CLAUDE.md`, skills and MCP config into the drafter's context
(~27k cache-creation tokens on a trivial prompt) and runs whatever model the operator's settings
happen to name. For a ledger whose entire purpose is testing whether a score predicts returns, a
drafter that silently changes when an unrelated config file is edited is an uncontrolled variable
sitting inside the experiment.

**Reversal cost:** moderate. Re-adding draft columns is a migration; re-establishing trust in
scores produced after they existed is not.

## 2026-09-21 — Node, not Bun

Runtime is Node v26.8.1. Verified on this machine that Node executes a `.ts` file directly, with no
flag and no loader — the thing Bun used to be needed for.

The sibling repo `profe` runs Bun, and copying it would have been the path of least thought. It
needs Bun for one concrete reason: one of its workspace packages publishes raw `.ts` with no build
step. This repo has no such package. Adopting a second runtime to solve a problem that does not
exist here would mean two runtimes to keep current, for nothing.

**Reversal cost:** low. No Node-specific API is load-bearing.

## 2026-09-21 — Not a Python backend, even though the repo is mostly Python

The tempting argument was "preserve the existing Python-to-database seam". That seam does not
exist. Grepping `research/` for `sqlalchemy`, `psycopg`, `create_engine` or `DATABASE_URL` returns
nothing: the warehouse reads Binance and writes parquet, and has never touched a database. There
was nothing to preserve, so the argument was about a coupling that was imagined.

What Python keeps is the work it is actually good at and already does: the parquet warehouse and
the forward-return join (`research/forward_returns.py`, not yet written; psycopg 3.2.13, verified importable on this
machine's system Python 3.14.7). It owns no table's shape, and that is enforced by a `GRANT`
rather than by a convention — a `research` role with `SELECT` on
`coins`/`reports`/`report_scores`/`report_team`/`citations` and `INSERT, UPDATE` on
`forward_returns`. Nothing else.

Python also never recomputes a score. Auditing a committed number means reading the stored row;
re-deriving one means running the authoritative TypeScript via `node apps/api/scripts/rescore.ts`.
A second implementation of a frozen formula is a second framework.

**Reversal cost:** high. Everything above depends on where the formulas live.

## 2026-09-21 — TanStack Start + Hono + Postgres, and specifically *not* TanStack Start's server as the backend

pnpm workspace, `packages: ["apps/*"]`. `apps/api`: Hono 4.13.8, `@hono/zod-validator` 0.9.1,
drizzle-orm 0.45.3, drizzle-kit 0.31.11, pg 8.23.0 via `drizzle-orm/node-postgres`, zod 4.6.5,
openai 7.20.0, viem 2.56.8. `apps/web`: `@tanstack/react-start` 1.168.57,
`@tanstack/react-router` 1.170.38, React 19.3.0, Vite 8.3.0, Tailwind + `@tailwindcss/vite` 4.3.3.
Shared: Biome 2.5.14, pnpm 10.33.0. One Postgres 16-alpine container.

The real alternative was collapsing the backend into TanStack Start's own server functions: fewer
moving parts, no RPC boundary, and it genuinely won on time-to-first-report. It lost on release
cadence and on lifespan. TanStack shipped **442 releases in 365 days**; Hono shipped **68**. A UI
framework moving that fast is fine for a UI — the UI is disposable and will be rewritten. The
ledger is not. Scoring, the commit gate and the schema must outlive several UIs, and burying them
inside a framework's server runtime couples the permanent thing to the fastest-moving thing in the
stack.

The frozen formulas live in `apps/api/src/scoring/{ranges,product,narrative,team,accrual}.ts` as
pure functions with no imports from the rest of the app. One copy, enforced by the module resolver:
`apps/api/package.json` declares `exports "." -> "./src/app.ts"`, so `apps/web` *cannot* import
`narrativeTotal()`. They are evaluated at exactly one moment — inside the commit transaction.
Ranges are rejected, never clamped.

Deliberately absent: shadcn, any component library, Better Auth, Redis, S3, BullMQ, git-hook gates,
jscpd, fallow. Those belong to a deployed product with customers. This has one user.

Postgres detail worth writing down because it will bite otherwise: bind `127.0.0.1:5433:5432`, not
5432 — that port is already held on this machine by an unrelated `medi-pal-db-1` (postgres:17.2).
And a fresh named volume `coinpicks_data`; never reuse `trade-god_postgres_data`, which still holds
the dead trading database and an `alembic_version` row at revision 006.

**Reversal cost:** high. This is the shape of everything built after it.

## 2026-09-21 — Loopback only, no hosted service (re-decided, not inherited)

Supersedes "Local only, no hosted service" from earlier today. The outcome is unchanged; the
*reason* is completely different, and inheriting the old sentence would have left a decision
standing on a fact that is no longer true.

The old reason was "running locally is what allows drafting to use the Claude Code subscription
instead of API billing". That reason died with the Claude CLI drafter (see the EvidenceFinder
entry). The surviving reasons, argued fresh:

- **Ledger integrity.** A single writer, at one desk, with no concurrent authorship. There is no
  `user_id` in any of the seven tables and no reason to add one.
- **No egress surface.** The citation verifier fetches arbitrary third-party URLs by design. On a
  loopback-only service that is a local HTTP client; exposed, it is an SSRF endpoint offered to the
  internet for free.
- **No uptime obligation.** Writing a report is a desk activity. Nothing waits on it, nothing pages
  anyone, and there is no host to lose — which the AWS closure just demonstrated is a real category
  of loss.

Daily run: `docker compose up -d db`, then `pnpm dev` (api on 8787, web on 5173 proxying `/api`).

**Reversal cost:** moderate — hosting would require auth, a user model, and a hardened verifier.

---

### — earlier the same day —

## 2026-09-21 — Local only, no hosted service **[SUPERSEDED the same day]**

*Superseded by "Loopback only, no hosted service (re-decided)" above. The conclusion survived; the
stated reason did not.*

The authoring workflow is a desk activity and needs no uptime. Running locally is also what allows
drafting to use the Claude Code subscription instead of API billing. No host also means no host to
lose.

**Reversal cost:** moderate — would require auth, hosting, and a different drafting path.

## 2026-09-21 — Electron, not Tauri; TypeScript, not Python **[SUPERSEDED the same day]**

*Superseded by "TanStack Start + Hono + Postgres" above. The TypeScript half survived; the Electron
half did not.*

`~/projects/klickbrain` planned Tauri (`docs/PROJECT.md:551`) and shipped Electron at v0.8.3 with
full packaging. Decision validated by execution, so it is reused. Once the app is Electron, a
Python backend buys nothing — and viem has Multicall3 built in where web3.py needs it bolted on.
Python stays for the offline warehouse only.

**Reversal cost:** high once the UI exists.

*What actually changed within hours:* the packaging and update burden of a desktop binary bought
nothing for a single-user tool on one machine, while a browser UI plus a local API keeps the
durable half (scoring, gate, schema) in a process that has no opinion about windows. The cost of
reversing was low precisely because no UI existed yet — which is the argument for making this class
of decision early and cheaply, not for making it once and defending it.

## 2026-09-21 — Framework formulas are frozen

CoinPicks formulas are implemented exactly as published, never tuned. The purpose of this tool is
to *test* the framework; a modified formula tests something else, and the ledger's verdict would be
about a method nobody uses. Discrepancies get raised with the user, not patched.

Concretely: ranges are rejected, never clamped. Narrative sub-scores may be fractional — the
framework's own worked example scores Communication 4.5/5 — so they are never constrained to
integers. Every `report_scores` row carries the `scoring_version` it was computed under, because
the failure this rule exists to prevent is not "someone changes a weight", it is "someone changes a
weight and nobody can tell which rows came before".

**Reversal cost:** low mechanically, total epistemically — retuning invalidates every prior
committed report as comparable evidence.

## 2026-09-21 — Retire automated trading; pivot to fundamental research tooling

The pre-registered OOS run (`research/signals/intraday/output/2b/oos_results.csv`) measured the
surviving strategy at **−15.19% return, profit factor 0.986, Sharpe −0.29 over 2,791 trades**
(−25.2% under stress). Training-set profit factor was 1.021. The 66-day paper run that looked
positive was about 1.8 months drawn from a roughly 6%-monthly-volatility distribution, checked at
three sequential gates, with its entire gain concentrated in about 10 of 312 trades.

Four systems — DCA, swing v1, swing v2, intraday — now all measure negative.

AWS closed the account holding the Lightsail box, destroying the paper telemetry. That closure is
the *occasion* for the pivot, not its cause: 1.8 months of noise would not have changed the reading
of a 2,791-trade out-of-sample result. We chose not to reconstruct the lost telemetry.

**Reversal cost:** high. All trading code is archived in `legacy/`, and the infrastructure is gone.
