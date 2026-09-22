# CoinPicks — Plan 3: the minimal report editor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator create a draft report for a coin and fill every field the commit gate will require — through a write path where a typo cannot silently empty a column, a blank box cannot become a measured zero, a fractional score cannot be rounded into range by Postgres, a citation cannot name a person who does not exist, and the list of what is still missing is generated from the same array that generates the database's CHECK constraint.

**Architecture:** `apps/api/src/db/gate-fields.ts` holds `GATE_REQUIREMENTS` — one array that generates both `rs_gate_completeness` (through `schema.ts` and a new `0003` migration) and the editor's blocker list (through `reports/blockers.ts`). `apps/api/src/app.ts` exports `createApp(db, migrations)`, a Hono app of thirteen routes; `server.ts` migrates as the owner, asserts the guards, closes that pool, opens the `coinpicks_app` pool and serves it on `PORT` (default 8789). Every number crosses the wire as the string the operator typed and is parsed once, by zod, through the frozen `assertIntegerRange` / `assertNonNegative` / `assertRange`. `apps/web` is a plain Vite 8 SPA on `@tanstack/react-router` with code-based routes; it reaches the API only through `hc<AppType>` and only through `import type`, which a test enforces by reading every source file. One Save button per section, one CAS bump per save.

**Tech Stack:** pnpm 10.33.0 workspace, `packages: ["apps/*"]`. Runtime **Node v26.8.1** — it executes `.ts` directly, in **strip-only mode** (see Global Constraints).

- `apps/api` adds: hono 4.13.8, @hono/zod-validator 0.9.1, @hono/node-server 2.1.1, zod 4.6.5. Already there: drizzle-orm 0.45.3, pg 8.23.0, drizzle-kit 0.31.11 (dev), @types/pg 8.23.1.
- `apps/web` is new: @tanstack/react-router 1.170.38, react 19.3.0, react-dom 19.3.0, hono 4.13.8 (for `hc`); dev: vite 8.3.0, @vitejs/plugin-react 6.1.1, tailwindcss 4.3.3, @tailwindcss/vite 4.3.3, @types/react 19.3.0, @types/react-dom 19.3.0, @types/node (catalog), typescript (catalog), vitest (catalog).
- **Catalog pins in `pnpm-workspace.yaml` are a deliberate deviation from "always latest"** and must be stated as such wherever these versions are listed: typescript 5.9.3 (latest is 7.0.2, the Go-native compiler, a fresh major) and vitest 4.1.11 (latest is 5.0.1, days old). Revisit the week after report #1 commits.
- **`@tanstack/react-start` is NOT used, and `routeTree.gen.ts` does not exist.** See decision 1 below; it needs a dated `agents/decisions.md` entry, which Task 8 writes.
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
| 5 | A one-word import slip shipped the ORM to the browser with a green build. Measured here: `import type { AppType }` gives a 571.57 kB bundle with no drizzle in it; `import { type AppType, createApp }` plus one value use gives 716.11 kB **with drizzle in it**, `vite build` exit 0, no warning | Task 4 — `boundary.test.ts` reads every file under `apps/web/src` and fails on any `'@coinpicks/api'` line that is not `import type` |
| 6 | Inputs seeded local state with `useState(value)` and never re-synced, so after a 409 the editor re-applied pre-conflict values over the winner | Task 5 — each section is keyed on a per-section seed token; a 409 bumps every token, re-reads, and says so |
| 7 | `snake('liquidityDepth2pctUsd')` yields `liquidity_depth2pct_usd`; the column is `liquidity_depth_2pct_usd`. The UI used the same wrong string to add and to filter, so it looked right | Task 2 — `CITABLE_FIELDS` reads `reportScores.<key>.name` off the drizzle column; `draft-columns.test.ts` asserts the digit case |
| 8 | A citation could be attached to a team member that was never saved: `TeamEditor` minted a browser-side uuid and `citations.field` is text with no FK | Tasks 3 and 6 — `addCitation` checks `team:<uuid>` against `report_team` inside the transaction; the editor offers evidence only for server rows |
| 9 | `rs_gate_completeness` is INERT on a draft — it is `CASE WHEN product_passed THEN ... ELSE true END` and `product_passed` is commit-written. Confirmed: `SELECT CASE WHEN NULL::boolean THEN false ELSE true END` returns `t` | Task 1 — one array generates both the CHECK and the blocker list, and a test asserts the committed .sql still matches |
| 10 | The naive `rs_gate_completeness` did not require the three product sub-scores. Confirmed on 16.13: `CASE WHEN true THEN (15 = NULL::int + 5 + 5) ELSE true END` is NULL and a CHECK accepts NULL, so `rs_product_total_is_sum` never forced them | Task 1 — `PRODUCT_EASE` / `PRODUCT_HAIR_FIRE` / `PRODUCT_EXCLUSIVITY` are conjuncts of the generated constraint |
| 11 | The design's tsconfig for `apps/web` did not compile: overriding only `moduleResolution` gives `TS5095` and `TS5109`, because the base sets `module: nodenext` | Task 4 — five keys, named, and compiled |
| 12 | `pnpm check` failed on the file the design ordered committed (`routeTree.gen.ts`), and `pnpm format` then fought the generator | Task 4 — code-based routes; the file does not exist |
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
biome check                              -> Checked 68 files. No fixes applied. (exit 0)
apps/api  vitest run                     -> Test Files 14 passed, Tests 119 passed
apps/web  vitest run                     -> Test Files 1 passed, Tests 5 passed
apps/web  vite build                     -> dist/assets/index-*.js 571.57 kB; grep for
                                            pg-protocol / drizzle / node:crypto -> 0 hits
drizzle-kit generate --name gate_completeness_generated
                                         -> drizzle/0003_gate_completeness_generated.sql
psql < 0000,0001,0002,0003               -> applied clean to a fresh database on PG 16.13
node src/server.ts                       -> coinpicks api on http://127.0.0.1:8789
curl 127.0.0.1:8789/health               -> {"ok":true,"migrations":4,"scoringVersion":"coinpicks-2026-09-21"}
vite dev + curl localhost:5173/api/health-> the same JSON through the proxy
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
apps/web  vitest run                     -> Test Files 1 passed, Tests 5 passed
apps/web  vite build                     -> 571.57 kB; grep for pg-protocol / drizzle /
                                            node:crypto -> 0
apps/web  the leak probe, re-measured    -> 716.11 kB WITH drizzle, `vite build` exit 0 and
                                            silent, boundary.test.ts fails naming
                                            lib/client.ts:1
biome check                              -> Checked 68 files. No fixes applied.
```

Four facts the audits disputed were re-measured rather than taken on trust, and two of the four went against the auditor:

- The Task 4 file count really is **5**, so `toBeGreaterThan(5)` really does fail there. Counted with the scanner's own `readdirSync`/`statSync` walk over the Task-4 file set.
- `evaluateBlockers` on an all-NULL draft gives **33 / 1 clear / 26 blocking / 6 unknown** with `DISCOVERY_MARKET_CAP` the only clear row, and after one `productEase` it is **2 clear / 25 blocking / 6 unknown**. The trace above said 5 clear; it now says what the function prints.
- `agents/CONTEXT.md`'s sub-score sentence is at lines **60–62**, not 59–61. One auditor said otherwise; `grep -n` says 60, 61, 62. Chore 1 is unchanged.
- `.superRefine()` is **not** `@deprecated` in the pinned zod 4.6.5 — checked in the installed `zod/v4/classic/schemas.d.cts`, where it sits undecorated beside `refine`. `z.string().uuid()` is, which is why this plan already uses `z.uuid()`. Task 2 Step 1 now records the check.

---

## Global Constraints

- **Framework formulas are frozen.** Every weight, range and threshold comes from the spec's "Normative formulas (frozen)" section and is reproduced exactly. Never adjust one because it looks better calibrated — raise it with the user instead.
- **The frozen formulas are evaluated in exactly one place: the commit transaction.** Build-order step 4 does not evaluate any of them, and **nothing in this plan adds numbers together.** `productGate`, `narrativeTotal`, `teamWeightedScore`, `annualHolderFlow` and `discoveryPremium` are never called by the editor or by its routes. What the editor *does* use from `scoring/` is the three validators — `assertIntegerRange`, `assertRange`, `assertNonNegative` — which reject out-of-range input rather than computing anything. That distinction is the whole reason there is no `/preview` route in this plan.
- **Ranges are rejected, never clamped.** An out-of-range score is a named 422 carrying the frozen message; it is not coerced.
- Rubric sub-scores are **whole numbers** (ruled 2026-09-21). Derived values such as the team weighted score are not.
- **Drizzle alone authors DDL.** `apps/api/src/db/schema.ts` declares every column; `apps/api/drizzle/*.sql` and `meta/_journal.json` are both committed; the API applies them at boot before the port is taken. **Never `drizzle-kit push`.** Never edit an applied migration — Task 1 adds `0003`, it does not touch `0000`.
- **Node 26 strips types; it does not transform them.** Verified on v26.8.1: `--experimental-transform-types` no longer exists. So no parameter properties, no `enum`, no `namespace`, no decorators, no `import =` anywhere under `apps/`. `erasableSyntaxOnly: true` makes a slip a compile error (`TS1294`). **Every relative import under `apps/api` carries an explicit `.ts`**, and every relative import under `apps/web` carries an explicit `.ts` or `.tsx` — one repo-wide rule beats two, and `allowImportingTsExtensions` is inherited by both.
- **Biome 2.5.14: single quotes, no semicolons, 100 columns.** `pnpm check` must pass on every file this plan commits. After `drizzle-kit generate`, **two** files come back Biome-unformatted — the new `meta/<n>_snapshot.json` and `meta/_journal.json`, which the generator rewrites without a trailing newline. `pnpm check --write` fixes both, exactly as it already did for `0000`–`0002`; a bare `pnpm check` first reports two errors, not one.
- **The API listens on `PORT`, default 8789.** Do not carry the claim that 8787 is held by `my-teacher-api-1` into any file: `docker ps` shows only `coinpicks-db` and `medi-pal-db-1`, and `ss -ltn` shows nothing on 8787 or 8789. Task 8 strikes that comment. A fabricated verification note in a repo whose standing lesson is fabricated verification notes should not survive another commit.
- **The request pool is `coinpicks_app`: NOSUPERUSER, owns nothing, DML on seven tables only.** `server.ts` keeps decision A's order: owner pool, migrate, assert the guards, close, then the app pool, then the port.
- **Every DB test scopes its queries by ids it created.** `vitest.config.ts` sets `fileParallelism: false` and one `coinpicks_test` database is shared; the triggers refuse TRUNCATE and refuse DELETE on a committed report, so there is no between-tests reset.
- Commits land on `main` directly (personal repo; the owner has said branches are unnecessary here).
- Commits never carry AI attribution — no `Co-Authored-By` trailers, no generated-with footers.
- `research/` and `tests/research/` must stay green: `python -m pytest -q` is **111 passed** and must remain so.
- After each task: `cd apps/api && pnpm test && pnpm typecheck`, `cd apps/web && pnpm test && pnpm typecheck` once it exists, and from the repo root `pnpm check --write && pnpm check`. All clean before the commit step.

---

## Task list

| Task | What it leaves behind |
|---|---|
| 1 | `db/gate-fields.ts` — one required-field array — generating both `rs_gate_completeness` (migration `0003`) and `reports/blockers.ts`, with the test that keeps them together |
| 2 | The wire's validation layer: `reports/{bounds,citable-fields,draft-columns,patch-schemas}.ts`. Numbers arrive as strings and are parsed once, through the frozen validators |
| 3 | The API: `reports/store.ts`, `app.ts` (thirteen routes), `server.ts` on Hono, and `routes.test.ts` — twelve cases against real Postgres |
| 4 | `apps/web`: the tsconfig split that compiles, the Vite SPA, `hc<AppType>`, the coin list, and `boundary.test.ts` |
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
### Task 4: `apps/web` — the tsconfig split that compiles, the SPA, and the boundary guard

**The tsconfig arrangement is the first thing to get right, because the design's version does not build.** Extending `tsconfig.base.json` and overriding only `moduleResolution` yields, on the pinned tsc 5.9.3:

```
error TS5095: Option 'bundler' can only be used when 'module' is set to 'preserve' or to 'es2015' or later.
error TS5109: Option 'moduleResolution' must be set to 'NodeNext' (or left unspecified) when option 'module' is set to 'NodeNext'.
```

because the base sets `module: nodenext` and that is inherited. Five keys are overridden, not one. The set below was compiled clean (exit 0, 2.1s) against the real `tsconfig.base.json` with React 19 JSX and explicit `.ts`/`.tsx` relative imports, with the inherited `erasableSyntaxOnly`, `verbatimModuleSyntax`, `allowImportingTsExtensions` and `noUncheckedIndexedAccess` all still active.

**`"node"` is in `types` on purpose.** `boundary.test.ts` reads the source tree with `node:fs`, and it has to live in the same program as the code it guards. It also makes visible something that happens anyway: `tsc --listFiles` shows **15 `apps/api` files and 83 `@types/node` files** entering the web program through `import type { AppType }`, whatever `types` says. The consequence to know about is that `setTimeout` is typed as returning `Timeout`, not `number` — step 4 uses no timers, and anything that stores one later writes `ReturnType<typeof setTimeout>`.

**There is no `@tanstack/react-start` and no `routeTree.gen.ts`.** Decision, recorded in Task 8: routes are code-based. The generated tree fails `biome check` (`assist/source/organizeImports` as an error, plus `noExplicitAny` and `noUnusedImports` on the generator's own output), its header asks to be excluded from the linter, `pnpm format` then reorders imports that the next `vite dev` regenerates back, and nothing asserts the committed tree matches the route files. Two routes do not need a code generator. SSR, server functions and head/meta also buy nothing on loopback, single-user, no-SEO, with the backend deliberately outside Start's server — and the design's own risk list conceded that SPA mode does not stop a loader added to `__root.tsx` later putting the web tier back on the network.

**Files:**
- Create: `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/vite.config.ts`, `apps/web/vitest.config.ts`, `apps/web/index.html`
- Create: `apps/web/src/index.css`, `apps/web/src/main.tsx`, `apps/web/src/router.tsx`, `apps/web/src/lib/client.ts`, `apps/web/src/pages/CoinList.tsx`
- Create: `apps/web/src/pages/ReportEditor.tsx` (a stub in this task; Task 5 writes it properly)
- Modify: `package.json` (the root `dev` script)
- Test: `apps/web/src/boundary.test.ts`

**Interfaces:**
- Consumes: `type AppType` from `@coinpicks/api`, by `import type` and by nothing else.
- Produces, from `src/lib/client.ts`: `client`, `ReportPayload`, `Scores`, `TeamRow`, `Citation`, `Blocker`, `Bounds`, `ProductBody`, `LiquidityBody`, `NarrativeBody`, `AccrualBody`, `RiskBody`, `TeamBody`, `CitationBody`, `type Fields<T> = Omit<T, 'version'>`, `interface ApiError`, `readError(response): Promise<ApiError>`.
- Produces, from `src/router.tsx`: `router`, plus the `@tanstack/react-router` `Register` augmentation that makes `<Link to="/reports/$reportId">` type-checked.

- [ ] **Step 1: The package**

Create `apps/web/package.json`:

```json
{
  "name": "@coinpicks/web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check"
  },
  "dependencies": {
    "@coinpicks/api": "workspace:*",
    "@tanstack/react-router": "1.170.38",
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
- [ ] **Step 3: Vite, vitest, the shell**

Create `apps/web/vite.config.ts`:

```ts
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8789',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```
Create `apps/web/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
```
Create `apps/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CoinPicks</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```
Create `apps/web/src/index.css`:

```css
@import "tailwindcss";
```
- [ ] **Step 4: The typed client — the one line the whole boundary rests on**

Create `apps/web/src/lib/client.ts`:

```ts
import type { AppType } from '@coinpicks/api'
import { hc, type InferRequestType, type InferResponseType } from 'hono/client'

/*
 * `import type`, and the whole line is type-only.
 *
 * `import { type AppType, createApp } from '@coinpicks/api'` — one word different, a genuine
 * value use — makes `vite build` exit 0 with no warning and grows the production bundle from
 * 571.57 kB to 716.11 kB, with drizzle in it. Biome's `useImportType` does not fire on the mixed
 * form and tsc under `verbatimModuleSyntax` accepts it, so `boundary.test.ts` is what actually
 * holds this line in place.
 */

/** Absolute, because `hc` builds URLs and a relative base is one more thing to be unsure about. */
export const client = hc<AppType>(`${window.location.origin}/api`)

export type ReportPayload = InferResponseType<(typeof client.reports)[':reportId']['$get'], 200>
export type Scores = ReportPayload['scores']
export type TeamRow = ReportPayload['team'][number]
export type Citation = ReportPayload['citations'][number]
export type Blocker = ReportPayload['blockers'][number]
export type Bounds = ReportPayload['bounds']

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
- [ ] **Step 5: Routes, code-based**

Create `apps/web/src/router.tsx`:

```tsx
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  useParams,
} from '@tanstack/react-router'
import { CoinList } from './pages/CoinList.tsx'
import { ReportEditor } from './pages/ReportEditor.tsx'

/*
 * CODE-BASED ROUTES, not file-based.
 *
 * There is no `routeTree.gen.ts`: a committed generated file fails `biome check`
 * (assist/source/organizeImports fires as an error, and `pnpm format` then reorders imports that
 * the next `vite dev` regenerates back), its own header asks to be excluded from the linter, and
 * nothing asserts the committed tree matches the route files. Two routes do not need a code
 * generator.
 */

const rootRoute = createRootRoute({ component: Outlet })

const coinsRoute = createRoute({
  component: CoinList,
  getParentRoute: () => rootRoute,
  path: '/',
})

function ReportRoute() {
  const { reportId } = useParams({ from: '/reports/$reportId' })
  return <ReportEditor reportId={reportId} />
}

const reportRoute = createRoute({
  component: ReportRoute,
  getParentRoute: () => rootRoute,
  path: '/reports/$reportId',
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([coinsRoute, reportRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
```
Create `apps/web/src/main.tsx`:

```tsx
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { router } from './router.tsx'

const host = document.getElementById('root')
if (host === null) throw new Error('index.html has no #root')

createRoot(host).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
```
- [ ] **Step 6: The coin list**

Create `apps/web/src/pages/CoinList.tsx`:

```tsx
import { Link, useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { type ApiError, client, readError } from '../lib/client.ts'

type CoinRows = Awaited<ReturnType<typeof fetchCoins>>

async function fetchCoins() {
  const response = await client.coins.$get()
  if (!response.ok) throw await readError(response)
  const body = await response.json()
  return body.rows
}

export function CoinList() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<CoinRows | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [form, setForm] = useState({
    symbol: '',
    name: '',
    chain: '',
    contractAddress: '',
    coingeckoId: '',
    addressSources: '',
  })
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(await fetchCoins())
      setError(null)
    } catch (thrown) {
      setError(thrown as ApiError)
    }
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
    setForm({
      symbol: '',
      name: '',
      chain: '',
      contractAddress: '',
      coingeckoId: '',
      addressSources: '',
    })
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
And a stub so the router compiles — Task 5 replaces this file entirely. Create `apps/web/src/pages/ReportEditor.tsx`:

```tsx
export function ReportEditor({ reportId }: { reportId: string }) {
  return <main className="mx-auto max-w-5xl p-6">The editor for {reportId} lands in Task 5.</main>
}
```

- [ ] **Step 7: The boundary guard**

Create `apps/web/src/boundary.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/*
 * THE TIER BOUNDARY, ENFORCED MECHANICALLY.
 *
 * Measured, not assumed, at the finished tree: with `import type { AppType } from
 * '@coinpicks/api'` the production bundle is 571.57 kB and contains no drizzle. Changing that
 * one line to `import { type AppType, createApp } from '@coinpicks/api'` plus one value use
 * makes `vite build` exit 0 with no error, and the bundle becomes 716.11 kB WITH drizzle in it.
 * The same probe on the day this file is written, with five source files, is 535.31 kB against
 * 679.88 kB.
 * Biome's useImportType does not fire on the mixed form and tsc under verbatimModuleSyntax
 * accepts it, so the only signal is a bundle nobody measures. That is why this is a test.
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
    return /\.tsx?$/.test(path) && !path.endsWith('.test.ts') ? [path] : []
  })
}

const FILES: SourceFile[] = sourceFiles(SRC).map((path) => ({
  path: path.slice(SRC.length + 1),
  lines: stripComments(readFileSync(path, 'utf8')).split('\n'),
}))

function offenders(pattern: RegExp): string[] {
  return FILES.flatMap((file) =>
    file.lines
      .map((line, index) => ({ line, number: index + 1 }))
      .filter((entry) => pattern.test(entry.line))
      .map((entry) => `${file.path}:${String(entry.number)} ${entry.line.trim()}`),
  )
}

describe('the web tier cannot reach the api tier at runtime', () => {
  it('scans every source file', () => {
    // Five at the end of Task 4 (main, router, lib/client, CoinList, ReportEditor) and fourteen
    // once Task 7 lands. The bound is the lower number on purpose: this case exists to stop the
    // scan passing because it matched nothing, not to count the tree.
    expect(FILES.length).toBeGreaterThanOrEqual(5)
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
    expect(found, 'a value import of @coinpicks/api ships drizzle and pg to the browser').toEqual(
      [],
    )
  })

  it('imports no node builtin, no driver and no ORM', () => {
    expect(offenders(/from '(node:[a-z/]+|pg|drizzle-orm[a-z/-]*)'/)).toEqual([])
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
The last two cases are dead weight until Tasks 5–7 add the code they guard; they are written now because the guard has to exist before the code it guards, not after.

- [ ] **Step 8: Make `pnpm dev` start both apps**

The root `dev` script names the api package only, so the setup sequence would have started one process and then curled a port nothing was listening on. In `/home/dev/projects/trade-god/package.json` replace

```json
    "dev": "pnpm --filter @coinpicks/api --parallel run dev",
```

with

```json
    "dev": "pnpm --parallel --if-present run dev",
```

- [ ] **Step 9: Compile it, build it, and measure the bundle**

```bash
cd /home/dev/projects/trade-god/apps/web
pnpm typecheck
pnpm test
pnpm build
```
Expected: typecheck silent in about two seconds; `Tests 5 passed` — five cases over the five source files this task leaves behind (`main.tsx`, `router.tsx`, `lib/client.ts`, `pages/CoinList.tsx`, `pages/ReportEditor.tsx`; `index.css` does not match `/\.tsx?$/` and `boundary.test.ts` excludes itself), which is why the scan's floor is `toBeGreaterThanOrEqual(5)` and not `toBeGreaterThan(5)`; and a build reporting roughly

```
dist/index.html                   0.39 kB
dist/assets/index-*.css           7.23 kB
dist/assets/index-*.js          535.31 kB
```

with rolldown's generic "some chunks are larger than 500 kB" note, which is React plus the router and is expected. Those are the numbers for **this task's** five source files; Tailwind scans the source for class names, so both grow as Tasks 5–7 add sections. At the end of Task 7 the same build reports `11.99 kB` and `571.57 kB`, which is the pair quoted everywhere else in this plan.

Then the measurement that matters:

```bash
grep -c -e pg-protocol -e drizzle -e node:crypto dist/assets/index-*.js || true
```
Expected: `0`. The `|| true` is not decoration: `grep -c` prints `0` and **exits 1** when there are no matches, which is the result being asked for.

- [ ] **Step 10: Break the boundary on purpose, watch both signals, put it back**

This is the one finding that cannot be checked by reading. In `apps/web/src/lib/client.ts`, temporarily change the first line to

```ts
import { type AppType, createApp } from '@coinpicks/api'
```

and add, directly above the `export const client` line,

```ts
export const leak = createApp
```

Then:

```bash
cd /home/dev/projects/trade-god/apps/web && pnpm build && pnpm test
```
Expected: `vite build` **exits 0 with no error and no warning**, the bundle grows from 535.31 kB to **679.88 kB** (571.57 kB → 716.11 kB once Task 7 has landed — the +144 kB is drizzle either way), `grep -c drizzle dist/assets/index-*.js` is now `1`, and `boundary.test.ts` fails with

```
imports @coinpicks/api only with `import type`
a value import of @coinpicks/api ships drizzle and pg to the browser
+ [ "lib/client.ts:1 import { type AppType, createApp } from '@coinpicks/api'" ]
```

Biome says nothing: `useImportType` only fires when *every* binding in the specifier is type-only, and tsc under `verbatimModuleSyntax` accepts the mixed form. Revert both edits, re-run `pnpm test` and see 5 passed.

- [ ] **Step 11: Run the two servers together**

```bash
cd /home/dev/projects/trade-god && pnpm dev
```
In another shell:
```bash
curl -s http://127.0.0.1:8789/health
curl -s http://localhost:5173/api/health
```
Expected: the same `{"ok":true,"migrations":4,"scoringVersion":"coinpicks-2026-09-21"}` from both — the first proves the API, the second proves the proxy. Open `http://localhost:5173/`, add a coin, and press "new draft"; the stub editor says which task fills it in.

If the api instead exits with `4 migrations are committed but 5 are applied`, a migration was applied outside the migrator and `drizzle.__drizzle_migrations` has a duplicate. Delete the row whose `hash` is not one of the four `.sql` files' sha256 and start again; Task 1 Step 7 applies `0003` through the migrator precisely so this cannot happen.

- [ ] **Step 12: Green, then commit**

```bash
cd /home/dev/projects/trade-god && pnpm -r run typecheck && pnpm -r run test
pnpm check --write && pnpm check
```

```bash
git add -A
git commit -m "feat: apps/web -- a plain Vite SPA, code-based routes, and a boundary test

The tsconfig overrides five keys, not one: the base sets module: nodenext, so
moduleResolution: bundler alone is TS5095 + TS5109.

No TanStack Start and no routeTree.gen.ts. The generated tree fails biome check
as an error, its own header asks to be excluded from the linter, pnpm format
then fights the generator, and nothing asserts the committed tree matches the
route files. Two routes do not need codegen.

boundary.test.ts exists because the leak is invisible: import { type AppType,
app } plus one value use builds clean and silently, and only the bundle knows
-- measured here at 570 kB without it and 715 kB with drizzle in it."
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
- Modify: `apps/web/src/pages/ReportEditor.tsx` (replaces the Task 4 stub entirely)

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

Replace `apps/web/src/pages/ReportEditor.tsx` entirely:

```tsx
import { Link } from '@tanstack/react-router'
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

export function ReportEditor({ reportId }: { reportId: string }) {
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
Expected: typecheck silent, `Tests 5 passed`, Biome clean, and both servers up. Open `http://localhost:5173/`, add a coin, press "new draft". The product gate and Risk notes sections render; the blocker list arrives in Task 6 and the other four sections in Task 7.

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
- Modify: `apps/web/src/pages/ReportEditor.tsx` (two edits)

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

In `apps/web/src/pages/ReportEditor.tsx`, add the import:

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
- Modify: `apps/web/src/pages/ReportEditor.tsx` (the final version)

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

Replace `apps/web/src/pages/ReportEditor.tsx` entirely:

```tsx
import { Link } from '@tanstack/react-router'
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

export function ReportEditor({ reportId }: { reportId: string }) {
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
Expected: api `Tests 119 passed` over 14 files, web `Tests 5 passed`, pytest `111 passed`, Biome clean.

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
- Modify: `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` (§9 and two rows of the stack table — the frozen formulas section is not touched)
- Modify: `agents/CONTEXT.md` (chore 1)
- Modify: `apps/api/src/server.ts` — already done in Task 3 (chore 2); verify
- Modify: `.env.example` (chore 3)
- Modify: `.github/workflows/ci.yml`
- Modify: `agents/decisions.md`, `agents/roadmap.md`

**Interfaces:**
- Consumes: nothing. **No file under `apps/` changes in this task at all** — every interface is already final. What changes is `.env.example`, the CI job, and the written record.
- Produces: no export. It produces the written record: the amended `CLAUDE.md` rules, the amended spec §9, the dated `agents/decisions.md` entry the TanStack Start reversal needs, and a CI step that builds the client so the bundle `boundary.test.ts` reasons about is actually produced.

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
Expected: no output. Task 3 replaced `server.ts`'s comment. The claim is false on this machine today — `docker ps` lists `coinpicks-db` and `medi-pal-db-1` and nothing else, `docker ps -a` lists no container bound to 8787 at all, and `ss -ltn` shows nothing on 8787 or 8789. A fabricated verification note in a repo whose standing lesson is fabricated verification notes should not survive another commit.

Then confirm the spec is the only remaining live carrier, so Step 4 knows what it is fixing:

```bash
grep -rn "8787" docs/superpowers/specs/
```
Expected: one hit, `2026-09-21-coin-research-platform-design.md:67`.

- [ ] **Step 3: Chore 3 — the stray fence in `.env.example`**

Delete line 35 of `.env.example`, which is a bare ```` ``` ```` left over from a paste. The `PORT=8789` line above it is correct and stays.

- [ ] **Step 4: Rewrite the UI section of the spec**

In `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md`. **The file is hard-wrapped at about 100 columns, so every quotation below is given with its line breaks exactly as they are on disk; a one-line find/replace matches nothing.** The line numbers are where the text sits before any edit in this step; match on the text, not on the number, because the paragraph replacement below turns three lines into seven.

Line 560, the heading:

```
## 9. UI (`apps/web`, TanStack Start)
```

becomes

```
## 9. UI (`apps/web`, Vite + TanStack Router)
```

Lines 562–564, the first paragraph:

```
TanStack Start 1.168.57 on @tanstack/react-router 1.170.38, React 19.3.0, Vite 8.3.0, Tailwind 4.3.3
via `@tailwindcss/vite`. No component library: the whole UI is four views and one long form, and a
design system is a dependency to maintain, not a shortcut.
```

becomes

```
Plain Vite 8.3.0 on @tanstack/react-router 1.170.38 with **code-based routes**, React 19.3.0,
Tailwind 4.3.3 via `@tailwindcss/vite`. No component library: the whole UI is four views and one
long form, and a design system is a dependency to maintain, not a shortcut. TanStack Start was
dropped on 2026-09-21 — SSR, server functions and head/meta buy nothing on loopback with the
backend deliberately outside Start's server, and its generated `routeTree.gen.ts` fails
`biome check` as an error while `pnpm format` and the generator fight over it. See
`agents/decisions.md`.
```

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

That parenthetical is the same fabricated claim Step 2 strikes from `server.ts`, and it is the last live copy of it. While in that table, the `Web` row still names `@tanstack/react-start 1.168.57`; replace `@tanstack/react-start 1.168.57 on @tanstack/react-router 1.170.38` with `@tanstack/react-router 1.170.38 (code-based routes)`.

**Leave the `## Normative formulas (frozen)` section untouched.**

- [ ] **Step 5: Update `CLAUDE.md`**

Five edits.

1. In the **Stack** table, replace the `apps/web` row

```
| `apps/web` | @tanstack/react-start 1.168.57 · @tanstack/react-router 1.170.38 · react/react-dom 19.3.0 · vite 8.3.0 · tailwindcss + @tailwindcss/vite 4.3.3 |
```

with

```
| `apps/web` | @tanstack/react-router 1.170.38 (code-based routes; **no @tanstack/react-start**) · react/react-dom 19.3.0 · @types/react + @types/react-dom 19.3.0 · vite 8.3.0 · @vitejs/plugin-react 6.1.1 · tailwindcss + @tailwindcss/vite 4.3.3 · hono 4.13.8 (for `hc`) |
```

and add `@hono/node-server 2.1.1` to the `apps/api` row.

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

- [ ] **Step 6: Teach CI to build the client**

The import-scan in `boundary.test.ts` is the mechanical guard, and it runs in the `Test` step already. The build is the measurement behind it, and it needs no database. In `.github/workflows/ci.yml`, after the `Test` step, append:

```yaml
      - name: Build the client
        # The boundary test greps the source; this compiles it. A value import of
        # @coinpicks/api builds clean and silently and only the bundle knows: measured at
        # 571.57 kB with `import type` and 716.11 kB with drizzle in it without. Two seconds.
        run: pnpm --filter @coinpicks/web run build
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
- **TanStack Start dropped; plain Vite + @tanstack/react-router with code-based routes.** SSR,
  server functions and head/meta buy nothing on loopback, single-user, no-SEO, with the backend
  deliberately outside Start's server; SPA mode turns most of it off and does not stop a loader
  added to `__root.tsx` later putting the web tier back on the network. Its generated
  `routeTree.gen.ts` fails `biome check` as an error, its own header asks to be excluded from
  the linter, `pnpm format` then reorders imports the next `vite dev` regenerates back, and
  nothing asserts the committed tree matches the route files. Reversal cost was zero today and
  rises the moment the UI exists — the same argument this log makes about the Electron reversal.
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
  with per-section CAS saves, and apps/web as a plain Vite SPA with a mechanical tier boundary.
  Next: step 5, the citation verifier.
```

- [ ] **Step 8: Full green, then commit**

```bash
cd /home/dev/projects/trade-god
python -m pytest -q
pnpm -r run typecheck
pnpm -r run test
pnpm check --write && pnpm check
pnpm --filter @coinpicks/web run build
grep -c -e pg-protocol -e drizzle -e node:crypto apps/web/dist/assets/index-*.js || true
```
Expected: pytest `111 passed`; typecheck silent; api `Tests 119 passed` over 14 files and web `Tests 5 passed`; Biome clean; a build around 571 kB; and `0` from the grep.

```bash
git add -A
git commit -m "docs: record step 4's rulings, and strike two stale claims

CONTEXT.md still told a fresh engineer that sub-scores are whole numbers and in
the same sentence never to constrain them to integers, citing the fabricated
worked example decisions.md already struck. decisions.md:319 keeps its
struck-through copy on purpose -- that one is the historical record.

The 8787 / my-teacher-api-1 note in server.ts was false on this machine: docker
ps lists two containers, neither of them that, and nothing listens on 8787.

Also: TanStack Start dropped for plain Vite, the spec's UI section rewritten to
match, and CI now builds the client so the bundle that the boundary test greps
is actually produced."
```

---
## Explicitly out of step 4

Step 4 **creates and edits a DRAFT**. It does not commit one, does not verify a citation, does not call an LLM, does not read a chain.

**Routes.** `POST /reports/:id/commit`. Any verify or re-verify route. Any candidates or EvidenceFinder route. Any chain route. Any vendor adapter — a CoinGecko lookup for market cap is spec §6 and step 5+; the schema already models a vendor number and a typed number identically, so an adapter saves typing rather than correctness and costs an HTTP client, a cache decision, a rate-limit story and a mock in every test. `DELETE /reports/:reportId` — discard belongs with the ledger view in step 6 (see the decisions log).

**Data.** Any write to a derived column (`DERIVED_COLUMNS`, eleven of them). Any write to `accrual_assessed` — Postgres refuses it with 428C9. Any `citations.status` other than the default `'unverified'`. Any `origin='model'`, `finder_provider` or `finder_model`. Any waiver UI or `waiver_reason` write — a waiver before anything has been checked waives nothing, and the gate refuses a waiver whose `last_outcome` is `'failed'`, which in step 4 is always NULL. Any `chain_facts` row. Any `forward_returns` row. The three `PHASE_A2_COLUMNS`.

**Behaviours.** No autosave and no debounce. No optimistic updates. No error boundaries, loading skeletons or transitions. No clamping — out of range is rejected and the refusal is shown verbatim. No arithmetic on any rubric value anywhere, in either tier. No `drizzle-kit push`, ever.

**Dependencies.** No component library, no form library (a resolver restating the bounds would be a fourth copy pinned by nothing), no state manager, no data-fetching library, no auth, no `user_id`, no jsdom, no `@testing-library/react`, no `@tanstack/react-start`, no `@tanstack/router-cli`, no `openai`, no `viem`, no `paths` alias in `apps/web`.

### Files that should not exist when this plan is done

`apps/web/src/routeTree.gen.ts` · `apps/web/src/components/ui/*` · `apps/web/src/lib/scoring.ts` or `totals.ts` or anything that adds numbers · `apps/web/src/lib/constants.ts` holding a rubric maximum · `apps/web/src/store/*` · `apps/web/src/routes/ledger.tsx` · `apps/web/src/routes/chain.tsx` · `apps/web/src/lib/auth.ts` · `apps/web/src/i18n/*` · any `*.test.tsx` · `apps/web/Dockerfile` · `apps/api/src/sources/*` · `apps/api/src/verify/*` · `apps/api/src/evidence/*` · `apps/api/src/chain/*` · `apps/api/src/providers.ts` (the spec names it `evidence/providers.ts` when it lands) · `apps/api/scripts/rescore.ts`.

And two symbols that should not exist anywhere: a `snake()` function, and a `commitAllowed` boolean.

```bash
cd /home/dev/projects/trade-god
test ! -e apps/web/src/routeTree.gen.ts && echo "no generated route tree"
grep -rn "function snake\|commitAllowed" apps/ || echo "neither symbol exists"
```

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

- **The blocker list is complete with respect to `rs_gate_completeness`, and that is all.** Every conjunct of that constraint has a row, mechanically. Nothing here promises the constraint is the whole commit gate — step 6 will add citation coverage, waiver rules and the frozen evaluations, and those are `unknown` rows or absent rows today.
- **`apps/web`'s typecheck compiles `apps/api`'s sources.** Fifteen of them, plus 83 `@types/node` files. Two packages report the same error, and a broken api compile blocks the web typecheck.
- **`hc<AppType>` instantiation depth is a watched number, not a solved problem.** An adversary measured 1.74s at 52 routes against the real 62-column `$inferSelect`; this plan ships thirteen. `time pnpm --filter @coinpicks/web run typecheck` is about 2.1s today. Treat a jump as the early warning, and **do not unpin TypeScript while adding routes.**
- **Nothing asserts the browser renders.** There is no jsdom, no `@testing-library/react` and no render test; the web suite is the boundary scan. The route suite covers the API's money path against real Postgres, and Tasks 5–7 each end with a manual walk-through whose expected text is written down. A render test suite is a step-6 decision, not something to add here by reflex.
- **`pnpm dev` runs two processes with no supervisor.** If the api dies, the proxy returns 502 and the editor shows `HTTP_502`. That is fine for one user on loopback and is not worth a process manager.
- **A figure below 1e-6 or at/above 1e21 has to be typed out in full to be saved again.** `numberOf` seeds a box with `String(value)`, and `String(1e-7)` is `'1e-7'`, which the API's digit regex refuses by design. The reachable case is a sub-0.0001% `accrualCaptureShare` or `accrualPct`: because a section sends all of its fields, editing the accrual rationale would come back `INVALID` on a fraction nobody touched. It is loud, named and recoverable by typing `0.0000001`. Both cheap repairs were tried and are worse — expanding the exponent in the browser needs `Number(parts[3])` and trips `boundary.test.ts` (measured: `editor/fields.tsx:38 const point = whole.length + Number(parts[3])`), and `toFixed(20)` silently rewrites `1.5e-20` as `0.00000000000000000002`. Widening the server's regex to admit exponents would re-open `'1e999'` → `Infinity`. The fix belongs on the read path; see item 8 of "What this hands to step 5".
