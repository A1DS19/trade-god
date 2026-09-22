# CoinPicks — Plan 3: the minimal report editor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator create a draft report for a coin and fill every field the commit gate will require — through a write path where a typo cannot silently empty a column, a blank box cannot become a measured zero, a fractional score cannot be rounded into range by Postgres, a citation cannot name a person who does not exist, and the list of what is still missing is generated from the same array that generates the database's CHECK constraint.

**Architecture:** `apps/api/src/db/gate-fields.ts` holds `GATE_REQUIREMENTS` — one array that generates both `rs_gate_completeness` (through `schema.ts` and a new `0003` migration) and the editor's blocker list (through `reports/blockers.ts`). `apps/api/src/app.ts` exports `createApp(db, migrations)`, a Hono app of thirteen routes; `server.ts` migrates as the owner, asserts the guards, closes that pool, opens the `coinpicks_app` pool and serves it on `PORT` (default 8789). Every number crosses the wire as the string the operator typed and is parsed once, by zod, through the frozen `assertIntegerRange` / `assertNonNegative` / `assertRange`. `apps/web` is **TanStack Start 1.168.57** on `@tanstack/react-router` with file-based routes and a committed `routeTree.gen.ts`; one Start server route, `routes/api.$.ts`, forwards `/api` to that Hono API on loopback in dev and in production alike, and it is the only outbound request the web tier makes. The browser reaches the API only through `hc<AppType>` and only through `import type` — enforced at build time by the Start plugin's `importProtection`, and by two tests that read the source tree and **both** built bundles. One Save button per section, one CAS bump per save.

**Tech Stack:** pnpm 10.33.0 workspace, `packages: ["apps/*"]`. Runtime **Node v26.8.1** — it executes `.ts` directly, in **strip-only mode** (see Global Constraints).

- `apps/api` adds: hono 4.13.8, @hono/zod-validator 0.9.1, @hono/node-server 2.1.1, zod 4.6.5. Already there: drizzle-orm 0.45.3, pg 8.23.0, drizzle-kit 0.31.11 (dev), @types/pg 8.23.1.
- `apps/web` is new: @tanstack/react-start 1.168.57, @tanstack/react-router 1.170.38, react 19.3.0, react-dom 19.3.0, hono 4.13.8 (for `hc`), @hono/node-server 2.1.1 (the built app's host); dev: vite 8.3.0, @vitejs/plugin-react 6.1.1, tailwindcss 4.3.3, @tailwindcss/vite 4.3.3, @types/react 19.3.0, @types/react-dom 19.3.0, @types/node (catalog), typescript (catalog), vitest (catalog).
- **Catalog pins in `pnpm-workspace.yaml` are a deliberate deviation from "always latest"** and must be stated as such wherever these versions are listed: typescript 5.9.3 (latest is 7.0.2, the Go-native compiler, a fresh major) and vitest 4.1.11 (latest is 5.0.1, days old). Revisit the week after report #1 commits.
- **`@tanstack/react-start` IS used, and `routeTree.gen.ts` is generated and committed.** An earlier draft of this plan dropped Start for plain Vite with code-based routes; **the owner reversed that on 2026-09-21**. Start is in the approved spec §9 and in `CLAUDE.md`'s stack table, the biome objection is closed by one exclude line (the sibling repo at `../profe` already runs exactly that), and Start's `importProtection` closes defect 5 at build time in a way plain Vite cannot. Task 8 Step 7 records the proposal, the review and the reversal.
- Postgres: the existing compose service, `postgres:16-alpine` on `127.0.0.1:5433`, container `coinpicks-db`. **Verified live for this plan: PostgreSQL 16.13 on x86_64-pc-linux-musl.**
- `drizzle-kit push` is **never** run. Only `generate` plus the boot migrator.

**Spec:** `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` — §9 the UI, §2 the method, §4 the data model, §7 the citation rules. The **"## Normative formulas (frozen)"** section is byte-frozen: it is never quoted altered and never changed.

---

## Where this plan came from

Five researchers produced a reconciled editor design; two adversaries then rebuilt the workspace and attacked it, several findings against this machine's live Node 26 and PostgreSQL 16.13. **Everything below is the corrected version.** Where a finding changed the design, the step says what the naive version did and why it was wrong — so the executor does not helpfully "fix" it back.

| # | What was confirmed live | Closed by |
|---|---|---|
| 1 | A typo in a numeric box silently CLEARED the field and read as a successful save: `JSON.stringify({productEase: Number('seven')})` is `{"productEase":null}`, and `null` is this API's "clear". Same for `'1,000'`, `'7%'`, `'1e999'` | Task 2 — every number crosses the wire as the typed string; Task 3's `routes.test.ts` asserts a refused save leaves the stored value alone |
| 2 | Postgres rounds a fraction into an integer column and the CHECK passes the rounded value: `INSERT (ease integer) VALUES (7.5),(8.5),(0.4)` stores `8,9,0` and `BETWEEN 0 AND 10` succeeds | Task 2 — `subScore()` runs the frozen `assertIntegerRange` before the UPDATE |
| 3 | A blank figure box saved with provenance became a MEASURED ZERO: `Number('') === 0`, and `rs_depth_provenance_complete` (a presence biconditional) plus `rs_depth_2pct_nonneg` (`>= 0`) both accept it | Task 2 — `measured()` takes the figure as a string that must match a digit regex; a blank is a named 422 |
| 4 | `savePatch(patch: Record<string, unknown>)` disabled every wire-level check: `hc` type-checks object literals but an index signature satisfies every optional target property, and zod's default object mode then strips the unknown key silently | Tasks 2 and 3 — six section routes, each with its own `z.strictObject`; no `Record<string, unknown>` anywhere |
| 5 | A one-word import slip shipped the ORM to the browser with a green build. Re-measured on a Start build of Task 4's own tree: `import type { AppType }` gives a **583,379-byte** client bundle with no ORM in it; `import { type AppType, createApp }` plus one value use gives **727,230 bytes** with `drizzle:` ×15 and this project's own `report_scores` / `rs_gate` strings in it, `vite build` exit 0, no warning. Put the same value import inside a `createServerFn` body instead and the **client bundle is clean** while `dist/server` carries the ORM | Task 4 — three signals, in this order: `importProtection` (both a `client` and a `server` specifier list) fails the build; `boundary.test.ts` reads every file under `apps/web/src`; `bundle.test.ts` reads `dist/client` **and** `dist/server` |
| 6 | Inputs seeded local state with `useState(value)` and never re-synced, so after a 409 the editor re-applied pre-conflict values over the winner | Task 5 — each section is keyed on a per-section seed token; a 409 bumps every token, re-reads, and says so |
| 7 | `snake('liquidityDepth2pctUsd')` yields `liquidity_depth2pct_usd`; the column is `liquidity_depth_2pct_usd`. The UI used the same wrong string to add and to filter, so it looked right | Task 2 — `CITABLE_FIELDS` reads `reportScores.<key>.name` off the drizzle column; `draft-columns.test.ts` asserts the digit case |
| 8 | A citation could be attached to a team member that was never saved: `TeamEditor` minted a browser-side uuid and `citations.field` is text with no FK | Tasks 3 and 6 — `addCitation` checks `team:<uuid>` against `report_team` inside the transaction; the editor offers evidence only for server rows |
| 9 | `rs_gate_completeness` is INERT on a draft — it is `CASE WHEN product_passed THEN ... ELSE true END` and `product_passed` is commit-written. Confirmed: `SELECT CASE WHEN NULL::boolean THEN false ELSE true END` returns `t` | Task 1 — one array generates both the CHECK and the blocker list, and a test asserts the committed .sql still matches |
| 10 | The naive `rs_gate_completeness` did not require the three product sub-scores. Confirmed on 16.13: `CASE WHEN true THEN (15 = NULL::int + 5 + 5) ELSE true END` is NULL and a CHECK accepts NULL, so `rs_product_total_is_sum` never forced them | Task 1 — `PRODUCT_EASE` / `PRODUCT_HAIR_FIRE` / `PRODUCT_EXCLUSIVITY` are conjuncts of the generated constraint |
| 11 | The design's tsconfig for `apps/web` did not compile: overriding only `moduleResolution` gives `TS5095` and `TS5109`, because the base sets `module: nodenext` | Task 4 — five keys, named, and compiled |
| 12 | `pnpm check` failed on the file the design ordered committed (`routeTree.gen.ts`), and `pnpm format` was said to then fight the generator | Task 4 Step 3 — one line in `biome.json`, because the file is generated. Re-measured: exit 1 without it (`organizeImports` at `routeTree.gen.ts:11`), exit 0 with it over one file fewer, and the file is byte-identical across `biome check --write` and the next `vite build`, so there is no fight |
| 13 | `assertJournalFullyApplied` compares `count(*)` only, and `integrity.test.ts` "restored" the row it deleted by INSERTing an invented hash at `max(created_at) + 1` — so the guard reported green over a database with a migration genuinely missing, and drizzle would re-apply that file at the next boot. Confirmed against drizzle 0.45.3's `pg-core/dialect.cjs` and the live `__drizzle_migrations` rows | Task 1 Step 9 — the guard compares the applied SET against the journal's `when` values, the restore puts back exactly what it removed, and a new case fabricates the count-matching state and asserts the refusal |
| 14 | A citation write re-seeded the product gate, so attaching evidence anywhere on the page discarded unsaved product-gate text — finding 6 turned inside out | Tasks 5 and 7 — `runSave` takes `SectionKey \| null` and the citation callbacks pass `null`; Task 7 Step 15 is the probe |
| 15 | The red per-section refusal cannot render on a 409: re-seeding changes the section's `key`, so `useSection`'s `setError` lands on an instance being replaced | Tasks 5 and 7 — the amber banner carries the refusal's code and message verbatim, and Task 5 Step 10 says so instead of expecting a message that cannot appear |

## What was actually run to check this plan

The workspace below was rebuilt in a scratch monorepo from the repo's real `apps/api`, `tsconfig.base.json` and `biome.json`, with the pinned versions installed from the registry, and every file in this plan was compiled, linted, tested and run there. Commands and their output:

```
pnpm install                             -> 3 workspace projects, no peer warnings
apps/api  tsc --noEmit                   -> clean, 1.6s
apps/web  tsc --noEmit                   -> clean, 2.1s
apps/web  tsc --noEmit --listFiles       -> 15 web files, 15 apps/api files, 83 @types/node files
apps/api  vitest run                     -> Test Files 14 passed, Tests 119 passed
drizzle-kit generate --name gate_completeness_generated
                                         -> drizzle/0003_gate_completeness_generated.sql
psql < 0000,0001,0002,0003               -> applied clean to a fresh database on PG 16.13
node src/server.ts                       -> coinpicks api on http://127.0.0.1:8789
curl 127.0.0.1:8789/health               -> {"ok":true,"migrations":4,"scoringVersion":"coinpicks-2026-09-21"}
vite dev + curl localhost:5173/api/health-> the same JSON
node (hc against the live server)        -> PATCH productEase:'7'     -> 200
                                            PATCH productEase:'seven' -> 422
                                              {"code":"INVALID","message":"productEase: ease must
                                               be a whole number written in digits"}
                                            GET  -> productEase still 7; 33 blockers,
                                                    25 blocking, 6 unknown, 2 clear -- the two
                                                    clear are PRODUCT_EASE and the vacuously
                                                    true DISCOVERY_MARKET_CAP
```

The negative type probes that prove the typing is real, not `any` (each one MUST error, and did):

```
productEase: 7                       -> TS2322: Type 'number' is not assignable to type 'string'.
{ narrativeCommunicatonRationale }   -> TS2561: '...' does not exist in type '{ version:
                                        number; narrativeMaturity: string | null; ... }'. Did
                                        you mean 'narrativeCommunicationRationale'?
scores.productEase = undefined       -> TS2322: Type 'undefined' is not assignable to 'number | null'
liquidityDepthMeasuredAt = new Date()-> TS2322: Type 'Date' is not assignable to type 'string'
```

The last one is load-bearing and worth stating: **Hono's `InferResponseType` applies `JSONParsed`, so a drizzle `timestamptz` column arrives in the browser typed as `string`, not `Date`.** The editor reads them as strings everywhere.

**Revision of 2026-09-21, after three audits.** Every change below was applied to that same workspace and re-run there, against the live PostgreSQL 16.13 in `coinpicks-db` and Node v26.8.1, before being written down:

```
apps/api  tsc --noEmit                   -> clean
apps/api  vitest run                     -> Test Files 14 passed, Tests 119 passed
apps/api  vitest run src/db/integrity.test.ts
                                         -> Tests 5 passed, and the migration table is left
                                            holding exactly the journal's four `when` values
                                            with no fabricated row
apps/web  tsc --noEmit                   -> clean
```

**The `apps/web` build and lint numbers from those two runs are not reproduced here.** They
measured the SPA shape that the owner has since reversed — a single bundle in `dist/assets`,
one test file, and a `biome check` over a tree with no generated route tree in it. What replaced
them is the block below, which is what Task 4 is written against.

Four facts the audits disputed were re-measured rather than taken on trust, and two of the four went against the auditor:

- The Task 4 file count really is the floor the scan asserts and not one more, so `toBeGreaterThan` really does fail there. Counted with the scanner's own `readdirSync`/`statSync` walk over the Task-4 file set. (It was 5 under the SPA shape; under Start it is **6** — `router.tsx`, `lib/client.ts` and the four files under `src/routes/`, with `routeTree.gen.ts` excluded by name.)
- `evaluateBlockers` on an all-NULL draft gives **33 / 1 clear / 26 blocking / 6 unknown** with `DISCOVERY_MARKET_CAP` the only clear row, and after one `productEase` it is **2 clear / 25 blocking / 6 unknown**. The trace above said 5 clear; it now says what the function prints.
- `agents/CONTEXT.md`'s sub-score sentence is at lines **60–62**, not 59–61. One auditor said otherwise; `grep -n` says 60, 61, 62. Chore 1 is unchanged.
- `.superRefine()` is **not** `@deprecated` in the pinned zod 4.6.5 — checked in the installed `zod/v4/classic/schemas.d.cts`, where it sits undecorated beside `refine`. `z.string().uuid()` is, which is why this plan already uses `z.uuid()`. Task 2 Step 1 now records the check.

**Reversal of 2026-09-21: `@tanstack/react-start` kept.** The owner reversed the drop. A working
Start setup was then built under this repo's exact constraints — the real `tsconfig.base.json`,
the real `biome.json`, Node v26.8.1, the pinned catalog — and every claim Task 4 makes was run in
it. Byte counts are `dist` on disk; the two guards count characters, which is 70 fewer.

```
pnpm install                             -> clean, no peer warnings
apps/web  tsc --noEmit                   -> clean, 2.0s, with the generated route tree in-program
apps/web  vitest run                     -> Test Files 2 passed, Tests 13 passed
apps/web  vite build                     -> client 296ms, ssr 205ms
                                            dist/client  5 js files, 583,379 bytes + 7,427 css
                                            dist/server  254,704 bytes
biome check, biome.json as it is today   -> EXIT 1, over one file more than below:
                                            organizeImports as an ERROR at routeTree.gen.ts:11,
                                            plus 3 noExplicitAny (20, 25, 30) and 1
                                            noUnusedImports (98) as warnings
biome check, one exclude line added      -> exit 0, No fixes applied, one file fewer
                                            (51 vs 52 in the scratch tree; the absolute number
                                             depends on how many files apps/api has by then --
                                             the repo is at 35 today. The delta is the fact.)
routeTree.gen.ts round trip              -> sha256 790aa396aff84af7... identical before
                                            `biome check --write`, after it, and after the next
                                            `vite build`. There is no fight to lose.
curl 127.0.0.1:8789/health               -> {"ok":true,...}
curl localhost:5173/api/health           -> the same JSON, through routes/api.$.ts. No proxy:
                                            with a Vite proxy pointed at a dead port the same
                                            URL returned 502 rather than falling through, so
                                            the proxy would make the shipped hop dead code.
pnpm start + curl 127.0.0.1:3000/        -> 200, server-rendered, and /api/health the same JSON
vite dev with 5173 already held          -> `Error: Port 5173 is already in use`, exit 1.
                                            Without strictPort it moves to 5174 in silence and
                                            the first curl reads the SIBLING REPO's HTML --
                                            5173 is held by it on this machine right now.
the leak probe, importProtection ON      -> vite build EXITS NON-ZERO, naming the line and
                                            printing the four-step import trace that reached it
the leak probe, importProtection OFF     -> vite build exit 0 and SILENT; client 583,379 ->
                                            727,230 bytes, carrying drizzle: x15, PgTable x1,
                                            PgColumn x2, report_scores x1, rs_gate x1 -- while
                                            drizzle-orm, pg-protocol and node:crypto are all 0.
                                            boundary + bundle: 4 failed, 9 passed
the same value import, confined to a     -> client 587,978 bytes with ZERO needles: the client
createServerFn body                         scan PASSES and so does the byte ceiling. dist/server
                                            carries drizzle: x15, PgTable x6, PgColumn x88,
                                            report_scores x2, rs_gate x1. Only the source scan and
                                            the SERVER scan catch it -> 2 failed, 11 passed
the dropped SPA's bundle command, run    -> "grep: dist/assets/index-*.js: No such file or
verbatim against a Start build              directory", and the pipeline EXITS 0. A guard
                                            reporting success having read zero bytes.
```

One claim from that proof did **not** reproduce and is not in this plan: that `@import 'tailwindcss'`
is a biome *parse* error needing `"css": { "parser": { "tailwindDirectives": true } }`. Measured
against this repo's config, `@import "tailwindcss";` with double quotes is clean; the single-quoted
form is a *formatter* error, because `javascript.formatter.quoteStyle` is JavaScript-only. Task 4
Step 4 writes double quotes and `biome.json` gains one line, not two.

---

## Global Constraints

- **Framework formulas are frozen.** Every weight, range and threshold comes from the spec's "Normative formulas (frozen)" section and is reproduced exactly. Never adjust one because it looks better calibrated — raise it with the user instead.
- **The frozen formulas are evaluated in exactly one place: the commit transaction.** Build-order step 4 does not evaluate any of them, and **nothing in this plan adds numbers together.** `productGate`, `narrativeTotal`, `teamWeightedScore`, `annualHolderFlow` and `discoveryPremium` are never called by the editor or by its routes. What the editor *does* use from `scoring/` is the three validators — `assertIntegerRange`, `assertRange`, `assertNonNegative` — which reject out-of-range input rather than computing anything. That distinction is the whole reason there is no `/preview` route in this plan.
- **Ranges are rejected, never clamped.** An out-of-range score is a named 422 carrying the frozen message; it is not coerced.
- Rubric sub-scores are **whole numbers** (ruled 2026-09-21). Derived values such as the team weighted score are not.
- **Drizzle alone authors DDL.** `apps/api/src/db/schema.ts` declares every column; `apps/api/drizzle/*.sql` and `meta/_journal.json` are both committed; the API applies them at boot before the port is taken. **Never `drizzle-kit push`.** Never edit an applied migration — Task 1 adds `0003`, it does not touch `0000`.
- **Node 26 strips types; it does not transform them.** Verified on v26.8.1: `--experimental-transform-types` no longer exists. So no parameter properties, no `enum`, no `namespace`, no decorators, no `import =` anywhere under `apps/`. `erasableSyntaxOnly: true` makes a slip a compile error (`TS1294`). **Every relative import under `apps/api` carries an explicit `.ts`**, and every relative import under `apps/web` carries an explicit `.ts` or `.tsx` — one repo-wide rule beats two, and `allowImportingTsExtensions` is inherited by both.
- **Biome 2.5.14: single quotes, no semicolons, 100 columns.** `pnpm check` must pass on every file this plan commits. The one exception is `apps/web/src/routeTree.gen.ts`, which is **generated** by the Start plugin on every dev start and every build: Task 4 Step 3 adds `"!**/routeTree.gen.ts"` to `biome.json`'s `files.includes`, exactly as the sibling repo at `../profe` does, and the file is still committed. Nothing else in this repo is exempt, and nothing hand-written is ever added to that exclusion. After `drizzle-kit generate`, **two** files come back Biome-unformatted — the new `meta/<n>_snapshot.json` and `meta/_journal.json`, which the generator rewrites without a trailing newline. `pnpm check --write` fixes both, exactly as it already did for `0000`–`0002`; a bare `pnpm check` first reports two errors, not one.
- **The API listens on `PORT`, default 8789.** Already settled at HEAD (`ebb74bc`): the 8787 collision was real and verified on 2026-09-21 — the server died with `EADDRINUSE` while `my-teacher-api-1` answered `/health` on the same port — but that container is not always up, so the comment no longer claims 8787 is permanently taken. The default stays 8789 because a port another project uses at all is a bad default for a check whose job is to prove something ran. **Nothing further to strike; do not re-litigate it.**
- **The request pool is `coinpicks_app`: NOSUPERUSER, owns nothing, DML on seven tables only.** `server.ts` keeps decision A's order: owner pool, migrate, assert the guards, close, then the app pool, then the port.
- **Every DB test scopes its queries by ids it created.** `vitest.config.ts` sets `fileParallelism: false` and one `coinpicks_test` database is shared; the triggers refuse TRUNCATE and refuse DELETE on a committed report, so there is no between-tests reset.
- Commits land on `main` directly (personal repo; the owner has said branches are unnecessary here).
- Commits never carry AI attribution — no `Co-Authored-By` trailers, no generated-with footers.
- `research/` and `tests/research/` must stay green: `python -m pytest -q` is **111 passed** and must remain so.
- After each task: `cd apps/api && pnpm test && pnpm typecheck`, `cd apps/web && pnpm test && pnpm typecheck` once it exists, and from the repo root `pnpm check --write && pnpm check`. All clean before the commit step. `apps/web`'s `test` script runs `vite build` before vitest on purpose — `bundle.test.ts` reads `dist/client` and `dist/server`, and scanning a `dist` left over from an earlier source tree is the same failure as scanning a directory that is not there.

---

## Task list

| Task | What it leaves behind |
|---|---|
| 1 | `db/gate-fields.ts` — one required-field array — generating both `rs_gate_completeness` (migration `0003`) and `reports/blockers.ts`, with the test that keeps them together |
| 2 | The wire's validation layer: `reports/{bounds,citable-fields,draft-columns,patch-schemas}.ts`. Numbers arrive as strings and are parsed once, through the frozen validators |
| 3 | The API: `reports/store.ts`, `app.ts` (thirteen routes), `server.ts` on Hono, and `routes.test.ts` — twelve cases against real Postgres |
| 4 | `apps/web`: the tsconfig split that compiles, TanStack Start, the one loopback hop in `routes/api.$.ts`, `hc<AppType>`, the coin list, and the two guards — `boundary.test.ts` on the source, `bundle.test.ts` on both built bundles |
| 5 | The editor shell: load, one Save per section, one CAS bump, the 409 that re-seeds every box, and the first two sections (product gate, risk notes) |
| 6 | The blocker list on screen, generated from `GATE_REQUIREMENTS`, with commit-written rows rendered `unknown` |
| 7 | The four remaining sections — liquidity, narrative, team, accrual — and the final shell |
| 8 | `CLAUDE.md`, the spec's §9, CI, the three chores, and the decisions log |

---
### Task 1: The one required-field list, the generated CHECK, and migration 0003

The owner's ruling of 2026-09-21: the set of fields a passed gate requires is defined **once**, as data in TypeScript, and both the editor's blocker list and the `rs_gate_completeness` CHECK constraint are generated from it.

It exists because the CHECK is **inert on a draft**. It is `CASE WHEN product_passed THEN ... ELSE true END`, and `product_passed` is only written at commit, so on every draft the CHECK evaluates `CASE WHEN NULL::boolean THEN false ELSE true END`, which is `t`. Nothing in the database refuses an incomplete draft. A hand-written blocker list could therefore tell the operator they are ready while the database would refuse them, and a conjunct the list forgot would render as *nothing at all* under the heading "what blocks the commit".

Two things change while the constraint is being regenerated, and both are corrections rather than convenience:

1. **The three product sub-scores become conjuncts.** `rs_product_total_is_sum` reads `product_total = ease + hair_fire + exclusivity`; with any of them NULL that comparison is NULL, and a CHECK accepts NULL. Reproduced on 16.13: a table with that exact constraint took `(NULL, 5, 5, total 16, passed true)`. The new constraint is a strict superset of the old one and no committed row exists to be invalidated.
2. **The accrual `CASE` is expanded into five independent conjuncts.** `CASE WHEN a THEN b AND c ELSE d END` is `(a OR d) AND (NOT a OR b) AND (NOT a OR c)` — the same constraint, with one blocker code per line instead of one code for five different absences.

**Files:**
- Create: `apps/api/src/db/gate-fields.ts`
- Create: `apps/api/src/reports/blockers.ts`
- Modify: `apps/api/src/db/schema.ts` (three edits, no column touched)
- Create (generated, committed): `apps/api/drizzle/0003_gate_completeness_generated.sql`, `apps/api/drizzle/meta/0003_snapshot.json`
- Modify (generated, committed): `apps/api/drizzle/meta/_journal.json`
- Modify: `apps/api/src/db/integrity.ts` (the boot guard compares the applied SET, not a count)
- Modify: `apps/api/src/db/integrity.test.ts` (two hard-coded migration counts, and a restore that
  put back a row it invented)
- Test: `apps/api/src/db/gate-fields.test.ts`

**Interfaces:**
- Consumes: `reportScores`, `ReportScoresRow` from `apps/api/src/db/schema.ts`.
- Produces, from `db/gate-fields.ts`:
  - `type GateSection = 'product' | 'liquidity' | 'narrative' | 'team' | 'accrual' | 'risk' | 'commit'`
  - `interface GateScoresRow` — 36 properties, a structural subset of `ReportScoresRow`; the full declaration is in Step 4
  - `type GateColumnKey = keyof GateScoresRow`
  - `type ColumnName = (key: GateColumnKey) => string`
  - `interface GateRequirement { code: string; section: GateSection; writtenBy: 'operator' | 'commit'; message: string; sql: (name: ColumnName) => string; satisfied: (row: GateScoresRow) => boolean }`
  - `const GATE_REQUIREMENTS: readonly GateRequirement[]` — 33 entries
  - `function gateCompletenessSql(name: ColumnName): string`
- Produces, from `reports/blockers.ts`:
  - `type BlockerState = 'clear' | 'blocking' | 'unknown'`
  - `interface Blocker { code: string; section: GateSection; state: BlockerState; message: string; implementedInStep: number | null }`
  - `function evaluateBlockers(scores: GateScoresRow): Blocker[]`

- [ ] **Step 1: Watch the constraint be inert on a draft, and watch the old one accept a NULL sub-score**

```bash
docker exec -i coinpicks-db psql -U coinpicks -d postgres -v ON_ERROR_STOP=0 <<'SQL'
SELECT CASE WHEN NULL::boolean THEN false ELSE true END AS gate_check_on_a_draft;
CREATE TEMP TABLE old_rule (
  a int, b int, c int, total int, passed boolean,
  CONSTRAINT old_total_is_sum CHECK (CASE WHEN passed IS NULL THEN true ELSE total = a + b + c END)
);
INSERT INTO old_rule VALUES (NULL, 5, 5, 16, true);
SELECT count(*) AS rows_the_old_rule_accepted_with_a_null_subscore FROM old_rule;
CREATE TEMP TABLE rnd (ease int CHECK (ease BETWEEN 0 AND 10));
INSERT INTO rnd VALUES (7.5), (8.5), (0.4);
SELECT array_agg(ease ORDER BY ease) AS stored FROM rnd;
SQL
```

Expected, exactly: `gate_check_on_a_draft` is `t`; `rows_the_old_rule_accepted_with_a_null_subscore` is `1`; `stored` is `{0,8,9}`. Those three results are the reason for this task, for the three new conjuncts, and for `subScore()` in Task 2. Write them down.

- [ ] **Step 2: Write the failing test first**

Create `apps/api/src/db/gate-fields.test.ts`:

```ts
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { getTableColumns } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { evaluateBlockers } from '../reports/blockers.ts'
import { GATE_REQUIREMENTS, type GateScoresRow, gateCompletenessSql } from './gate-fields.ts'
import { type ReportScoresRow, reportScores } from './schema.ts'

/*
 * ONE LIST, TWO CONSUMERS, AND A TEST THAT THEY STILL AGREE.
 *
 * `rs_gate_completeness` is generated from GATE_REQUIREMENTS and so is the blocker list, but the
 * migration is a committed artifact: someone can edit the array and forget `drizzle-kit
 * generate`, and then the editor's list and the database's constraint disagree while both look
 * authored. This is the same technique frozen-surface.test.ts uses on the frozen numbers.
 */

const DRIZZLE = resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle')

const migrations = readdirSync(DRIZZLE)
  .filter((entry) => entry.endsWith('.sql'))
  .sort()
  .map((entry) => readFileSync(resolve(DRIZZLE, entry), 'utf8'))
  .join('\n')

const generated = gateCompletenessSql((key) => reportScores[key].name)

describe('the generated gate constraint', () => {
  it('appears verbatim in the committed migrations', () => {
    expect(
      migrations,
      'GATE_REQUIREMENTS changed and no migration was generated for it. Run\n' +
        '  cd apps/api && pnpm exec drizzle-kit generate --name <what_changed>\n' +
        'and commit the new .sql, its snapshot and the journal entry.',
    ).toContain(generated)
  })

  it('names only real report_scores columns', () => {
    const real = new Set(Object.values(getTableColumns(reportScores)).map((column) => column.name))
    const named = [...generated.matchAll(/"report_scores"\."([a-z0-9_]+)"/g)].map(
      (match) => match[1] as string,
    )
    expect(named.length).toBeGreaterThan(30)
    expect(named.filter((name) => !real.has(name))).toEqual([])
  })

  it('gives every requirement a unique blocker code', () => {
    const codes = GATE_REQUIREMENTS.map((requirement) => requirement.code)
    expect(new Set(codes).size).toBe(codes.length)
  })

  it('requires the three product sub-scores, which the hand-written version did not', () => {
    // `product_total = ease + hair_fire + exclusivity` is NULL when any of them is NULL, and a
    // CHECK accepts NULL. Confirmed on 16.13: the old constraint took (NULL, 5, 5, total 16).
    for (const code of ['PRODUCT_EASE', 'PRODUCT_HAIR_FIRE', 'PRODUCT_EXCLUSIVITY']) {
      expect(GATE_REQUIREMENTS.map((requirement) => requirement.code)).toContain(code)
    }
  })
})

/**
 * The structural pin. `GateScoresRow` is a hand-declared subset of the real row so that
 * `gate-fields.ts` can stay free of a schema import; this is what makes a renamed or retyped
 * column a compile error rather than a blocker that silently reads `undefined !== null`.
 */
const STRUCTURAL_PIN = (row: ReportScoresRow): GateScoresRow => row

describe('the blocker list', () => {
  const empty: GateScoresRow = {
    overviewSentence: null,
    productEase: null,
    productHairFire: null,
    productExclusivity: null,
    productPassed: null,
    productEaseRationale: null,
    productHairFireRationale: null,
    productExclusivityRationale: null,
    liquidityTier: null,
    liquidityJustification: null,
    liquidityDepth2pctUsd: null,
    liquidityTopPoolTvlUsd: null,
    liquidityNoDexPool: false,
    narrativeMaturity: null,
    narrativeSmartMoney: null,
    narrativeHairFire: null,
    narrativeCommunication: null,
    narrativeLineage: null,
    narrativeMutation: null,
    narrativeTotal: null,
    narrativeMaturityRationale: null,
    narrativeSmartMoneyRationale: null,
    narrativeHairFireRationale: null,
    narrativeCommunicationRationale: null,
    narrativeLineageRationale: null,
    narrativeMutationRationale: null,
    teamWeightedScore: null,
    accrualAssessed: false,
    accrualAbsentReason: null,
    accrualRationale: null,
    accrualGrossAnnualFlowUsd: null,
    accrualNetAnnualFlowUsd: null,
    discoveryMarketCapUsd: null,
    discoveryPremiumKind: null,
    riskNotes: null,
    waivedCitationCount: null,
  }

  it('accepts the real row type', () => {
    expect(typeof STRUCTURAL_PIN).toBe('function')
  })

  it('has one row per conjunct', () => {
    expect(evaluateBlockers(empty)).toHaveLength(GATE_REQUIREMENTS.length)
  })

  it('never marks a commit-written column clear', () => {
    const commitRows = evaluateBlockers(empty).filter(
      (blocker) => blocker.state === 'unknown' && blocker.implementedInStep === 6,
    )
    expect(commitRows.map((blocker) => blocker.code)).toEqual([
      'NARRATIVE_TOTAL',
      'TEAM_WEIGHTED_SCORE',
      'ACCRUAL_GROSS_FLOW',
      'ACCRUAL_NET_FLOW',
      'DISCOVERY_PREMIUM_KIND',
      'WAIVED_CITATION_COUNT',
    ])
  })

  it('counts a blank string as missing, not as present', () => {
    const blanks = evaluateBlockers({ ...empty, riskNotes: '   ', overviewSentence: '' })
    const codes = blanks.filter((blocker) => blocker.state === 'blocking').map((b) => b.code)
    expect(codes).toContain('RISK_NOTES')
    expect(codes).toContain('OVERVIEW_SENTENCE')
  })

  it('clears the top-pool row when no DEX pool exists', () => {
    const ticked = evaluateBlockers({ ...empty, liquidityNoDexPool: true })
    const row = ticked.find((blocker) => blocker.code === 'LIQUIDITY_TOP_POOL')
    expect(row?.state).toBe('clear')
  })
})
```
- [ ] **Step 3: Run it and see it fail for the right reason**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/db/gate-fields.test.ts
```
Expected: `Error: Failed to load url ./gate-fields.ts` — the module does not exist yet. Not an assertion failure; a missing file.

- [ ] **Step 4: Write the required-field list**

Create `apps/api/src/db/gate-fields.ts`:

```ts
/*
 * THE ONE required-field list.
 *
 * `rs_gate_completeness` and the editor's blocker list are both generated from this array.
 * Ruled 2026-09-21, because an adversary confirmed the CHECK is INERT on a draft: it is
 * `CASE WHEN product_passed THEN ... ELSE true END` and `product_passed` is only written at
 * commit, so `SELECT CASE WHEN NULL::boolean THEN false ELSE true END` returns `t`. Nothing in
 * the database refuses an incomplete draft. A hand-written blocker list could therefore tell the
 * operator they are ready while the database would refuse them, and a conjunct the list forgot
 * would render as nothing at all under the heading "what blocks the commit".
 *
 * So: one array, two consumers, and `gate-fields.test.ts` asserts the committed .sql still
 * reproduces the string this file generates.
 *
 * Column NAMES are not written here. `gateCompletenessSql` takes a resolver and `schema.ts`
 * passes `(key) => t[key].name`, so the snake_case spelling always comes from the drizzle column
 * itself. The naive version hand-wrote them, and a regex derivation of the same thing produced
 * `liquidity_depth2pct_usd` for `liquidity_depth_2pct_usd` — a key nothing reads.
 */

export type GateSection =
  | 'product'
  | 'liquidity'
  | 'narrative'
  | 'team'
  | 'accrual'
  | 'risk'
  | 'commit'

/**
 * The columns a requirement may read. Structurally a subset of `ReportScoresRow`; the
 * assignability is asserted in `gate-fields.test.ts`, so a renamed or retyped column is a
 * compile error here rather than a silently false blocker.
 */
export interface GateScoresRow {
  overviewSentence: string | null
  productEase: number | null
  productHairFire: number | null
  productExclusivity: number | null
  productPassed: boolean | null
  productEaseRationale: string | null
  productHairFireRationale: string | null
  productExclusivityRationale: string | null
  liquidityTier: 'low' | 'medium' | 'high' | null
  liquidityJustification: string | null
  liquidityDepth2pctUsd: number | null
  liquidityTopPoolTvlUsd: number | null
  liquidityNoDexPool: boolean
  narrativeMaturity: number | null
  narrativeSmartMoney: number | null
  narrativeHairFire: number | null
  narrativeCommunication: number | null
  narrativeLineage: number | null
  narrativeMutation: number | null
  narrativeTotal: number | null
  narrativeMaturityRationale: string | null
  narrativeSmartMoneyRationale: string | null
  narrativeHairFireRationale: string | null
  narrativeCommunicationRationale: string | null
  narrativeLineageRationale: string | null
  narrativeMutationRationale: string | null
  teamWeightedScore: number | null
  accrualAssessed: boolean
  accrualAbsentReason: string | null
  accrualRationale: string | null
  accrualGrossAnnualFlowUsd: number | null
  accrualNetAnnualFlowUsd: number | null
  discoveryMarketCapUsd: number | null
  discoveryPremiumKind: 'MULTIPLE' | 'ISSUANCE_NEGATIVE' | 'PURE_PREMIUM' | null
  riskNotes: string | null
  waivedCitationCount: number | null
}

export type GateColumnKey = keyof GateScoresRow

/** Resolves a camelCase key to the column's real snake_case name. */
export type ColumnName = (key: GateColumnKey) => string

export interface GateRequirement {
  /** The blocker code the editor renders and step 6 will reuse. */
  readonly code: string
  readonly section: GateSection
  /**
   * `operator` — the editor writes it, so its state is known now.
   * `commit` — build-order step 6 writes it, so the editor renders it `unknown`, never a tick.
   */
  readonly writtenBy: 'operator' | 'commit'
  readonly message: string
  /** One conjunct of `rs_gate_completeness`. */
  readonly sql: (name: ColumnName) => string
  readonly satisfied: (row: GateScoresRow) => boolean
}

const q = (name: ColumnName, key: GateColumnKey): string => `"report_scores"."${name(key)}"`

const isProse = (value: unknown): boolean => typeof value === 'string' && value.trim() !== ''

/** Prose that must actually exist — `present()` in schema.ts, `length(btrim(coalesce(...)))`. */
function prose(
  code: string,
  section: GateSection,
  key: GateColumnKey,
  message: string,
): GateRequirement {
  return {
    code,
    section,
    writtenBy: 'operator',
    message,
    sql: (name) => `length(btrim(coalesce(${q(name, key)}, ''))) > 0`,
    satisfied: (row) => isProse(row[key]),
  }
}

/** A value that must be present. */
function value(
  code: string,
  section: GateSection,
  writtenBy: 'operator' | 'commit',
  key: GateColumnKey,
  message: string,
): GateRequirement {
  return {
    code,
    section,
    writtenBy,
    message,
    sql: (name) => `${q(name, key)} IS NOT NULL`,
    satisfied: (row) => row[key] !== null,
  }
}

/**
 * Every conjunct of `rs_gate_completeness`, in DDL order.
 *
 * The accrual CASE is expanded into five independent conjuncts. `CASE WHEN a THEN b AND c ELSE d
 * END` is `(a OR d) AND (NOT a OR b) AND (NOT a OR c)`, which is the same constraint with one
 * blocker code per line instead of one code for five different absences.
 */
export const GATE_REQUIREMENTS: readonly GateRequirement[] = [
  prose('OVERVIEW_SENTENCE', 'product', 'overviewSentence', 'the one-sentence overview is empty'),
  // The three sub-scores are NOT in the hand-written constraint this replaces, and that was a
  // hole: rs_product_total_is_sum reads `product_total = ease + hair_fire + exclusivity`, and
  // with any of them NULL the comparison is NULL, which a CHECK accepts. Verified on 16.13.
  value('PRODUCT_EASE', 'product', 'operator', 'productEase', 'Ease of Use is not scored'),
  value(
    'PRODUCT_HAIR_FIRE',
    'product',
    'operator',
    'productHairFire',
    'Hair-on-Fire (the gate field, 0-10) is not scored',
  ),
  value(
    'PRODUCT_EXCLUSIVITY',
    'product',
    'operator',
    'productExclusivity',
    'Exclusivity Factor is not scored',
  ),
  prose(
    'PRODUCT_EASE_RATIONALE',
    'product',
    'productEaseRationale',
    'Ease of Use has no rationale',
  ),
  prose(
    'PRODUCT_HAIR_FIRE_RATIONALE',
    'product',
    'productHairFireRationale',
    'Hair-on-Fire has no rationale',
  ),
  prose(
    'PRODUCT_EXCLUSIVITY_RATIONALE',
    'product',
    'productExclusivityRationale',
    'Exclusivity Factor has no rationale',
  ),
  value(
    'LIQUIDITY_TIER',
    'liquidity',
    'operator',
    'liquidityTier',
    'no liquidity tier has been assigned',
  ),
  prose(
    'LIQUIDITY_JUSTIFICATION',
    'liquidity',
    'liquidityJustification',
    'the liquidity tier has no justification',
  ),
  value(
    'LIQUIDITY_DEPTH',
    'liquidity',
    'operator',
    'liquidityDepth2pctUsd',
    'the +/-2% depth figure is missing',
  ),
  {
    code: 'LIQUIDITY_TOP_POOL',
    section: 'liquidity',
    writtenBy: 'operator',
    message: 'the largest DEX pool TVL is missing, and "no DEX pool exists" is not ticked',
    sql: (name) =>
      `(${q(name, 'liquidityTopPoolTvlUsd')} IS NOT NULL OR ${q(name, 'liquidityNoDexPool')})`,
    satisfied: (row) => row.liquidityTopPoolTvlUsd !== null || row.liquidityNoDexPool,
  },
  value(
    'NARRATIVE_MATURITY',
    'narrative',
    'operator',
    'narrativeMaturity',
    'Narrative Maturity is not scored',
  ),
  value(
    'NARRATIVE_SMART_MONEY',
    'narrative',
    'operator',
    'narrativeSmartMoney',
    'Smart Money Compatibility is not scored',
  ),
  value(
    'NARRATIVE_HAIR_FIRE',
    'narrative',
    'operator',
    'narrativeHairFire',
    'Hair-on-Fire Innovation (the narrative field, 0-6) is not scored',
  ),
  value(
    'NARRATIVE_COMMUNICATION',
    'narrative',
    'operator',
    'narrativeCommunication',
    'Narrative Communication is not scored',
  ),
  value(
    'NARRATIVE_LINEAGE',
    'narrative',
    'operator',
    'narrativeLineage',
    'Narrative Lineage is not scored',
  ),
  value(
    'NARRATIVE_MUTATION',
    'narrative',
    'operator',
    'narrativeMutation',
    'Narrative Mutation is not scored',
  ),
  value(
    'NARRATIVE_TOTAL',
    'narrative',
    'commit',
    'narrativeTotal',
    'the narrative total is written by the commit route from narrativeTotal()',
  ),
  prose(
    'NARRATIVE_MATURITY_RATIONALE',
    'narrative',
    'narrativeMaturityRationale',
    'Narrative Maturity has no rationale',
  ),
  prose(
    'NARRATIVE_SMART_MONEY_RATIONALE',
    'narrative',
    'narrativeSmartMoneyRationale',
    'Smart Money Compatibility has no rationale',
  ),
  prose(
    'NARRATIVE_HAIR_FIRE_RATIONALE',
    'narrative',
    'narrativeHairFireRationale',
    'Hair-on-Fire Innovation has no rationale',
  ),
  prose(
    'NARRATIVE_COMMUNICATION_RATIONALE',
    'narrative',
    'narrativeCommunicationRationale',
    'Narrative Communication has no rationale',
  ),
  prose(
    'NARRATIVE_LINEAGE_RATIONALE',
    'narrative',
    'narrativeLineageRationale',
    'Narrative Lineage has no rationale',
  ),
  prose(
    'NARRATIVE_MUTATION_RATIONALE',
    'narrative',
    'narrativeMutationRationale',
    'Narrative Mutation has no rationale',
  ),
  value(
    'TEAM_WEIGHTED_SCORE',
    'team',
    'commit',
    'teamWeightedScore',
    'the team weighted score is written by the commit route from teamWeightedScore()',
  ),
  {
    code: 'ACCRUAL_ABSENT_REASON',
    section: 'accrual',
    writtenBy: 'operator',
    message:
      'the four accrual inputs are not all filled, so the report must say why no accrual figure exists',
    sql: (name) =>
      `(${q(name, 'accrualAssessed')} OR length(btrim(coalesce(${q(name, 'accrualAbsentReason')}, ''))) > 0)`,
    satisfied: (row) => row.accrualAssessed || isProse(row.accrualAbsentReason),
  },
  prose(
    'ACCRUAL_RATIONALE',
    'accrual',
    'accrualRationale',
    'the accrual section has no rationale naming the mechanism',
  ),
  {
    code: 'ACCRUAL_GROSS_FLOW',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'gross annual holder flow is written by the commit route from annualHolderFlow()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'accrualGrossAnnualFlowUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.accrualGrossAnnualFlowUsd !== null,
  },
  {
    code: 'ACCRUAL_NET_FLOW',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'net annual holder flow is written by the commit route from annualHolderFlow()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'accrualNetAnnualFlowUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.accrualNetAnnualFlowUsd !== null,
  },
  {
    code: 'DISCOVERY_MARKET_CAP',
    section: 'accrual',
    writtenBy: 'operator',
    message: 'the accrual section is assessed, so it needs a market cap with its provenance',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'discoveryMarketCapUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.discoveryMarketCapUsd !== null,
  },
  {
    code: 'DISCOVERY_PREMIUM_KIND',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'the discovery premium verdict is written by the commit route from discoveryPremium()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'discoveryPremiumKind')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.discoveryPremiumKind !== null,
  },
  prose('RISK_NOTES', 'risk', 'riskNotes', 'the risk notes are empty'),
  value(
    'WAIVED_CITATION_COUNT',
    'commit',
    'commit',
    'waivedCitationCount',
    'the waived-citation count is written by the commit route',
  ),
]

/**
 * `rs_gate_completeness`, generated. One line on purpose: the string is compared byte-for-byte
 * against the committed .sql by gate-fields.test.ts, and a newline is one more thing a generator
 * or a formatter can reflow.
 */
export function gateCompletenessSql(name: ColumnName): string {
  const conjuncts = GATE_REQUIREMENTS.map((requirement) => requirement.sql(name)).join(' AND ')
  return `CASE WHEN ${q(name, 'productPassed')} THEN ${conjuncts} ELSE true END`
}
```
Note what this file does **not** do: it never writes a snake_case column name. `gateCompletenessSql` takes a resolver and `schema.ts` passes `(key) => t[key].name`, so every spelling comes from the drizzle column itself. The naive design derived the same strings with `field.replace(/[A-Z]/g, c => '_' + c.toLowerCase())`, which produces `liquidity_depth2pct_usd` for `liquidity_depth_2pct_usd` — a digit run gets no separator.

- [ ] **Step 5: Wire it into `schema.ts` — three edits, no column touched**

In `apps/api/src/db/schema.ts`:

1. Add the import directly under the `drizzle-orm/pg-core` import block:

```ts
import { gateCompletenessSql } from './gate-fields.ts'
```

2. Delete the now-unused `present` helper (Biome fails the build on it otherwise):

```ts
/** Same, but tolerant of NULL — for use inside the gate-completeness CASE. */
const present = (c: SQLWrapper) => sql`length(btrim(coalesce(${c}, ''))) > 0`
```

3. Replace the whole `check('rs_gate_completeness', sql`CASE WHEN ${t.productPassed} THEN ... ELSE true END`)` entry — the last element of the `reportScores` extras array, 37 lines — with this single line:

```ts
    check('rs_gate_completeness', sql.raw(gateCompletenessSql((key) => t[key].name))),
```

`sql.raw` is what keeps the generated SQL byte-identical to the string the test greps for. `git diff apps/api/src/db/schema.ts` must show exactly those three hunks and nothing else.

- [ ] **Step 6: Generate the migration**

```bash
cd /home/dev/projects/trade-god/apps/api
pnpm exec drizzle-kit generate --name gate_completeness_generated
```
Expected: `[✓] Your SQL migration file ➜ drizzle/0003_gate_completeness_generated.sql`, above a table that reports `report_scores 62 columns`. `--name` is not cosmetic: without it drizzle-kit invents a random three-word tag and the plan's later greps would not match.

Read the file. It is two statements, `DROP CONSTRAINT` then `ADD CONSTRAINT`, and the CHECK body is one line — the exact string `gateCompletenessSql` produced. Confirm the `liquidity_depth_2pct_usd` spelling appears in it:

```bash
grep -c 'liquidity_depth_2pct_usd' drizzle/0003_gate_completeness_generated.sql
```
Expected: `1`.

- [ ] **Step 7: Apply it to the dev database and watch it refuse**

Apply it **through the migrator**, not with psql. This plan's own rule is that a migration reaches a database through `migrate()`, which also writes the `drizzle.__drizzle_migrations` row; a hand-applied file leaves that row missing, and drizzle then re-applies the file at the next boot because its journal `when` is newer than the newest recorded row.

```bash
cd /home/dev/projects/trade-god
docker compose up -d db
pnpm --filter @coinpicks/api run start
```
Expected: `coinpicks api on http://127.0.0.1:8789, pool user coinpicks_app`. That line means the migrator ran, `assertJournalFullyApplied` counted four and `assertGuardsInstalled` passed. **Ctrl-C.** Confirm the row landed:

```bash
docker exec -i -e PGPASSWORD=coinpicks_owner coinpicks-db psql -h 127.0.0.1 -U coinpicks_owner \
  -d coinpicks -t -c 'SELECT count(*) FROM drizzle.__drizzle_migrations'
```
Expected: `4`.

Then the probe. It runs inside `BEGIN … ROLLBACK` — a CHECK is immediate, so the constraint still fires, and the dev database is left exactly as it was found. The naive version left a coin called `TST` and an empty draft behind, and the first thing the operator sees in Task 4's coin list is a fake coin they did not add.

```bash
docker exec -i -e PGPASSWORD=coinpicks_owner coinpicks-db psql -h 127.0.0.1 -U coinpicks_owner -d coinpicks <<'SQL'
BEGIN;
INSERT INTO coins (id, symbol, name, chain)
  VALUES ('11111111-1111-4111-8111-111111111111','TST','Test','ethereum');
INSERT INTO reports (id, coin_id)
  VALUES ('22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111');
UPDATE report_scores SET narrative_maturity = 7
  WHERE report_id = '22222222-2222-4222-8222-222222222222';
UPDATE report_scores SET scoring_version='test', product_total=16, product_passed=true
  WHERE report_id = '22222222-2222-4222-8222-222222222222';
ROLLBACK;
SQL
```
Expected: the third statement reports `UPDATE 1` — an incomplete draft still saves — and the fourth fails with

```
ERROR:  new row for relation "report_scores" violates check constraint "rs_gate_completeness"
```

then `ROLLBACK`. That is the whole point of the task in one line: the draft is free, the scored row is not. Confirm nothing survived:

```bash
docker exec -i -e PGPASSWORD=coinpicks_owner coinpicks-db psql -h 127.0.0.1 -U coinpicks_owner \
  -d coinpicks -t -c "SELECT count(*) FROM coins WHERE symbol = 'TST'"
```
Expected: `0`.

- [ ] **Step 8: Write the blocker list — the array's second consumer**

Create `apps/api/src/reports/blockers.ts`:

```ts
import { GATE_REQUIREMENTS, type GateScoresRow, type GateSection } from '../db/gate-fields.ts'

export type BlockerState = 'clear' | 'blocking' | 'unknown'

export interface Blocker {
  code: string
  section: GateSection
  state: BlockerState
  message: string
  /** The build-order step that will write this column, when `state` is `'unknown'`. */
  implementedInStep: number | null
}

/**
 * The blocker list, straight off GATE_REQUIREMENTS — the same array that generates
 * `rs_gate_completeness`. Nothing is hand-listed here, so a conjunct cannot be forgotten in one
 * place and remembered in the other.
 *
 * A requirement written by the commit route is `unknown`, NEVER `clear`. A green tick for a
 * check nobody has written is this repo's standing failure mode.
 */
export function evaluateBlockers(scores: GateScoresRow): Blocker[] {
  return GATE_REQUIREMENTS.map((requirement) => {
    const state: BlockerState =
      requirement.writtenBy === 'commit'
        ? 'unknown'
        : requirement.satisfied(scores)
          ? 'clear'
          : 'blocking'
    return {
      code: requirement.code,
      section: requirement.section,
      message: requirement.message,
      state,
      implementedInStep: requirement.writtenBy === 'commit' ? 6 : null,
    }
  })
}
```
- [ ] **Step 9: Make the boot guard compare the applied SET, and repair the test that hid it**

Two problems, and the second is why the first matters now.

`assertJournalFullyApplied` compares `count(*)` against `journal.entries.length` and nothing else. And `integrity.test.ts`'s last case DELETEs the newest applied row, asserts the refusal, and then "restores" it in the `finally` by INSERTing an **invented** hash at `max(created_at) + 1`. The count adds up again, so the case's closing `resolves.toBe(3)` passes over a database that is genuinely **missing a migration** — a test that passed because a row existed rather than because the guard fired, which is this repo's standing failure mode written out in eleven lines.

It also arms a second failure. Verified by reading drizzle 0.45.3's `pg-core/dialect.cjs`: `created_at` is written as the journal entry's `folderMillis`, and the migrator re-applies any file whose `folderMillis` is greater than the single newest applied row. The invented row's stamp is `max(created_at) + 1`, which is *smaller* than the deleted migration's `when` by about 100 seconds — so the next `migrate()` re-applies that file and the boot check then refuses with `N migrations are committed but N+1 are applied`. Confirmed live on this machine: the dev database's three `created_at` values are exactly the journal's three `when` values.

Three edits, in this order.

**(a) Harden the guard.** In `apps/api/src/db/integrity.ts`, replace the body of `assertJournalFullyApplied`

```ts
  const journal = JSON.parse(
    readFileSync(resolve(MIGRATIONS_FOLDER, 'meta/_journal.json'), 'utf8'),
  ) as { entries: unknown[] }
  const applied = await db.execute<{ n: number }>(
    sql`SELECT count(*)::int AS n FROM drizzle.__drizzle_migrations`,
  )
  const n = applied.rows[0]?.n ?? 0
  if (n !== journal.entries.length) {
    throw new Error(
      `${journal.entries.length} migrations are committed but ${n} are applied. Drizzle's ` +
        'migrator compares only the newest applied row and never checks a hash, so an ' +
        'out-of-order file is skipped silently. Refusing to serve.',
    )
  }
  return n
```

with

```ts
  const journal = JSON.parse(
    readFileSync(resolve(MIGRATIONS_FOLDER, 'meta/_journal.json'), 'utf8'),
  ) as { entries: { when: number }[] }
  const applied = await db.execute<{ created_at: string }>(
    sql`SELECT created_at FROM drizzle.__drizzle_migrations ORDER BY created_at`,
  )
  const n = applied.rows.length
  if (n !== journal.entries.length) {
    throw new Error(
      `${journal.entries.length} migrations are committed but ${n} are applied. Drizzle's ` +
        'migrator compares only the newest applied row and never checks a hash, so an ' +
        'out-of-order file is skipped silently. Refusing to serve.',
    )
  }
  // A count is not a set. drizzle writes the journal entry's `when` into created_at, so the
  // two are comparable directly, and any journal entry whose stamp is absent means a
  // committed migration is missing however well the total adds up.
  const stamps = new Set(applied.rows.map((row) => Number(row.created_at)))
  const missing = journal.entries.filter((entry) => !stamps.has(entry.when))
  if (missing.length > 0) {
    throw new Error(
      `the migration count matches, but ${String(missing.length)} committed migration(s) are ` +
        `not applied: ${missing.map((entry) => String(entry.when)).join(', ')}. A row with the ` +
        'wrong created_at also makes drizzle re-apply the file it stands in for. Refusing ' +
        'to serve.',
    )
  }
  return n
```

`created_at` is `bigint`, and `pg` returns bigint as a string, which is why the stamps are `Number()`-ed before the comparison.

**(b) Read the count from the journal.** `integrity.test.ts` writes `3` into two assertions and greps for `/3 migrations are committed but 2 are applied/`. With `0003` committed those become 4 and 3, and they would break again on `0004`.

Add to the imports at the top of the file:

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
```

change `import { openDb } from './client.ts'` to

```ts
import { MIGRATIONS_FOLDER, openDb } from './client.ts'
```

insert directly above `const app = openDb(TEST_APP_URL, 2)`:

```ts
/** Read from the journal rather than written down: every new migration would otherwise edit
 *  two assertions in this file, and a number nobody updates is a test that gets deleted. */
const JOURNALLED = (
  JSON.parse(readFileSync(resolve(MIGRATIONS_FOLDER, 'meta/_journal.json'), 'utf8')) as {
    entries: unknown[]
  }
).entries.length
```

and in the first case, `passes against a correctly migrated database`, replace

```ts
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(3)
```

with

```ts
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
```

That is the only `toBe(3)` to edit by hand — the file's other two assertions live inside the case that (c) replaces wholesale, and its replacement already carries `JOURNALLED`.

**(c) Restore what was deleted, and prove the set check fires.** Replace the last case — everything from `  it('refuses to serve when a committed migration was never applied', async () => {` down to and including the `  })` that closes that `it`, leaving the `describe`'s own final `})` on the last line of the file alone — with a helper, the repaired case, and one new one:

```ts
  /** The newest applied row, lifted out so the `finally` can put back exactly what it found.
   *  Restoring an invented hash at `max(created_at) + 1` leaves the database one migration
   *  short with a total that still adds up, and drizzle then re-applies the real file at the
   *  next boot because its `when` is newer than the fake row's. */
  async function newestAppliedRow(): Promise<{ hash: string; created_at: string }> {
    const found = await owner.db.execute<{ hash: string; created_at: string }>(sql`
      SELECT hash, created_at FROM drizzle.__drizzle_migrations
       ORDER BY created_at DESC LIMIT 1`)
    const row = found.rows[0]
    if (row === undefined) throw new Error('no applied migrations to remove')
    return row
  }

  it('refuses to serve when a committed migration was never applied', async () => {
    const victim = await newestAppliedRow()
    await owner.db.execute(
      sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = ${victim.created_at}`,
    )
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        `${String(JOURNALLED)} migrations are committed but ${String(JOURNALLED - 1)} are applied`,
      )
    } finally {
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES (${victim.hash}, ${victim.created_at})`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
  })

  it('refuses to serve when the count is right but the set is wrong', async () => {
    const victim = await newestAppliedRow()
    await owner.db.execute(
      sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = ${victim.created_at}`,
    )
    await owner.db.execute(sql`
      INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
      VALUES ('a row that only makes the count add up', 1)`)
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        /the migration count matches, but 1 committed migration\(s\) are not applied/,
      )
    } finally {
      await owner.db.execute(sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = 1`)
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES (${victim.hash}, ${victim.created_at})`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
  })
```

The second case is the one that matters: it fabricates exactly the state the old `finally` used to leave behind, and the guard must still refuse it. Run the file on its own and read the migration table afterwards —

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm exec vitest run src/db/integrity.test.ts
docker exec -i -e PGPASSWORD=coinpicks_owner coinpicks-db psql -h 127.0.0.1 -U coinpicks_owner \
  -d coinpicks_test -t -c 'SELECT hash, created_at FROM drizzle.__drizzle_migrations ORDER BY created_at'
```
Expected: `Tests 5 passed`, and four rows whose `created_at` values are the journal's four `when` values, with no `restored-by-integrity-test` among them.

- [ ] **Step 10: Green, then commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
python -m pytest -q
```

Expected: vitest `Test Files 12 passed`, `Tests 99 passed` (89 before, +9 from `gate-fields.test.ts`, +1 from the new `integrity.test.ts` case); typecheck silent; `pnpm check --write` reformats `apps/api/drizzle/meta/0003_snapshot.json` and `apps/api/drizzle/meta/_journal.json` (drizzle-kit writes both unformatted, exactly as it did for `0000`–`0002`) and the following `pnpm check` is clean; pytest `111 passed`.

```bash
git add -A
git commit -m "feat: generate rs_gate_completeness from one required-field list

The CHECK is inert on a draft -- product_passed is only written at commit, and
CASE WHEN NULL THEN false ELSE true END is true -- so a hand-written blocker
list could tell the operator they are ready while the database would refuse
them, and a conjunct the list forgot would render as nothing at all. One array
now generates both, and a test asserts the committed .sql still matches it.

Two corrections came with the regeneration: the three product sub-scores are
now required (product_total = ease + hair_fire + exclusivity is NULL when any
is NULL, and a CHECK accepts NULL -- reproduced on 16.13), and the accrual CASE
is expanded into five conjuncts so each absence has its own blocker code."
```

---
### Task 2: The wire's validation layer — strings in, frozen validators, one parse

Nothing in this task speaks HTTP. It is the layer that decides what a section save is allowed to contain, and it exists as its own task because three of the four silent-corruption defects live here.

The decision that closes all three: **every number crosses the wire as the string the operator typed.** `Number('seven')` is NaN, `JSON.stringify(NaN)` is `null`, and `null` is this API's "clear this field" — so under the naive design a typo returned 200, bumped the CAS version, emptied the column, and left the typo on screen. Verified in Node 26 for `'seven'`, `'1,000'`, `'7%'` and `'1e999'`. A string can be refused; a `null` cannot be told apart from an intentional clear.

**Files:**
- Create: `apps/api/src/reports/bounds.ts`
- Create: `apps/api/src/reports/citable-fields.ts`
- Create: `apps/api/src/reports/draft-columns.ts`
- Create: `apps/api/src/reports/patch-schemas.ts`
- Modify: `apps/api/src/reports/errors.ts` (one new class)
- Modify: `apps/api/package.json` (four dependencies)
- Modify: `apps/api/src/scoring/frozen-surface.test.ts` (one appended describe block)
- Test: `apps/api/src/reports/draft-columns.test.ts`

**Interfaces:**
- Consumes: `NARRATIVE_MAX` from `scoring/narrative.ts`; `assertIntegerRange`, `assertNonNegative`, `assertRange` from `scoring/ranges.ts`; `reportScores`, `ReportScoresRow` from `db/schema.ts`. **No frozen file is edited.**
- Produces, from `reports/bounds.ts`: `PRODUCT_SUB_SCORE_MAX = 10`, `TEAM_RUNG_MAX = { h: 5, m: 3, l: 2 }`, `TEAM_MIN_PEOPLE = 3`, `TEAM_MAX_PEOPLE = 5`.
- Produces, from `reports/citable-fields.ts`: `CITABLE_FIELDS` (16 keys), `TEAM_FIELD_PREFIX`, `teamMemberIdOf(field): string | null`, `isScoreField(field): boolean`, `isCitableField(field): boolean`.
- Produces, from `reports/draft-columns.ts`: `DRAFT_COLUMNS` (46), `DERIVED_COLUMNS` (11), `PHASE_A2_COLUMNS` (3), `UNWRITABLE_COLUMNS` (2), `type DraftColumn`, `type ScoresPatch = Partial<Pick<ReportScoresRow, DraftColumn>>`.
- Produces, from `reports/patch-schemas.ts`: `subScore(field, max)`, `money(field)`, `fraction(field)`, `measured(field)`, `reportParam`, `versionQuery`, `citationParam`, `productPatch`, `liquidityPatch`, `narrativePatch`, `accrualPatch`, `riskPatch`, `teamPut`, `citationPost`, `coinPost`, `reportPost`.
- Produces, from `reports/errors.ts`: `class UnknownTeamMemberError` with `httpStatus = 422` and `field: string`.

- [ ] **Step 1: Install the four dependencies**

`apps/api` currently depends on exactly `drizzle-orm` and `pg`, and its `exports` map already points `.` at `./src/app.ts`, a file that does not exist. Both are fixed here and in Task 3.

In `apps/api/package.json`, replace the `dependencies` block with:

```json
  "dependencies": {
    "@hono/node-server": "2.1.1",
    "@hono/zod-validator": "0.9.1",
    "drizzle-orm": "0.45.3",
    "hono": "4.13.8",
    "pg": "8.23.0",
    "zod": "4.6.5"
  }
```

```bash
cd /home/dev/projects/trade-god && pnpm install
```
Expected: no peer warnings. `@hono/zod-validator@0.9.1` peers `hono >=4.11.2` and `zod ^3.25.0 || ^4.0.0`; `@hono/node-server@2.1.1` peers `hono ^4`. Both are satisfied.

Then one deprecation check, because the repo rule is "no deprecated features" and zod 4 carries `@deprecated` markers that compile silently. `z.string().uuid()`, `.url()` and `.datetime()` ARE marked — which is why Step 6 uses `z.uuid()`, `z.url()` and `z.iso.datetime()`. `.superRefine()`, which this plan's whole numeric layer rests on, is **not**; verified against the installed 4.6.5:

```bash
grep -c 'deprecated' "$(find /home/dev/projects/trade-god/node_modules/.pnpm -maxdepth 1 -name 'zod@4.6.5')/node_modules/zod/v4/classic/schemas.d.cts" || true
grep -B4 'superRefine(refinement' "$(find /home/dev/projects/trade-god/node_modules/.pnpm -maxdepth 1 -name 'zod@4.6.5')/node_modules/zod/v4/classic/schemas.d.cts"
```
Expected: the file does carry `@deprecated` markers, and none of them is on the `superRefine` declaration — it sits in the plain method block beside `refine`, undecorated. If that ever changes, `.check((ctx) => …)` is zod 4's supported form and the three builders in Step 6 are the only call sites.

- [ ] **Step 2: Write the bounds the frozen modules hold inline**

`scoring/product.ts` writes `assertIntegerRange('ease', input.ease, 0, 10)` inline and `scoring/team.ts` writes `< 3`, `> 5` and `* 5` inline. Exporting them would edit two frozen files to avoid a copy that `frozen-surface.test.ts` already pins against the DDL; so the numbers live in a non-frozen module and Step 8 pins them there instead.

Create `apps/api/src/reports/bounds.ts`:

```ts
/*
 * Rubric bounds that the frozen modules hold as inline literals rather than as exports.
 *
 * These are a PIN, not a second copy. `scoring/product.ts` writes `assertIntegerRange('ease',
 * input.ease, 0, 10)` inline and `scoring/team.ts` writes `< 3`, `> 5` and `* 5` inline;
 * exporting them would mean editing two frozen files to avoid a copy that
 * `frozen-surface.test.ts` already pins against the DDL. So the numbers live here, beside the
 * code that needs them at the WRITE path, and `frozen-surface.test.ts` asserts each one against
 * the committed .sql and against the frozen functions' own behaviour.
 */

/** Ease / Hair-on-Fire / Exclusivity are each 0-10 (`rs_product_*_range`). */
export const PRODUCT_SUB_SCORE_MAX = 10

/** H 0-5, M 0-3, L 0-2 (`rt_h_range`, `rt_m_range`, `rt_l_range`). */
export const TEAM_RUNG_MAX = { h: 5, m: 3, l: 2 } as const

/** `teamWeightedScore()` throws outside this range. Not a CHECK — cardinality across rows. */
export const TEAM_MIN_PEOPLE = 3
export const TEAM_MAX_PEOPLE = 5
```
- [ ] **Step 3: Write the citation vocabulary, read off the drizzle columns**

Create `apps/api/src/reports/citable-fields.ts`:

```ts
import { reportScores } from '../db/schema.ts'

/*
 * The `citations.field` vocabulary, READ OFF THE DRIZZLE COLUMNS.
 *
 * The naive version derived it in the browser with
 * `field.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase())`. That yields
 * `liquidity_depth2pct_usd` for a column actually named `liquidity_depth_2pct_usd` — digits get
 * no separator — so depth citations filed and re-read consistently by the UI would be counted as
 * zero by a commit gate querying real column names. `citations.field` is plain text with no FK
 * and no enum, so nothing else would have caught it.
 *
 * `reportScores.productEase.name` is the column's own spelling. A rename moves both sides at
 * once; a deletion is a compile error here.
 */
export const CITABLE_FIELDS = {
  productEase: reportScores.productEase.name,
  productHairFire: reportScores.productHairFire.name,
  productExclusivity: reportScores.productExclusivity.name,
  liquidityDepth2pctUsd: reportScores.liquidityDepth2pctUsd.name,
  liquidityTopPoolTvlUsd: reportScores.liquidityTopPoolTvlUsd.name,
  narrativeMaturity: reportScores.narrativeMaturity.name,
  narrativeSmartMoney: reportScores.narrativeSmartMoney.name,
  narrativeHairFire: reportScores.narrativeHairFire.name,
  narrativeCommunication: reportScores.narrativeCommunication.name,
  narrativeLineage: reportScores.narrativeLineage.name,
  narrativeMutation: reportScores.narrativeMutation.name,
  accrualSegmentRevenueUsd: reportScores.accrualSegmentRevenueUsd.name,
  accrualCaptureShare: reportScores.accrualCaptureShare.name,
  accrualPct: reportScores.accrualPct.name,
  accrualAnnualIssuanceUsd: reportScores.accrualAnnualIssuanceUsd.name,
  discoveryMarketCapUsd: reportScores.discoveryMarketCapUsd.name,
} as const

/** A team citation is `'team:' || report_team.id` — the uuid, never the position. It reaches
 *  the browser in `bounds.teamFieldPrefix`; apps/web never writes the literal, which is the
 *  same rule that closed the `liquidity_depth2pct_usd` finding one column over. */
export const TEAM_FIELD_PREFIX = 'team:'

const SCORE_FIELDS: ReadonlySet<string> = new Set(Object.values(CITABLE_FIELDS))

/** The uuid a `team:<uuid>` field names, or null when this is not a team field. */
export function teamMemberIdOf(field: string): string | null {
  if (!field.startsWith(TEAM_FIELD_PREFIX)) return null
  return field.slice(TEAM_FIELD_PREFIX.length)
}

/** True for a `report_scores` column in the vocabulary. */
export function isScoreField(field: string): boolean {
  return SCORE_FIELDS.has(field)
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/**
 * True for a field name this editor is allowed to write.
 *
 * A `team:<uuid>` field passes the SPELLING check here and is then checked for EXISTENCE inside
 * the citation transaction. Both halves are needed: an id that is not a uuid at all would reach
 * Postgres as `22P02 invalid input syntax for type uuid` — a 500 on a typo — and an id that is a
 * uuid but names nobody would attach evidence to a person the report does not have.
 */
export function isCitableField(field: string): boolean {
  if (isScoreField(field)) return true
  const memberId = teamMemberIdOf(field)
  return memberId !== null && UUID.test(memberId)
}
```
Note the value type: `reportScores.productEase.name` is typed `string`, not the literal `'product_ease'`. The compile-time check is on the **keys** — `CITABLE_FIELDS.narativeMaturity` is a TS error — and the values' correctness comes from their source rather than from their type. Step 5's test asserts the values against `getTableColumns(reportScores)` and asserts the one that the regex got wrong.

- [ ] **Step 4: Partition the 62 columns**

Create `apps/api/src/reports/draft-columns.ts`:

```ts
import type { ReportScoresRow } from '../db/schema.ts'

/*
 * Which of `report_scores`' 62 columns the EDITOR may write.
 *
 * `draft-columns.test.ts` reads the real column list off the drizzle table and asserts these four
 * arrays partition it exactly, so a column added to schema.ts with no home fails the suite. A
 * column nobody classified is a column nobody decided about, and the write path would have
 * defaulted it into "the editor can set this".
 */

/** The operator types these, through the six section routes. */
export const DRAFT_COLUMNS = [
  'overviewSentence',
  'productEase',
  'productHairFire',
  'productExclusivity',
  'productEaseRationale',
  'productHairFireRationale',
  'productExclusivityRationale',
  'liquidityTier',
  'liquidityTierAssignedAt',
  'liquidityJustification',
  'liquidityDepth2pctUsd',
  'liquidityDepthSource',
  'liquidityDepthUrl',
  'liquidityDepthLabel',
  'liquidityDepthMeasuredAt',
  'liquidityTopPoolTvlUsd',
  'liquidityTopPoolSource',
  'liquidityTopPoolUrl',
  'liquidityTopPoolLabel',
  'liquidityTopPoolMeasuredAt',
  'liquidityNoDexPool',
  'narrativeMaturity',
  'narrativeSmartMoney',
  'narrativeHairFire',
  'narrativeCommunication',
  'narrativeLineage',
  'narrativeMutation',
  'narrativeMaturityRationale',
  'narrativeSmartMoneyRationale',
  'narrativeHairFireRationale',
  'narrativeCommunicationRationale',
  'narrativeLineageRationale',
  'narrativeMutationRationale',
  'accrualSegmentRevenueUsd',
  'accrualCaptureShare',
  'accrualPct',
  'accrualAnnualIssuanceUsd',
  'accrualAbsentReason',
  'accrualRationale',
  'accrualFinding',
  'discoveryMarketCapUsd',
  'discoveryMarketCapSource',
  'discoveryMarketCapUrl',
  'discoveryMarketCapLabel',
  'discoveryMarketCapMeasuredAt',
  'riskNotes',
] as const

/** Written only inside the commit transaction (build-order step 6), from the frozen functions. */
export const DERIVED_COLUMNS = [
  'scoringVersion',
  'productTotal',
  'productPassed',
  'narrativeTotal',
  'teamWeightedScore',
  'accrualGrossAnnualFlowUsd',
  'accrualNetAnnualFlowUsd',
  'accrualZeroFactor',
  'discoveryPremiumKind',
  'discoveryPremiumMultiple',
  'waivedCitationCount',
] as const

/** The viem chain layer's columns. */
export const PHASE_A2_COLUMNS = [
  'liquiditySurvivingPools',
  'accrualContractAddress',
  'accrualMeasuredTrailing90dUsd',
] as const

/** The primary key, and the one GENERATED ALWAYS column — Postgres refuses a write with 428C9. */
export const UNWRITABLE_COLUMNS = ['reportId', 'accrualAssessed'] as const

export type DraftColumn = (typeof DRAFT_COLUMNS)[number]

/** What a section route is allowed to hand `saveSection`. Derived columns are not in the type. */
export type ScoresPatch = Partial<Pick<ReportScoresRow, DraftColumn>>
```
- [ ] **Step 5: The partition test, which is also the vocabulary test**

Create `apps/api/src/reports/draft-columns.test.ts`:

```ts
import { getTableColumns } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { reportScores } from '../db/schema.ts'
import { CITABLE_FIELDS } from './citable-fields.ts'
import {
  DERIVED_COLUMNS,
  DRAFT_COLUMNS,
  PHASE_A2_COLUMNS,
  UNWRITABLE_COLUMNS,
} from './draft-columns.ts'

const columns = Object.keys(getTableColumns(reportScores))

describe('report_scores is partitioned exactly', () => {
  it('classifies every column exactly once', () => {
    const classified = [
      ...DRAFT_COLUMNS,
      ...DERIVED_COLUMNS,
      ...PHASE_A2_COLUMNS,
      ...UNWRITABLE_COLUMNS,
    ]
    expect(new Set(classified).size, 'a column is classified twice').toBe(classified.length)
    // A column with no home is a column nobody decided about, and the write path defaults it
    // into "the editor may set this".
    expect([...columns].sort()).toEqual([...classified].sort())
  })

  it('keeps every derived column out of the editor list', () => {
    for (const derived of DERIVED_COLUMNS) {
      expect(DRAFT_COLUMNS as readonly string[]).not.toContain(derived)
    }
  })
})

describe('the citation vocabulary', () => {
  it('uses the drizzle columns own spelling', () => {
    const real = new Set(Object.values(getTableColumns(reportScores)).map((column) => column.name))
    for (const [key, name] of Object.entries(CITABLE_FIELDS)) {
      expect(real.has(name), `${key} -> ${name} is not a report_scores column`).toBe(true)
    }
  })

  it('spells the one column with a digit in it correctly', () => {
    // The regex derivation this replaces produced `liquidity_depth2pct_usd`: /[A-Z]/ never
    // separates a digit run. Every other name round-tripped, which is what made it silent.
    expect(CITABLE_FIELDS.liquidityDepth2pctUsd).toBe('liquidity_depth_2pct_usd')
  })
})
```
```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/reports/draft-columns.test.ts
```
Expected: `Tests 4 passed`. If the partition is wrong the failure prints the two sorted arrays and the difference is the column you forgot.

- [ ] **Step 6: The patch schemas — one parse, through the frozen validators**

Create `apps/api/src/reports/patch-schemas.ts`:

```ts
import { z } from 'zod'
import { NARRATIVE_MAX } from '../scoring/narrative.ts'
import { assertIntegerRange, assertNonNegative, assertRange } from '../scoring/ranges.ts'
import { PRODUCT_SUB_SCORE_MAX, TEAM_MAX_PEOPLE, TEAM_RUNG_MAX } from './bounds.ts'
import { isCitableField } from './citable-fields.ts'

/*
 * EVERY NUMBER ARRIVES AS THE STRING THE OPERATOR TYPED.
 *
 * The naive editor called `Number(typed)` in the browser and sent the result. Verified in Node
 * 26: `JSON.stringify({ productEase: Number('seven') })` is `{"productEase":null}`, and the same
 * for '1,000', '7%' and '1e999' (Infinity -> null). `null` is this API's "clear this field", so
 * no validator downstream can tell a typo from a deliberate clear: the save returns 200, bumps
 * the CAS version, and silently empties the column.
 *
 * Sending the raw string moves the parse to one place that can REFUSE. `null` still means clear,
 * and it can now only be produced by a box the operator actually emptied.
 *
 * `.trim()` first, then a regex that admits digits and nothing else. '' and '   ' fail it, so a
 * blank string can never reach `Number('')` -> 0 either.
 */

const WHOLE = /^(0|[1-9]\d*)$/
const DECIMAL = /^(0|[1-9]\d*)(\.\d+)?$/

/**
 * A whole-number sub-score, validated by the FROZEN `assertIntegerRange` before it can reach
 * Postgres. That order is load-bearing: `INSERT INTO t (ease integer) VALUES (7.5)` stores 8 on
 * 16.13 and `BETWEEN 0 AND 10` then passes on the rounded value, so the CHECK cannot defend the
 * 2026-09-21 integer ruling on its own. Verified live.
 *
 * One builder, used by all nine sub-scores and all three team rungs, so there is one place to
 * forget rather than fifteen.
 */
export function subScore(field: string, max: number) {
  return z
    .string()
    .trim()
    .regex(WHOLE, `${field} must be a whole number written in digits`)
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertIntegerRange(field, parsed, 0, max)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** A non-negative dollar amount, validated by the frozen `assertNonNegative`. */
export function money(field: string) {
  return z
    .string()
    .trim()
    .regex(DECIMAL, `${field} must be a number written in digits, with at most one decimal point`)
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertNonNegative(field, parsed)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** A fraction in [0, 1] — never a percentage. `assertRange` rejects 50 rather than dividing it. */
export function fraction(field: string) {
  return z
    .string()
    .trim()
    .regex(DECIMAL, `${field} must be a number written in digits, with at most one decimal point`)
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertRange(field, parsed, 0, 1)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** Prose: trimmed, and an empty box is an explicit null rather than a blank string. */
const prose = z
  .string()
  .trim()
  .transform((text) => (text === '' ? null : text))
  .nullable()

/**
 * A measured figure and the story of where it came from, as ONE object.
 *
 * `rs_depth_provenance_complete` and its two siblings are biconditionals, so five separate
 * nullable fields can express a state the database refuses. One object cannot: it is all five or
 * it is `null`.
 *
 * The figure is `money(...)`, so a blank box is a 422 and never `Number('') === 0`. The naive
 * version wrote `value: Number(figure)` with no blank guard, which stored "+/-2% depth = $0,
 * verified, DefiLlama, 14:32" — a fabricated measured zero, immutable after commit.
 */
export function measured(field: string) {
  return z
    .object({
      value: money(field),
      source: z.string().trim().min(1, `${field} needs a source`),
      url: z.url(`${field} needs a source URL`),
      label: z.enum(['verified', 'vendor_claim']),
      measuredAt: z.iso
        .datetime({ offset: true })
        .refine(
          (text) => Date.parse(text) <= Date.now(),
          `${field}: a measurement cannot be in the future`,
        )
        .transform((text) => new Date(text)),
    })
    .nullable()
}

export const reportParam = z.object({ reportId: z.uuid() })

/** The CAS token on a DELETE, where there is no body to put it in. */
export const versionQuery = z.object({
  version: z
    .string()
    .regex(/^[1-9]\d*$/, 'version must be a positive whole number')
    .transform(Number),
})
export const citationParam = z.object({ reportId: z.uuid(), citationId: z.uuid() })

/** The CAS token. Rule 4: good for exactly one write. */
const version = z.number().int().min(1)

export const productPatch = z.strictObject({
  version,
  overviewSentence: prose,
  productEase: subScore('ease', PRODUCT_SUB_SCORE_MAX).nullable(),
  productHairFire: subScore('hairFire', PRODUCT_SUB_SCORE_MAX).nullable(),
  productExclusivity: subScore('exclusivity', PRODUCT_SUB_SCORE_MAX).nullable(),
  productEaseRationale: prose,
  productHairFireRationale: prose,
  productExclusivityRationale: prose,
})

export const liquidityPatch = z.strictObject({
  version,
  depth: measured('liquidityDepth2pctUsd'),
  topPool: measured('liquidityTopPoolTvlUsd'),
  liquidityNoDexPool: z.boolean(),
  liquidityTier: z.enum(['low', 'medium', 'high']).nullable(),
  liquidityJustification: prose,
})

export const narrativePatch = z.strictObject({
  version,
  narrativeMaturity: subScore('maturity', NARRATIVE_MAX.maturity).nullable(),
  narrativeSmartMoney: subScore('smartMoney', NARRATIVE_MAX.smartMoney).nullable(),
  narrativeHairFire: subScore('hairFire', NARRATIVE_MAX.hairFire).nullable(),
  narrativeCommunication: subScore('communication', NARRATIVE_MAX.communication).nullable(),
  narrativeLineage: subScore('lineage', NARRATIVE_MAX.lineage).nullable(),
  narrativeMutation: subScore('mutation', NARRATIVE_MAX.mutation).nullable(),
  narrativeMaturityRationale: prose,
  narrativeSmartMoneyRationale: prose,
  narrativeHairFireRationale: prose,
  narrativeCommunicationRationale: prose,
  narrativeLineageRationale: prose,
  narrativeMutationRationale: prose,
})

export const accrualPatch = z.strictObject({
  version,
  accrualSegmentRevenueUsd: money('segmentRevenueUsd').nullable(),
  accrualCaptureShare: fraction('captureShare').nullable(),
  accrualPct: fraction('accrualPct').nullable(),
  accrualAnnualIssuanceUsd: money('annualIssuanceUsd').nullable(),
  accrualAbsentReason: prose,
  accrualRationale: prose,
  accrualFinding: prose,
  marketCap: measured('marketCapUsd'),
})

export const riskPatch = z.strictObject({
  version,
  riskNotes: prose,
})

/**
 * The WHOLE team, replaced in one transaction.
 *
 * Positions are the array index, so nothing on the wire can claim a slot twice and
 * `rt_report_position_uniq` (not deferrable) cannot be tripped by a reorder. An existing person
 * keeps their `id`, which is what keeps their `team:<uuid>` citations attached.
 */
export const teamPut = z.strictObject({
  version,
  members: z
    .array(
      z.strictObject({
        id: z.uuid().nullable(),
        name: z.string().trim().min(1, 'a team member needs a name'),
        roles: z.array(z.string().trim().min(1)).min(1, 'a team member needs at least one role'),
        isFounder: z.boolean(),
        h: subScore('h', TEAM_RUNG_MAX.h),
        m: subScore('m', TEAM_RUNG_MAX.m),
        l: subScore('l', TEAM_RUNG_MAX.l),
        summary: z.string().trim().min(1, 'a team member needs a prior-experience summary'),
      }),
    )
    // No minimum: a half-entered team is a legitimate draft state, and cardinality is
    // teamWeightedScore()'s to reject at commit. The maximum is enforced because an over-full
    // set is never valid under any later ruling.
    .max(TEAM_MAX_PEOPLE, `the framework allows at most ${TEAM_MAX_PEOPLE} people`),
})

export const citationPost = z.strictObject({
  version,
  field: z
    .string()
    .trim()
    .refine(
      isCitableField,
      'not a citable field: use a name from CITABLE_FIELDS or `team:<report_team.id>`',
    ),
  url: z.url('a citation needs a URL'),
  quote: z.string().trim().min(1, 'a citation needs the exact quote to search for'),
})

export const coinPost = z.strictObject({
  symbol: z.string().trim().min(1),
  name: z.string().trim().min(1),
  chain: z.string().trim().min(1),
  contractAddress: z.string().trim().min(1).nullable(),
  coingeckoId: z.string().trim().min(1).nullable(),
  addressSources: z.array(z.url()),
})

export const reportPost = z.strictObject({ coinId: z.uuid() })
```
Three things in that file are the fix rather than the obvious choice, and reverting any of them reopens a confirmed defect:

- **`subScore` takes a string, not a number.** A `z.number()` field would accept the `null` that `JSON.stringify(NaN)` produces and could never tell it from a clear.
- **`subScore` calls `assertIntegerRange` before the value can reach Postgres.** `INSERT (ease integer) VALUES (7.5)` stores `8` and `BETWEEN 0 AND 10` then passes on the rounded value. The CHECK cannot defend the integer ruling on its own; it only ever sees the rounded integer.
- **`measured()` is one object or `null`, and its figure is `money(...)`.** The naive version had five independent fields and `value: Number(figure)`, and `Number('')` is 0 — so a blank figure box with real provenance stored "±2% depth = $0, verified, DefiLlama, 14:32", which `rs_depth_provenance_complete` (a presence biconditional) and `rs_depth_2pct_nonneg` (`>= 0`) both accept, immutably.

Note also `z.uuid()`, `z.url()` and `z.iso.datetime()` rather than `z.string().uuid()` / `.url()` / `.datetime()`: the chained forms are `@deprecated` in zod 4.6.5 and compile without a word of complaint.

- [ ] **Step 7: Add the one new error class**

Append to `apps/api/src/reports/errors.ts`:

```ts

/**
 * A citation whose `team:<uuid>` field names a member this report does not have. `citations.field`
 * is text with no foreign key, so this is the only place the reference can be checked before the
 * commit gate counts it as evidence.
 */
export class UnknownTeamMemberError extends Error {
  readonly httpStatus = 422
  readonly field: string

  constructor(field: string) {
    super(`no team member on this report matches ${field}. Save the team first.`)
    this.name = 'UnknownTeamMemberError'
    this.field = field
  }
}
```

- [ ] **Step 8: Pin the four bounds that nothing pinned**

`FROZEN_SURFACE` in `apps/api/src/scoring/frozen-surface.test.ts` already lists `productSubScoreMax`, `teamHMax`, `teamMMax`, `teamLMax`, `teamFounderWeight`, `teamMinPeople` and `teamMaxPeople` — and compares none of them against anything. A literal in a test table that nothing asserts is the failure this project keeps finding. This block gives them something to be wrong against, and pins `reports/bounds.ts` at the same time.

Change the import block at the top of that file from

```ts
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './product.ts'
import { SCORING_VERSION } from './ranges.ts'
```

to

```ts
import {
  PRODUCT_SUB_SCORE_MAX,
  TEAM_MAX_PEOPLE,
  TEAM_MIN_PEOPLE,
  TEAM_RUNG_MAX,
} from '../reports/bounds.ts'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './product.ts'
import { SCORING_VERSION } from './ranges.ts'
import { teamWeightedScore } from './team.ts'
```

and append to the end of the file:

```ts

/*
 * `reports/bounds.ts` restates four numbers that product.ts and team.ts hold as inline literals.
 * Exporting them from the frozen modules would edit two frozen files to avoid a copy; pinning
 * them here costs nothing and pins them to the DDL and to the functions' own behaviour instead.
 *
 * It also gives teamFounderWeight / teamMinPeople / teamMaxPeople something to compare against.
 * Before this block they sat in the FROZEN_SURFACE table above, compared with nothing at all —
 * a literal in a test table that nothing asserts is the failure this project keeps finding.
 */
describe('the write path reproduces the bounds the frozen code holds inline', () => {
  const ddl = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle/0000_init.sql'),
    'utf8',
  )

  it('matches the frozen surface table', () => {
    expect({
      productSubScoreMax: PRODUCT_SUB_SCORE_MAX,
      teamHMax: TEAM_RUNG_MAX.h,
      teamMMax: TEAM_RUNG_MAX.m,
      teamLMax: TEAM_RUNG_MAX.l,
      teamMinPeople: TEAM_MIN_PEOPLE,
      teamMaxPeople: TEAM_MAX_PEOPLE,
    }).toEqual({
      productSubScoreMax: FROZEN_SURFACE.productSubScoreMax,
      teamHMax: FROZEN_SURFACE.teamHMax,
      teamMMax: FROZEN_SURFACE.teamMMax,
      teamLMax: FROZEN_SURFACE.teamLMax,
      teamMinPeople: FROZEN_SURFACE.teamMinPeople,
      teamMaxPeople: FROZEN_SURFACE.teamMaxPeople,
    })
  })

  it('matches the DDL', () => {
    for (const column of ['product_ease', 'product_hair_fire', 'product_exclusivity']) {
      expect(ddl).toContain(`"report_scores"."${column}" BETWEEN 0 AND ${PRODUCT_SUB_SCORE_MAX}`)
    }
    expect(ddl).toContain(`"report_team"."h" BETWEEN 0 AND ${TEAM_RUNG_MAX.h}`)
    expect(ddl).toContain(`"report_team"."m" BETWEEN 0 AND ${TEAM_RUNG_MAX.m}`)
    expect(ddl).toContain(`"report_team"."l" BETWEEN 0 AND ${TEAM_RUNG_MAX.l}`)
  })

  it("matches teamWeightedScore()'s own refusals", () => {
    const person = (isFounder: boolean) => ({ name: 'x', isFounder, h: 1, m: 1, l: 1 })
    const below = Array.from({ length: TEAM_MIN_PEOPLE - 1 }, () => person(false))
    const above = Array.from({ length: TEAM_MAX_PEOPLE + 1 }, () => person(false))
    expect(() => teamWeightedScore(below)).toThrow(
      `team must have ${TEAM_MIN_PEOPLE} to ${TEAM_MAX_PEOPLE} people, got ${below.length}`,
    )
    expect(() => teamWeightedScore(above)).toThrow(
      `team must have ${TEAM_MIN_PEOPLE} to ${TEAM_MAX_PEOPLE} people, got ${above.length}`,
    )
  })

  it('weights the founder by teamFounderWeight, measured against the function', () => {
    // Everyone but the founder scores zero, so the result is (founder x W) / (W + others) and
    // nothing else -- which pins team.ts's inline `* 5` AND the table's literal at once.
    // `expect(FROZEN_SURFACE.teamFounderWeight).toBe(5)` would be a literal compared to a
    // literal: it cannot fail however team.ts is edited, which is the failure this whole block
    // exists to stop. The framework's 7.25 worked example is already pinned, verbatim, by
    // scoring/team.test.ts.
    const weight = FROZEN_SURFACE.teamFounderWeight
    const founderScore = TEAM_RUNG_MAX.h + TEAM_RUNG_MAX.m + TEAM_RUNG_MAX.l
    const others = TEAM_MIN_PEOPLE - 1
    const team = [
      {
        name: 'founder',
        isFounder: true,
        h: TEAM_RUNG_MAX.h,
        m: TEAM_RUNG_MAX.m,
        l: TEAM_RUNG_MAX.l,
      },
      ...Array.from({ length: others }, (_, index) => ({
        name: `other-${String(index)}`,
        isFounder: false,
        h: 0,
        m: 0,
        l: 0,
      })),
    ]
    expect(teamWeightedScore(team)).toBeCloseTo((founderScore * weight) / (weight + others), 10)
  })
})
```

`readFileSync`, `resolve`, `dirname` and `fileURLToPath` are already imported at the top of that file; do not import them twice.

- [ ] **Step 9: Green, then commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
```
Expected: `Test Files 13 passed`, `Tests 107 passed` (99 from Task 1, +4 partition, +4 frozen bounds); typecheck silent; Biome clean.

```bash
git add -A
git commit -m "feat: the wire's validation layer -- strings in, frozen validators, one parse

Number('seven') is NaN and JSON.stringify turns NaN into null, which this API
reads as 'clear this field', so a typo used to return 200, bump the CAS version
and empty the column. Numbers now arrive as the string the operator typed and
are parsed once, by zod, through assertIntegerRange / assertNonNegative /
assertRange -- which also gets in front of Postgres rounding 7.5 into 8 and the
CHECK passing on the rounded value.

CITABLE_FIELDS is read off the drizzle columns rather than derived by regex:
the regex spelled liquidity_depth_2pct_usd as liquidity_depth2pct_usd, and the
UI used the same wrong string to add and to filter, so it looked correct."
```

---
### Task 3: The API — store, app factory, thirteen routes, and the suite that proves them

**Files:**
- Create: `apps/api/src/reports/store.ts`
- Create: `apps/api/src/app.ts`
- Modify: `apps/api/src/server.ts` (rewritten onto Hono)
- Test: `apps/api/src/reports/routes.test.ts`

**Interfaces:**
- Consumes: `Db`, `Tx` from `db/client.ts`; the tables and row types from `db/schema.ts`; `casBumpVersion` from `reports/cas.ts`; everything Task 2 produced; `evaluateBlockers` from `reports/blockers.ts`; `NARRATIVE_MAX`, `NARRATIVE_TOTAL_MAX`, `PRODUCT_GATE_THRESHOLD`, `ScoreRangeError`, `SCORING_VERSION` from `scoring/`.
- Produces, from `reports/store.ts`:
  - `interface ReportPayload { report: ReportRow; coin: CoinRow; scores: ReportScoresRow; team: ReportTeamRow[]; citations: CitationRow[] }`
  - `readReport(db, reportId): Promise<ReportPayload | null>`
  - `saveSection(db, reportId, expectedVersion, patch: ScoresPatch): Promise<{ version: number; scores: ReportScoresRow }>`
  - `interface TeamMemberInput { id: string | null; name: string; roles: string[]; isFounder: boolean; h: number; m: number; l: number; summary: string }`
  - `replaceTeam(db, reportId, expectedVersion, members): Promise<{ version: number; team: ReportTeamRow[]; citationsRemoved: number }>`
  - `interface CitationInput { field: string; url: string; quote: string }`
  - `addCitation(db, reportId, expectedVersion, input): Promise<{ version: number; citations: CitationRow[] }>`
  - `removeCitation(db, reportId, expectedVersion, citationId): Promise<{ version: number; citations: CitationRow[] }>`
- Produces, from `app.ts`: `createApp(db: Db, migrations: number)` and `type AppType = ReturnType<typeof createApp>`.

The route table, which is the contract `apps/web` is written against:

| Method | Path | Body / query | 200 |
|---|---|---|---|
| GET | `/health` | — | `{ ok, migrations, scoringVersion }` |
| GET | `/coins` | — | `{ rows: { coin, reportId, reportStatus, reportCreatedAt }[] }` |
| POST | `/coins` | `coinPost` | `{ coin }` |
| POST | `/reports` | `{ coinId }` | `{ report }` |
| GET | `/reports/:reportId` | — | `{ report, coin, scores, team, citations, blockers, bounds }` |
| PATCH | `/reports/:reportId/product` | `productPatch` | `{ version, scores }` |
| PATCH | `/reports/:reportId/liquidity` | `liquidityPatch` | `{ version, scores }` |
| PATCH | `/reports/:reportId/narrative` | `narrativePatch` | `{ version, scores }` |
| PATCH | `/reports/:reportId/accrual` | `accrualPatch` | `{ version, scores }` |
| PATCH | `/reports/:reportId/risk` | `riskPatch` | `{ version, scores }` |
| PUT | `/reports/:reportId/team` | `teamPut` | `{ version, team, citationsRemoved }` |
| POST | `/reports/:reportId/citations` | `citationPost` | `{ version, citations }` |
| DELETE | `/reports/:reportId/citations/:citationId` | `?version=N` | `{ version, citations }` |

Six section routes rather than one `PATCH /scores` taking a bag: the naive design's `savePatch(patch: Record<string, unknown>)` disabled every wire-level check on the widest write surface in the app. `hc` type-checks an object *literal* — `{ productEase: 'x' }` is TS2322 and `{ nope: 1 }` is TS2353 — but a variable typed `Record<string, unknown>` satisfies every optional target property, and zod's default object mode then strips the unknown key silently. One strict schema per section, and the shape is checked on both sides.

- [ ] **Step 1: Write the store**

Create `apps/api/src/reports/store.ts`:

```ts
import { and, asc, eq } from 'drizzle-orm'
import type { Db, Tx } from '../db/client.ts'
import {
  type CitationRow,
  type CoinRow,
  citations,
  coins,
  type ReportRow,
  type ReportScoresRow,
  type ReportTeamRow,
  reportScores,
  reports,
  reportTeam,
} from '../db/schema.ts'
import { casBumpVersion } from './cas.ts'
import { teamMemberIdOf } from './citable-fields.ts'
import type { ScoresPatch } from './draft-columns.ts'
import { ReportNotFoundError, UnknownTeamMemberError } from './errors.ts'

export interface ReportPayload {
  report: ReportRow
  coin: CoinRow
  scores: ReportScoresRow
  team: ReportTeamRow[]
  citations: CitationRow[]
}

/** Either handle reads the same way; only writes care which one they are on. */
type Reader = Pick<Db | Tx, 'select'>

function readTeam(reader: Reader, reportId: string): Promise<ReportTeamRow[]> {
  return reader
    .select()
    .from(reportTeam)
    .where(eq(reportTeam.reportId, reportId))
    .orderBy(asc(reportTeam.position))
}

function readCitations(reader: Reader, reportId: string): Promise<CitationRow[]> {
  return reader
    .select()
    .from(citations)
    .where(eq(citations.reportId, reportId))
    .orderBy(asc(citations.createdAt))
}

/**
 * The whole report, or null when there is no such row.
 *
 * The `scores` row is joined rather than left optional. `reports_seed_scores` guarantees it
 * exists, but `rows[0]` is `T | undefined` under `noUncheckedIndexedAccess`, and a bare
 * `c.json({ scores })` would put that `| undefined` on the wire — roughly forty TS18048s in the
 * editor, none of which the operator can do anything about.
 */
export async function readReport(db: Db, reportId: string): Promise<ReportPayload | null> {
  const rows = await db
    .select({ report: reports, coin: coins, scores: reportScores })
    .from(reports)
    .innerJoin(coins, eq(coins.id, reports.coinId))
    .innerJoin(reportScores, eq(reportScores.reportId, reports.id))
    .where(eq(reports.id, reportId))
    .limit(1)

  const row = rows[0]
  if (row === undefined) return null

  return {
    report: row.report,
    coin: row.coin,
    scores: row.scores,
    team: await readTeam(db, reportId),
    citations: await readCitations(db, reportId),
  }
}

/**
 * One section, one CAS bump, one transaction.
 *
 * Ruled 2026-09-21: an explicit Save per section, not save-on-blur. `casBumpVersion` bumps
 * `reports.version` on EVERY successful call, so per-field blur saves fire many CAS writes, and
 * two edits started before the first response lands means the second is refused 409 while the
 * screen still shows it as entered.
 */
export function saveSection(
  db: Db,
  reportId: string,
  expectedVersion: number,
  patch: ScoresPatch,
): Promise<{ version: number; scores: ReportScoresRow }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)
    const saved = await tx
      .update(reportScores)
      .set(patch)
      .where(eq(reportScores.reportId, reportId))
      .returning()
    const scores = saved[0]
    if (scores === undefined) throw new ReportNotFoundError(reportId)
    return { version, scores }
  })
}

export interface TeamMemberInput {
  id: string | null
  name: string
  roles: string[]
  isFounder: boolean
  h: number
  m: number
  l: number
  summary: string
}

/**
 * The whole team, replaced in one transaction.
 *
 * Row-by-row editing cannot express a reorder: `rt_report_position_uniq` is not deferrable, so
 * swapping two people trips 23505 halfway through, and moving the founder trips
 * `rt_one_founder_per_report` the same way. Deleting every row and re-inserting in array order
 * sidesteps both, and the array index IS the position, so nothing on the wire can claim a slot
 * twice.
 *
 * A person who already exists keeps their `id`, which is what keeps their `team:<uuid>`
 * citations attached. Citations naming a member who did not survive are deleted here: evidence
 * pointing at nobody would otherwise still be counted by the commit gate.
 */
export function replaceTeam(
  db: Db,
  reportId: string,
  expectedVersion: number,
  members: TeamMemberInput[],
): Promise<{ version: number; team: ReportTeamRow[]; citationsRemoved: number }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)

    await tx.delete(reportTeam).where(eq(reportTeam.reportId, reportId))

    const inserted =
      members.length === 0
        ? []
        : await tx
            .insert(reportTeam)
            .values(
              members.map((member, index) => ({
                // A null id is a person who has never been saved; Postgres mints one.
                ...(member.id === null ? {} : { id: member.id }),
                reportId,
                position: index + 1,
                name: member.name,
                roles: member.roles,
                isFounder: member.isFounder,
                h: member.h,
                m: member.m,
                l: member.l,
                summary: member.summary,
              })),
            )
            .returning()

    const surviving = new Set(inserted.map((row) => row.id))
    const existing = await tx
      .select({ id: citations.id, field: citations.field })
      .from(citations)
      .where(eq(citations.reportId, reportId))

    let citationsRemoved = 0
    for (const citation of existing) {
      const memberId = teamMemberIdOf(citation.field)
      if (memberId === null || surviving.has(memberId)) continue
      await tx.delete(citations).where(eq(citations.id, citation.id))
      citationsRemoved += 1
    }

    return { version, team: inserted, citationsRemoved }
  })
}

export interface CitationInput {
  field: string
  url: string
  quote: string
}

/**
 * Add a human citation.
 *
 * `origin` is always `'human'` and `status` keeps its `'unverified'` default — step 4 writes no
 * other value. `selected_at` is stamped on insert: a citation the operator typed is selected by
 * definition, and `selected_at IS NULL` is reserved for an unselected MODEL candidate (step 8).
 *
 * A `team:<uuid>` field is checked against `report_team` INSIDE the transaction. `citations.field`
 * is plain text with no foreign key, and the naive editor minted a browser-side uuid for a new
 * person and offered their evidence box before the person was ever saved — so a citation could
 * point at a `report_team.id` that does not exist, and the commit gate would count it as evidence.
 */
export function addCitation(
  db: Db,
  reportId: string,
  expectedVersion: number,
  input: CitationInput,
): Promise<{ version: number; citations: CitationRow[] }> {
  return db.transaction(async (tx) => {
    const memberId = teamMemberIdOf(input.field)
    if (memberId !== null) {
      const member = await tx
        .select({ id: reportTeam.id })
        .from(reportTeam)
        .where(and(eq(reportTeam.reportId, reportId), eq(reportTeam.id, memberId)))
        .limit(1)
      if (member[0] === undefined) throw new UnknownTeamMemberError(input.field)
    }

    const version = await casBumpVersion(tx, reportId, expectedVersion)
    await tx.insert(citations).values({
      reportId,
      field: input.field,
      url: input.url,
      quote: input.quote,
      origin: 'human',
      selectedAt: new Date(),
    })
    return { version, citations: await readCitations(tx, reportId) }
  })
}

export function removeCitation(
  db: Db,
  reportId: string,
  expectedVersion: number,
  citationId: string,
): Promise<{ version: number; citations: CitationRow[] }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)
    await tx
      .delete(citations)
      .where(and(eq(citations.reportId, reportId), eq(citations.id, citationId)))
    return { version, citations: await readCitations(tx, reportId) }
  })
}
```
Two shapes in there are deliberate and were both reproduced as failures first:

- **`readReport` joins `report_scores` rather than selecting it separately.** `rows[0]` is `T | undefined` under `noUncheckedIndexedAccess`, and `c.json({ scores })` would put that `| undefined` on the wire — roughly forty `TS18048`s in the editor over a row `reports_seed_scores` guarantees exists.
- **`replaceTeam` deletes the whole set and re-inserts in array order.** `rt_report_position_uniq` is not deferrable, so a row-by-row swap trips 23505 halfway through, and moving the founder trips `rt_one_founder_per_report` the same way.

- [ ] **Step 2: Write the app factory and the thirteen routes**

Create `apps/api/src/app.ts`:

```ts
import { zValidator } from '@hono/zod-validator'
import { asc, eq, sql } from 'drizzle-orm'
import type { ValidationTargets } from 'hono'
import { Hono } from 'hono'
import type { ZodType } from 'zod'
import type { Db } from './db/client.ts'
import { coins, reports } from './db/schema.ts'
import { evaluateBlockers } from './reports/blockers.ts'
import {
  PRODUCT_SUB_SCORE_MAX,
  TEAM_MAX_PEOPLE,
  TEAM_MIN_PEOPLE,
  TEAM_RUNG_MAX,
} from './reports/bounds.ts'
import { CITABLE_FIELDS, TEAM_FIELD_PREFIX } from './reports/citable-fields.ts'
import type { ScoresPatch } from './reports/draft-columns.ts'
import {
  AlreadyCommittedError,
  ReportNotFoundError,
  StaleVersionError,
  sqlstateOf,
  UnknownTeamMemberError,
} from './reports/errors.ts'
import {
  accrualPatch,
  citationParam,
  citationPost,
  coinPost,
  liquidityPatch,
  narrativePatch,
  productPatch,
  reportParam,
  reportPost,
  riskPatch,
  teamPut,
  versionQuery,
} from './reports/patch-schemas.ts'
import {
  addCitation,
  readReport,
  removeCitation,
  replaceTeam,
  saveSection,
} from './reports/store.ts'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './scoring/narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './scoring/product.ts'
import { SCORING_VERSION, ScoreRangeError } from './scoring/ranges.ts'

/**
 * Every bound, threshold and closed vocabulary the editor needs, served rather than copied.
 *
 * `apps/web` holds no rubric literal at all. The naive editor wrote `draft.length >= 5` and
 * `const TIERS = ['low','medium','high']`, which are a frozen bound and a pgEnum reproduced in a
 * tier where nothing pins them — and the guard test that was supposed to catch that only grepped
 * for two constant names. `teamFieldPrefix` is here for the same reason: `team:` is this API's
 * citation vocabulary, one string away from the `liquidity_depth2pct_usd` finding, and
 * `boundary.test.ts` cannot see a bare prefix the way it sees a bare number.
 */
const BOUNDS = {
  productSubScoreMax: PRODUCT_SUB_SCORE_MAX,
  productGateThreshold: PRODUCT_GATE_THRESHOLD,
  narrativeMax: NARRATIVE_MAX,
  narrativeTotalMax: NARRATIVE_TOTAL_MAX,
  teamRungMax: TEAM_RUNG_MAX,
  teamMinPeople: TEAM_MIN_PEOPLE,
  teamMaxPeople: TEAM_MAX_PEOPLE,
  liquidityTiers: ['low', 'medium', 'high'],
  provenanceLabels: ['verified', 'vendor_claim'],
  citableFields: CITABLE_FIELDS,
  teamFieldPrefix: TEAM_FIELD_PREFIX,
  scoringVersion: SCORING_VERSION,
} as const

/**
 * ONE refusal shape for every validation failure, and 422 rather than zod-validator's default
 * 400.
 *
 * It matters because the message carries the FROZEN text: `subScore()` runs
 * `assertIntegerRange` inside a superRefine, so typing 11 into Ease of Use comes back as
 * "ease must be between 0 and 10, got 11" — the same sentence the commit route will raise. The
 * default hook returns a serialised ZodError the editor would have had to re-interpret.
 */
function check<T extends ZodType, Target extends keyof ValidationTargets>(
  target: Target,
  schema: T,
) {
  return zValidator(target, schema, (result, c) => {
    if (result.success) return undefined
    const issues = result.error.issues.map((issue) => ({
      path: issue.path.map(String).join('.'),
      message: issue.message,
    }))
    const first = issues[0]
    return c.json(
      {
        code: 'INVALID',
        message:
          first === undefined
            ? 'the request is not valid'
            : `${first.path === '' ? 'body' : first.path}: ${first.message}`,
        issues,
      },
      422,
    )
  })
}

/**
 * The editor's API. Build-order step 4: it creates and edits a DRAFT.
 *
 * `createApp` takes the pool rather than opening one, so `server.ts` keeps decision A's ordering
 * (migrate as the owner, close that pool, THEN open the request pool) and so the route tests can
 * run the real routes against `coinpicks_test` through `app.request()`.
 */
export function createApp(db: Db, migrations: number) {
  return (
    new Hono()
      .onError((error, c) => {
        if (error instanceof StaleVersionError) {
          return c.json(
            {
              code: 'STALE_VERSION',
              message: error.message,
              actualVersion: error.actualVersion,
            },
            409,
          )
        }
        if (error instanceof AlreadyCommittedError) {
          return c.json({ code: 'ALREADY_COMMITTED', message: error.message }, 409)
        }
        if (error instanceof ReportNotFoundError) {
          return c.json({ code: 'NOT_FOUND', message: error.message }, 404)
        }
        if (error instanceof UnknownTeamMemberError) {
          return c.json({ code: 'UNKNOWN_TEAM_MEMBER', message: error.message }, 422)
        }
        if (error instanceof ScoreRangeError) {
          return c.json({ code: 'OUT_OF_RANGE', message: error.message, field: error.field }, 422)
        }
        // drizzle 0.45.3 wraps every driver error, so `error.code` is always undefined; the
        // SQLSTATE is on `.cause`. sqlstateOf walks the chain.
        const sqlstate = sqlstateOf(error)
        if (sqlstate === 'CP001') {
          return c.json(
            { code: 'REPORT_COMMITTED', message: 'this report is committed and immutable' },
            409,
          )
        }
        if (sqlstate === '23514' || sqlstate === '23505') {
          const constraint = (error as { cause?: { constraint?: string } }).cause?.constraint
          return c.json(
            {
              code: sqlstate === '23514' ? 'CONSTRAINT_REFUSED' : 'DUPLICATE',
              message: `the database refused it: ${constraint ?? sqlstate}`,
            },
            422,
          )
        }
        console.error(error)
        return c.json({ code: 'INTERNAL', message: 'the request failed' }, 500)
      })

      /**
       * Carries the migration count AND the scoring version. The count is what proves the journal
       * applied; the version string is what distinguishes this application from anything else
       * answering on a nearby port — this machine has recorded a green /health read off another
       * application's process.
       */
      .get('/health', async (c) => {
        await db.execute(sql`SELECT 1`)
        return c.json({ ok: true, migrations, scoringVersion: SCORING_VERSION })
      })

      .get('/coins', async (c) => {
        const rows = await db
          .select({
            coin: coins,
            reportId: reports.id,
            reportStatus: reports.status,
            reportCreatedAt: reports.createdAt,
          })
          .from(coins)
          .leftJoin(reports, eq(reports.coinId, coins.id))
          .orderBy(asc(coins.symbol), asc(reports.createdAt))
        return c.json({ rows })
      })

      .post('/coins', check('json', coinPost), async (c) => {
        const input = c.req.valid('json')
        const inserted = await db.insert(coins).values(input).returning()
        const coin = inserted[0]
        if (coin === undefined) throw new Error('insert into coins returned no row')
        return c.json({ coin })
      })

      .post('/reports', check('json', reportPost), async (c) => {
        const { coinId } = c.req.valid('json')
        const inserted = await db.insert(reports).values({ coinId }).returning()
        const report = inserted[0]
        if (report === undefined) throw new Error('insert into reports returned no row')
        return c.json({ report })
      })

      .get('/reports/:reportId', check('param', reportParam), async (c) => {
        const { reportId } = c.req.valid('param')
        const payload = await readReport(db, reportId)
        if (payload === null) throw new ReportNotFoundError(reportId)
        return c.json({
          ...payload,
          blockers: evaluateBlockers(payload.scores),
          bounds: BOUNDS,
        })
      })

      .patch(
        '/reports/:reportId/product',
        check('param', reportParam),
        check('json', productPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/liquidity',
        check('param', reportParam),
        check('json', liquidityPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, depth, topPool, ...fields } = c.req.valid('json')
          /*
           * The tier's timestamp is re-stamped on every liquidity save that carries a tier, and
           * that is what makes `rs_tier_not_older_than_its_inputs` unfailable rather than merely
           * unlikely: the section always saves the tier and both measurements together, every
           * `measured_at` was already refused if it was in the future, and `now()` runs after the
           * request was parsed. Do not "fix" this into a stale-tier flag the UI then has to
           * announce — the naive design chose a `tierCleared` boolean that nothing rendered.
           */
          const patch: ScoresPatch = {
            ...fields,
            liquidityTierAssignedAt: fields.liquidityTier === null ? null : new Date(),
            liquidityDepth2pctUsd: depth === null ? null : depth.value,
            liquidityDepthSource: depth === null ? null : depth.source,
            liquidityDepthUrl: depth === null ? null : depth.url,
            liquidityDepthLabel: depth === null ? null : depth.label,
            liquidityDepthMeasuredAt: depth === null ? null : depth.measuredAt,
            liquidityTopPoolTvlUsd: topPool === null ? null : topPool.value,
            liquidityTopPoolSource: topPool === null ? null : topPool.source,
            liquidityTopPoolUrl: topPool === null ? null : topPool.url,
            liquidityTopPoolLabel: topPool === null ? null : topPool.label,
            liquidityTopPoolMeasuredAt: topPool === null ? null : topPool.measuredAt,
          }
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/narrative',
        check('param', reportParam),
        check('json', narrativePatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/accrual',
        check('param', reportParam),
        check('json', accrualPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, marketCap, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = {
            ...fields,
            discoveryMarketCapUsd: marketCap === null ? null : marketCap.value,
            discoveryMarketCapSource: marketCap === null ? null : marketCap.source,
            discoveryMarketCapUrl: marketCap === null ? null : marketCap.url,
            discoveryMarketCapLabel: marketCap === null ? null : marketCap.label,
            discoveryMarketCapMeasuredAt: marketCap === null ? null : marketCap.measuredAt,
          }
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/risk',
        check('param', reportParam),
        check('json', riskPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .put(
        '/reports/:reportId/team',
        check('param', reportParam),
        check('json', teamPut),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, members } = c.req.valid('json')
          const founders = members.filter((member) => member.isFounder).length
          if (founders > 1) {
            return c.json(
              {
                code: 'TWO_FOUNDERS',
                message: `the framework allows one founder, got ${founders}`,
              },
              422,
            )
          }
          return c.json(await replaceTeam(db, reportId, version, members))
        },
      )

      .post(
        '/reports/:reportId/citations',
        check('param', reportParam),
        check('json', citationPost),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...input } = c.req.valid('json')
          return c.json(await addCitation(db, reportId, version, input))
        },
      )

      .delete(
        '/reports/:reportId/citations/:citationId',
        check('param', citationParam),
        check('query', versionQuery),
        async (c) => {
          const { reportId, citationId } = c.req.valid('param')
          const { version } = c.req.valid('query')
          return c.json(await removeCitation(db, reportId, version, citationId))
        },
      )
  )
}

export type AppType = ReturnType<typeof createApp>
```
`createApp(db, migrations)` takes the pool rather than opening one. That keeps `server.ts`'s boot ordering exact (a module-level pool would be constructed while the owner pool is still open) and it is what lets the route tests run the real routes against `coinpicks_test` through `app.request()`, with no port and no network.

`app.onError` handles every failure, so each route declares only its 200 shape plus the validator's 422. The client narrows with `res.ok`.

- [ ] **Step 3: Move `server.ts` onto Hono**

Replace `apps/api/src/server.ts` entirely:

```ts
import { serve } from '@hono/node-server'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { createApp } from './app.ts'
import { MIGRATIONS_FOLDER, openDb, requireEnv } from './db/client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './db/integrity.ts'

// 8789. Overridable through PORT, because a port collision is local to a machine: the editor's
// vite dev server proxies /api here, and a server that fails with EADDRINUSE while something
// ELSE answers on the same port is how a boot check gets recorded as green without ever having
// run. /health carries `scoringVersion` so the answer can be attributed to THIS application.
const PORT = Number(process.env.PORT ?? 8789)

/*
 * Boot, in the order decision A requires and no other.
 *
 * The owner pool exists for the length of the migration and is closed before the app pool is
 * opened. It is not kept around "just in case": a session that owns the tables can DROP TRIGGER
 * in one statement, and if it is not open, nothing a request can reach is able to.
 */
const owner = openDb(requireEnv('DATABASE_URL_OWNER'), 1)
let appliedMigrations = 0
try {
  await migrate(owner.db, { migrationsFolder: MIGRATIONS_FOLDER })
  appliedMigrations = await assertJournalFullyApplied(owner.db)
  await assertGuardsInstalled(owner.db)
} finally {
  await owner.close()
}

const app = openDb(requireEnv('DATABASE_URL'))
await assertNotSuperuser(app.db)

serve(
  { fetch: createApp(app.db, appliedMigrations).fetch, hostname: '127.0.0.1', port: PORT },
  () => {
    console.log(`coinpicks api on http://127.0.0.1:${PORT}, pool user coinpicks_app`)
  },
)
```
The boot order is unchanged and must stay unchanged: owner pool, migrate, assert the journal, assert the guards, close, app pool, assert NOSUPERUSER, then the port. The port comment no longer claims 8787 is held by `my-teacher-api-1`; `docker ps` shows only `coinpicks-db` and `medi-pal-db-1`, and nothing listens on 8787.

- [ ] **Step 4: Write the route suite**

Create `apps/api/src/reports/routes.test.ts`:

```ts
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { createApp } from '../app.ts'
import { openDb } from '../db/client.ts'
import { createDraftReport, TEST_APP_URL } from '../db/testing.ts'

/*
 * The editor's money path, against a real PostgreSQL.
 *
 * Every case here is a defect that was reproduced live before the route existed, so each test is
 * named after what it stops rather than after the route it calls.
 */

const handle = openDb(TEST_APP_URL, 4)
// 0, and deliberately not a count: the number only reaches `/health`, and no case in this file
// calls it. A literal nothing asserts is a number nobody updates — the shape Task 1 removed from
// integrity.test.ts.
const app = createApp(handle.db, 0)

afterAll(() => handle.close())

async function send(path: string, method: string, body: unknown): Promise<Response> {
  return app.request(path, {
    method,
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  })
}

interface Refusal {
  code: string
  message: string
  actualVersion?: number
}

const blankProduct = {
  overviewSentence: null,
  productEase: null,
  productHairFire: null,
  productExclusivity: null,
  productEaseRationale: null,
  productHairFireRationale: null,
  productExclusivityRationale: null,
}

const blankLiquidity = {
  depth: null,
  topPool: null,
  liquidityNoDexPool: false,
  liquidityTier: null,
  liquidityJustification: null,
}

async function readEase(reportId: string): Promise<number | null> {
  const rows = await handle.db.execute<{ product_ease: number | null }>(
    sql`SELECT product_ease FROM report_scores WHERE report_id = ${reportId}`,
  )
  return rows.rows[0]?.product_ease ?? null
}

describe('a typo in a numeric box', () => {
  it('is refused by name and leaves the saved value alone', async () => {
    const { reportId } = await createDraftReport(handle.db)

    const saved = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '7',
    })
    expect(saved.status).toBe(200)
    expect(await readEase(reportId)).toBe(7)

    // Number('seven') is NaN, JSON.stringify(NaN) is null, and null means "clear this field".
    // The string arrives intact instead, so the API can refuse it.
    for (const typed of ['seven', '1,000', '7%', '1e999', '7.5', '-1', '']) {
      const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
        ...blankProduct,
        version: 2,
        productEase: typed,
      })
      expect(refused.status, `"${typed}" was accepted`).toBe(422)
    }
    expect(await readEase(reportId), 'a refused save cleared the column').toBe(7)
  })

  it('rejects 7.5 through the frozen assertIntegerRange, before Postgres can round it', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '7.5',
    })
    expect(refused.status).toBe(422)
    // Postgres stores 7.5 into an integer column as 8 and BETWEEN 0 AND 10 then passes on the
    // rounded value. Verified on 16.13. The CHECK cannot defend the integer ruling alone.
    expect(await readEase(reportId)).toBeNull()
  })

  it('rejects an out-of-range score with the frozen message', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '11',
    })
    expect(refused.status).toBe(422)
    expect(JSON.stringify(await refused.json())).toContain('ease must be between 0 and 10, got 11')
  })
})

describe('a measured figure', () => {
  it('cannot be stored as a zero the operator never measured', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      depth: {
        value: '',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        measuredAt: '2026-09-21T10:00:00+02:00',
      },
    })
    expect(refused.status).toBe(422)
    const rows = await handle.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores
           WHERE report_id = ${reportId} AND liquidity_depth_2pct_usd IS NOT NULL`,
    )
    expect(rows.rows[0]?.n).toBe(0)
  })

  it('cannot be dated in the future, which would lock the tier forever', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      depth: {
        value: '1000000',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        measuredAt: '2099-01-01T00:00:00+00:00',
      },
    })
    expect(refused.status).toBe(422)
  })

  it('saves with its tier, and the tier is never older than its inputs', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const saved = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      liquidityTier: 'medium',
      liquidityJustification: 'thin but real',
      depth: {
        value: '1000000',
        source: 'CoinGecko',
        url: 'https://coingecko.com/',
        label: 'vendor_claim',
        measuredAt: '2026-09-20T09:00:00+00:00',
      },
    })
    expect(saved.status).toBe(200)
    const rows = await handle.db.execute<{ ok: boolean }>(
      sql`SELECT liquidity_tier_assigned_at >= liquidity_depth_measured_at AS ok
            FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(rows.rows[0]?.ok).toBe(true)
  })
})

describe('the compare-and-swap token', () => {
  it('is spent by one write, and the second is refused with the real version', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const first = await send(`/reports/${reportId}/risk`, 'PATCH', {
      version: 1,
      riskNotes: 'first',
    })
    expect(first.status).toBe(200)

    const stale = await send(`/reports/${reportId}/risk`, 'PATCH', {
      version: 1,
      riskNotes: 'second',
    })
    expect(stale.status).toBe(409)
    const refusal = (await stale.json()) as Refusal
    expect(refusal.code).toBe('STALE_VERSION')
    expect(refusal.actualVersion).toBe(2)
  })
})

describe('team citations', () => {
  it('refuse to attach to a person the database does not have', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/citations`, 'POST', {
      version: 1,
      field: 'team:11111111-2222-4333-8444-555555555555',
      url: 'https://example.com/bio',
      quote: 'grew revenue to $40m',
    })
    expect(refused.status).toBe(422)
    const refusal = (await refused.json()) as Refusal
    expect(refusal.code).toBe('UNKNOWN_TEAM_MEMBER')
  })

  it('survive a reorder and disappear with the person they named', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const person = (name: string, isFounder: boolean) => ({
      id: null,
      name,
      roles: ['Founder'],
      isFounder,
      h: '4',
      m: '2',
      l: '1',
      summary: `${name} ran a $10m book`,
    })

    const created = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 1,
      members: [person('Ada', true), person('Bo', false), person('Cy', false)],
    })
    expect(created.status).toBe(200)
    const team = (await created.json()) as { version: number; team: { id: string }[] }
    const ada = team.team[0] as { id: string }
    const cy = team.team[2] as { id: string }

    const cited = await send(`/reports/${reportId}/citations`, 'POST', {
      version: team.version,
      field: `team:${cy.id}`,
      url: 'https://example.com/cy',
      quote: 'grew revenue to $40m',
    })
    expect(cited.status).toBe(200)
    const afterCitation = (await cited.json()) as { version: number }

    // A reorder that moves the founder: row-by-row updates trip rt_report_position_uniq and
    // rt_one_founder_per_report halfway through. The whole-set replace cannot.
    const reordered = await send(`/reports/${reportId}/team`, 'PUT', {
      version: afterCitation.version,
      members: [
        { ...person('Bo', false), id: team.team[1]?.id ?? null },
        { ...person('Cy', false), id: cy.id },
        { ...person('Ada', true), id: ada.id },
      ],
    })
    expect(reordered.status).toBe(200)
    expect((await reordered.json()) as { citationsRemoved: number }).toMatchObject({
      citationsRemoved: 0,
    })

    const dropped = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 4,
      members: [{ ...person('Ada', true), id: ada.id }],
    })
    expect(dropped.status).toBe(200)
    expect((await dropped.json()) as { citationsRemoved: number }).toMatchObject({
      citationsRemoved: 1,
    })
  })

  it('refuses two founders by name rather than by constraint', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 1,
      members: [
        {
          id: null,
          name: 'A',
          roles: ['x'],
          isFounder: true,
          h: '1',
          m: '1',
          l: '1',
          summary: 's',
        },
        {
          id: null,
          name: 'B',
          roles: ['x'],
          isFounder: true,
          h: '1',
          m: '1',
          l: '1',
          summary: 's',
        },
      ],
    })
    expect(refused.status).toBe(422)
    expect((await refused.json()) as Refusal).toMatchObject({ code: 'TWO_FOUNDERS' })
  })
})

describe('the report payload', () => {
  it('carries a blocker per conjunct and never calls a commit-written column clear', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const response = await app.request(`/reports/${reportId}`)
    expect(response.status).toBe(200)
    const payload = (await response.json()) as {
      blockers: { code: string; state: string }[]
      bounds: { productSubScoreMax: number; citableFields: Record<string, string> }
      scores: { productEase: number | null }
    }
    expect(payload.scores.productEase).toBeNull()
    expect(payload.bounds.productSubScoreMax).toBe(10)
    expect(payload.bounds.citableFields.liquidityDepth2pctUsd).toBe('liquidity_depth_2pct_usd')
    expect(payload.blockers.some((blocker) => blocker.state === 'unknown')).toBe(true)
    expect(
      payload.blockers.filter((blocker) => blocker.code === 'WAIVED_CITATION_COUNT')[0]?.state,
    ).toBe('unknown')
  })

  it('answers a missing report with 404, not with an undefined scores row', async () => {
    const response = await app.request('/reports/11111111-2222-4333-8444-555555555555')
    expect(response.status).toBe(404)
  })
})
```
- [ ] **Step 5: Run it against real Postgres**

```bash
cd /home/dev/projects/trade-god
docker compose up -d db
pnpm --filter @coinpicks/api run db:bootstrap
cd apps/api && pnpm test src/reports/routes.test.ts
```
Expected: `Test Files 1 passed`, `Tests 12 passed`. `global-setup.ts` drops and rebuilds `coinpicks_test` from the four committed migrations at the start of the run, so `0003` is exercised here too.

If `a typo in a numeric box` fails at `"seven" was accepted`, the wire is carrying numbers instead of strings — check that `patch-schemas.ts` was not "simplified" to `z.number()`.

- [ ] **Step 6: Boot it and prove the boot check means something**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm dev
```
In another shell:
```bash
curl -s http://127.0.0.1:8789/health
```
Expected, exactly: `{"ok":true,"migrations":4,"scoringVersion":"coinpicks-2026-09-21"}`.

Three separate facts, and the plan wants all three: `ok` is a `SELECT 1` on the **app** pool; `migrations` is the count `assertJournalFullyApplied` returned, so a skipped migration refuses to start rather than answering; `scoringVersion` is a compile-time constant from `scoring/ranges.ts`, so the answer can be attributed to **this** application. This machine has recorded a green `/health` read off a different application's process.

- [ ] **Step 7: Green, then commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
```
Expected: `Test Files 14 passed`, `Tests 119 passed`; typecheck silent; Biome clean.

```bash
git add -A
git commit -m "feat: the editor's API -- thirteen routes, one CAS bump per section save

Six section routes rather than one PATCH taking a bag: a savePatch(patch:
Record<string, unknown>) type-checks against every optional property, and zod's
default object mode then drops a mistyped key silently -- a 200, a version bump
and a rationale that never persisted.

replaceTeam replaces the whole set because rt_report_position_uniq is not
deferrable and a row-by-row reorder trips 23505 halfway through; it also drops
citations naming members that did not survive, because evidence pointing at
nobody would still be counted by the commit gate. A team:<uuid> citation is
checked against report_team inside the transaction -- citations.field is text
with no foreign key."
```

---
### Task 4: `apps/web` — the tsconfig split that compiles, TanStack Start, and the two-sided boundary guard

**The tsconfig arrangement is the first thing to get right, because the design's version does not build.** Extending `tsconfig.base.json` and overriding only `moduleResolution` yields, on the pinned tsc 5.9.3:

```
error TS5095: Option 'bundler' can only be used when 'module' is set to 'preserve' or to 'es2015' or later.
error TS5109: Option 'moduleResolution' must be set to 'NodeNext' (or left unspecified) when option 'module' is set to 'NodeNext'.
```

because the base sets `module: nodenext` and that is inherited. Five keys are overridden, not one. The set below was compiled clean against the real `tsconfig.base.json` with React 19 JSX and explicit `.ts`/`.tsx` relative imports, with the inherited `erasableSyntaxOnly`, `verbatimModuleSyntax`, `allowImportingTsExtensions` and `noUncheckedIndexedAccess` all still active — and, under Start, with the generated route tree in the same program.

**`moduleResolution: bundler` is load-bearing twice, not once.** It lets `apps/api`'s explicit-`.ts` relative imports resolve inside the web program, *and* it lets `routeTree.gen.ts`'s extensionless `import { Route } from './routes/__root'` resolve. The generated tree cannot compile under `nodenext`, which is the second reason the override is five keys rather than an experiment.

**`"node"` is in `types` on purpose.** `boundary.test.ts` and `bundle.test.ts` read the source tree and the built output with `node:fs`, and they have to live in the same program as the code they guard. It also makes visible something that happens anyway: `tsc --listFiles` shows **15 `apps/api` files and 83 `@types/node` files** entering the web program through `import type { AppType }`, whatever `types` says. The consequence to know about is that `setTimeout` is typed as returning `Timeout`, not `number` — step 4 uses no timers, and anything that stores one later writes `ReturnType<typeof setTimeout>`.

**`@tanstack/react-start` 1.168.57 stays, and `routeTree.gen.ts` is generated and committed.** An earlier draft of this plan dropped Start for plain Vite with code-based routes. **The owner reversed that on 2026-09-21**; Task 8 Step 7 records the reversal. Start is in the approved spec §9 and in `CLAUDE.md`'s stack table, and both premises of the drop were re-tested here and both are closed:

- *The generated tree fails `biome check`.* True, and **one line closes it.** Measured against a real Start build of this tree: with `biome.json` as it is today, `biome check` walks the generated tree and **exits 1** — `assist/source/organizeImports` as an **error** at `routeTree.gen.ts:11`, plus four warnings (`lint/suspicious/noExplicitAny` at 20, 25 and 30, and `lint/correctness/noUnusedImports` at 98). With `"!**/routeTree.gen.ts"` added to `files.includes` it walks **one file fewer and exits 0**. (In the scratch tree that was 52 against 51; the repo checks 35 files today and will check more once this plan lands, so the delta of exactly one is the part to hold onto, not the total.) That is exactly the arrangement the sibling repo at `../profe` already runs — its `biome.json` line 9 reads `"includes": ["**", "!**/dist", "!**/node_modules", "!**/routeTree.gen.ts"]` while its `apps/web/package.json` line 22 pins `"@tanstack/react-start": "1.168.49"`. The file is excluded **because it is generated**: the Start plugin rewrites it from `src/routes/` on every `vite dev` and every `vite build`, so linting it is linting an output.
- *`pnpm format` and the generator then fight over it.* Not reproducible once it is excluded. Round-tripped here: `sha256(routeTree.gen.ts)` is `790aa396aff84af7…` before `biome check --write`, unchanged after it, and unchanged after the next `vite build`; `biome check` exits 0 across the round trip.

And keeping Start buys something the SPA could not have had. The Start vite plugin ships **`importProtection`**, a first-class build-time import guard. Defect 5 — the one-word import slip — stops being a bundle nobody measures and becomes a build that fails with a full import trace. Plain Vite plus `@tanstack/react-router` has no equivalent, at any price.

**The leak guard matters MORE under Start, not less.** A Start build emits **two** bundles — `dist/client/` (what a browser downloads) and `dist/server/` (the SSR fetch handler) — and two things follow, both measured here rather than reasoned about:

- **A scan of the wrong directory passes.** The SPA draft's own command, run verbatim against a Start build, prints `grep: dist/assets/index-*.js: No such file or directory` and the pipeline **exits 0 having read zero bytes**. The `|| true` — which that draft explicitly defended as "not decoration" — is what converts the missing directory into a pass. Step 11 names `dist/client` and drops the `|| true`, and `bundle.test.ts` asserts both directories exist and that what it read was big enough to be a real bundle.
- **A client-only scan is not sufficient.** A value import used only inside a `createServerFn` body leaves the client bundle spotless — measured at **587,978 bytes against a clean 583,379, zero ORM needles, under the byte ceiling** — and puts drizzle plus this project's table and constraint names in `dist/server` (`drizzle:` ×15, `PgTable` ×6, `PgColumn` ×88, `report_scores` ×2, `rs_gate` ×1). That is a database handle in the tier that is supposed to hold none. `bundle.test.ts` scans **both** halves, and `importProtection` carries a `server` specifier list as well as a `client` one.

**What Start's server is for here, and what it is not.** One sentence, and Task 8 puts it in the decisions log: *Start's server hosts the page and one loopback hop, and nothing else.* Two consequences are written into files rather than into prose:

- `routes/__root.tsx` now executes on the server, so the SPA draft's "no network egress from `__root.tsx` by construction" is replaced by a mechanical guarantee. `boundary.test.ts` asserts that `__root.tsx` contains none of `loader`, `beforeLoad`, `createServerFn`, `fetch(`, `ssr:`, and that no file under `src/` other than `routes/api.$.ts` contains `fetch(` at all. That is stronger than "by construction", because it fails a commit rather than a code review — and the SPA draft itself conceded that a loader added later would have put the web tier back on the network.
- **The citation verifier (step 5) and the EvidenceFinder (step 8) do not belong in a Start server function.** Both fetch a third party or hold a key, and the tier that holds `DATABASE_URL` — and would hold an LLM key — is `apps/api`. They are reached from the browser through the same `hc<AppType>` hop as everything else. `importProtection.server` is what mechanically stops someone taking the shortcut, because a server function reaching for `@coinpicks/api` fails the SSR build.

**Files:**
- Create: `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/vite.config.ts`, `apps/web/vitest.config.ts`
- Create: `apps/web/src/styles.css`, `apps/web/src/router.tsx`, `apps/web/src/lib/client.ts`
- Create: `apps/web/src/routes/__root.tsx`, `apps/web/src/routes/index.tsx`, `apps/web/src/routes/api.$.ts`
- Create: `apps/web/src/routes/reports.$reportId.tsx` (a stub in this task; Task 5 writes it properly)
- Create: `apps/web/scripts/serve.ts`
- Generated by the Start plugin and **committed**: `apps/web/src/routeTree.gen.ts`
- Modify: `biome.json` (one exclude line), `package.json` (the root `dev` script)
- Test: `apps/web/src/boundary.test.ts`, `apps/web/src/bundle.test.ts`

There is no `index.html` and no `src/main.tsx`. Start supplies both; `src/routes/__root.tsx` is the document.

**Interfaces:**
- Consumes: `type AppType` from `@coinpicks/api`, by `import type` and by nothing else.
- Produces, from `src/lib/client.ts`: `client`, `ReportPayload`, `Scores`, `TeamRow`, `Citation`, `Blocker`, `Bounds`, `CoinRows`, `ProductBody`, `LiquidityBody`, `NarrativeBody`, `AccrualBody`, `RiskBody`, `TeamBody`, `CitationBody`, `type Fields<T> = Omit<T, 'version'>`, `interface ApiError`, `readError(response): Promise<ApiError>`.
- Produces, from `src/router.tsx`: `getRouter`, plus the `@tanstack/react-router` `Register` augmentation that makes `<Link to="/reports/$reportId">` type-checked.
- Produces, from each file under `src/routes/`: `Route`. The route tree is generated from those exports; nothing hand-assembles it.

- [ ] **Step 1: The package**

Create `apps/web/package.json`:

```json
{
  "name": "@coinpicks/web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "start": "node --env-file-if-exists=../../.env scripts/serve.ts",
    "test": "vite build && vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check"
  },
  "dependencies": {
    "@coinpicks/api": "workspace:*",
    "@hono/node-server": "2.1.1",
    "@tanstack/react-router": "1.170.38",
    "@tanstack/react-start": "1.168.57",
    "hono": "4.13.8",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "4.3.3",
    "@types/node": "catalog:",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.1",
    "tailwindcss": "4.3.3",
    "typescript": "catalog:",
    "vite": "8.3.0",
    "vitest": "catalog:"
  }
}
```
```bash
cd /home/dev/projects/trade-god && pnpm install
```
Expected: no peer warnings. `@vitejs/plugin-react@6.1.1` peers `vite ^8.0.0`; its three other peers (`oxc-transform-react`, `@rolldown/plugin-babel`, `babel-plugin-react-compiler`) are all `optional: true`. `@tailwindcss/vite@4.3.3` peers `vite ^5.2.0 || ^6 || ^7 || ^8`. `@tanstack/react-router@1.170.38` peers `react >=18`.

Three things about this file are decisions, not boilerplate:

- **`test` runs `vite build` first.** `bundle.test.ts` reads `dist/client` and `dist/server`, and a scan of a `dist` left over from an earlier source tree is the same failure as a scan of a directory that does not exist: a guard reporting success over bytes it did not read. Building first makes the scanned bundle the current one, every time, and it costs about a second (measured: 296 ms for the client environment and 205 ms for the ssr environment). It also means `pnpm -r --if-present run test` — which is what CI runs and what every later task's green step runs — needs no build step in front of it.
- **No `@tanstack/router-plugin` and no `@tanstack/router-cli`.** Start's vite plugin carries the route generator. The sibling repo has `@tanstack/router-cli` only because it runs a manual `tsr generate` script; nothing here does.
- **`@hono/node-server` is a runtime dependency**, not a dev one: `scripts/serve.ts` (Step 8) is what hosts the built app.

Without `@types/react` and `@types/react-dom` this package cannot typecheck at all: `TS7016: Could not find a declaration file for module 'react'` and `TS7026: JSX element implicitly has type 'any'`. They are in the list above; do not trim them.

- [ ] **Step 2: The tsconfig — five keys, named**

Create `apps/web/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "module": "preserve",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "types": ["vite/client", "node"]
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "vite.config.ts", "vitest.config.ts"]
}
```

Five keys, and Start needs no sixth. `scripts/serve.ts` is deliberately **outside** `include`: it imports `../dist/server/server.js`, which does not exist until `vite build` has run, so `tsc --noEmit` on a clean checkout would otherwise fail on a file that is never executed unbuilt.

- [ ] **Step 3: One line in `biome.json`, because the route tree is generated**

In `/home/dev/projects/trade-god/biome.json`, replace

```json
    "includes": ["apps/**", "*.json", "*.jsonc"]
```

with

```json
    "includes": ["apps/**", "*.json", "*.jsonc", "!**/routeTree.gen.ts"]
```

That is the whole change, and it is the sibling repo's arrangement: `../profe/biome.json` line 9 excludes the same filename, beside `@tanstack/react-start` in `../profe/apps/web/package.json`. **The reason is that the file is generated** — the Start plugin rewrites it from `src/routes/` on every dev start and every build — not that it is inconvenient. Its own header says the same thing: *"you should also exclude this file from your linter and/or formatter"*.

Nothing else is needed. `!**/node_modules`, `!**/dist` and `!**/.tanstack` would be redundant: `vcs.useIgnoreFile: true` is already set and `.gitignore` already lists `node_modules/`, `dist/`, `.output/` and `.tanstack/`. Measured with the one-line change on a tree that has a real `routeTree.gen.ts` in it: `No fixes applied.`, exit 0, over exactly one file fewer than without it.

**Do not add `"css": { "parser": { "tailwindDirectives": true } }`.** The sibling repo carries it; this repo does not need it, and the claim that `@import 'tailwindcss'` is a biome *parse* error does not reproduce here. Measured on this machine, against the config above: `@import "tailwindcss";` with **double** quotes is clean, and the single-quoted form is a *formatter* error, not a parse error — `javascript.formatter.quoteStyle` is JavaScript-only and biome formats CSS strings with double quotes regardless. Step 4 writes the file with double quotes.

- [ ] **Step 4: Vite, vitest and the stylesheet**

Create `apps/web/vite.config.ts`:

```ts
import tailwindcss from '@tailwindcss/vite'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import viteReact from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/*
 * NO `server.proxy`. `src/routes/api.$.ts` serves the `/api` prefix in dev AND in production, so
 * the hop that ships is the hop that is developed against. With a Vite proxy in front of it the
 * server route is dead code in dev and the only code in production -- measured: with the proxy
 * configured and its target pointed at a dead port, `curl /api/health` returned 502 rather than
 * falling through to the route, which is two paths where the project only wants one.
 */
export default defineConfig({
  plugins: [
    tanstackStart({
      /*
       * THE LEAK GUARD, AT BUILD TIME. This is the thing plain Vite has no equivalent of.
       *
       * `import { type AppType, createApp } from '@coinpicks/api'` plus one value use is the
       * defect the boundary test exists for: tsc accepts it, biome says nothing, and the client
       * bundle silently grows by 136 kB. With this option the build STOPS, naming the line and
       * printing the whole import chain that reached it.
       *
       * `server` as well as `client`, and they are different rules. `client` says "not in the
       * browser". `server` says "not in the RENDERER either" -- without it a value import used
       * only inside a `createServerFn` body builds clean, leaves the client bundle spotless, and
       * puts drizzle plus this project's DDL in dist/server, which is a database handle in the
       * tier that is supposed to hold none. Measured both ways.
       *
       * A type-only import is erased before the bundler sees the specifier, so `hc<AppType>`
       * still compiles with both lists in place.
       */
      importProtection: {
        behavior: 'error',
        client: { specifiers: ['@coinpicks/api', /^drizzle-orm/, /^pg$/] },
        enabled: true,
        server: { specifiers: ['@coinpicks/api', /^drizzle-orm/, /^pg$/] },
      },
    }),
    // react's vite plugin must come AFTER start's vite plugin; tailwind last.
    viteReact(),
    tailwindcss(),
  ],
  // Vite 8 resolves tsconfig `paths` natively. Declared because the documented default is false.
  resolve: { tsconfigPaths: true },
  /*
   * `strictPort`, because this machine has already been bitten. 5173 is held by the sibling repo's
   * dev server right now; without this, `vite dev` moves to 5174 with one grey line of output and
   * the first `curl localhost:5173/` reads ANOTHER APP'S HTML. Measured with 5173 occupied:
   * `Error: Port 5173 is already in use`, exit 1. A loud failure beats a health check that passed
   * against the wrong process -- which is the same lesson as the 8787 note Task 8 strikes.
   */
  server: { port: 5173, strictPort: true },
})
```

Create `apps/web/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

// Node, not jsdom: both suites read files off disk — the source tree and the built bundles — and
// neither renders a component. There is no jsdom and no @testing-library/react in this plan.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
```

Create `apps/web/src/styles.css`:

```css
@import "tailwindcss";
```

Double quotes, per Step 3. `__root.tsx` links it through `import appCss from '../styles.css?url'`, which is how Tailwind reaches the document under Start — there is no `index.html` to put a `<link>` in.

- [ ] **Step 5: The typed client — the one line the whole boundary rests on**

Create `apps/web/src/lib/client.ts`:

```ts
import type { AppType } from '@coinpicks/api'
import { hc, type InferRequestType, type InferResponseType } from 'hono/client'

/*
 * `import type`, and the whole line is type-only.
 *
 * The mixed form -- `import` then `{ type AppType, createApp }` -- is one word different and a
 * genuine value use. tsc accepts it under `verbatimModuleSyntax`, biome's `useImportType` does
 * not fire on it, and the client bundle goes from 583,379 to 727,230 bytes with this project's
 * DDL in it. Three things hold this line in place, in the order they fire: the Start plugin's
 * `importProtection` (vite.config.ts) fails the BUILD with an import trace, `boundary.test.ts`
 * reads this source, and `bundle.test.ts` reads dist/client -- which is the browser's half of a
 * Start build, and the only half a client-side scan may look at.
 */

/*
 * TanStack Start renders this app on the server as well as in the browser, so this module is
 * evaluated in a place where `window` does not exist. `import.meta.env.SSR` is replaced by a
 * literal at build time — `true` in the server bundle, `false` in the client bundle — so the
 * branch not taken is eliminated rather than guarded, and neither bundle carries a reference to
 * a global it does not have.
 *
 * Browser: same-origin `/api`, which `src/routes/api.$.ts` forwards to the Hono API in dev and
 * in production alike. Server: the loopback origin directly, no hop.
 */
const API_BASE = import.meta.env.SSR
  ? (import.meta.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:8789')
  : `${window.location.origin}/api`

export const client = hc<AppType>(API_BASE)

export type ReportPayload = InferResponseType<(typeof client.reports)[':reportId']['$get'], 200>
export type Scores = ReportPayload['scores']
export type TeamRow = ReportPayload['team'][number]
export type Citation = ReportPayload['citations'][number]
export type Blocker = ReportPayload['blockers'][number]
export type Bounds = ReportPayload['bounds']

export type CoinRows = InferResponseType<typeof client.coins.$get, 200>['rows']

type JsonOf<T> = T extends { json: infer J } ? J : never

export type ProductBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['product']['$patch']>
>
export type LiquidityBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['liquidity']['$patch']>
>
export type NarrativeBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['narrative']['$patch']>
>
export type AccrualBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['accrual']['$patch']>
>
export type RiskBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['risk']['$patch']>
>
export type TeamBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['team']['$put']>
>
export type CitationBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['citations']['$post']>
>

/** A section's fields, with the CAS token removed — the editor never chooses it. */
export type Fields<T> = Omit<T, 'version'>

export interface ApiError {
  code: string
  message: string
  actualVersion?: number
}

/**
 * The refusal, in the shape every route's `onError` and validator hook produce.
 *
 * Never throws: a failed save must always end with something legible beside the Save button, and
 * "the server said something I could not parse" is legible.
 */
export async function readError(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return { code: 'UNREADABLE', message: `HTTP ${response.status} with no JSON body` }
  }
  const record = body as Record<string, unknown>
  const code = typeof record.code === 'string' ? record.code : `HTTP_${response.status}`
  const message =
    typeof record.message === 'string' ? record.message : `the server refused it (${code})`
  const actualVersion = typeof record.actualVersion === 'number' ? record.actualVersion : undefined
  return actualVersion === undefined ? { code, message } : { code, message, actualVersion }
}
```

**`window.location.origin` at module scope is a bug under Start, not a style point.** Start evaluates this module on the server, where `window` is undefined, and the SPA draft's version crashed the first render. `import.meta.env.SSR` is better than a runtime `typeof window` guard: Vite replaces it with a literal per environment, so the dead branch is eliminated and neither bundle carries a reference to a global it lacks.

Two names for one origin, and it is deliberate: `VITE_API_ORIGIN` is read at **build** time and reaches the client bundle if it is ever set; `COINPICKS_API_ORIGIN` in `routes/api.$.ts` is read at **run** time, in the process. This plan gives no route a `loader`, so nothing on the server ever calls `client` at all — the SSR branch exists so the module can be *evaluated* there, not so it can be *used* there.

- [ ] **Step 6: The router and the shell route**

Create `apps/web/src/router.tsx`:

```tsx
import { createRouter } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'

// `getRouter`, not a module-level `router`: TanStack Start calls this once per REQUEST on the
// server, and a shared instance would leak one render's loaded data into the next. The name is
// the convention Start's plugin looks for in `src/router.tsx`.
//
// `routeTree.gen.ts` is generated by the Start plugin from `src/routes/`, and is excluded from
// biome by one pattern in the repo-root biome.json — the same arrangement the sibling repo runs.
//
// LINE comments, not a block comment. That biome pattern is `!` then `**` then `/routeTree...`,
// and the `*` `/` in the middle of it closes a `/*` block early: `vite build` reported
// "Unterminated string" at this line with the paragraph written the other way.
export function getRouter() {
  return createRouter({
    routeTree,
    scrollRestoration: true,
    defaultPreload: 'intent',
  })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof getRouter>
  }
}
```

The import of `./routeTree.gen` is **extensionless on purpose** — it is the generator's own spelling, and it resolves because `moduleResolution` is `bundler` (Step 2). Do not "fix" it to `./routeTree.gen.ts`; the next `vite build` writes it back.

Create `apps/web/src/routes/__root.tsx`:

```tsx
import { createRootRoute, HeadContent, Scripts } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import appCss from '../styles.css?url'

/*
 * THE BOUNDARY RULE, stated where it is easiest to break.
 *
 * This file runs on the SERVER as well as in the browser. It therefore has, and must keep
 * having: no `loader`, no `beforeLoad`, no `createServerFn`, no `fetch`, and no import of
 * `@coinpicks/api` as a value. The renderer holds no key and calls no third party; the only
 * process allowed to do either is the Hono API. `boundary.test.ts` asserts each of those five
 * words is absent from this file, because "we did not add one" is not a guarantee.
 */
export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'CoinPicks' },
    ],
    links: [{ rel: 'stylesheet', href: appCss }],
  }),
  shellComponent: RootDocument,
})

function RootDocument({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body className="bg-white text-neutral-900">
        {children}
        <Scripts />
      </body>
    </html>
  )
}
```

`shellComponent` — not `component` plus a hand-written `<html>` — is the 1.168 convention, and the sibling repo uses the same.

- [ ] **Step 7: The three route files**

Create `apps/web/src/routes/index.tsx`:

```tsx
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { type ApiError, type CoinRows, client, readError } from '../lib/client.ts'

/*
 * NO `loader`, and no `beforeLoad`.
 *
 * The list is fetched in an effect, in the BROWSER. A loader runs on the server first, and the
 * server half of this tier is the one place that must not start reaching outwards: it holds no
 * key and calls no third party, and `boundary.test.ts` is written to keep it that way. Step 4 has
 * no SEO and no first-paint data requirement, so a loader would buy nothing and cost the rule.
 */
export const Route = createFileRoute('/')({ component: CoinList })

const EMPTY_FORM = {
  symbol: '',
  name: '',
  chain: '',
  contractAddress: '',
  coingeckoId: '',
  addressSources: '',
}

function CoinList() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<CoinRows | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const response = await client.coins.$get()
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const body = await response.json()
    setRows(body.rows)
    setError(null)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const startReport = async (coinId: string) => {
    setBusy(true)
    const response = await client.reports.$post({ json: { coinId } })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const body = await response.json()
    await navigate({ params: { reportId: body.report.id }, to: '/reports/$reportId' })
  }

  const createCoin = async () => {
    setBusy(true)
    const response = await client.coins.$post({
      json: {
        symbol: form.symbol,
        name: form.name,
        chain: form.chain,
        contractAddress: form.contractAddress.trim() === '' ? null : form.contractAddress,
        coingeckoId: form.coingeckoId.trim() === '' ? null : form.coingeckoId,
        addressSources: form.addressSources
          .split(/[\s,]+/)
          .map((source) => source.trim())
          .filter((source) => source !== ''),
      },
    })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    setForm(EMPTY_FORM)
    await load()
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-medium">CoinPicks</h1>
      {error === null ? null : (
        <p className="mt-3 border-l-4 border-red-700 bg-red-50 py-1 pl-2 text-sm text-red-900">
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}

      <table className="mt-6 w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-400">
            <th className="py-1">Coin</th>
            <th>Chain</th>
            <th>Report</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(rows ?? []).map((row) => (
            <tr
              className="border-b border-neutral-200"
              key={`${row.coin.id}:${row.reportId ?? ''}`}
            >
              <td className="py-1">
                {row.coin.symbol} — {row.coin.name}
              </td>
              <td>{row.coin.chain}</td>
              <td>
                {row.reportId === null ? (
                  <span className="text-neutral-500">none</span>
                ) : (
                  <Link
                    className="underline"
                    params={{ reportId: row.reportId }}
                    to="/reports/$reportId"
                  >
                    open
                  </Link>
                )}
              </td>
              <td>{row.reportStatus ?? '—'}</td>
              <td>
                <button
                  className="border border-neutral-500 px-2 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void startReport(row.coin.id)}
                  type="button"
                >
                  new draft
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="mt-10 border-t border-neutral-300 pt-4">
        <h2 className="text-lg font-medium">Add a coin</h2>
        <p className="mt-1 text-sm text-neutral-600">
          A contract address needs at least two independent sources — the database refuses one.
          Leave the address blank for a native asset.
        </p>
        <div className="mt-3 grid max-w-2xl grid-cols-2 gap-2 text-sm">
          {(
            [
              ['symbol', 'Ticker'],
              ['name', 'Project name'],
              ['chain', 'Chain'],
              ['contractAddress', 'Contract address'],
              ['coingeckoId', 'CoinGecko id'],
              ['addressSources', 'Address source URLs'],
            ] as const
          ).map(([key, label]) => (
            <label className="flex flex-col gap-1" key={key}>
              <span className="text-neutral-700">{label}</span>
              <input
                className="border border-neutral-400 px-2 py-1"
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                value={form[key]}
              />
            </label>
          ))}
        </div>
        <button
          className="mt-3 border border-neutral-500 px-3 py-1 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void createCoin()}
          type="button"
        >
          Add coin
        </button>
      </section>
    </main>
  )
}
```

Create `apps/web/src/routes/api.$.ts` — **the one outbound request in the whole web tier**:

```ts
import { createFileRoute } from '@tanstack/react-router'

/*
 * THE ONE HOP TO THE API, IN DEV AND IN PRODUCTION.
 *
 * A Vite `server.proxy` on `/api` would work in dev and would not exist in a built app, leaving
 * the shipped hop untested -- measured: with a proxy configured and pointed at a dead port,
 * `/api/health` returned 502 rather than falling through to this route, so in dev the route
 * would never run at all. A Start server route runs in both, so there is one path, not two.
 *
 * It is the ONE place in apps/web where the server makes an outbound request, and the boundary
 * rule survives it for one reason only — the target is this machine's own API on loopback, built
 * from an origin this process is configured with. It never takes a URL from the request, from a
 * report, or from a citation. Fetching a third-party URL is the citation verifier's job in
 * build-order step 5 and it belongs to apps/api, which is the tier that holds keys.
 */
const API_ORIGIN = process.env.COINPICKS_API_ORIGIN ?? 'http://127.0.0.1:8789'

async function forward({ request }: { request: Request }): Promise<Response> {
  const url = new URL(request.url)
  const target = `${API_ORIGIN}${url.pathname.replace(/^\/api/, '')}${url.search}`
  const response = await fetch(target, {
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
    // `manual`, so a redirect reaches the BROWSER. hono's proxy default is `follow`, which
    // resolves the chain in this process and drops both the Location and any Set-Cookie on it.
    // The sibling repo shipped that bug and only found it in production.
    headers: request.headers,
    method: request.method,
    redirect: 'manual',
    // Required by undici whenever a body is a stream, and a PATCH body is.
    ...{ duplex: 'half' },
  })
  return new Response(response.body, {
    headers: response.headers,
    status: response.status,
    statusText: response.statusText,
  })
}

export const Route = createFileRoute('/api/$')({
  server: {
    handlers: {
      DELETE: forward,
      GET: forward,
      PATCH: forward,
      POST: forward,
      PUT: forward,
    },
  },
})
```

`createFileRoute(...)({ server: { handlers } })` is the 1.168 spelling. `createAPIFileRoute` is the older one and is not what this version exports.

And a stub so the route exists and `<Link to="/reports/$reportId">` has something to type against — Task 5 replaces this file entirely. Create `apps/web/src/routes/reports.$reportId.tsx`:

```tsx
import { createFileRoute } from '@tanstack/react-router'

/*
 * A stub, so the route exists and the generated tree has something to type `<Link to=...>`
 * against. Task 5 replaces this file entirely.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportEditor })

function ReportEditor() {
  const { reportId } = Route.useParams()
  return <main className="mx-auto max-w-5xl p-6">The editor for {reportId} lands in Task 5.</main>
}
```

**A warning for anyone scripting this file's creation:** the filename contains `$reportId`. In a shell heredoc that is a variable, and an unescaped `cat > src/routes/reports.$reportId.tsx` produces `reports..tsx`, a `/reports/` route, and a `Route.useParams()` typed `{}` — with everything still compiling. Escape the `$`, or write the file with an editor.

- [ ] **Step 8: The production host**

`vite build` under Start does **not** emit a server. It emits `dist/server/server.js`, which default-exports `{ fetch }` and nothing else, plus `dist/client/` as files. These are the twenty lines that host them. Create `apps/web/scripts/serve.ts`:

```ts
import { serve } from '@hono/node-server'
import { serveStatic } from '@hono/node-server/serve-static'
import { Hono } from 'hono'
import ssr from '../dist/server/server.js'

/*
 * The web tier in production: the assets first, everything else -- pages AND the `/api/$` route
 * -- through the SSR handler.
 *
 * Deliberately OUTSIDE apps/web/tsconfig.json's `include`: it imports ../dist/server/server.js,
 * which does not exist until `vite build` has run, so `tsc --noEmit` on a clean checkout would
 * fail on a file that is never executed unbuilt.
 */
const PORT = Number(process.env.PORT ?? 3000)

const app = new Hono()
  .use('/assets/*', serveStatic({ root: './dist/client' }))
  .all('*', (c) => ssr.fetch(c.req.raw))

serve({ fetch: app.fetch, hostname: '127.0.0.1', port: PORT }, (info) => {
  console.log(`coinpicks web on http://127.0.0.1:${info.port}`)
})
```

This is the one `Number()` call anywhere in `apps/web`, and it is legal because `boundary.test.ts` scans `src/` and this file is not under it — and because a port read from the process's own environment is not operator input on the wire. The no-`Number()` rule stands unchanged for everything under `src/`.

- [ ] **Step 9: The two guards**

Create `apps/web/src/boundary.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/*
 * THE TIER BOUNDARY, ENFORCED MECHANICALLY — the SOURCE half.
 *
 * `bundle.test.ts` reads the built output; this reads the source. Both are needed and neither
 * replaces the other: a source scan names the offending line, and only a bundle scan can catch a
 * leak that arrives through a dependency nobody typed.
 *
 * Measured, not assumed, against a real build of this tree: with `import type { AppType } from
 * '@coinpicks/api'` the client bundle is 583,379 bytes and carries no ORM. Changing that one line
 * to `import { type AppType, createApp } from '@coinpicks/api'` plus one value use makes it
 * 727,230 bytes, with this project's table and constraint names in it. Biome's useImportType does
 * not fire on the mixed form and tsc under verbatimModuleSyntax accepts it.
 *
 * Three signals fire on that slip, in this order: the Start plugin's importProtection fails the
 * BUILD (vite.config.ts), this test names the line, and bundle.test.ts reads dist/client. This
 * one is the signal that survives someone turning the first one off.
 *
 * The second rule is the arithmetic ban. The frozen formulas are evaluated in exactly one place
 * and apps/web is not it, so no rubric bound is written here at all — every maximum, threshold
 * and vocabulary arrives in the report payload as `bounds`.
 *
 * Comments are blanked before scanning and test files are skipped, so the prose above (which
 * names every banned construct on purpose) does not indict itself.
 */

const SRC = dirname(fileURLToPath(import.meta.url))

/** Replaces comment bodies with spaces, keeping every line number intact. */
function stripComments(source: string): string {
  const blank = (text: string) => text.replace(/[^\n]/g, ' ')
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + blank(match.slice(lead.length)))
}

interface SourceFile {
  path: string
  lines: string[]
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    if (!/\.tsx?$/.test(path)) return []
    if (path.endsWith('.test.ts')) return []
    // The generated route tree is an OUTPUT of the files this scan already reads, and it is
    // excluded from biome for the same reason.
    if (path.endsWith('routeTree.gen.ts')) return []
    return [path]
  })
}

const FILES: SourceFile[] = sourceFiles(SRC).map((path) => ({
  path: path.slice(SRC.length + 1),
  lines: stripComments(readFileSync(path, 'utf8')).split('\n'),
}))

function offenders(pattern: RegExp, only?: (file: SourceFile) => boolean): string[] {
  return FILES.filter((file) => only === undefined || only(file)).flatMap((file) =>
    file.lines
      .map((line, index) => ({ line, number: index + 1 }))
      .filter((entry) => pattern.test(entry.line))
      .map((entry) => `${file.path}:${String(entry.number)} ${entry.line.trim()}`),
  )
}

/** Everything but the one route that is allowed to make an outbound loopback request. */
const RENDERER = (file: SourceFile): boolean => file.path !== join('routes', 'api.$.ts')

describe('the web tier cannot reach the api tier at runtime', () => {
  it('scans every source file', () => {
    // Six at the end of Task 4 — router, lib/client, routes/__root, routes/index,
    // routes/reports.$reportId, routes/api.$ — and fifteen once Task 7 lands. The bound is the
    // lower number on purpose: this case exists to stop the scan passing because it matched
    // nothing, not to count the tree.
    expect(FILES.length).toBeGreaterThanOrEqual(6)
  })

  it('imports @coinpicks/api only with `import type`', () => {
    const found = FILES.flatMap((file) =>
      file.lines
        .map((line, index) => ({ line, number: index + 1 }))
        .filter(
          (entry) =>
            entry.line.includes("'@coinpicks/api'") &&
            !entry.line.trimStart().startsWith('import type '),
        )
        .map((entry) => `${file.path}:${String(entry.number)} ${entry.line.trim()}`),
    )
    expect(
      found,
      'a value import of @coinpicks/api ships the ORM and the DDL to the browser',
    ).toEqual([])
  })

  it('imports no node builtin, no driver and no ORM', () => {
    expect(offenders(/from '(node:[a-z/]+|pg|drizzle-orm[a-z/-]*)'/)).toEqual([])
  })
})

describe('the renderer never fetches', () => {
  it('has exactly one file allowed to make an outbound request', () => {
    expect(offenders(/\bfetch\(/, RENDERER)).toEqual([])
  })

  it('declares no loader, beforeLoad or server function in the shell', () => {
    const root = FILES.find((file) => file.path === join('routes', '__root.tsx'))
    expect(root, 'routes/__root.tsx is gone or was renamed').toBeDefined()
    const shell = (root?.lines ?? []).join('\n')
    for (const forbidden of ['loader', 'beforeLoad', 'createServerFn', 'fetch(', 'ssr:']) {
      expect(shell, `__root.tsx must not declare ${forbidden}`).not.toContain(forbidden)
    }
  })

  it('points the one proxy at an origin this process configures, never at a request URL', () => {
    const proxy = FILES.find((file) => file.path === join('routes', 'api.$.ts'))
    expect(proxy, 'routes/api.$.ts is gone or was renamed').toBeDefined()
    const source = (proxy?.lines ?? []).join('\n')
    expect(source).toContain("process.env.COINPICKS_API_ORIGIN ?? 'http://127.0.0.1:8789'")
    // Built from API_ORIGIN and the request's PATH only. Asserted in three pieces rather than as
    // one template literal, which biome reads as a placeholder in a plain string.
    expect(source).toContain('const target = ')
    expect(source).toContain('API_ORIGIN')
    expect(source).toContain('url.pathname.replace')
    expect(source, 'the proxy target must never come from the request body').not.toContain(
      'await request.json()',
    )
  })
})

describe('the web tier does no rubric arithmetic', () => {
  it('writes no bare rubric number', () => {
    expect(
      offenders(/(?<![\w.$-])(16|31)(?![\w.%-])/),
      'a rubric bound is written in apps/web instead of arriving in `bounds`',
    ).toEqual([])
  })

  it('never calls Number() on operator input', () => {
    expect(
      offenders(/(?<![\w.$])Number\(/),
      'apps/web parses a number instead of sending the string the operator typed',
    ).toEqual([])
  })
})
```

Create `apps/web/src/bundle.test.ts`:

```ts
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/*
 * THE BUNDLE SCAN. TanStack Start emits TWO bundles and only one of them is the browser's:
 *
 *   apps/web/dist/client/assets/*.js   <- served as files; this is what a browser downloads
 *   apps/web/dist/server/**\/*.js      <- the SSR fetch handler; runs in node
 *
 * The directory is NAMED here rather than globbed loosely, because the obvious wrong answer
 * passes silently. The command a plain-Vite SPA would use --
 * `grep -c -e drizzle dist/assets/index-*.js || true` -- run against a Start build prints
 * "grep: dist/assets/index-*.js: No such file or directory" and, with the `|| true`, the
 * pipeline EXITS 0. That is a guard reporting success having read zero bytes. Both the existence
 * of each directory and a byte floor are asserted below so that cannot happen quietly.
 *
 * `apps/web`'s `test` script runs `vite build` before vitest for the same reason: a scan of a
 * dist left over from an earlier source tree is the same failure wearing a different hat.
 */

const WEB = dirname(dirname(fileURLToPath(import.meta.url)))
const CLIENT = join(WEB, 'dist', 'client')
const SERVER = join(WEB, 'dist', 'server')

/*
 * NEEDLES THAT SURVIVE MINIFICATION.
 *
 * This list was written wrong first and the mistake is the reason it is spelled out. With a real
 * leak in place, the built client chunk contains
 *
 *   drizzle: x15   PgTable x1   PgColumn x2   report_scores x1   rs_gate x1
 *   drizzle-orm x0   pg-protocol x0   node:crypto x0   DATABASE_URL x0   coinpicks_app x0
 *
 * The module SPECIFIER is gone -- rolldown rewrote it -- and the `pg` driver never arrives at
 * all, because `db/client.ts` reaches apps/web only as a type. What survives is the string
 * literals drizzle builds its class registry from (`Symbol.for('drizzle:entityKind')`) and, more
 * to the point, the DDL: this project's table and constraint names, in the browser, for anyone
 * to read. So `pg-protocol`, `node:crypto`, `DATABASE_URL` and `coinpicks_app` are kept as
 * belt-and-braces and are NOT what catches this.
 */
const FORBIDDEN = [
  'drizzle:',
  'PgTable',
  'PgColumn',
  'report_scores',
  'rs_gate',
  'pg-protocol',
  'DATABASE_URL',
  'coinpicks_app',
] as const

/*
 * The client bundle's ceiling, in characters as `readFileSync(..., 'utf8').length` counts them --
 * which is a few dozen fewer than `dist` on disk, and the same either way.
 *
 * The needle list catches what it knows to look for; this catches the rest. Measured on the Task 4
 * tree: clean 583,321, and a value import of `@coinpicks/api` 719,045 -- with `vite build` exiting
 * 0 and silent either way once importProtection is off. The SPA draft of this plan grew its own
 * tree by about 36 kB between Task 4 and Task 7, so 660,000 sits roughly 40,000 above a clean
 * finished tree and 59,000 below a leaking one.
 *
 * Raise it deliberately, in the commit that makes the app bigger, with the measured number
 * written into this comment -- and never to make a red test green.
 */
const CLIENT_CHAR_CEILING = 660_000

function jsFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return jsFiles(path)
    return /\.m?js$/.test(path) ? [path] : []
  })
}

function scan(directory: string): { files: number; characters: number; hits: string[] } {
  const files = jsFiles(directory)
  const hits: string[] = []
  let characters = 0
  for (const path of files) {
    const source = readFileSync(path, 'utf8')
    characters += source.length
    for (const needle of FORBIDDEN) {
      const count = source.split(needle).length - 1
      if (count > 0) hits.push(`${relative(WEB, path)}: ${needle} x${String(count)}`)
    }
  }
  return { characters, files: files.length, hits }
}

describe('the built client bundle', () => {
  it('exists, which means `vite build` ran', () => {
    expect(existsSync(CLIENT), `${relative(WEB, CLIENT)} is missing -- run \`pnpm build\``).toBe(
      true,
    )
    expect(existsSync(SERVER), 'dist/server is missing, so this is not a Start build').toBe(true)
  })

  it('is big enough to be a real bundle, so a clean scan means something', () => {
    const { files, characters } = scan(CLIENT)
    expect(files).toBeGreaterThanOrEqual(2)
    expect(characters).toBeGreaterThan(200_000)
  })

  it('carries no ORM, no schema, no driver and no connection string', () => {
    expect(scan(CLIENT).hits).toEqual([])
  })

  it('has not silently grown by the size of a dependency nobody meant to ship', () => {
    expect(scan(CLIENT).characters).toBeLessThan(CLIENT_CHAR_CEILING)
  })
})

describe('the built server bundle', () => {
  it('carries no ORM, no schema and no connection string either', () => {
    // The renderer is not the tier that holds a database handle; apps/api is. A value import used
    // only inside a createServerFn body leaves the CLIENT bundle spotless and lands here instead
    // -- measured on the Task 4 tree: client 587,978 bytes with ZERO needles and comfortably under
    // the ceiling, while dist/server carries drizzle: x15, PgTable x6, PgColumn x88,
    // report_scores x2, rs_gate x1. This case is the only one that sees it.
    expect(scan(SERVER).hits).toEqual([])
  })
})
```

The arithmetic cases and half the renderer cases are dead weight until Tasks 5–7 add the code they guard; they are written now because a guard has to exist before the code it guards, not after.

- [ ] **Step 10: Make `pnpm dev` start both apps**

The root `dev` script names the api package only, so the setup sequence would have started one process and then curled a port nothing was listening on. In `/home/dev/projects/trade-god/package.json` replace

```json
    "dev": "pnpm --filter @coinpicks/api --parallel run dev",
```

with

```json
    "dev": "pnpm --parallel --if-present run dev",
```

- [ ] **Step 11: Generate the tree, compile, build, and measure BOTH bundles**

The build comes first, because it is what writes `routeTree.gen.ts` — until it has run once, `tsc` has no route tree to compile and `Route.useParams()` has no route to be typed against.

```bash
cd /home/dev/projects/trade-god/apps/web
pnpm build
pnpm typecheck
pnpm test
```
Expected, in that order. `pnpm build` reports two environments and writes the tree:

```
vite v8.3.0 building client environment for production...
dist/client/assets/styles-*.css              7.42 kB
dist/client/assets/reports._reportId-*.js    0.50 kB
dist/client/assets/rolldown-runtime-*.js     0.58 kB
dist/client/assets/routes-*.js              10.57 kB
dist/client/assets/jsx-dev-runtime-*.js     44.84 kB
dist/client/assets/index-*.js              526.86 kB
vite v8.3.0 building ssr environment for production...
dist/server/server.js                      238.39 kB
```

with rolldown's generic "some chunks are larger than 500 kB" note, which is React plus the router and is expected. Exact totals for **this task's** tree, measured: **`dist/client` 5 JS files, 583,379 bytes** plus a 7,427-byte stylesheet, and **`dist/server` 254,704 bytes**. Tailwind scans the source for class names and Task 5 replaces the stub with the real editor, so both grow through Tasks 5–7.

`pnpm typecheck` is silent in about two seconds. `pnpm test` rebuilds (about a second) and reports **`Test Files 2 passed`, `Tests 13 passed`** — eight boundary cases and five bundle cases, over the six source files this task leaves behind (`router.tsx`, `lib/client.ts`, `routes/__root.tsx`, `routes/index.tsx`, `routes/reports.$reportId.tsx`, `routes/api.$.ts`). `styles.css` does not match `/\.tsx?$/`, the two test files exclude themselves, and `routeTree.gen.ts` is excluded by name — which is why the scan's floor is `toBeGreaterThanOrEqual(6)` and not `toBeGreaterThan(6)`.

Then the measurement that matters, by hand, against the directory a browser actually downloads:

```bash
grep -c -e 'drizzle:' -e PgTable -e report_scores -e rs_gate -e pg-protocol dist/client/assets/*.js; echo "grep exit=$? (1 means NO match, which is the passing case)"
grep -rc -e 'drizzle:' -e PgTable -e report_scores dist/server --include='*.js'
```
Expected: `0` on every line of both.

**Do not carry over the SPA draft's version of this command.** `grep -c ... dist/assets/index-*.js || true` reads a directory a Start build does not create; measured here, it prints `grep: dist/assets/index-*.js: No such file or directory` and the `|| true` makes the pipeline **exit 0 having matched nothing**. The needles changed too: in a bundle with a real leak, `drizzle-orm`, `pg-protocol` and `node:crypto` are all **0** — rolldown rewrites the module specifier away and the `pg` driver never arrives at all, because `apps/api` imports its pool as a type. What survives minification is `Symbol.for('drizzle:entityKind')` and this project's own DDL strings.

- [ ] **Step 12: Break the boundary on purpose — three ways — and put it back**

This is the finding that cannot be checked by reading, and under Start it has three parts. Do all three.

**(a) The slip fails the build.** In `apps/web/src/lib/client.ts`, temporarily change the first line to

```ts
import { type AppType, createApp } from '@coinpicks/api'
```

and add, directly above the `export const client` line,

```ts
export const leak = createApp
```

Then `pnpm build`. Expected: **exit non-zero**, no bundle, and this, verbatim:

```
vite v8.3.0 building client environment for production...
✗ Build failed in 269ms
error during build:
[plugin tanstack-start-core:import-protection]
[import-protection] Import denied in client environment

  Denied by specifier pattern: @coinpicks/api
  Importer: src/lib/client.ts:30:21
  Import: "@coinpicks/api"
  Resolved: /home/dev/projects/trade-god/apps/api/src/app.ts

  Trace:
    1. src/router.tsx:2:27 (entry) (import "./routeTree.gen")
    2. src/routeTree.gen.ts:7:53 (import "./routes/reports.$reportId")
    3. src/routes/reports.$reportId.tsx:3:70 (import "../lib/client.ts")
    4. src/lib/client.ts:30:21 (import "@coinpicks/api")
```

**(b) With the guard off, the build is silent — and the tests are not.** Temporarily set `enabled: false` in `vite.config.ts`'s `importProtection`, then `pnpm build && pnpm test`. Expected: `vite build` **exits 0 with no error and no warning about the leak**, the client bundle grows from 583,379 to **727,230 bytes**, and four cases fail:

```
FAIL boundary.test.ts > imports @coinpicks/api only with `import type`
  + [ "lib/client.ts:1 import { type AppType, createApp } from '@coinpicks/api'" ]
FAIL bundle.test.ts > carries no ORM, no schema, no driver and no connection string
  + [ "dist/client/assets/routes-*.js: drizzle: x15", "…: PgTable x1", "…: PgColumn x2",
      "…: report_scores x1", "…: rs_gate x1" ]
FAIL bundle.test.ts > has not silently grown by the size of a dependency nobody meant to ship
  AssertionError: expected 727172 to be less than 660000
FAIL bundle.test.ts > the built server bundle > carries no ORM, no schema and no connection string
```

`report_scores` and `rs_gate` are this project's own table and constraint names, minified into a file a browser downloads. `drizzle-orm`, `pg-protocol` and `node:crypto` are all **0** in that same file — which is why the needle list looks the way it does.

Biome says nothing: `useImportType` only fires when *every* binding in the specifier is type-only, and tsc under `verbatimModuleSyntax` accepts the mixed form. **Revert the `client.ts` edits**, leave `enabled: false` for (c).

**(c) The client-only scan is the one that would have lied.** Now put the value import somewhere a Start build moves off the browser. In `apps/web/src/routes/index.tsx`, temporarily add

```tsx
import { createServerFn } from '@tanstack/react-start'
import { createApp } from '@coinpicks/api'

const probe = createServerFn().handler(() => typeof createApp)
```

and a `void probe` inside `CoinList`. Then `pnpm build && pnpm test`. Expected — and this is the whole reason `bundle.test.ts` scans two directories:

```
client bundle  587,978 bytes -- clean 583,379 plus a 4.6 kB RPC stub, and ZERO ORM needles
server bundle  dist/server/assets/routes-*.js: drizzle: x15, PgTable x6, PgColumn x88,
                                               report_scores x2, rs_gate x1
client scan    PASS        byte ceiling   PASS
source scan    FAIL        server scan    FAIL
Tests  2 failed | 11 passed (13)
```

Then set `enabled: true` back and run `pnpm build` once more. Expected: the SSR environment now fails too, exit non-zero — but the diagnostic is poor, and knowing that in advance is the point of doing this:

```
vite v8.3.0 building ssr environment for production...
✗ Build failed in 196ms
[MISSING_EXPORT] "createApp" is not exported by "\0tanstack-start-import-protection:mock-edge:…"
   ╭─[ src/routes/index.tsx?tss-serverfn-split:3:10 ]
```

It fails, which is what matters; it does not say "import denied" the way the client environment does. Note also that the **client** environment builds first and succeeds, so a failed build can still leave a `dist/client` on disk — which is the second reason `pnpm test` builds before it scans.

Revert every edit from (a), (b) and (c), then `pnpm test` and see `Tests 13 passed`.

- [ ] **Step 13: Run the two servers together**

```bash
cd /home/dev/projects/trade-god && pnpm dev
```
In another shell:
```bash
curl -s http://127.0.0.1:8789/health
curl -s http://localhost:5173/api/health
```
Expected: the same `{"ok":true,"migrations":4,"scoringVersion":"coinpicks-2026-09-21"}` from both — the first proves the API, the second proves `routes/api.$.ts`, which is the same code the production build runs. Open `http://localhost:5173/`, add a coin, and press "new draft"; the stub editor says which task fills it in.

If `vite dev` exits with `Error: Port 5173 is already in use`, that is `strictPort` doing its job — something else holds the port (on this machine, the sibling repo's dev server). Stop it or move this one; do **not** let Vite pick 5174 silently and then curl 5173.

If the api instead exits with `4 migrations are committed but 5 are applied`, a migration was applied outside the migrator and `drizzle.__drizzle_migrations` has a duplicate. Delete the row whose `hash` is not one of the four `.sql` files' sha256 and start again; Task 1 Step 7 applies `0003` through the migrator precisely so this cannot happen.

The built app can be checked the same way, and should be at least once:

```bash
cd /home/dev/projects/trade-god/apps/web && pnpm build && pnpm start
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/
curl -s http://127.0.0.1:3000/api/health
```
Expected: `200` and the same health JSON — the page server-rendered, and the `/api` hop working outside dev. (`vite preview` serves the whole thing too, including `/api/*`; it is a quick check, not a production host.)

- [ ] **Step 14: Green, then commit**

```bash
cd /home/dev/projects/trade-god && pnpm -r run typecheck && pnpm -r run test
pnpm check --write && pnpm check
```
Expected: Biome `No fixes applied.` and exit 0. Check the file count it prints against a run with the Step 3 exclusion removed: it must be exactly **one lower**, and the removed run must **exit 1** on `routeTree.gen.ts:11`. That pair is the check; the absolute number is whatever `apps/api` plus `apps/web` add up to on the day. `git status` must also show `apps/web/src/routeTree.gen.ts` as a file to be **added** — it is generated, it is committed, and `.gitignore` does not list it.

```bash
git add -A
git commit -m "feat: apps/web -- TanStack Start, one loopback hop, and a two-sided boundary guard

The tsconfig overrides five keys, not one: the base sets module: nodenext, so
moduleResolution: bundler alone is TS5095 + TS5109. bundler is also what lets
the generated route tree's extensionless imports resolve.

routeTree.gen.ts is committed and excluded from biome by one line, because it is
generated -- the same arrangement the sibling repo runs. Measured: exit 1 without
the exclusion (organizeImports at routeTree.gen.ts:11) and exit 0 with it, over one
file fewer, and the file is byte-identical across biome check --write and the next
vite build.

Two guards, because Start emits two bundles. boundary.test.ts reads the source;
bundle.test.ts reads dist/client AND dist/server. A value import used only inside
a createServerFn leaves the client bundle spotless and puts drizzle plus this
project's DDL in dist/server, so a client-only grep passes on it -- measured.
importProtection fails the build on both, which is the thing plain Vite could not
have done at all."
```

---
### Task 5: The editor shell and the section-save model

The owner's second ruling of 2026-09-21: **one Save button per section**, sending that section's fields as one patch under one CAS bump. Not save-on-blur.

`casBumpVersion` bumps `reports.version` on every successful call — its own docblock says a client's token is good for exactly one write. The naive per-field blur save therefore fires many CAS writes at typing speed: blur a score, click a citation's "add" before the first response lands, and the second request carries a spent token and comes back 409 while the screen still shows the value as entered. Sections mark themselves dirty so the operator can see there is something unsaved.

The second half of the model is what happens on a conflict. The naive editor seeded every input with `useState(value)` and never re-synced; React applies a `useState` initial value only on mount, and the editor is one route with stable component identity, so re-fetching after a 409 updated the data and left the boxes showing the losing text — one blur away from writing it over the winner. Here each section is a component keyed on a per-section **seed token**: a successful save bumps only that section's token, so a sibling's unsaved text survives; a 409 bumps **every** token, re-reads, and says in a banner that unsaved text was discarded. A remount cannot re-apply a pre-conflict value.

Two consequences of that mechanism are built into `runSave` rather than left to be discovered:

- **A 409 reports through the BANNER, not through the section.** Bumping the seeds changes each section's `key`, which unmounts the component the save was started from, so `useSection`'s `setError(refusal)` lands on an instance that is being replaced and the red per-section message never appears. `ReportEditor` is not keyed, so the banner is the only thing on the page that survives the remount — and it therefore carries the refusal's code and message verbatim.
- **A citation write bumps NO seed.** `runSave`'s section is `SectionKey | null` and the citation callbacks pass `null`. Hard-coding `'product'` there — the obvious thing to write, since `Citations` first appears in the product gate — means attaching evidence anywhere on the page silently discards unsaved product-gate text, which is finding 6 turned inside out. The new row reaches `<Citations>` through the `citations` prop that `load()` refreshed; nothing needs to remount.

**Files:**
- Create: `apps/web/src/editor/fields.tsx`
- Create: `apps/web/src/editor/common.tsx`
- Create: `apps/web/src/editor/ProductSection.tsx`
- Create: `apps/web/src/editor/RiskSection.tsx`
- Modify: `apps/web/src/routes/reports.$reportId.tsx` (replaces the Task 4 stub entirely)

**Interfaces:**
- Consumes: everything `src/lib/client.ts` exports.
- Produces, from `editor/fields.tsx`: `blankToNull(text): string | null`, `textOf(value): string`, `numberOf(value): string`, `Row`, `TextField`, `WholeNumberField`, `AmountField`, `ProseField`, `ChoiceField`, `CheckField`, `interface MeasuredForm`, `isMeasuredEmpty(form): boolean`, `MeasuredFields`.
- Produces, from `editor/common.tsx`: `type Save<B> = (fields: Fields<B>) => Promise<ApiError | null>`, `interface SectionProps`, `SectionShell`, `useSection<F, B>(seed, toBody, save)`, `Citations`, `seedMeasured(value, source, url, label, measuredAt): MeasuredForm`, `type MeasuredWire`, `toMeasured(form): MeasuredWire | null`.
- Produces: `ProductSection`, `RiskSection`, `ReportEditor`.

- [ ] **Step 1: The input primitives**

Create `apps/web/src/editor/fields.tsx`:

```tsx
import type { ReactNode } from 'react'

/*
 * THE BROWSER NEVER CALLS Number().
 *
 * Every numeric box is a text input whose string goes on the wire exactly as typed. `Number`
 * turns 'seven', '1,000' and '7%' into NaN, `JSON.stringify` turns NaN into `null`, and `null` is
 * this API's "clear this field" — so a typo used to save cleanly, bump the CAS version, and empty
 * the column while the box still showed the typo. The server's zod owns the parse and answers a
 * bad string with a named 422.
 *
 * A blank box is the ONLY thing that becomes `null`, and that is an edit the operator can see
 * themselves making.
 */

export const blankToNull = (text: string): string | null => (text.trim() === '' ? null : text)

export const textOf = (value: string | null): string => value ?? ''

/**
 * A stored figure, seeded into its box.
 *
 * `String` is deliberate, and this is deliberately NOT an expansion of exponential notation.
 * Below 1e-6 and at or above 1e21 `String` switches to exponent form — `String(1e-7)` is
 * `'1e-7'` — which the API's digit regex refuses, so a figure that small has to be typed out in
 * full before that section will save again. That is loud, named and recoverable. Both cheaper
 * repairs are worse and were measured here: expanding the exponent in the browser needs
 * `Number(parts[3])`, which `boundary.test.ts` refuses by name, and `toFixed(20)` SILENTLY
 * rewrites 1.5e-20 as 0.00000000000000000002. The real fix is for the read path to serve
 * figures as text; it is written down for step 5 rather than half-done here.
 */
export const numberOf = (value: number | null): string => (value === null ? '' : String(value))

/** A labelled row. A <div> with an aria-label on the control, not a <label> wrapping
 *  {children}: biome's noLabelWithoutControl cannot see through children and fails the build. */
export function Row({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-3 py-1 text-sm">
      <span className="w-72 shrink-0 text-neutral-700">{label}</span>
      {children}
    </div>
  )
}

export function TextField({
  disabled,
  label,
  onChange,
  placeholder,
  value,
  width = 'w-96',
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  placeholder?: string
  value: string
  width?: string
}) {
  return (
    <Row label={label}>
      <input
        aria-label={label}
        className={`${width} border border-neutral-400 px-2 py-1 disabled:bg-neutral-100`}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </Row>
  )
}

/**
 * A whole-number sub-score. `type="text"`, not `type="number"`: a spinner cannot express 7.5, and
 * 7.5 is a value the API must be given the chance to REJECT rather than one the UI hides. The
 * maximum in the caption arrives in the report payload; no rubric number is written here.
 */
export function WholeNumberField({
  disabled,
  label,
  max,
  onChange,
  value,
}: {
  disabled: boolean
  label: string
  max: number
  onChange: (value: string) => void
  value: string
}) {
  return (
    <Row label={label}>
      <input
        aria-label={label}
        className="w-20 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        inputMode="numeric"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
      <span className="text-xs text-neutral-500">whole number, 0 to {max}</span>
    </Row>
  )
}

export function AmountField({
  caption,
  disabled,
  label,
  onChange,
  value,
}: {
  caption: string
  disabled: boolean
  label: string
  onChange: (value: string) => void
  value: string
}) {
  return (
    <Row label={label}>
      <input
        aria-label={label}
        className="w-48 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        inputMode="decimal"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
      <span className="text-xs text-neutral-500">{caption}</span>
    </Row>
  )
}

export function ProseField({
  disabled,
  label,
  onChange,
  value,
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  value: string
}) {
  return (
    <label className="flex flex-col gap-1 py-1 text-sm">
      <span className="text-neutral-700">{label}</span>
      <textarea
        className="border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        rows={2}
        value={value}
      />
    </label>
  )
}

export function ChoiceField({
  disabled,
  label,
  onChange,
  options,
  value,
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  options: readonly string[]
  value: string
}) {
  return (
    <Row label={label}>
      <select
        aria-label={label}
        className="border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </Row>
  )
}

export function CheckField({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean
  disabled: boolean
  label: string
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 py-1 text-sm">
      <input
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <span>{label}</span>
    </label>
  )
}

/** The five boxes of one measured figure. They move together or not at all. */
export interface MeasuredForm {
  value: string
  source: string
  url: string
  label: string
  measuredAt: string
}

export const isMeasuredEmpty = (form: MeasuredForm): boolean =>
  Object.values(form).every((entry) => entry.trim() === '')

/**
 * All five, or none.
 *
 * `rs_depth_provenance_complete` and its two siblings are biconditionals, so the wire carries one
 * object or `null` — five independent nullable fields could express a state the database refuses.
 * The naive version had a "Save figure with its provenance" button that called
 * `onSave({ value: Number(figure), ... })` with no blank guard, and `Number('')` is 0: a blank
 * figure box became "+/-2% depth = $0, verified, DefiLlama, 14:32", immutable after commit.
 * Here a blank figure is the empty string, and the server's `money()` refuses it by name.
 */
export function MeasuredFields({
  disabled,
  form,
  label,
  onChange,
  provenanceLabels,
}: {
  disabled: boolean
  form: MeasuredForm
  label: string
  onChange: (form: MeasuredForm) => void
  provenanceLabels: readonly string[]
}) {
  const set = (key: keyof MeasuredForm) => (next: string) => onChange({ ...form, [key]: next })
  return (
    <fieldset className="my-2 border border-neutral-300 p-3">
      <legend className="px-1 text-sm text-neutral-700">{label}</legend>
      <AmountField
        caption="digits, at most one decimal point"
        disabled={disabled}
        label="Figure (USD)"
        onChange={set('value')}
        value={form.value}
      />
      <TextField
        disabled={disabled}
        label="Source"
        onChange={set('source')}
        placeholder="CoinGecko, DefiLlama, ..."
        value={form.source}
      />
      <TextField
        disabled={disabled}
        label="Source URL"
        onChange={set('url')}
        placeholder="https://"
        value={form.url}
      />
      <ChoiceField
        disabled={disabled}
        label="Provenance"
        onChange={set('label')}
        options={provenanceLabels}
        value={form.label}
      />
      <TextField
        disabled={disabled}
        label="Measured at"
        onChange={set('measuredAt')}
        placeholder="2026-09-21T14:32:00+02:00"
        value={form.measuredAt}
        width="w-72"
      />
      <p className="mt-1 text-xs text-neutral-600">
        All five, or leave all five blank. The timestamp needs an offset and cannot be in the future
        — three CHECK constraints depend on it.
      </p>
    </fieldset>
  )
}
```
`Row` is a `<div>` with an `aria-label` on the control rather than a `<label>` wrapping `{children}`: biome's `lint/a11y/noLabelWithoutControl` cannot see a control that arrives through children, and it fails `pnpm check` as an **error**.

- [ ] **Step 2: The section shell, the save hook, and the evidence block**

Create `apps/web/src/editor/common.tsx`:

```tsx
import { type ReactNode, useState } from 'react'
import type {
  ApiError,
  Bounds,
  Citation,
  CitationBody,
  Fields,
  LiquidityBody,
  Scores,
} from '../lib/client.ts'
import { isMeasuredEmpty, type MeasuredForm, numberOf, textOf } from './fields.tsx'

export type Save<B> = (fields: Fields<B>) => Promise<ApiError | null>

export interface SectionProps {
  bounds: Bounds
  citations: Citation[]
  disabled: boolean
  onAddCitation: (input: Fields<CitationBody>) => Promise<ApiError | null>
  onRemoveCitation: (citationId: string) => Promise<ApiError | null>
  scores: Scores
}

/*
 * ONE SAVE BUTTON PER SECTION, sending that section's fields as one patch under one CAS bump.
 *
 * Ruled 2026-09-21. `casBumpVersion` bumps `reports.version` on every successful call, so the
 * naive per-field blur save fires many CAS writes: blur a score, click a citation's "add" before
 * the first response lands, and the second request carries a spent token and is refused 409 while
 * the screen still shows the value as entered.
 */
export function SectionShell({
  children,
  dirty,
  disabled,
  error,
  onSave,
  saving,
  title,
}: {
  children: ReactNode
  dirty: boolean
  disabled: boolean
  error: ApiError | null
  onSave: () => void
  saving: boolean
  title: string
}) {
  return (
    <section className="mt-8 border-t border-neutral-300 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-medium">{title}</h2>
        <div className="flex items-center gap-3">
          {dirty ? <span className="text-xs text-amber-800">unsaved changes</span> : null}
          <button
            className="border border-neutral-500 px-3 py-1 text-sm disabled:opacity-50"
            disabled={saving || disabled}
            onClick={onSave}
            type="button"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
      <div className="mt-3">{children}</div>
      {error === null ? null : (
        <p className="mt-3 border-l-4 border-red-700 bg-red-50 py-1 pl-2 text-sm text-red-900">
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}
    </section>
  )
}

export function useSection<F, B>(
  seed: () => F,
  toBody: (form: F) => Fields<B>,
  save: Save<B>,
): {
  dirty: boolean
  error: ApiError | null
  form: F
  onSave: () => void
  saving: boolean
  update: (form: F) => void
} {
  const [form, setForm] = useState(seed)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const update = (next: F) => {
    setForm(next)
    setDirty(true)
  }

  const onSave = () => {
    setSaving(true)
    void save(toBody(form)).then((refusal) => {
      setSaving(false)
      setError(refusal)
      if (refusal === null) setDirty(false)
    })
  }

  return { dirty, error, form, onSave, saving, update }
}

const STATUS_CLASS: Record<string, string> = {
  unverified: 'bg-neutral-200 text-neutral-800',
  verified: 'bg-green-100 text-green-900',
  near_miss: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-900',
  unverifiable_js: 'bg-amber-100 text-amber-900',
  waived: 'bg-purple-100 text-purple-900',
}

/**
 * The evidence attached to one field.
 *
 * `field` is a value from the API's CITABLE_FIELDS, never a string this tier computes. The naive
 * version derived it with a regex that produced `liquidity_depth2pct_usd` for a column named
 * `liquidity_depth_2pct_usd`, and since the same wrong string was used to add AND to filter, the
 * UI looked entirely correct while the commit gate would have counted zero.
 *
 * The boxes are cleared only on success. The quote is the one thing in this product that must be
 * transcribed exactly, and an unconditional clear meant a refused add silently ate it.
 */
export function Citations({
  citations,
  disabled,
  field,
  label,
  onAdd,
  onRemove,
}: {
  citations: Citation[]
  disabled: boolean
  field: string
  label: string
  onAdd: (input: Fields<CitationBody>) => Promise<ApiError | null>
  onRemove: (citationId: string) => Promise<ApiError | null>
}) {
  const [url, setUrl] = useState('')
  const [quote, setQuote] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const mine = citations.filter((citation) => citation.field === field)

  const add = () => {
    setBusy(true)
    void onAdd({ field, url, quote }).then((refusal) => {
      setBusy(false)
      setError(refusal)
      if (refusal !== null) return
      setUrl('')
      setQuote('')
    })
  }

  return (
    <div className="my-2 ml-4 border-l border-neutral-300 pl-3 text-sm">
      <p className="text-neutral-600">{label}</p>
      <ul>
        {mine.map((citation) => (
          <li className="flex flex-wrap items-baseline gap-2 py-0.5" key={citation.id}>
            <span
              className={`rounded px-1 text-xs ${STATUS_CLASS[citation.status] ?? 'bg-neutral-200'}`}
            >
              {citation.status}
            </span>
            <a className="underline" href={citation.url} rel="noreferrer" target="_blank">
              {citation.url}
            </a>
            <span className="text-neutral-600">“{citation.quote}”</span>
            <button
              className="text-red-800 underline disabled:opacity-50"
              disabled={disabled || busy}
              onClick={() => {
                setBusy(true)
                void onRemove(citation.id).then((refusal) => {
                  setBusy(false)
                  setError(refusal)
                })
              }}
              type="button"
            >
              remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-1 flex flex-wrap gap-2">
        <input
          className="w-72 border border-neutral-400 px-2 py-1"
          disabled={disabled || busy}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://"
          value={url}
        />
        <input
          className="w-96 border border-neutral-400 px-2 py-1"
          disabled={disabled || busy}
          onChange={(event) => setQuote(event.target.value)}
          placeholder="the exact quote to search the page for"
          value={quote}
        />
        <button
          className="border border-neutral-500 px-2 disabled:opacity-50"
          disabled={disabled || busy}
          onClick={add}
          type="button"
        >
          add
        </button>
      </div>
      {error === null ? null : (
        <p className="mt-1 text-red-900">
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Measured figures, shared by liquidity and accrual
// ---------------------------------------------------------------------------

export function seedMeasured(
  value: number | null,
  source: string | null,
  url: string | null,
  label: string | null,
  measuredAt: string | null,
): MeasuredForm {
  return {
    value: numberOf(value),
    source: textOf(source),
    url: textOf(url),
    label: textOf(label),
    measuredAt: textOf(measuredAt),
  }
}

export type MeasuredWire = NonNullable<Fields<LiquidityBody>['depth']>

export function toMeasured(form: MeasuredForm): MeasuredWire | null {
  if (isMeasuredEmpty(form)) return null
  return {
    value: form.value,
    source: form.source,
    url: form.url,
    // The server's enum refuses anything else by name; the browser does not pre-judge it.
    label: form.label as MeasuredWire['label'],
    measuredAt: form.measuredAt,
  }
}
```
- [ ] **Step 3: Two sections, to prove the model end to end**

Create `apps/web/src/editor/ProductSection.tsx`:

```tsx
import type { ProductBody } from '../lib/client.ts'
import { Citations, type Save, type SectionProps, SectionShell, useSection } from './common.tsx'
import { blankToNull, numberOf, ProseField, textOf, WholeNumberField } from './fields.tsx'

interface ProductForm {
  overviewSentence: string
  productEase: string
  productHairFire: string
  productExclusivity: string
  productEaseRationale: string
  productHairFireRationale: string
  productExclusivityRationale: string
}

export function ProductSection({
  bounds,
  citations,
  disabled,
  onAddCitation,
  onRemoveCitation,
  onSave,
  scores,
}: SectionProps & { onSave: Save<ProductBody> }) {
  const section = useSection<ProductForm, ProductBody>(
    () => ({
      overviewSentence: textOf(scores.overviewSentence),
      productEase: numberOf(scores.productEase),
      productHairFire: numberOf(scores.productHairFire),
      productExclusivity: numberOf(scores.productExclusivity),
      productEaseRationale: textOf(scores.productEaseRationale),
      productHairFireRationale: textOf(scores.productHairFireRationale),
      productExclusivityRationale: textOf(scores.productExclusivityRationale),
    }),
    (form) => ({
      overviewSentence: blankToNull(form.overviewSentence),
      productEase: blankToNull(form.productEase),
      productHairFire: blankToNull(form.productHairFire),
      productExclusivity: blankToNull(form.productExclusivity),
      productEaseRationale: blankToNull(form.productEaseRationale),
      productHairFireRationale: blankToNull(form.productHairFireRationale),
      productExclusivityRationale: blankToNull(form.productExclusivityRationale),
    }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="1 · Product gate"
    >
      <p className="mb-3 text-sm text-neutral-600">
        Three sub-scores, 0–{bounds.productSubScoreMax} each. The frozen gate passes at{' '}
        {bounds.productGateThreshold}+, decided inside the commit transaction (build-order step 6) —
        nothing on this page adds them up.
      </p>
      <ProseField
        disabled={disabled}
        label="One-sentence overview"
        onChange={(value) => update({ ...form, overviewSentence: value })}
        value={form.overviewSentence}
      />
      <WholeNumberField
        disabled={disabled}
        label="Ease of Use"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productEase: value })}
        value={form.productEase}
      />
      <ProseField
        disabled={disabled}
        label="Ease of Use rationale"
        onChange={(value) => update({ ...form, productEaseRationale: value })}
        value={form.productEaseRationale}
      />
      <Citations
        citations={citations}
        disabled={disabled}
        field={bounds.citableFields.productEase}
        label="Evidence for Ease of Use"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
      <WholeNumberField
        disabled={disabled}
        label="Hair-on-Fire (gate field)"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productHairFire: value })}
        value={form.productHairFire}
      />
      <ProseField
        disabled={disabled}
        label="Hair-on-Fire rationale"
        onChange={(value) => update({ ...form, productHairFireRationale: value })}
        value={form.productHairFireRationale}
      />
      <Citations
        citations={citations}
        disabled={disabled}
        field={bounds.citableFields.productHairFire}
        label="Evidence for Hair-on-Fire"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
      <WholeNumberField
        disabled={disabled}
        label="Exclusivity Factor"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productExclusivity: value })}
        value={form.productExclusivity}
      />
      <ProseField
        disabled={disabled}
        label="Exclusivity Factor rationale"
        onChange={(value) => update({ ...form, productExclusivityRationale: value })}
        value={form.productExclusivityRationale}
      />
      <Citations
        citations={citations}
        disabled={disabled}
        field={bounds.citableFields.productExclusivity}
        label="Evidence for Exclusivity"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
    </SectionShell>
  )
}
```
Create `apps/web/src/editor/RiskSection.tsx`:

```tsx
import type { RiskBody } from '../lib/client.ts'
import { type Save, type SectionProps, SectionShell, useSection } from './common.tsx'
import { blankToNull, ProseField, textOf } from './fields.tsx'

export function RiskSection({
  disabled,
  onSave,
  scores,
}: SectionProps & { onSave: Save<RiskBody> }) {
  const section = useSection<{ riskNotes: string }, RiskBody>(
    () => ({ riskNotes: textOf(scores.riskNotes) }),
    (form) => ({ riskNotes: blankToNull(form.riskNotes) }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="6 · Risk notes"
    >
      <p className="mb-3 text-sm text-neutral-600">
        framework/06 files risk notes under "extras", but rs_gate_completeness makes them mandatory
        on a report whose gate passed. That deviation is deliberate; do not "fix" it back to
        optional.
      </p>
      <ProseField
        disabled={disabled}
        label="Risk notes"
        onChange={(riskNotes) => update({ ...form, riskNotes })}
        value={form.riskNotes}
      />
    </SectionShell>
  )
}
```
- [ ] **Step 4: The shell**

Replace `apps/web/src/routes/reports.$reportId.tsx` entirely:

```tsx
import { createFileRoute, Link } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ProductSection } from '../editor/ProductSection.tsx'
import { RiskSection } from '../editor/RiskSection.tsx'
import {
  type ApiError,
  type CitationBody,
  client,
  type Fields,
  type ProductBody,
  type ReportPayload,
  type RiskBody,
  readError,
} from '../lib/client.ts'

type SectionKey = 'product' | 'liquidity' | 'narrative' | 'team' | 'accrual' | 'risk'

const FRESH_SEEDS: Record<SectionKey, number> = {
  product: 0,
  liquidity: 0,
  narrative: 0,
  team: 0,
  accrual: 0,
  risk: 0,
}

/*
 * This file IS the route, so the report id comes from the router's typed params rather than from
 * a prop nobody passes: `createFileRoute('/reports/$reportId')` is what puts the route in the
 * generated tree, and `Route.useParams()` is what types `reportId` as a string off it.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportEditor })

function ReportEditor() {
  const { reportId } = Route.useParams()
  const [payload, setPayload] = useState<ReportPayload | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [seeds, setSeeds] = useState(FRESH_SEEDS)
  const [conflict, setConflict] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  /*
   * The CAS token, held in a ref as well as in state.
   *
   * `reports.version` is bumped by EVERY successful write, so the token a save sends has to be
   * the one the last response produced — not one read out of a render that may not have happened
   * yet. Deriving it from `payload` inside an async callback is how two saves started close
   * together end up sending the same spent token.
   */
  const current = useRef<ReportPayload | null>(null)
  current.current = payload

  const load = useCallback(async () => {
    const response = await client.reports[':reportId'].$get({ param: { reportId } })
    if (!response.ok) {
      setLoadError(await readError(response))
      return
    }
    setPayload(await response.json())
    setLoadError(null)
  }, [reportId])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * One save: one CAS bump, then a re-read.
   *
   * The re-read is deliberate. The blocker list is computed by the API from the same array that
   * generates the CHECK constraint, and re-reading is what keeps the screen showing the database
   * rather than a client-side guess at what the write did.
   *
   * On a 409 every section is re-seeded from the server and the operator is told. The naive
   * editor seeded each input with `useState(value)` and never re-synced, so after a conflict the
   * boxes kept the losing text and the next save wrote it over the winner.
   */
  const runSave = useCallback(
    async (section: SectionKey | null, call: (version: number) => Promise<Response>) => {
      const report = current.current
      if (report === null) {
        return { code: 'NOT_LOADED', message: 'the report has not loaded yet' }
      }
      setNotice(null)
      const response = await call(report.report.version)
      if (!response.ok) {
        const refusal = await readError(response)
        if (refusal.code === 'STALE_VERSION' || refusal.code === 'ALREADY_COMMITTED') {
          await load()
          setSeeds((previous) => {
            const next = { ...previous }
            for (const key of Object.keys(next) as SectionKey[]) next[key] = previous[key] + 1
            return next
          })
          /*
           * The banner carries the refusal, because the section cannot.
           *
           * Re-seeding changes every section's React `key`, so the component the save was
           * started from unmounts: the `setError(refusal)` useSection runs next lands on an
           * instance that is being replaced, and the red per-section message never renders.
           * ReportEditor itself is not keyed, so this banner survives the remount.
           */
          const why =
            refusal.code === 'STALE_VERSION'
              ? 'This report moved on in another tab.'
              : 'This report is committed and the database refuses every write to it.'
          setConflict(
            `${refusal.code} — ${refusal.message}. ${why} Every section has been reloaded ` +
              'from the database and any unsaved text on this page was discarded.',
          )
        }
        return refusal
      }
      setConflict(null)
      await load()
      /*
       * `null` means "no section owns this write": a citation belongs to whichever section
       * renders it, and bumping one fixed key would silently discard unsaved text in THAT
       * section whenever evidence was attached anywhere else on the page. The new row reaches
       * <Citations> through the `citations` prop that load() refreshed, so no remount is needed.
       */
      if (section !== null) {
        setSeeds((previous) => ({ ...previous, [section]: previous[section] + 1 }))
      }
      return null
    },
    [load],
  )

  const saveProduct = useCallback(
    (fields: Fields<ProductBody>) =>
      runSave('product', (version) =>
        client.reports[':reportId'].product.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveRisk = useCallback(
    (fields: Fields<RiskBody>) =>
      runSave('risk', (version) =>
        client.reports[':reportId'].risk.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const addCitation = useCallback(
    (input: Fields<CitationBody>) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations.$post({
          param: { reportId },
          json: { ...input, version },
        }),
      ),
    [reportId, runSave],
  )

  const removeCitation = useCallback(
    (citationId: string) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations[':citationId'].$delete({
          param: { reportId, citationId },
          query: { version: String(version) },
        }),
      ),
    [reportId, runSave],
  )

  if (loadError !== null) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p className="text-red-900">
          <strong>{loadError.code}</strong> — {loadError.message}
        </p>
        <Link className="underline" to="/">
          back to the coin list
        </Link>
      </main>
    )
  }

  if (payload === null) return <main className="mx-auto max-w-5xl p-6">Loading…</main>

  const closed = payload.report.status !== 'draft'
  const common = {
    bounds: payload.bounds,
    citations: payload.citations,
    disabled: closed,
    onAddCitation: addCitation,
    onRemoveCitation: removeCitation,
    scores: payload.scores,
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <Link className="text-sm underline" to="/">
        ← all coins
      </Link>
      <h1 className="mt-2 text-2xl font-medium">
        {payload.coin.symbol} — {payload.coin.name}
      </h1>
      <p className="text-sm text-neutral-600">
        {payload.coin.chain} · {payload.report.status} · version {payload.report.version} ·
        framework {payload.bounds.scoringVersion}
      </p>
      {closed ? (
        <p className="mt-3 border-l-4 border-neutral-700 bg-neutral-100 py-1 pl-2 text-sm">
          This report is committed. It is immutable at the database level; every field below is
          read-only.
        </p>
      ) : null}
      {conflict === null ? null : (
        <p className="mt-3 border-l-4 border-amber-700 bg-amber-50 py-1 pl-2 text-sm text-amber-900">
          {conflict}
        </p>
      )}
      {notice === null ? null : (
        <p className="mt-3 border-l-4 border-blue-700 bg-blue-50 py-1 pl-2 text-sm text-blue-900">
          {notice}
        </p>
      )}

      <ProductSection {...common} key={`product-${String(seeds.product)}`} onSave={saveProduct} />
      <RiskSection {...common} key={`risk-${String(seeds.risk)}`} onSave={saveRisk} />

      <p className="mt-10 border-t-2 border-neutral-400 pt-4 text-sm text-neutral-600">
        The blocker list lands in Task 6 and the four remaining sections in Task 7.
      </p>
    </main>
  )
}
```
- [ ] **Step 5: Compile and lint, then start the stack**

```bash
cd /home/dev/projects/trade-god/apps/web && pnpm typecheck && pnpm test
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
pnpm dev
```
Expected: typecheck silent, `Tests 13 passed` over two files (`pnpm test` rebuilds first, so the bundle scan reads this task's tree and not Task 4's), Biome clean, and both servers up. Open `http://localhost:5173/`, add a coin, press "new draft". The product gate and Risk notes sections render; the blocker list arrives in Task 6 and the other four sections in Task 7.

- [ ] **Step 6: A save that works**

Type `7` into Ease of Use and press **Save**. Expected: the "unsaved changes" marker clears and the version in the header goes from 1 to 2.

- [ ] **Step 7: A typo does not clear the column**

Type `seven` over the `7` and press **Save**. Expected, beside the button:

```
INVALID — productEase: ease must be a whole number written in digits
```

Then reload the page. Ease of Use still reads `7`. Under the naive design it read `seven` on screen and `NULL` in the database, after a save that returned 200.

- [ ] **Step 8: A fraction is refused, not rounded**

Type `7.5` and press **Save**. Expected: `INVALID — productEase: ease must be a whole number written in digits`. Postgres would have stored `8` and `BETWEEN 0 AND 10` would have passed on the rounded value.

- [ ] **Step 9: An out-of-range score carries the frozen sentence**

Type `11` and press **Save**. Expected: `INVALID — productEase: ease must be between 0 and 10, got 11` — the `ScoreRangeError` sentence from `scoring/ranges.ts`, unedited.

- [ ] **Step 10: Drive the conflict, because it is the half that is easy to get wrong**

Open the same report in two browser tabs. In tab A, type something into Risk notes and Save. In tab B — still holding the old version — type something different into Risk notes and Save.

Expected in tab B: the amber banner, carrying the refusal itself,

> STALE_VERSION — report … moved on: client holds version N, database has N+1. This report moved on in another tab. Every section has been reloaded from the database and any unsaved text on this page was discarded.

and **the Risk notes box now showing tab A's text, not tab B's**. That last part is the finding: a box left showing the loser's text is one Save away from overwriting the winner.

There is deliberately **no red per-section message** here, and expecting one would be a red test recorded as green: re-seeding changes the section's `key`, the section unmounts, and `useSection`'s `setError` lands on the instance being replaced. That is why the banner carries the code and the message. A 422 is unaffected — it bumps no seed, so every `INVALID` line in Steps 7–9 renders in its section as written.

- [ ] **Step 11: Green, then commit**

```bash
cd /home/dev/projects/trade-god && pnpm -r run typecheck && pnpm -r run test && pnpm check
git add -A
git commit -m "feat: the editor shell, one Save per section, one CAS bump

Ruled today: explicit save per section, not save-on-blur. casBumpVersion bumps
reports.version on every successful call, so per-field saves fire many CAS
writes at typing speed and the second of two edits started before the first
response lands is refused while the screen still shows it as entered.

Sections are keyed on a per-section seed token. A successful save re-seeds only
that section, so a sibling's unsaved text survives; a 409 re-seeds all of them
and says so. The naive version seeded each input with useState(value) and never
re-synced, so after a conflict the boxes kept the losing text.

A 409 reports through the banner rather than through the section, because
re-seeding unmounts the section the save was started from and the setError that
follows lands on an instance being replaced. A citation write bumps no seed at
all -- hard-coding 'product' there would discard unsaved product-gate text every
time evidence was attached anywhere else on the page."
```

---
### Task 6: The blocker list, wired to the generated source of truth

The list on screen is the second consumer of `GATE_REQUIREMENTS`. Nothing is hand-listed in the browser; the API evaluates the same array that generates `rs_gate_completeness` and ships one row per conjunct.

Three properties are the point of the task, and all three were failures in the naive version:

- **A requirement written by the commit route renders `unknown`, never a tick.** `narrative_total`, `team_weighted_score`, the two accrual flows, the premium verdict and `waived_citation_count` are written inside the commit transaction, which does not exist. A green tick for a check nobody has written is this repo's standing failure mode.
- **The empty state never says "Nothing."** A list that has nothing to say and prints "Nothing." is indistinguishable from a list that forgot a conjunct.
- **There is no Commit button.** Not disabled — absent. The naive design rendered `<button disabled={!preview.commitAllowed} type="button">Commit</button>` with no handler, driven by a boolean computed in step 4 that step 6's in-transaction gate is not obliged to reuse. That is how two gates that disagree get born.

**Files:**
- Create: `apps/web/src/editor/Blockers.tsx`
- Modify: `apps/web/src/routes/reports.$reportId.tsx` (two edits)

**Interfaces:**
- Consumes: `type Blocker` from `src/lib/client.ts` — itself `InferResponseType<...>['blockers'][number]`, so a change to `evaluateBlockers`'s return type is a compile error here.
- Produces: `Blockers({ blockers })`.

- [ ] **Step 1: Write it**

Create `apps/web/src/editor/Blockers.tsx`:

```tsx
import type { Blocker } from '../lib/client.ts'

const PILL: Record<Blocker['state'], string> = {
  clear: 'bg-green-100 text-green-900',
  blocking: 'bg-red-100 text-red-900',
  unknown: 'bg-neutral-200 text-neutral-700',
}

/**
 * What a report that PASSES the product gate still needs.
 *
 * Every row comes from the API's GATE_REQUIREMENTS — the same array that generates
 * `rs_gate_completeness` — so a conjunct cannot exist in the database and be missing here.
 *
 * Three things this deliberately does NOT do:
 *  - it does not decide whether this report passes the gate. That is productGate(), evaluated
 *    once, inside the commit transaction.
 *  - it does not render a check written by the commit route as clear. Those rows say
 *    "not implemented", in grey, forever until step 6 writes them.
 *  - it never prints the word "Nothing." The empty state names what it means instead. A list
 *    that has nothing to say and says "Nothing." is indistinguishable from a list that forgot.
 */
export function Blockers({ blockers }: { blockers: Blocker[] }) {
  const outstanding = blockers.filter((blocker) => blocker.state !== 'clear')
  return (
    <section className="mt-10 border-t-2 border-neutral-400 pt-4">
      <h2 className="text-lg font-medium">What a passed report still needs</h2>
      <p className="mt-1 text-sm text-neutral-600">
        {blockers.filter((blocker) => blocker.state === 'clear').length} of {blockers.length}{' '}
        requirements are met. Whether this report passes the product gate is decided by the frozen
        gate inside the commit transaction, which is build-order step 6 and does not exist yet.
      </p>
      {outstanding.length === 0 ? (
        <p className="mt-3 text-sm">
          Every requirement this editor can evaluate is met. Nothing here says the report is
          commitable — the commit gate has not been written.
        </p>
      ) : (
        <ul className="mt-3 space-y-1 text-sm">
          {outstanding.map((blocker) => (
            <li key={blocker.code}>
              <span className={`rounded px-1 text-xs ${PILL[blocker.state]}`}>
                {blocker.state === 'unknown'
                  ? `not implemented (step ${String(blocker.implementedInStep)})`
                  : blocker.section}
              </span>{' '}
              <strong>{blocker.code}</strong> — {blocker.message}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-sm text-neutral-600">
        <strong>Commit</strong> is build-order step 6. There is no button for it here: a control
        driven by a boolean nothing can act on is a control that lies.
      </p>
    </section>
  )
}
```
- [ ] **Step 2: Wire it into the shell — two edits**

In `apps/web/src/routes/reports.$reportId.tsx`, add the import:

```tsx
import { Blockers } from '../editor/Blockers.tsx'
```

(`pnpm check --write` sorts it into place; do not hand-place it.)

Then replace the placeholder paragraph

```tsx
      <p className="mt-10 border-t-2 border-neutral-400 pt-4 text-sm text-neutral-600">
        The blocker list lands in Task 6 and the four remaining sections in Task 7.
      </p>
```

with

```tsx
      <Blockers blockers={payload.blockers} />
```

- [ ] **Step 3: Read it against the database**

```bash
cd /home/dev/projects/trade-god && pnpm dev
```

On a fresh draft the heading reads **"What a passed report still needs"** and the counter says `1 of 33 requirements are met` — measured, not estimated: 1 clear, 26 blocking, 6 `unknown`. The one already clear is `DISCOVERY_MARKET_CAP`, whose conjunct is `NOT accrual_assessed OR discovery_market_cap_usd IS NOT NULL` and is vacuously true while the accrual section is unassessed; that is the constraint's own semantics and the list reports it rather than hiding it. Six rows carry the grey pill `not implemented (step 6)`. Fill the product gate section and save; the count moves to `8 of 33` and the **seven** product rows — three sub-scores, three rationales and the overview sentence — disappear, because `Blockers` renders only the rows that are not clear.

Then confirm the list and the database agree, from the other side:

```bash
docker exec -i -e PGPASSWORD=coinpicks_owner coinpicks-db psql -h 127.0.0.1 -U coinpicks_owner -d coinpicks -tAc \
  "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'rs_gate_completeness';" \
  | grep -o 'IS NOT NULL\|length(btrim' | wc -l
```
Expected: `33` — one per row in the list, which is what `gate-fields.test.ts` already asserts from the other direction.

- [ ] **Step 4: Green, then commit**

```bash
cd /home/dev/projects/trade-god && pnpm -r run typecheck && pnpm -r run test && pnpm check --write && pnpm check
git add -A
git commit -m "feat: the blocker list, off the same array that generates the CHECK

Nothing is hand-listed in the browser: the API evaluates GATE_REQUIREMENTS and
ships one row per conjunct of rs_gate_completeness. A requirement the commit
route writes renders grey and says which step implements it -- never a tick --
and the empty state names what it means instead of printing 'Nothing.'

No Commit button. The naive design rendered one with no handler, disabled by a
boolean computed here that step 6's in-transaction gate is not obliged to
reuse."
```

---
### Task 7: The four remaining sections

Liquidity, narrative, team and accrual. Each follows the model Task 5 established exactly — seed from the server row, edit locally, one Save, `blankToNull` and never `Number()` — so what is worth reading here is the handful of places where the section does something the naive design got wrong.

**Files:**
- Create: `apps/web/src/editor/LiquiditySection.tsx`
- Create: `apps/web/src/editor/NarrativeSection.tsx`
- Create: `apps/web/src/editor/TeamSection.tsx`
- Create: `apps/web/src/editor/AccrualSection.tsx`
- Modify: `apps/web/src/routes/reports.$reportId.tsx` (the final version)

**Interfaces:**
- Consumes: `common.tsx`, `fields.tsx`, and the body types from `src/lib/client.ts`.
- Produces: `LiquiditySection`, `NarrativeSection`, `TeamSection`, `AccrualSection`, and the final `ReportEditor`.

- [ ] **Step 1: Liquidity**

Create `apps/web/src/editor/LiquiditySection.tsx`:

```tsx
import type { Fields, LiquidityBody } from '../lib/client.ts'
import {
  type Save,
  type SectionProps,
  SectionShell,
  seedMeasured,
  toMeasured,
  useSection,
} from './common.tsx'
import {
  blankToNull,
  CheckField,
  ChoiceField,
  MeasuredFields,
  type MeasuredForm,
  ProseField,
  textOf,
} from './fields.tsx'

interface LiquidityForm {
  depth: MeasuredForm
  topPool: MeasuredForm
  liquidityNoDexPool: boolean
  liquidityTier: string
  liquidityJustification: string
}

export function LiquiditySection({
  bounds,
  disabled,
  onSave,
  scores,
}: SectionProps & { onSave: Save<LiquidityBody> }) {
  const section = useSection<LiquidityForm, LiquidityBody>(
    () => ({
      depth: seedMeasured(
        scores.liquidityDepth2pctUsd,
        scores.liquidityDepthSource,
        scores.liquidityDepthUrl,
        scores.liquidityDepthLabel,
        scores.liquidityDepthMeasuredAt,
      ),
      topPool: seedMeasured(
        scores.liquidityTopPoolTvlUsd,
        scores.liquidityTopPoolSource,
        scores.liquidityTopPoolUrl,
        scores.liquidityTopPoolLabel,
        scores.liquidityTopPoolMeasuredAt,
      ),
      liquidityNoDexPool: scores.liquidityNoDexPool,
      liquidityTier: textOf(scores.liquidityTier),
      liquidityJustification: textOf(scores.liquidityJustification),
    }),
    (form) => ({
      depth: toMeasured(form.depth),
      topPool: toMeasured(form.topPool),
      liquidityNoDexPool: form.liquidityNoDexPool,
      liquidityTier: blankToNull(form.liquidityTier) as Fields<LiquidityBody>['liquidityTier'],
      liquidityJustification: blankToNull(form.liquidityJustification),
    }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="2 · Liquidity"
    >
      <p className="mb-3 text-sm text-neutral-600">
        There is no formula here — the tool measures and the human tiers. Saving this section
        re-stamps the tier's timestamp, so a tier can never end up older than the numbers printed
        beside it.
      </p>
      <MeasuredFields
        disabled={disabled}
        form={form.depth}
        label="±2% depth across CEXs"
        onChange={(depth) => update({ ...form, depth })}
        provenanceLabels={bounds.provenanceLabels}
      />
      <MeasuredFields
        disabled={disabled}
        form={form.topPool}
        label="Largest DEX pool TVL"
        onChange={(topPool) => update({ ...form, topPool })}
        provenanceLabels={bounds.provenanceLabels}
      />
      <CheckField
        checked={form.liquidityNoDexPool}
        disabled={disabled}
        label="No DEX pool exists (different from 'not measured')"
        onChange={(liquidityNoDexPool) => update({ ...form, liquidityNoDexPool })}
      />
      <ChoiceField
        disabled={disabled}
        label="Liquidity tier"
        onChange={(liquidityTier) => update({ ...form, liquidityTier })}
        options={bounds.liquidityTiers}
        value={form.liquidityTier}
      />
      <ProseField
        disabled={disabled}
        label="Why that tier"
        onChange={(liquidityJustification) => update({ ...form, liquidityJustification })}
        value={form.liquidityJustification}
      />
    </SectionShell>
  )
}
```
The tier and both measurements save together, and the route re-stamps `liquidity_tier_assigned_at` whenever the tier is present. That is what makes `rs_tier_not_older_than_its_inputs` unfailable rather than merely unlikely, and it is why there is no `tierCleared` flag: the naive design chose to clear the tier silently and "announce" it through a boolean that nothing rendered, so the operator's liquidity judgment vanished on a successful save with no message.

- [ ] **Step 2: Narrative**

Create `apps/web/src/editor/NarrativeSection.tsx`:

```tsx
import type { NarrativeBody } from '../lib/client.ts'
import { Citations, type Save, type SectionProps, SectionShell, useSection } from './common.tsx'
import { blankToNull, numberOf, ProseField, textOf, WholeNumberField } from './fields.tsx'

const NARRATIVE_ROWS = [
  ['narrativeMaturity', 'narrativeMaturityRationale', 'maturity', 'Narrative Maturity'],
  [
    'narrativeSmartMoney',
    'narrativeSmartMoneyRationale',
    'smartMoney',
    'Smart Money Compatibility',
  ],
  ['narrativeHairFire', 'narrativeHairFireRationale', 'hairFire', 'Hair-on-Fire Innovation'],
  [
    'narrativeCommunication',
    'narrativeCommunicationRationale',
    'communication',
    'Narrative Communication',
  ],
  ['narrativeLineage', 'narrativeLineageRationale', 'lineage', 'Narrative Lineage'],
  ['narrativeMutation', 'narrativeMutationRationale', 'mutation', 'Narrative Mutation'],
] as const

type NarrativeForm = Record<(typeof NARRATIVE_ROWS)[number][0 | 1], string>

export function NarrativeSection({
  bounds,
  citations,
  disabled,
  onAddCitation,
  onRemoveCitation,
  onSave,
  scores,
}: SectionProps & { onSave: Save<NarrativeBody> }) {
  const section = useSection<NarrativeForm, NarrativeBody>(
    () => ({
      narrativeMaturity: numberOf(scores.narrativeMaturity),
      narrativeSmartMoney: numberOf(scores.narrativeSmartMoney),
      narrativeHairFire: numberOf(scores.narrativeHairFire),
      narrativeCommunication: numberOf(scores.narrativeCommunication),
      narrativeLineage: numberOf(scores.narrativeLineage),
      narrativeMutation: numberOf(scores.narrativeMutation),
      narrativeMaturityRationale: textOf(scores.narrativeMaturityRationale),
      narrativeSmartMoneyRationale: textOf(scores.narrativeSmartMoneyRationale),
      narrativeHairFireRationale: textOf(scores.narrativeHairFireRationale),
      narrativeCommunicationRationale: textOf(scores.narrativeCommunicationRationale),
      narrativeLineageRationale: textOf(scores.narrativeLineageRationale),
      narrativeMutationRationale: textOf(scores.narrativeMutationRationale),
    }),
    (form) => ({
      narrativeMaturity: blankToNull(form.narrativeMaturity),
      narrativeSmartMoney: blankToNull(form.narrativeSmartMoney),
      narrativeHairFire: blankToNull(form.narrativeHairFire),
      narrativeCommunication: blankToNull(form.narrativeCommunication),
      narrativeLineage: blankToNull(form.narrativeLineage),
      narrativeMutation: blankToNull(form.narrativeMutation),
      narrativeMaturityRationale: blankToNull(form.narrativeMaturityRationale),
      narrativeSmartMoneyRationale: blankToNull(form.narrativeSmartMoneyRationale),
      narrativeHairFireRationale: blankToNull(form.narrativeHairFireRationale),
      narrativeCommunicationRationale: blankToNull(form.narrativeCommunicationRationale),
      narrativeLineageRationale: blankToNull(form.narrativeLineageRationale),
      narrativeMutationRationale: blankToNull(form.narrativeMutationRationale),
    }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="3 · Narrative"
    >
      <p className="mb-3 text-sm text-neutral-600">
        Six sub-scores out of {bounds.narrativeTotalMax}, each with a 1–2 sentence rationale and at
        least one citation. The total is written by the commit route from narrativeTotal(); it is
        not computed here.
      </p>
      {NARRATIVE_ROWS.map(([scoreKey, rationaleKey, maxKey, label]) => (
        <div key={scoreKey}>
          <WholeNumberField
            disabled={disabled}
            label={label}
            max={bounds.narrativeMax[maxKey]}
            onChange={(value) => update({ ...form, [scoreKey]: value })}
            value={form[scoreKey]}
          />
          <ProseField
            disabled={disabled}
            label={`${label} rationale`}
            onChange={(value) => update({ ...form, [rationaleKey]: value })}
            value={form[rationaleKey]}
          />
          <Citations
            citations={citations}
            disabled={disabled}
            field={bounds.citableFields[scoreKey]}
            label={`Evidence for ${label}`}
            onAdd={onAddCitation}
            onRemove={onRemoveCitation}
          />
        </div>
      ))}
    </SectionShell>
  )
}
```
Every maximum comes from `bounds.narrativeMax[...]` and every citation key from `bounds.citableFields[...]`. There is no `7`, `6`, `5`, `4` or `3` in this file, and `boundary.test.ts` would not have caught them if there were — which is exactly why they are served rather than trusted.

- [ ] **Step 3: Team**

Create `apps/web/src/editor/TeamSection.tsx`:

```tsx
import type { TeamBody, TeamRow } from '../lib/client.ts'
import { Citations, type Save, type SectionProps, SectionShell, useSection } from './common.tsx'

type MemberForm = TeamBody['members'][number]

function seedMembers(team: TeamRow[]): MemberForm[] {
  return team.map((person) => ({
    id: person.id,
    name: person.name,
    roles: person.roles,
    isFounder: person.isFounder,
    h: String(person.h),
    m: String(person.m),
    l: String(person.l),
    summary: person.summary,
  }))
}

const BLANK_MEMBER: MemberForm = {
  id: null,
  name: '',
  roles: [],
  isFounder: false,
  h: '',
  m: '',
  l: '',
  summary: '',
}

export function TeamSection({
  bounds,
  citations,
  disabled,
  onAddCitation,
  onRemoveCitation,
  onSave,
  team,
}: Omit<SectionProps, 'scores'> & { onSave: Save<TeamBody>; team: TeamRow[] }) {
  const section = useSection<MemberForm[], TeamBody>(
    () => seedMembers(team),
    (members) => ({ members }),
    onSave,
  )
  const { form, update } = section

  const patch = (index: number, next: Partial<MemberForm>) =>
    update(form.map((person, at) => (at === index ? { ...person, ...next } : person)))

  const move = (index: number, delta: number) => {
    const target = index + delta
    const a = form[index]
    const b = form[target]
    if (a === undefined || b === undefined) return
    const next = [...form]
    next[index] = b
    next[target] = a
    update(next)
  }

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="4 · Team"
    >
      <p className="mb-3 text-sm text-neutral-600">
        The commit gate wants {bounds.teamMinPeople}–{bounds.teamMaxPeople} people and exactly one
        founder; teamWeightedScore() decides that inside the commit transaction. Each summary is one
        sentence about PRIOR experience carrying a financial metric — never about this project.
        Saving replaces the whole set in one transaction, and the order on screen is the order
        stored.
      </p>
      <ul className="space-y-2">
        {form.map((person, index) => (
          <li
            className="border border-neutral-300 p-2"
            key={person.id ?? `unsaved-${String(index)}`}
          >
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="w-6 text-neutral-500">{index + 1}</span>
              <input
                className="w-40 border border-neutral-400 px-2 py-1"
                disabled={disabled}
                onChange={(event) => patch(index, { name: event.target.value })}
                placeholder="name"
                value={person.name}
              />
              <input
                className="w-56 border border-neutral-400 px-2 py-1"
                disabled={disabled}
                onChange={(event) =>
                  patch(index, {
                    roles: event.target.value
                      .split(',')
                      .map((role) => role.trim())
                      .filter((role) => role !== ''),
                  })
                }
                placeholder="roles, comma separated"
                value={person.roles.join(', ')}
              />
              <label className="flex items-center gap-1">
                <input
                  checked={person.isFounder}
                  disabled={disabled}
                  name="founder"
                  onChange={() =>
                    update(form.map((other, at) => ({ ...other, isFounder: at === index })))
                  }
                  type="radio"
                />
                founder
              </label>
              {(['h', 'm', 'l'] as const).map((rung) => (
                <label className="flex items-center gap-1 text-xs" key={rung}>
                  {rung.toUpperCase()} 0–{bounds.teamRungMax[rung]}
                  <input
                    className="w-12 border border-neutral-400 px-1 py-1"
                    disabled={disabled}
                    inputMode="numeric"
                    onChange={(event) => patch(index, { [rung]: event.target.value })}
                    value={person[rung]}
                  />
                </label>
              ))}
              <button
                className="border border-neutral-400 px-2 disabled:opacity-40"
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                type="button"
              >
                ↑
              </button>
              <button
                className="border border-neutral-400 px-2 disabled:opacity-40"
                disabled={disabled || index === form.length - 1}
                onClick={() => move(index, 1)}
                type="button"
              >
                ↓
              </button>
              <button
                className="border border-neutral-400 px-2 text-red-800"
                disabled={disabled}
                onClick={() => update(form.filter((_, at) => at !== index))}
                type="button"
              >
                remove
              </button>
            </div>
            <input
              className="mt-2 w-full border border-neutral-400 px-2 py-1 text-sm"
              disabled={disabled}
              onChange={(event) => patch(index, { summary: event.target.value })}
              placeholder="one sentence about prior experience, with a financial metric"
              value={person.summary}
            />
          </li>
        ))}
      </ul>
      <button
        className="mt-2 border border-neutral-500 px-3 py-1 text-sm"
        disabled={disabled}
        onClick={() => update([...form, BLANK_MEMBER])}
        type="button"
      >
        Add person
      </button>

      {/*
        Evidence is offered for SAVED members only, off the server's rows — never off the form.
        The naive editor minted a browser-side uuid on "Add person" and rendered the evidence box
        immediately, so a citation could be filed against a report_team.id that was never
        inserted. `citations.field` is text with no foreign key, and the commit gate would have
        counted it.
      */}
      <div className="mt-4">
        {team.length === 0 ? (
          <p className="text-sm text-neutral-600">
            Save the team before attaching evidence — a citation can only name a person the database
            has.
          </p>
        ) : null}
        {team.map((person) => (
          <Citations
            citations={citations}
            disabled={disabled}
            field={`${bounds.teamFieldPrefix}${person.id}`}
            key={person.id}
            label={`Evidence for ${person.name}`}
            onAdd={onAddCitation}
            onRemove={onRemoveCitation}
          />
        ))}
      </div>
    </SectionShell>
  )
}
```
Two things to leave alone:

- **No `draft.length >= bounds.teamMaxPeople` guard on "Add person".** Cardinality is `teamWeightedScore()`'s to reject at commit, and the route refuses an over-full set by name. A disabled button that explains nothing is worse than a refusal that does, and the naive version wrote the bound as a literal `5`.
- **Evidence is rendered from `team` (the server's rows), never from `form`.** The naive `TeamEditor` minted `crypto.randomUUID()` on "Add person" and offered the evidence box immediately, so a citation could be filed against a `report_team.id` that was never inserted — `citations.field` is text with no foreign key, and the commit gate would have counted it.

- [ ] **Step 4: Accrual and the discovery premium**

Create `apps/web/src/editor/AccrualSection.tsx`:

```tsx
import type { AccrualBody } from '../lib/client.ts'
import {
  Citations,
  type Save,
  type SectionProps,
  SectionShell,
  seedMeasured,
  toMeasured,
  useSection,
} from './common.tsx'
import {
  AmountField,
  blankToNull,
  MeasuredFields,
  type MeasuredForm,
  numberOf,
  ProseField,
  textOf,
} from './fields.tsx'

interface AccrualForm {
  accrualSegmentRevenueUsd: string
  accrualCaptureShare: string
  accrualPct: string
  accrualAnnualIssuanceUsd: string
  accrualAbsentReason: string
  accrualRationale: string
  accrualFinding: string
  marketCap: MeasuredForm
}

export function AccrualSection({
  bounds,
  citations,
  disabled,
  onAddCitation,
  onRemoveCitation,
  onSave,
  scores,
}: SectionProps & { onSave: Save<AccrualBody> }) {
  const section = useSection<AccrualForm, AccrualBody>(
    () => ({
      accrualSegmentRevenueUsd: numberOf(scores.accrualSegmentRevenueUsd),
      accrualCaptureShare: numberOf(scores.accrualCaptureShare),
      accrualPct: numberOf(scores.accrualPct),
      accrualAnnualIssuanceUsd: numberOf(scores.accrualAnnualIssuanceUsd),
      accrualAbsentReason: textOf(scores.accrualAbsentReason),
      accrualRationale: textOf(scores.accrualRationale),
      accrualFinding: textOf(scores.accrualFinding),
      marketCap: seedMeasured(
        scores.discoveryMarketCapUsd,
        scores.discoveryMarketCapSource,
        scores.discoveryMarketCapUrl,
        scores.discoveryMarketCapLabel,
        scores.discoveryMarketCapMeasuredAt,
      ),
    }),
    (form) => ({
      accrualSegmentRevenueUsd: blankToNull(form.accrualSegmentRevenueUsd),
      accrualCaptureShare: blankToNull(form.accrualCaptureShare),
      accrualPct: blankToNull(form.accrualPct),
      accrualAnnualIssuanceUsd: blankToNull(form.accrualAnnualIssuanceUsd),
      accrualAbsentReason: blankToNull(form.accrualAbsentReason),
      accrualRationale: blankToNull(form.accrualRationale),
      accrualFinding: blankToNull(form.accrualFinding),
      marketCap: toMeasured(form.marketCap),
    }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="5 · Value accrual and discovery premium"
    >
      <p className="mb-3 text-sm text-neutral-600">
        Cash-flow accrual only. Capture share and token accrual are FRACTIONS in [0, 1] — a value
        typed on a 0–100 scale is rejected, not divided. Leaving all four blank is a different state
        from a measured zero: say why instead, in the box below.{' '}
        <strong>Assessed: {scores.accrualAssessed ? 'yes' : 'no'}</strong> (generated by the
        database from the four inputs).
      </p>
      <AmountField
        caption="USD per year"
        disabled={disabled}
        label="Segment revenue"
        onChange={(value) => update({ ...form, accrualSegmentRevenueUsd: value })}
        value={form.accrualSegmentRevenueUsd}
      />
      <Citations
        citations={citations}
        disabled={disabled}
        field={bounds.citableFields.accrualSegmentRevenueUsd}
        label="Evidence for segment revenue"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
      <AmountField
        caption="fraction in [0, 1]"
        disabled={disabled}
        label="Capture share"
        onChange={(value) => update({ ...form, accrualCaptureShare: value })}
        value={form.accrualCaptureShare}
      />
      <AmountField
        caption="fraction in [0, 1], despite the name"
        disabled={disabled}
        label="Token accrual"
        onChange={(value) => update({ ...form, accrualPct: value })}
        value={form.accrualPct}
      />
      <AmountField
        caption="USD per year"
        disabled={disabled}
        label="Annual issuance"
        onChange={(value) => update({ ...form, accrualAnnualIssuanceUsd: value })}
        value={form.accrualAnnualIssuanceUsd}
      />
      <ProseField
        disabled={disabled}
        label="Why there is no accrual figure (required when the four boxes are not all filled)"
        onChange={(value) => update({ ...form, accrualAbsentReason: value })}
        value={form.accrualAbsentReason}
      />
      <ProseField
        disabled={disabled}
        label="Accrual rationale — name the mechanism"
        onChange={(value) => update({ ...form, accrualRationale: value })}
        value={form.accrualRationale}
      />
      <ProseField
        disabled={disabled}
        label="Accrual finding (optional prose)"
        onChange={(value) => update({ ...form, accrualFinding: value })}
        value={form.accrualFinding}
      />
      <MeasuredFields
        disabled={disabled}
        form={form.marketCap}
        label="Market cap"
        onChange={(marketCap) => update({ ...form, marketCap })}
        provenanceLabels={bounds.provenanceLabels}
      />
      <Citations
        citations={citations}
        disabled={disabled}
        field={bounds.citableFields.discoveryMarketCapUsd}
        label="Evidence for market cap"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
    </SectionShell>
  )
}
```
`accrualAssessed` is displayed, never sent: it is `GENERATED ALWAYS` and Postgres refuses a write to it with 428C9. It is in `UNWRITABLE_COLUMNS` for that reason, so `ScoresPatch` does not have the key.

- [ ] **Step 5: The final shell**

Replace `apps/web/src/routes/reports.$reportId.tsx` entirely:

```tsx
import { createFileRoute, Link } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { AccrualSection } from '../editor/AccrualSection.tsx'
import { Blockers } from '../editor/Blockers.tsx'
import { LiquiditySection } from '../editor/LiquiditySection.tsx'
import { NarrativeSection } from '../editor/NarrativeSection.tsx'
import { ProductSection } from '../editor/ProductSection.tsx'
import { RiskSection } from '../editor/RiskSection.tsx'
import { TeamSection } from '../editor/TeamSection.tsx'
import {
  type AccrualBody,
  type ApiError,
  type CitationBody,
  client,
  type Fields,
  type LiquidityBody,
  type NarrativeBody,
  type ProductBody,
  type ReportPayload,
  type RiskBody,
  readError,
  type TeamBody,
} from '../lib/client.ts'

type SectionKey = 'product' | 'liquidity' | 'narrative' | 'team' | 'accrual' | 'risk'

const FRESH_SEEDS: Record<SectionKey, number> = {
  product: 0,
  liquidity: 0,
  narrative: 0,
  team: 0,
  accrual: 0,
  risk: 0,
}

/*
 * This file IS the route, so the report id comes from the router's typed params rather than from
 * a prop nobody passes: `createFileRoute('/reports/$reportId')` is what puts the route in the
 * generated tree, and `Route.useParams()` is what types `reportId` as a string off it.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportEditor })

function ReportEditor() {
  const { reportId } = Route.useParams()
  const [payload, setPayload] = useState<ReportPayload | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [seeds, setSeeds] = useState(FRESH_SEEDS)
  const [conflict, setConflict] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  /*
   * The CAS token, held in a ref as well as in state.
   *
   * `reports.version` is bumped by EVERY successful write, so the token a save sends has to be
   * the one the last response produced — not one read out of a render that may not have happened
   * yet. Deriving it from `payload` inside an async callback is how two saves started close
   * together end up sending the same spent token.
   */
  const current = useRef<ReportPayload | null>(null)
  current.current = payload

  const load = useCallback(async () => {
    const response = await client.reports[':reportId'].$get({ param: { reportId } })
    if (!response.ok) {
      setLoadError(await readError(response))
      return
    }
    setPayload(await response.json())
    setLoadError(null)
  }, [reportId])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * One save: one CAS bump, then a re-read.
   *
   * The re-read is deliberate. The blocker list is computed by the API from the same array that
   * generates the CHECK constraint, and re-reading is what keeps the screen showing the database
   * rather than a client-side guess at what the write did.
   *
   * On a 409 every section is re-seeded from the server and the operator is told. The naive
   * editor seeded each input with `useState(value)` and never re-synced, so after a conflict the
   * boxes kept the losing text and the next save wrote it over the winner.
   */
  const runSave = useCallback(
    async (section: SectionKey | null, call: (version: number) => Promise<Response>) => {
      const report = current.current
      if (report === null) {
        return { code: 'NOT_LOADED', message: 'the report has not loaded yet' }
      }
      setNotice(null)
      const response = await call(report.report.version)
      if (!response.ok) {
        const refusal = await readError(response)
        if (refusal.code === 'STALE_VERSION' || refusal.code === 'ALREADY_COMMITTED') {
          await load()
          setSeeds((previous) => {
            const next = { ...previous }
            for (const key of Object.keys(next) as SectionKey[]) next[key] = previous[key] + 1
            return next
          })
          /*
           * The banner carries the refusal, because the section cannot.
           *
           * Re-seeding changes every section's React `key`, so the component the save was
           * started from unmounts: the `setError(refusal)` useSection runs next lands on an
           * instance that is being replaced, and the red per-section message never renders.
           * ReportEditor itself is not keyed, so this banner survives the remount.
           */
          const why =
            refusal.code === 'STALE_VERSION'
              ? 'This report moved on in another tab.'
              : 'This report is committed and the database refuses every write to it.'
          setConflict(
            `${refusal.code} — ${refusal.message}. ${why} Every section has been reloaded ` +
              'from the database and any unsaved text on this page was discarded.',
          )
        }
        return refusal
      }
      setConflict(null)
      await load()
      /*
       * `null` means "no section owns this write": a citation belongs to whichever section
       * renders it, and bumping one fixed key would silently discard unsaved text in THAT
       * section whenever evidence was attached anywhere else on the page. The new row reaches
       * <Citations> through the `citations` prop that load() refreshed, so no remount is needed.
       */
      if (section !== null) {
        setSeeds((previous) => ({ ...previous, [section]: previous[section] + 1 }))
      }
      return null
    },
    [load],
  )

  const saveProduct = useCallback(
    (fields: Fields<ProductBody>) =>
      runSave('product', (version) =>
        client.reports[':reportId'].product.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveLiquidity = useCallback(
    (fields: Fields<LiquidityBody>) =>
      runSave('liquidity', (version) =>
        client.reports[':reportId'].liquidity.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveNarrative = useCallback(
    (fields: Fields<NarrativeBody>) =>
      runSave('narrative', (version) =>
        client.reports[':reportId'].narrative.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveAccrual = useCallback(
    (fields: Fields<AccrualBody>) =>
      runSave('accrual', (version) =>
        client.reports[':reportId'].accrual.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveRisk = useCallback(
    (fields: Fields<RiskBody>) =>
      runSave('risk', (version) =>
        client.reports[':reportId'].risk.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveTeam = useCallback(
    (fields: Fields<TeamBody>) =>
      runSave('team', async (version) => {
        const response = await client.reports[':reportId'].team.$put({
          param: { reportId },
          json: { ...fields, version },
        })
        if (response.ok) {
          const body = await response.json()
          if (body.citationsRemoved > 0) {
            setNotice(
              `${String(body.citationsRemoved)} citation(s) belonging to removed team members ` +
                'were deleted. Evidence pointing at nobody would still have been counted.',
            )
          }
        }
        return response
      }),
    [reportId, runSave],
  )

  const addCitation = useCallback(
    (input: Fields<CitationBody>) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations.$post({
          param: { reportId },
          json: { ...input, version },
        }),
      ),
    [reportId, runSave],
  )

  const removeCitation = useCallback(
    (citationId: string) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations[':citationId'].$delete({
          param: { reportId, citationId },
          query: { version: String(version) },
        }),
      ),
    [reportId, runSave],
  )

  if (loadError !== null) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p className="text-red-900">
          <strong>{loadError.code}</strong> — {loadError.message}
        </p>
        <Link className="underline" to="/">
          back to the coin list
        </Link>
      </main>
    )
  }

  if (payload === null) return <main className="mx-auto max-w-5xl p-6">Loading…</main>

  const closed = payload.report.status !== 'draft'
  const common = {
    bounds: payload.bounds,
    citations: payload.citations,
    disabled: closed,
    onAddCitation: addCitation,
    onRemoveCitation: removeCitation,
    scores: payload.scores,
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <Link className="text-sm underline" to="/">
        ← all coins
      </Link>
      <h1 className="mt-2 text-2xl font-medium">
        {payload.coin.symbol} — {payload.coin.name}
      </h1>
      <p className="text-sm text-neutral-600">
        {payload.coin.chain} · {payload.report.status} · version {payload.report.version} ·
        framework {payload.bounds.scoringVersion}
      </p>
      {closed ? (
        <p className="mt-3 border-l-4 border-neutral-700 bg-neutral-100 py-1 pl-2 text-sm">
          This report is committed. It is immutable at the database level; every field below is
          read-only.
        </p>
      ) : null}
      {conflict === null ? null : (
        <p className="mt-3 border-l-4 border-amber-700 bg-amber-50 py-1 pl-2 text-sm text-amber-900">
          {conflict}
        </p>
      )}
      {notice === null ? null : (
        <p className="mt-3 border-l-4 border-blue-700 bg-blue-50 py-1 pl-2 text-sm text-blue-900">
          {notice}
        </p>
      )}

      <ProductSection {...common} key={`product-${String(seeds.product)}`} onSave={saveProduct} />
      <LiquiditySection
        {...common}
        key={`liquidity-${String(seeds.liquidity)}`}
        onSave={saveLiquidity}
      />
      <NarrativeSection
        {...common}
        key={`narrative-${String(seeds.narrative)}`}
        onSave={saveNarrative}
      />
      <TeamSection
        {...common}
        key={`team-${String(seeds.team)}`}
        onSave={saveTeam}
        team={payload.team}
      />
      <AccrualSection {...common} key={`accrual-${String(seeds.accrual)}`} onSave={saveAccrual} />
      <RiskSection {...common} key={`risk-${String(seeds.risk)}`} onSave={saveRisk} />

      <Blockers blockers={payload.blockers} />
    </main>
  )
}
```
- [ ] **Step 6: Start the stack and fill the product gate**

```bash
cd /home/dev/projects/trade-god && pnpm dev
```

Open a draft. Fill the one-sentence overview, all three sub-scores, all three rationales, and attach one citation to each sub-score. Press **Save** on section 1. Expected: the marker clears, the version climbs by one, and the counter goes from `1 of 33` to `8 of 33` — the product section owns seven of the conjuncts.

- [ ] **Step 7: Fill liquidity**

Both measured figures (figure, source, URL, provenance, measured-at), the "no DEX pool" box if it applies, a tier, and the justification. Save. Expected: the tier's timestamp is re-stamped on the server, so `rs_tier_not_older_than_its_inputs` is never near being tripped, and the four liquidity conjuncts clear — `12 of 33`.

- [ ] **Step 8: Fill narrative**

Six sub-scores, six rationales, and at least one citation under each. Save. Expected: all twelve narrative conjuncts clear — `24 of 33` — while `NARRATIVE_TOTAL` stays grey and reads `not implemented (step 6)`, because the commit route writes it and the commit route does not exist.

- [ ] **Step 9: Fill the team**

Add three people with names, roles, one-sentence prior-experience summaries, H/M/L rungs and exactly one founder. Save. Then attach a citation to each person.

Expected: the counter does **not** move. The team's only conjunct is `TEAM_WEIGHTED_SCORE`, which the commit route writes, so it stays grey at `not implemented (step 6)`. `framework/05` still requires the people and the sourced quotes; `rs_gate_completeness` simply does not check them, and the list reports the constraint rather than a wish.

- [ ] **Step 10: Fill accrual and the risk notes**

Segment revenue and the market cap as measured figures, capture share and accrual percentage as fractions, annual issuance, and the risk notes. Save each section.

Expected: `27 of 33`, **0 blocking and 6 unknown**. Filling all four accrual inputs makes the generated `accrual_assessed` true, which clears `ACCRUAL_ABSENT_REASON` (the report no longer has to say why there is no accrual figure) and keeps `DISCOVERY_MARKET_CAP` clear now that it is no longer vacuous; `ACCRUAL_RATIONALE` and `RISK_NOTES` clear outright. The six that remain are exactly the commit-written rows — `NARRATIVE_TOTAL`, `TEAM_WEIGHTED_SCORE`, `ACCRUAL_GROSS_FLOW`, `ACCRUAL_NET_FLOW`, `DISCOVERY_PREMIUM_KIND`, `WAIVED_CITATION_COUNT` — and they stay grey. The whole walk, measured: 1 → 8 → 12 → 24 → 24 → 27.

Five probes follow. Each one is a defect that used to pass silently, so each is worth doing deliberately rather than trusting.

- [ ] **Step 11: Probe — a blank figure with full provenance**

In liquidity, fill **source, URL, provenance and measured-at and leave the figure blank**, then Save. Expected:

```
INVALID — depth.value: liquidityDepth2pctUsd must be a number written in digits…
```

and nothing stored. The naive version wrote `$0, verified, DefiLlama` into an immutable ledger, because `Number('') === 0` and both the presence biconditional and the `>= 0` CHECK accept it.

- [ ] **Step 12: Probe — a future measurement**

Put tomorrow's date in measured-at and Save. Expected:

```
INVALID — depth.measuredAt: liquidityDepth2pctUsd: a measurement cannot be in the future
```

One future timestamp would otherwise have locked the liquidity tier until the clock caught up.

- [ ] **Step 13: Probe — a percentage in a fraction box**

In accrual, type `50` into capture share and Save. Expected:

```
INVALID — accrualCaptureShare: captureShare must be between 0 and 1, got 50
```

Rejected, not divided by 100.

- [ ] **Step 14: Probe — evidence for a person the database does not have**

Reload, press **Add person**, and look under the new row: there is no evidence box, and where the team is empty the section reads *"Save the team before attaching evidence — a citation can only name a person the database has."* Then, with three saved members, attach a citation to the third, remove the third, and Save. Expected: the blue notice

```
1 citation(s) belonging to removed team members were deleted.
```

The naive editor minted a browser-side uuid on "Add person" and offered the box immediately; `citations.field` is text with no foreign key, and the commit gate would have counted the orphan.

- [ ] **Step 15: Probe — a citation does not eat unsaved text**

In the product gate, type `THIS TEXT MUST SURVIVE` into **Ease of Use rationale** and do **not** save — the section marker reads "unsaved changes". Now scroll to narrative and add a citation under any sub-score. Expected: the citation appears, and the Ease of Use rationale **still reads `THIS TEXT MUST SURVIVE`** with its marker still showing. If it blanks, `runSave`'s citation callbacks are passing `'product'` instead of `null` and are re-seeding a section the operator is typing in.

- [ ] **Step 16: Green, then commit**

```bash
cd /home/dev/projects/trade-god && pnpm -r run typecheck && pnpm -r run test && pnpm check --write && pnpm check
python -m pytest -q
```
Expected: api `Tests 119 passed` over 14 files, web `Tests 13 passed` over 2 files, pytest `111 passed`, Biome clean.

Then read the one number this task can move and nothing else pins:

```bash
cd /home/dev/projects/trade-god/apps/web && find dist/client -name '*.js' -printf '%s\n' | paste -sd+ | bc
```
Measured at the end of Task 4 the same total was **583,379**, and `bundle.test.ts`'s ceiling is
660,000. If Task 7's finished tree comes in above it, raise the ceiling **in this commit** with the
measured number written into that file's comment — never silently, and never by making a red test
green after the fact. If it comes in well under, leave the ceiling alone: its job is to sit between
an honest tree and a leaking one (719,045), not to track the app's size.

```bash
git add -A
git commit -m "feat: liquidity, narrative, team and accrual

The liquidity section saves the tier with both measurements and the route
re-stamps the tier's timestamp, so rs_tier_not_older_than_its_inputs cannot be
tripped -- no tierCleared flag, which the naive design announced in prose and
never rendered.

Team evidence is rendered from the server's rows, never from the form: the
naive editor minted a browser-side uuid on 'Add person' and offered the
evidence box immediately, and citations.field is text with no foreign key. No
Add-person cap either -- cardinality is teamWeightedScore()'s to reject, and a
literal 5 in apps/web is a frozen bound nothing pins."
```

---
### Task 8: Docs, CI, the three chores, and the decisions log

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` (one sentence in §9 and one row of the stack table — §9's heading and first paragraph are **correct as they stand** and the frozen formulas section is not touched)
- Modify: `agents/CONTEXT.md` (chore 1)
- Modify: `apps/api/src/server.ts` — already done in Task 3 (chore 2); verify
- Modify: `.env.example` (chore 3)
- Modify: `.github/workflows/ci.yml`
- Modify: `agents/decisions.md`, `agents/roadmap.md`

**Interfaces:**
- Consumes: nothing. **No file under `apps/` changes in this task at all** — every interface is already final. What changes is `.env.example`, the CI job, and the written record.
- Produces: no export. It produces the written record: the amended `CLAUDE.md` rules, the amended spec §9, the dated `agents/decisions.md` entry recording that dropping TanStack Start was **proposed, reviewed and reversed** — and why — and a CI step that catches a committed route tree that no longer matches the route files.

- [ ] **Step 1: Chore 1 — the stale sub-score sentence**

`agents/CONTEXT.md` is the file the session convention says to take vocabulary from, and lines 60–62 currently read:

> **Narrative score** — the /31 total across six sub-scores. Sub-scores are **whole numbers** (the framework's own worked example scores Communication 4.5/5) — never round or constrain them to integers.

That sentence contradicts itself, and the parenthetical cites the fabricated ARB example that `agents/decisions.md` has already struck. A fresh engineer reading it builds decimal inputs. Replace it with:

```markdown
**Narrative score** — the /31 total across six sub-scores. Sub-scores are **whole numbers**
(ruled 2026-09-21): the lessons state their scales as integer-contiguous bands, and the product
gate partitions into "16+" / "0–15", a partition that only covers integers. Derived values — the
team weighted score is a mean — are not integers.
```

**`agents/decisions.md:319` carries the same sentence and must NOT be touched.** It is wrapped in `~~ ~~` and followed by "**[Superseded 2026-09-21 — that example is not in any lesson; sub-scores are integers. See the entry above.]**", which is the correct historical record. `agents/roadmap.md` does not contain the dead number; do not go looking for it there.

- [ ] **Step 2: Chore 2 — confirm the fabricated port note is gone**

Scope the check to what this plan owns. The two prior plans in `docs/superpowers/plans/` also say `8787`; those are the historical record of what was believed at the time and are **not** edited, exactly as `decisions.md:319` is not. The spec's live claim is a different matter and Step 4 strikes it.

```bash
cd /home/dev/projects/trade-god && grep -rn "my-teacher-api-1\|8787" apps/ .env.example
```
Expected: one hit — `apps/web/vite.config.ts`, the `strictPort` comment, which cites the 8787 episode deliberately as the reason a dev server must fail loudly rather than drift to another port. That is a citation, not a claim, and it stays. `apps/api/src/server.ts` was already corrected at HEAD `ebb74bc`; there is nothing to strike there.

Then confirm the spec is the only remaining live carrier, so Step 4 knows what it is fixing:

```bash
grep -rn "8787" docs/superpowers/specs/
```
Expected: one hit, `2026-09-21-coin-research-platform-design.md:67`.

- [ ] **Step 3: Chore 3 — the stray fence in `.env.example`**

Delete line 35 of `.env.example`, which is a bare ```` ``` ```` left over from a paste. The `PORT=8789` line above it is correct and stays.

- [ ] **Step 4: Two amendments to the spec — and one that is no longer wanted**

In `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md`. **The file is hard-wrapped at about 100 columns, so every quotation below is given with its line breaks exactly as they are on disk; a one-line find/replace matches nothing.** The line numbers are where the text sits before any edit in this step; match on the text, not on the number, because the paragraph replacement below turns two lines into six.

**§9's heading and first paragraph are correct as they stand and are NOT edited.** An earlier draft of this step rewrote

```
## 9. UI (`apps/web`, TanStack Start)
```

to name Vite and TanStack Router, and rewrote the paragraph under it to say Start had been dropped. The owner reversed that decision on 2026-09-21; the spec already says what is true, and the amendment is struck. Leave lines 560 and 562–564 exactly as they are.

Lines 579–580, the Commit-button sentence:

```
**The Commit button is disabled and names exactly what blocks it** — empty decisions, unverified
selected citations, out-of-range values, a stale `version`.
```

becomes

```
**What blocks a commit is named on the page, generated from one list.**
`apps/api/src/db/gate-fields.ts` holds the conjuncts of `rs_gate_completeness` as data; the DDL
and the editor's blocker list are both generated from it, and a test asserts the committed
migration still reproduces the generated string. A requirement written by the commit route
renders as "not implemented", never as a tick. The Commit button itself arrives with the commit
gate in build-order step 6; until something can act on it, there is no button.
```

And in the same file's stack table, the `API` row currently reads

```
| API | `apps/api` — hono 4.13.8, @hono/zod-validator 0.9.1, zod 4.6.5, on port **8789** (8787 is held by an unrelated container on this machine; overridable via `PORT`) |
```

Replace it with

```
| API | `apps/api` — hono 4.13.8, @hono/zod-validator 0.9.1, @hono/node-server 2.1.1, zod 4.6.5, on port **8789**, overridable via `PORT` |
```

That parenthetical is the same fabricated claim Step 2 strikes from `server.ts`, and it is the last live copy of it. **The `Web` row is not touched**: it already reads `@tanstack/react-start 1.168.57 on @tanstack/react-router 1.170.38`, which is what this plan builds.

**Leave the `## Normative formulas (frozen)` section untouched.**

- [ ] **Step 5: Update `CLAUDE.md`**

Five edits.

1. In the **Stack** table, the `apps/web` row already names `@tanstack/react-start 1.168.57` and stays that way — an earlier draft of this step removed it, and the owner reversed that. What it is missing is the rest of the package list. Replace

```
| `apps/web` | @tanstack/react-start 1.168.57 · @tanstack/react-router 1.170.38 · react/react-dom 19.3.0 · vite 8.3.0 · tailwindcss + @tailwindcss/vite 4.3.3 |
```

with

```
| `apps/web` | @tanstack/react-start 1.168.57 · @tanstack/react-router 1.170.38 (file-based routes; `src/routeTree.gen.ts` is generated and committed) · react/react-dom 19.3.0 · @types/react + @types/react-dom 19.3.0 · vite 8.3.0 · @vitejs/plugin-react 6.1.1 · tailwindcss + @tailwindcss/vite 4.3.3 · hono 4.13.8 (for `hc`) · @hono/node-server 2.1.1 (hosts the built app) |
```

and add `@hono/node-server 2.1.1` to the `apps/api` row. Then, directly under the table, add:

```markdown
**`apps/web/src/routeTree.gen.ts` is generated, committed, and excluded from Biome.** The Start
vite plugin rewrites it from `src/routes/` on every `vite dev` and every `vite build`, so
`biome.json` carries one exclusion for it — the same line the sibling repo at `../profe` runs —
and CI runs `git diff --exit-code` on it after the build, which is what catches a route added
without committing the tree. Never hand-edit it, and never add anything hand-written to that
exclusion.
```

2. Under **THE FROZEN FORMULAS**, after the bullet beginning "They are evaluated at **exactly one moment**", add:

```markdown
- The three **validators** in `scoring/ranges.ts` — `assertRange`, `assertIntegerRange`,
  `assertNonNegative` — are not formulas and are called wherever operator input is accepted.
  The editor's write path runs them before any value reaches Postgres, because
  `INSERT (ease integer) VALUES (7.5)` stores `8` and `BETWEEN 0 AND 10` then passes on the
  rounded value. Nothing outside the commit transaction ever ADDS two scores together.
```

3. Under **Postgres**, after schema rule 5, add:

```markdown
**One required-field list.** The conjuncts of `rs_gate_completeness` are data, in
`apps/api/src/db/gate-fields.ts`. `schema.ts` generates the CHECK from it, `reports/blockers.ts`
generates the editor's blocker list from it, and `db/gate-fields.test.ts` asserts the committed
`.sql` still contains the generated string. Ruled 2026-09-21, because the CHECK is INERT on a
draft — it is `CASE WHEN product_passed THEN … ELSE true END` and `product_passed` is only
written at commit — so a hand-written blocker list could tell the operator they are ready while
the database would refuse them.
```

4. In **Build order**, the list wraps mid-phrase across three lines, so a find/replace on
   `4. minimal editor` matches nothing. Replace all three lines

```
1. archive (**done**) · 2. frozen scoring core · 3. schema + migrations + the trigger · 4. minimal
editor · 5. citation verifier · 6. commit gate + ledger view · 7. bench the three models on one
real coin · 8. wire the EvidenceFinder.
```

   with

```
1. archive (**done**) · 2. frozen scoring core (**done**) · 3. schema + migrations + the trigger
(**done**) · 4. minimal editor (**done**) · 5. citation verifier · 6. commit gate + ledger view ·
7. bench the three models on one real coin · 8. wire the EvidenceFinder.
```

   Steps 2 and 3 are marked at the same time: the frozen core and the schema are both committed
   and neither was ever ticked.

5. Delete the stray code fence — a bare ```` ``` ```` on its own line (line 179 before the other four edits; match on its neighbours, not on the number) between

```
   `apps/api/src/scoring/frozen-surface.test.ts` fails if a frozen number moves without a
   deliberate bump, and pins the CHECK constraints against the same numbers.
```

   and

```
4. **`reports.version` integer NOT NULL with compare-and-swap writes** —
```

   It is the same paste artefact as chore 3's, one file over. Unmatched, it opens a code block
   that runs to line 274 and swallows schema rules 4 and 5, the seven-table list, the whole
   "The LLM is an EvidenceFinder, not a drafter" section and "Python's role". Verify with

```bash
grep -cE '^[`]{3}' CLAUDE.md
```

   Expected: an even number (8 after the deletion, 9 before it).

- [ ] **Step 6: Teach CI to notice a stale route tree**

**No separate build step is added, and the earlier draft's one is not wanted.** `@coinpicks/web`'s `test` script runs `vite build` before vitest (Task 4 Step 1), so the existing `Test` step already builds the client and the server, and with `importProtection` on that build is itself a boundary gate — a value import of `@coinpicks/api` fails it outright rather than shipping quietly. A second `pnpm --filter @coinpicks/web run build` would only do the same work twice.

What CI genuinely cannot see today is the one real objection the drop-Start draft raised and never answered: **nothing asserts that the committed route tree matches the route files.** Biome does not lint it — it is generated — and `tsc` compiles whatever is committed. But the `Test` step has just regenerated it, so a diff is the whole check.

In `.github/workflows/ci.yml`, add a comment above the `Test` step and one step after it:

```yaml
      - name: Test
        # @coinpicks/web's `test` runs `vite build` first: bundle.test.ts scans dist/client and
        # dist/server, and a scan of a stale dist is a guard reporting success over bytes it did
        # not read. That build is also a gate in its own right -- the Start plugin's
        # importProtection fails it on a value import of @coinpicks/api, in either environment.
        run: pnpm -r --if-present run test

      - name: The committed route tree matches the route files
        # vite build has just rewritten apps/web/src/routeTree.gen.ts from src/routes/. A
        # non-empty diff therefore means someone added, renamed or deleted a route and did not
        # commit the regenerated tree. Nothing else checks this file: it is excluded from Biome
        # because it is generated, and tsc happily compiles a stale one.
        run: git diff --exit-code apps/web/src/routeTree.gen.ts
```

- [ ] **Step 7: Record the decisions**

Append to `agents/decisions.md`, dated 2026-09-21:

```markdown
## 2026-09-21 — the minimal editor (build-order step 4)

- **One required-field list, generated both ways.** The conjuncts of `rs_gate_completeness` are
  data in `apps/api/src/db/gate-fields.ts`; the DDL and the blocker list are both generated from
  it and a test asserts the committed `.sql` still matches. The reason is that the CHECK is inert
  on a draft — `SELECT CASE WHEN NULL::boolean THEN false ELSE true END` is `t` — so nothing in
  the database refuses an incomplete draft and a hand-written list could disagree with it
  silently.
- **Two corrections came with the regeneration.** The three product sub-scores are now required
  (`product_total = ease + hair_fire + exclusivity` is NULL when any is NULL and a CHECK accepts
  NULL — reproduced on 16.13), and the accrual `CASE` is expanded into five conjuncts so each
  absence has its own blocker code. Migration `0003_gate_completeness_generated.sql`.
- **Explicit save per section, not save-on-blur.** `casBumpVersion` bumps the version on every
  successful call, so per-field saves churn the token; two edits started before the first
  response lands means the second is refused while the screen still shows it as entered.
- **A citation write owns no section, and a 409 reports through the banner.** `runSave` takes
  `SectionKey | null`; the citation callbacks pass `null` so attaching evidence cannot re-seed a
  section the operator is typing in, and the 409 path folds the refusal's code and message into
  the page-level banner because re-seeding unmounts the section that would otherwise show it.
- **The boot guard compares the applied SET of migrations, not the count.** `count(*)` was
  satisfied by any row at all, and `integrity.test.ts`'s own `finally` used to insert an invented
  hash to make the total add up — leaving a database one migration short that the guard called
  green, and that drizzle would have re-applied at the next boot because the invented row's
  `created_at` is older than the real file's `when`. The journal's `when` values are now compared
  against `drizzle.__drizzle_migrations.created_at` directly.
- **Every number crosses the wire as the string the operator typed.** `Number('seven')` is NaN
  and `JSON.stringify` turns NaN into `null`, which this API reads as "clear this field" — so a
  typo used to return 200, bump the version and empty the column. The parse happens once, in
  zod, through the frozen validators. This also gets in front of Postgres rounding `7.5` into
  `8` and the CHECK passing on the rounded value.
- **Dropping TanStack Start was proposed, reviewed, and REVERSED by the owner.** The proposal was
  plain Vite plus `@tanstack/react-router` with code-based routes, on three grounds: that the
  generated `routeTree.gen.ts` fails `biome check` as an error, that `pnpm format` and the
  generator then fight over it, and that dropping Start removes the network-egress hazard in
  `__root.tsx` by construction. Start stays. It is what was asked for when this pivot began, it
  is in the approved spec §9 and in `CLAUDE.md`'s stack table, and two of the three grounds do
  not survive measurement:
  - **The biome objection costs one line**, and the sibling repo at `../profe` has been running
    exactly that line beside `@tanstack/react-start` since before this repo existed. Measured
    here: `biome check` exits 1 without `"!**/routeTree.gen.ts"`, on
    `assist/source/organizeImports` at `routeTree.gen.ts:11`, and exits 0 with it, over exactly
    one file fewer. The file is excluded because it is **generated**, which is the same reason
    its own header gives.
  - **There is no fight.** `sha256(routeTree.gen.ts)` is identical before `biome check --write`,
    after it, and after the next `vite build`.
  - **The third ground was real and is now closed better.** `__root.tsx` does execute on the
    server under Start, so "by construction" is gone — but the drop only ever bought
    "by construction until someone adds a loader", which that proposal conceded itself.
    `boundary.test.ts` now asserts that `__root.tsx` contains none of `loader`, `beforeLoad`,
    `createServerFn`, `fetch(` or `ssr:`, and that `routes/api.$.ts` is the only file under
    `src/` that fetches anything at all. A test fails a commit; a construction argument fails a
    code review, if anyone is looking.

  And keeping Start bought something the SPA could not have had. The Start vite plugin's
  **`importProtection`** turns defect 5 — `import { type AppType, createApp }`, one word
  different, `vite build` exit 0, 135,724 bytes of ORM and this project's own DDL strings in the
  browser — into a build that fails with the full import trace. Both a `client` and a `server`
  specifier list, because they are different rules: the same value import confined to a
  `createServerFn` body leaves the client bundle spotless (measured: 587,978 bytes against a
  clean 583,379, zero ORM needles, under the ceiling) and puts drizzle in `dist/server`, which is
  a database handle in the renderer. `bundle.test.ts` scans both halves for the same reason.

  **Start's server hosts the page and one loopback hop, and nothing else.** `routes/api.$.ts`
  forwards `/api` to `COINPICKS_API_ORIGIN` — loopback, configured by the process, never a URL
  taken from a request, a report or a citation — and it replaces a dev-only Vite proxy, so the
  hop that ships is the hop that is developed against. The citation verifier (step 5) and the
  EvidenceFinder (step 8) do **not** go in server functions: both reach a third party or hold a
  key, and the tier that holds `DATABASE_URL` is `apps/api`. `importProtection.server` is what
  stops that shortcut mechanically — a server function reaching for `@coinpicks/api` fails the
  SSR build.
- **`reports/bounds.ts` rather than exporting from the frozen modules.** `product.ts` and
  `team.ts` hold `0, 10`, `< 3`, `> 5` and `* 5` as inline literals. Exporting them would edit
  two frozen files to avoid a copy; the copy lives in a non-frozen module and
  `frozen-surface.test.ts` pins it against the DDL and against the functions' own refusals. That
  also gives `teamFounderWeight` / `teamMinPeople` / `teamMaxPeople` something to be compared
  against — they sat in that table comparing with nothing.
- **`CITABLE_FIELDS` is read off the drizzle columns.** The regex derivation it replaces spelled
  `liquidity_depth_2pct_usd` as `liquidity_depth2pct_usd`, and because the same wrong string was
  used to add AND to filter, the UI was internally consistent and the commit gate would have
  counted zero.
- **The liquidity route re-stamps `liquidity_tier_assigned_at` on every save carrying a tier.**
  The section always saves the tier with both measurements, a future `measured_at` is already
  refused, and `now()` runs after the request is parsed — so
  `rs_tier_not_older_than_its_inputs` cannot be tripped. Rejected alternative: clear the tier and
  set a `tierCleared` flag, which the design announced in prose and rendered nowhere.
- **No Commit button in step 4.** Not disabled — absent. A control driven by a boolean computed
  here that step 6's in-transaction gate is not obliged to reuse is how two gates that disagree
  get born.
- **No `DELETE /reports/:id`.** Two open drafts on one coin are allowed and harmless, so a
  mistyped draft is not blocking: the operator starts another and the bad one sits in the list.
  Discard is the only destructive route step 4 could carry, against twelve ENABLE ALWAYS
  triggers, in a product whose thesis is that nothing is ever deleted. It belongs with the
  ledger view in step 6, where "which drafts are junk" is a question with a screen to answer it.
- **Open: whether a dropped project must state why it was dropped.** `rs_gate_completeness`
  requires nothing downstream on a failure, so step 4 follows the schema and requires nothing.
  The rejected population is the whole reason drops are committed, and a drop with no stated
  reason is a row the ledger can count but not interpret. Step 6's call, deliberately.
- **Open: which non-narrative fields need citations at the commit gate.** Step 4 writes the
  strings, so `CITABLE_FIELDS`'s 16 entries plus `team:<uuid>` are a commitment made now. Spec
  §2.3 names the six narrative sub-scores; `framework/05` and `/06` require sourced quotes per
  team member; `framework/06`'s style rule would also cover the product sub-scores and the
  accrual inputs. Step 6 must adopt or narrow the list.
- **Open: what happens to downstream values typed while the gate passed, when it is later
  lowered to failed.** No constraint requires them empty. Step 4 keeps them. Step 6 must rule:
  NULL them inside the commit transaction, or refuse the commit until the operator clears them.
```

Append to `agents/roadmap.md`:

```markdown
- 2026-09-21 — build-order step 4 complete: the minimal editor. One required-field list
  generating both `rs_gate_completeness` and the blocker list, migration 0003, thirteen API routes
  with per-section CAS saves, and apps/web on TanStack Start with a mechanical tier boundary on
  both sides of the build. Next: step 5, the citation verifier.
```

- [ ] **Step 8: Full green, then commit**

```bash
cd /home/dev/projects/trade-god
python -m pytest -q
pnpm -r run typecheck
pnpm -r run test
pnpm check --write && pnpm check
git diff --exit-code apps/web/src/routeTree.gen.ts
cd apps/web
grep -c -e 'drizzle:' -e PgTable -e report_scores -e rs_gate -e pg-protocol dist/client/assets/*.js; echo "grep exit=$? (1 means NO match, which is the passing case)"
grep -rc -e 'drizzle:' -e PgTable -e report_scores dist/server --include='*.js'
```
Expected: pytest `111 passed`; typecheck silent; api `Tests 119 passed` over 14 files and web `Tests 13 passed` over 2 files; Biome clean; the route-tree diff empty; and `0` on every line of both greps.

`pnpm -r run test` is what builds — `@coinpicks/web`'s `test` script runs `vite build` first — so there is no separate build command here and `dist/client` is guaranteed to be this tree's. **Note what the grep does not say.** It names `dist/client`, not `dist/assets`, because a Start build has no `dist/assets` and the old command exited 0 having read nothing. And it looks for `drizzle:` rather than `drizzle-orm`: in a client bundle with a real leak, `drizzle-orm`, `pg-protocol` and `node:crypto` are all **0** — rolldown rewrites the specifier away and the `pg` driver never arrives — while `drizzle:` is 15 and this project's own `report_scores` and `rs_gate` are in the browser for anyone to read.

```bash
git add -A
git commit -m "docs: record step 4's rulings, and strike two stale claims

CONTEXT.md still told a fresh engineer that sub-scores are whole numbers and in
the same sentence never to constrain them to integers, citing the fabricated
worked example decisions.md already struck. decisions.md:319 keeps its
struck-through copy on purpose -- that one is the historical record.

The 8787 / my-teacher-api-1 note in server.ts was false on this machine: docker
ps lists two containers, neither of them that, and nothing listens on 8787.

Also: the proposal to drop TanStack Start is recorded as reversed, with what the
three grounds for it actually measured -- one biome exclude line, a route tree
that is byte-identical across format and rebuild, and a boundary now asserted by
a test rather than by construction. CI gains the one check nothing else does:
the committed route tree still matches the route files."
```

---
## Explicitly out of step 4

Step 4 **creates and edits a DRAFT**. It does not commit one, does not verify a citation, does not call an LLM, does not read a chain.

**Routes.** `POST /reports/:id/commit`. Any verify or re-verify route. Any candidates or EvidenceFinder route. Any chain route. Any vendor adapter — a CoinGecko lookup for market cap is spec §6 and step 5+; the schema already models a vendor number and a typed number identically, so an adapter saves typing rather than correctness and costs an HTTP client, a cache decision, a rate-limit story and a mock in every test. `DELETE /reports/:reportId` — discard belongs with the ledger view in step 6 (see the decisions log).

**Data.** Any write to a derived column (`DERIVED_COLUMNS`, eleven of them). Any write to `accrual_assessed` — Postgres refuses it with 428C9. Any `citations.status` other than the default `'unverified'`. Any `origin='model'`, `finder_provider` or `finder_model`. Any waiver UI or `waiver_reason` write — a waiver before anything has been checked waives nothing, and the gate refuses a waiver whose `last_outcome` is `'failed'`, which in step 4 is always NULL. Any `chain_facts` row. Any `forward_returns` row. The three `PHASE_A2_COLUMNS`.

**Behaviours.** No autosave and no debounce. No optimistic updates. No error boundaries, loading skeletons or transitions. No clamping — out of range is rejected and the refusal is shown verbatim. No arithmetic on any rubric value anywhere, in either tier. No `drizzle-kit push`, ever.

**Dependencies.** No component library, no form library (a resolver restating the bounds would be a fourth copy pinned by nothing), no state manager, no data-fetching library, no auth, no `user_id`, no jsdom, no `@testing-library/react`, no `@tanstack/router-plugin` and no `@tanstack/router-cli` (Start's vite plugin carries the route generator), no `openai`, no `viem`, no `paths` alias in `apps/web`.

**Start's server, beyond the two things it does here.** No `createServerFn` anywhere. No `loader` and no `beforeLoad` on any route — `boundary.test.ts` fails on one in `__root.tsx`, and the coin list fetches in an effect for the same reason. No second outbound request: `routes/api.$.ts` forwards `/api` to loopback and that is the whole list. The citation verifier and the EvidenceFinder are `apps/api`'s, in steps 5 and 8, because that is the tier that holds keys.

### Files that should not exist when this plan is done

`apps/web/src/components/ui/*` · `apps/web/src/lib/scoring.ts` or `totals.ts` or anything that adds numbers · `apps/web/src/lib/constants.ts` holding a rubric maximum · `apps/web/src/store/*` · `apps/web/src/routes/ledger.tsx` · `apps/web/src/routes/chain.tsx` · `apps/web/src/lib/auth.ts` · `apps/web/src/i18n/*` · any `*.test.tsx` · `apps/web/Dockerfile` · `apps/api/src/sources/*` · `apps/api/src/verify/*` · `apps/api/src/evidence/*` · `apps/api/src/chain/*` · `apps/api/src/providers.ts` (the spec names it `evidence/providers.ts` when it lands) · `apps/api/scripts/rescore.ts`.

`apps/web/src/routeTree.gen.ts` is **not** on that list any more: it is generated by the Start plugin, it is committed, and `biome.json` excludes it by name. Two symbols should not exist anywhere either: a `snake()` function, and a `commitAllowed` boolean.

```bash
cd /home/dev/projects/trade-god
test -e apps/web/src/routeTree.gen.ts && echo "the generated route tree is committed"
git diff --exit-code apps/web/src/routeTree.gen.ts && echo "and it matches the route files"
grep -rn "function snake\|commitAllowed" apps/ || echo "neither symbol exists"
cd apps/web && pnpm test
```

**Do not check the server-function ban with a bare `grep`.** `routes/__root.tsx` and
`routes/index.tsx` both *name* `createServerFn` and `beforeLoad` in their comments, on purpose, so
`grep -rn "createServerFn\|beforeLoad" apps/web/src` matches the two files it is meant to clear.
`boundary.test.ts` blanks comment bodies before scanning, which is exactly why that check is a test
and not a one-liner — the same reason the bundle scan is a test and not a `grep ... || true`.

---

## What this hands to step 5 (the verifier) and step 6 (the commit gate)

Each of these is a decision step 4 has already made by writing something, or a hole it has deliberately left open. They are written out so the next plan inherits the fix rather than the bug.

1. **`CITABLE_FIELDS` is a commitment.** Step 4 writes those 16 strings plus `team:<uuid>` into `citations.field`. The commit gate owns the vocabulary and must adopt or narrow the list; anything it drops leaves rows nothing reads.
2. **`readReportRows` must filter on `selected_at IS NOT NULL`.** Step 4 stamps `selected_at` on every insert because a human-typed citation is selected by definition, so today the filter is a no-op — but `selected_at IS NULL` is reserved for an unselected model candidate, and §8.2 is explicit that one is never a blocker and never a credential.
3. **The three sub-scores are required only on a PASSED report.** `rs_gate_completeness` fires on `product_passed`, so a dropped report can still commit with NULL sub-scores and `productGate()` would throw inside the commit transaction. The gate must check them before it calls the frozen function, and answer with a named blocker rather than a 500.
4. **`waived_citation_count` is a blocker row that renders `unknown` today.** So are `narrative_total`, `team_weighted_score`, both accrual flows and `discovery_premium_kind`. Step 6 fills them by writing the columns, not by editing `blockers.ts`.
5. **The liquidity freshness window is still unset.** The schema now carries `liquidity_depth_measured_at`, `liquidity_top_pool_measured_at` and `liquidity_tier_assigned_at`, and step 4 guarantees the tier is never older than its inputs — but nothing says how old is too old. Whatever number is chosen redefines "fresh" for reports committed under the old one, so it wants setting once, before report #1.
6. **A committed report's editor is read-only by `disabled`, and by CP001 underneath.** The editor greys every control when `status !== 'draft'`; the triggers refuse the write regardless, and `app.onError` maps CP001 to a 409. Do not let step 6 rely on the greying.
7. **`citations_reset_verification` exists for an edit path step 4 does not have.** Step 4 has add and remove only; while `origin` is always `'human'` and `status` always `'unverified'` the two are equivalent. Step 5 needs the edit route and the trigger is already there for it.
8. **The read path should serve figures as TEXT, not as `number`.** `GET /reports/:id` returns `double precision` columns as JSON numbers, so the browser has to turn one back into digits to seed its box — and `String` writes an exponent below 1e-6, which the write path refuses (see "Known limits"). The whole point of this plan's wire design is that a number crosses as the string a human typed; the read direction is the half that did not get it, because fixing it means a text projection in `readReport` and every section seeding from it instead of from `numberOf`. Step 5 touches `readReport` anyway for `selected_at`; do it there rather than teaching `apps/web` to parse.

---

## Open, and the owner's to rule on — not blocking this plan

| # | Question | Where it bites |
|---|---|---|
| 1 | **Must a dropped project state why it was dropped?** The schema says no; the rejected population is the whole reason drops are committed. An app-level rule if it is wanted, and it belongs to step 6 rather than to step 4 inventing it. | step 6's gate |
| 2 | **Where does a liquidity or pool URL live — the provenance columns, `citations`, or both?** `framework/06` asks for a link to the largest DEX pool; the schema has dedicated provenance columns *and* a citations table that can key on any field. Step 4 offers both, which creates two sources that can disagree inside an immutable report. | step 5 / step 6 |
| 3 | **`coins.address_sources` as a raw URL array, or as citations?** The CHECK requires ≥ 2 for a contract address and the editor is the only writer — but the project's thesis is that a claim is backed by a *verified quote*, and a raw URL array on `coins` sits outside that. `coins` also has no immutability trigger, so those URLs stay mutable forever. | step 5 |
| 4 | **Should the downstream sections lock while the gate is unscored, or only when it explicitly fails?** `framework/02` and `/06` say run the product test first and kill the project on a failure; neither says an unfinished gate closes anything. Step 4 locks nothing and says so on the page. | step 6 |
| 5 | **`chain_facts` is deliberately outside the immutability trigger set**, so a committed report's on-chain evidence stays rewritable. Recorded as open in `decisions.md`; it does not affect step 4 and should not be closed by accident when the chain panel lands. | Phase A.2 |

---

## Known limits of what this plan guarantees

- **The build-time leak guard rides on an UNPINNED transitive.** `importProtection` — the thing that
  stops `import { createApp }` from shipping drizzle and pg to the browser, and the single strongest
  reason this plan kept TanStack Start — is emitted by `@tanstack/start-plugin-core`, not by
  `@tanstack/react-start`. Pinning `@tanstack/react-start` to 1.168.57 does **not** pin it: it
  resolved to **1.171.47** during verification (stack frame
  `node_modules/.pnpm/@tanstack+start-plugin-core@1.171.47_.../vite/import-protection-plugin/plugin.js`).
  So a `pnpm update` can change the guard's behaviour, or its diagnostic text, without any version in
  `apps/web/package.json` moving. Two consequences: the expected trace quoted in Task 4 Step 12 is
  the 1.171.47 wording and may drift, and the guard itself could in principle weaken silently. The
  bundle scan in `boundary.test.ts` is the backstop and is deliberately NOT removed just because the
  build-time check exists — belt and braces, because only one of the two is pinned.
- **The blocker list is complete with respect to `rs_gate_completeness`, and that is all.** Every conjunct of that constraint has a row, mechanically. Nothing here promises the constraint is the whole commit gate — step 6 will add citation coverage, waiver rules and the frozen evaluations, and those are `unknown` rows or absent rows today.
- **`apps/web`'s typecheck compiles `apps/api`'s sources.** Fifteen of them, plus 83 `@types/node` files, plus drizzle's `.d.ts` tree behind them. Two packages report the same error, and a broken api compile blocks the web typecheck. It also compiles `routeTree.gen.ts`, which carries `@ts-nocheck` and is therefore checked by nothing but CI's `git diff`.
- **`hc<AppType>` instantiation depth is a watched number, not a solved problem.** An adversary measured 1.74s at 52 routes against the real 62-column `$inferSelect`; this plan ships thirteen. `time pnpm --filter @coinpicks/web run typecheck` is about 2.1s today. Treat a jump as the early warning, and **do not unpin TypeScript while adding routes.**
- **Nothing asserts the browser renders.** There is no jsdom, no `@testing-library/react` and no render test; the web suite is the two scans — `boundary.test.ts` over the source, `bundle.test.ts` over `dist/client` and `dist/server`. Under Start that also means nothing asserts the **server** render works beyond Task 4 Step 13's `curl`, which is one manual check of one page. The route suite covers the API's money path against real Postgres, and Tasks 5–7 each end with a manual walk-through whose expected text is written down. A render test suite is a step-6 decision, not something to add here by reflex.
- **`pnpm dev` runs two processes with no supervisor.** If the api dies, `routes/api.$.ts`'s `fetch` to loopback fails and the editor shows the refusal `readError` builds from whatever comes back. That is fine for one user on loopback and is not worth a process manager. `strictPort` means the web process refuses to start on the wrong port rather than moving quietly — which on this machine is not hypothetical, because the sibling repo holds 5173.
- **A figure below 1e-6 or at/above 1e21 has to be typed out in full to be saved again.** `numberOf` seeds a box with `String(value)`, and `String(1e-7)` is `'1e-7'`, which the API's digit regex refuses by design. The reachable case is a sub-0.0001% `accrualCaptureShare` or `accrualPct`: because a section sends all of its fields, editing the accrual rationale would come back `INVALID` on a fraction nobody touched. It is loud, named and recoverable by typing `0.0000001`. Both cheap repairs were tried and are worse — expanding the exponent in the browser needs `Number(parts[3])` and trips `boundary.test.ts` (measured: `editor/fields.tsx:38 const point = whole.length + Number(parts[3])`), and `toFixed(20)` silently rewrites `1.5e-20` as `0.00000000000000000002`. Widening the server's regex to admit exponents would re-open `'1e999'` → `Infinity`. The fix belongs on the read path; see item 8 of "What this hands to step 5".
