# CoinPicks — Plan 2: Schema, migrations, the immutability triggers and the role split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the ledger a database that cannot be quietly rewritten — seven tables whose domains are CHECK constraints rather than TypeScript opinions, a committed report that no statement from the application's own connection can edit, and a Postgres role split that makes "the app cannot disable its own guard" literally true rather than merely intended.

**Architecture:** `apps/api/src/db/schema.ts` is the only DDL author. `drizzle-kit generate` writes `apps/api/drizzle/0000_init.sql`; two `generate --custom` migrations follow it — `0001_immutability_triggers.sql` (six plpgsql functions, twelve triggers, all `ENABLE ALWAYS`) and `0002_role_grants.sql` (the privilege wall). Three login roles, created once by a superuser script outside the migration chain: `coinpicks_owner` owns every table and is used **only** by the boot migrator; `coinpicks_app` is `LOGIN NOSUPERUSER`, owns nothing and holds only `SELECT/INSERT/UPDATE/DELETE`; `research` reads five tables and writes the outcome columns of `forward_returns` and nothing else. `server.ts` opens the owner pool, migrates, asserts the guards are intact, closes it, and only then opens the app pool and takes the port.

**Tech Stack:** pnpm 10.33.0 workspace, `packages: ["apps/*"]`. Runtime **Node v26.8.1** — it executes `.ts` directly, in **strip-only mode**: it erases types, it does not transform them (see Global Constraints).

- `apps/api` adds: drizzle-orm 0.45.3, pg 8.23.0 (via `drizzle-orm/node-postgres`); dev: drizzle-kit 0.31.11, @types/pg 8.23.1.
- Already installed: typescript 5.9.3, vitest 4.1.11, @types/node 26.6.2, @biomejs/biome 2.5.14.
- **Not in this plan:** hono, @hono/zod-validator, zod, openai, viem. The HTTP framework lands in build-order step 4 (the editor); `server.ts` here uses `node:http` so that this plan's dependency surface is exactly the database.
- **Catalog pins in `pnpm-workspace.yaml` are a deliberate deviation from "always latest"** and must be stated as such wherever these versions are listed: typescript 5.9.3 (latest is 7.0.2, the Go-native compiler, a fresh major) and vitest 4.1.11 (latest is 5.0.1, days old). Revisit the week after report #1 commits.
- Postgres: ONE docker compose service, `postgres:16-alpine`, bound `127.0.0.1:5433:5432` — not 5432, which `medi-pal-db-1` (postgres:17.2) already holds on this machine — on the fresh named volume `coinpicks_data`. **Verified live for this plan: PostgreSQL 16.13 on x86_64-pc-linux-musl, container `coinpicks-db`, data checksums on.**
- `drizzle-kit push` is **never** run. It diffs `schema.ts` against the live database and would not know about the two hand-written migrations; the triggers would silently disappear. Only `generate` + the boot migrator.

**Spec:** `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` — §4 data model, §7 the commit gate's citation rules, §8 the EvidenceFinder's containment, §10 the ledger. The **"## Normative formulas (frozen)"** section is byte-frozen: it is never quoted altered and never changed.

---

## Where this plan came from

Six researchers produced a reconciled schema design; three adversaries then attacked it against this machine's live PostgreSQL 16.13 and confirmed defects in it. **Everything below is the corrected version.** Where a finding changed the design, the step says what the naive version did and why it was wrong — so the executor does not helpfully "fix" it back.

The eight attacks that were reproduced live and are closed by construction here:

| # | What was confirmed against PG 16.13 | Closed by |
|---|---|---|
| 1 | A committed report's scores, team and citations could be **re-parented onto a draft** with three ordinary `UPDATE`s, gutting the committed row | Task 4 — `report_id` is unconditionally immutable; the trigger checks **OLD** on UPDATE/DELETE, NEW only on INSERT |
| 2 | `coins` carried every committed report's identity and was **freely mutable forever** — re-pointing a coin silently re-points every forward return | Task 3 + Task 4 — `reports.coin_symbol / coin_chain / coin_contract_address`, written **by the commit trigger**, frozen thereafter |
| 3 | The app ran as the owning superuser: `SET session_replication_role = replica` flipped a committed report back to draft and then deleted it | Tasks 2 & 5 — two roles, two DSNs, one process |
| 4 | No trigger had `ENABLE ALWAYS`, so replica mode silenced all of them | Task 4 — twelve `ALTER TABLE ... ENABLE ALWAYS TRIGGER`, asserted at boot in Task 6 |
| 5 | `DECLARE parent_id text` against `uuid` keys: **every** child write died with `operator does not exist: uuid = text` | Task 4 — `reports.id%TYPE` |
| 6 | `ON DELETE CASCADE` was dead — a draft with any child could not be discarded (`CP404` from the child trigger) | Task 4 — the missing-parent branch returns OLD for DELETE only |
| 7 | A report could be committed with `scoring_version`, `product_passed` and `product_total` all NULL — and a **born-committed** row could be INSERTed, permanently frozen and impossible to fill | Task 4 — `coinpicks_assert_commitable()` on `BEFORE INSERT OR UPDATE OF status` |
| 8 | A break-even token committed as `MULTIPLE` with a discovery premium of **3.4e21** (gross `70000.00000000001`, issuance `70000`, net `1.455e-11`) | Task 8 in TypeScript, Task 3 in SQL |

---

## Global Constraints

- **Framework formulas are frozen.** Every weight, range and threshold comes from the spec's "Normative formulas (frozen)" section and is reproduced exactly. Never adjust one because it looks better calibrated — raise it with the user instead.
- **Ranges are rejected, never clamped.** An out-of-range score throws; it is not silently coerced.
- Rubric sub-scores are **whole numbers** (ruled 2026-09-21). Derived values such as the team weighted score are not.
- **Drizzle alone authors DDL.** `apps/api/src/db/schema.ts` declares every column; `apps/api/drizzle/*.sql` and `meta/_journal.json` are both committed; the API applies them at boot before the port is taken. Alembic is not this repo's migration tool.
- **Node 26 strips types; it does not transform them.** Verified on v26.8.1: `--experimental-transform-types` no longer exists, only `--experimental-strip-types` / `--no-strip-types`. So no parameter properties, no `enum`, no `namespace`, no decorators, no `import =` — anywhere under `apps/`. `erasableSyntaxOnly: true` in `tsconfig.base.json` makes a slip a compile error (`TS1294`). Every relative import carries an explicit `.ts`, because Node refuses an extensionless specifier (`ERR_MODULE_NOT_FOUND`) while `moduleResolution: "bundler"` happily resolved one.
- **Every DB test scopes its queries by ids it created.** Vitest runs test files in parallel against one `coinpicks_test` database, and the triggers refuse `TRUNCATE` and refuse `DELETE` on a committed report — so there is no between-tests reset. `SELECT count(*) FROM reports` is a flaky assertion; `WHERE report_id = <the one this test made>` is not. Test pools use `max: 4` (the server is configured `max_connections=30`).
- **Never `CREATE INDEX CONCURRENTLY` in a migration.** Drizzle's migrator wraps all pending files in one transaction.
- Commits land on `main` directly (personal repo; the owner has said branches are unnecessary here).
- Commits never carry AI attribution — no `Co-Authored-By` trailers, no generated-with footers.
- `research/` and `tests/research/` must stay green: `python -m pytest -q` is **111 passed** and must remain so.
- After each task: `cd apps/api && pnpm test`, `pnpm typecheck`, and from the repo root `pnpm check --write && pnpm check`. All three clean before the commit step.

---

## Task list

| Task | What it leaves behind |
|---|---|
| 1 | Node's runtime contract: erasable TypeScript, explicit `.ts` imports, 31 scoring tests still green |
| 2 | drizzle-orm/pg installed, the three roles bootstrapped, `db/client.ts`, both DSNs proven |
| 3 | `schema.ts` — seven tables, eight enums, the CHECK wall — and `0000_init.sql` |
| 4 | `0001_immutability_triggers.sql` and the attack suite that proves it |
| 5 | `0002_role_grants.sql` and the privilege wall, proven from both non-owner roles |
| 6 | `server.ts`: migrate as owner, assert the guards, downgrade to the app role, serve |
| 7 | `reports/cas.ts` + `reports/errors.ts`, with the lost-update concurrency test |
| 8 | The accrual noise floor in `scoring/accrual.ts` |
| 9 | `SCORING_VERSION` and the test that stops the DDL and the formulas drifting apart |
| 10 | `CLAUDE.md`, the spec's rule 2, `.env.example`, CI, and the decisions log |

---

### Task 1: Node's runtime contract — erasable TypeScript and explicit `.ts` imports

Nothing in this plan can boot until this is true. `node apps/api/src/server.ts` is how the app runs, and Node 26.8.1 runs `.ts` by **erasing** types, not by compiling them. Two things in the repo today break that, and `pnpm typecheck` is currently blind to both:

1. `ScoreRangeError`'s constructor uses TypeScript **parameter properties** (`readonly field: string` in the parameter list). Verified on v26.8.1: `SyntaxError [ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX]: TypeScript parameter property is not supported in strip-only mode`. There is no flag for it any more — `--experimental-transform-types` was removed; `node --help` lists only `--experimental-strip-types, --no-strip-types`.
2. Every relative import in `src/scoring/` is extensionless (`from './ranges'`). Node: `ERR_MODULE_NOT_FOUND`. `moduleResolution: "bundler"` resolves it happily, so typecheck stays green while the runtime dies.

The fix is one tsconfig and a mechanical edit. `erasableSyntaxOnly` then makes the first failure a compile error forever, and `nodenext` makes the second one.

**Files:**
- Modify: `tsconfig.base.json`
- Modify: `apps/api/src/scoring/ranges.ts` (the error class only — no formula is touched)
- Modify: `apps/api/src/scoring/{product,narrative,team,accrual}.ts` and `apps/api/src/scoring/{product,narrative,team,accrual}.test.ts` (import specifiers only)
- Test: the existing `apps/api/src/scoring/*.test.ts` — 31 tests, unchanged assertions

**Interfaces:**
- Consumes: nothing.
- Produces: no new export. `ScoreRangeError` keeps its exact public shape — `new ScoreRangeError(field: string, value: number, min: number, max: number)` with readonly `field`, `value`, `min`, `max` and `message` = `` `${field} must be between ${min} and ${max}, got ${value}` ``.

- [ ] **Step 1: See the runtime failure before fixing it**

```bash
cd /home/dev/projects/trade-god/apps/api
node -e "import('./src/scoring/accrual.ts').then(m=>console.log(m))"
```
Expected: `Error [ERR_MODULE_NOT_FOUND]: Cannot find module .../ranges imported from .../accrual.ts`. That is failure (2). Write the exact text down; step 4 asserts it is gone.

- [ ] **Step 2: Tighten `tsconfig.base.json` so both failures become compile errors**

Replace `/home/dev/projects/trade-god/tsconfig.base.json` with:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "allowImportingTsExtensions": true,
    "erasableSyntaxOnly": true,
    "verbatimModuleSyntax": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "skipLibCheck": true,
    "noEmit": true
  }
}
```

`allowImportingTsExtensions` needs `noEmit`, which is already set. `nodenext` makes an extensionless relative import an error, so typecheck and runtime finally agree. `verbatimModuleSyntax` forces `import type` where a specifier is type-only, which is what type-erasure needs to be safe.

- [ ] **Step 3: Run typecheck and watch it fail in exactly two ways**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm typecheck
```
Expected: `src/scoring/ranges.ts(3,5): error TS1294: This syntax is not allowed when 'erasableSyntaxOnly' is enabled.` four times (lines 3–6, one per parameter property), plus `TS2835`-class errors on every extensionless relative import in `src/scoring/`.

- [ ] **Step 4: Rewrite `ScoreRangeError` into erasable form**

In `apps/api/src/scoring/ranges.ts`, replace the class with:

```ts
export class ScoreRangeError extends Error {
  readonly field: string
  readonly value: number
  readonly min: number
  readonly max: number

  constructor(field: string, value: number, min: number, max: number) {
    super(`${field} must be between ${min} and ${max}, got ${value}`)
    this.name = 'ScoreRangeError'
    this.field = field
    this.value = value
    this.min = min
    this.max = max
  }
}
```

Nothing else in the file changes. `assertRange`, `assertIntegerRange` and `assertNonNegative` — and every comment in them — stay exactly as they are.

- [ ] **Step 5: Put the `.ts` back on every relative import**

```bash
cd /home/dev/projects/trade-god/apps/api/src/scoring
sed -i "s|from '\./ranges'|from './ranges.ts'|g;
        s|from '\./product'|from './product.ts'|g;
        s|from '\./narrative'|from './narrative.ts'|g;
        s|from '\./team'|from './team.ts'|g;
        s|from '\./accrual'|from './accrual.ts'|g" *.ts
grep -rn "from '\./" .
```
Expected: every line printed ends in `.ts'`. There should be nine such imports across the eight files.

- [ ] **Step 6: Prove the runtime, the typechecker and the tests all agree**

```bash
cd /home/dev/projects/trade-god/apps/api
node -e "import('./src/scoring/accrual.ts').then(m=>console.log(Object.keys(m)))"
pnpm typecheck
pnpm test
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
```
Expected, in order: `[ 'annualHolderFlow', 'discoveryPremium' ]` — no `ERR_MODULE_NOT_FOUND`, no `ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`; typecheck silent; `Test Files 4 passed (4) / Tests 31 passed (31)`; Biome clean.

- [ ] **Step 7: Commit**

```bash
cd /home/dev/projects/trade-god
git add -A
git commit -m "build: make the TypeScript actually runnable under Node 26

Node 26 strips types, it does not transform them: parameter properties throw
ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX and an extensionless relative import throws
ERR_MODULE_NOT_FOUND. moduleResolution:bundler hid both from typecheck, so the
suite was green over code that could not boot. erasableSyntaxOnly and nodenext
make each one a compile error instead."
```

---

### Task 2: Database dependencies, the two roles, and the client

Decision A, taken by the owner on 2026-09-21: **two roles, two DSNs, one process.** An attacker confirmed that the single owning superuser the earlier design proposed could `SET session_replication_role = replica` and then flip a committed report back to draft and delete it — three statements, every trigger installed and silent. A `NOSUPERUSER` non-owner is refused all of it (`permission denied to set parameter "session_replication_role"`, `must be owner of relation citations`), and the immutability triggers still fire against it normally.

The roles are created by a psql script run as the compose superuser, **not** by a migration: `CREATE ROLE` is cluster-scoped and a migration applies exactly once per database, so a role created inside one would not exist for the test database. This script is the one place a superuser is used, and it also owns `coinpicks_test`.

**Files:**
- Modify: `apps/api/package.json` (dependencies + `db:bootstrap`, `dev`, `start` scripts)
- Modify: `pnpm-lock.yaml` (regenerated by pnpm)
- Create: `apps/api/scripts/bootstrap-roles.sql`
- Create: `apps/api/drizzle.config.ts`
- Create: `apps/api/src/db/client.ts`
- Test: `apps/api/src/db/client.test.ts`

**Interfaces:**
- Consumes: `DATABASE_URL_OWNER`, `DATABASE_URL` from the environment.
- Produces, from `apps/api/src/db/client.ts`:
  - `type Db = NodePgDatabase<typeof schema>`
  - `type Tx = Parameters<Parameters<Db['transaction']>[0]>[0]`
  - `interface DbHandle { db: Db; pool: Pool; close: () => Promise<void> }`
  - `openDb(connectionString: string, max?: number): DbHandle`
  - `requireEnv(name: string): string`
  - `const MIGRATIONS_FOLDER: string`

- [ ] **Step 1: Install the four packages**

```bash
cd /home/dev/projects/trade-god
pnpm --filter @coinpicks/api add drizzle-orm@0.45.3 pg@8.23.0
pnpm --filter @coinpicks/api add -D drizzle-kit@0.31.11 @types/pg@8.23.1
```
Expected: `apps/api/package.json` grows a `dependencies` block with `drizzle-orm` and `pg`, and two entries in `devDependencies`. `pg` 8.23.0 ships no type declarations of its own, which is why `@types/pg` 8.23.1 is not optional.

- [ ] **Step 2: Add the three scripts to `apps/api/package.json`**

Set the `scripts` block to exactly:

```json
  "scripts": {
    "dev": "node --env-file-if-exists=../../.env --watch src/server.ts",
    "start": "node --env-file-if-exists=../../.env src/server.ts",
    "db:bootstrap": "docker exec -i coinpicks-db psql -U coinpicks -d postgres -v ON_ERROR_STOP=1 < scripts/bootstrap-roles.sql",
    "db:generate": "drizzle-kit generate",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check"
  },
```

`--env-file-if-exists` (not `--env-file`) so a missing `.env` produces `requireEnv`'s message rather than a Node startup error. The root `pnpm dev` already runs `pnpm --filter @coinpicks/api --parallel run dev`, which until now targeted a script that did not exist and silently ran nothing.

- [ ] **Step 3: Write `apps/api/scripts/bootstrap-roles.sql`**

```sql
-- The three login roles, and the test database. Run ONCE per Postgres cluster, as the
-- compose superuser, and again whenever you want a clean coinpicks_test:
--
--   pnpm --filter @coinpicks/api run db:bootstrap
--
-- This is NOT a Drizzle migration and must never become one. CREATE ROLE is cluster-scoped
-- while a migration applies once per database, so a role created inside one would be missing
-- from coinpicks_test. It is also the only place a superuser connection is used.
--
-- WHY THREE ROLES. An attacker confirmed on PostgreSQL 16.13 that a session owning the
-- tables can `SET session_replication_role = replica` and then UPDATE a committed report
-- back to draft and DELETE it, with every immutability trigger installed and silent, and can
-- `DROP TRIGGER` outright. A NOSUPERUSER non-owner is refused all three. So:
--
--   coinpicks_owner  owns every table; used ONLY by the boot migrator, which closes its pool
--                    before the port is taken.
--   coinpicks_app    owns nothing; DML on the seven tables and nothing else. This is the
--                    request pool.
--   research         SELECT on five tables, and the outcome columns of forward_returns.
--
-- Passwords are the role names. This is a loopback-only, single-user, no-auth ledger on
-- 127.0.0.1:5433 and the compose file already ships `coinpicks:coinpicks`; a secret that is
-- printed in .env.example is not a secret, and pretending otherwise would be theatre.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coinpicks_owner') THEN
    CREATE ROLE coinpicks_owner;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coinpicks_app') THEN
    CREATE ROLE coinpicks_app;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'research') THEN
    CREATE ROLE research;
  END IF;
END $$;

ALTER ROLE coinpicks_owner LOGIN PASSWORD 'coinpicks_owner'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE coinpicks_app LOGIN PASSWORD 'coinpicks_app'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE research LOGIN PASSWORD 'research'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

ALTER ROLE coinpicks_owner SET search_path = public;
ALTER ROLE coinpicks_app   SET search_path = public;
ALTER ROLE research        SET search_path = public;

-- Database ownership, not a pile of grants: the owner of a database is implicitly a member
-- of pg_database_owner, which owns schema public, so this one statement gives the migrator
-- CREATE on public and the right to create the `drizzle` schema its journal lives in.
ALTER DATABASE coinpicks OWNER TO coinpicks_owner;
GRANT CONNECT ON DATABASE coinpicks TO coinpicks_app, research;

-- The test database. Rebuilt from scratch here, and re-migrated by vitest's globalSetup at
-- the start of every run. WITH (FORCE) because a stray psql session would otherwise block
-- the drop.
DROP DATABASE IF EXISTS coinpicks_test WITH (FORCE);
CREATE DATABASE coinpicks_test OWNER coinpicks_owner;
GRANT CONNECT ON DATABASE coinpicks_test TO coinpicks_app, research;
```

- [ ] **Step 4: Run it and read the result**

```bash
cd /home/dev/projects/trade-god
docker compose up -d db
pnpm --filter @coinpicks/api run db:bootstrap
docker exec coinpicks-db psql -U coinpicks -d postgres \
  -c "select rolname, rolsuper, rolcanlogin from pg_roles where rolname like 'coinpicks%' or rolname='research' order by 1;" \
  -c "select datname, pg_get_userbyid(datdba) as owner from pg_database where datname like 'coinpicks%' order by 1;"
```
Expected: `coinpicks | t | t`, `coinpicks_app | f | t`, `coinpicks_owner | f | t`, `research | f | t`; and both `coinpicks` and `coinpicks_test` owned by `coinpicks_owner`. The `f` in the `rolsuper` column for `coinpicks_app` is the whole point of the task.

- [ ] **Step 5: Write `apps/api/drizzle.config.ts`**

```ts
import { defineConfig } from 'drizzle-kit'

/**
 * `drizzle-kit generate` only — it needs no database connection, so there are no
 * dbCredentials here on purpose.
 *
 * NEVER run `drizzle-kit push`. It diffs schema.ts against the live database and knows
 * nothing about drizzle/0001_immutability_triggers.sql or drizzle/0002_role_grants.sql,
 * which schema.ts does not and cannot re-emit. A push would leave the ledger unguarded and
 * say nothing.
 */
export default defineConfig({
  dialect: 'postgresql',
  schema: './src/db/schema.ts',
  out: './drizzle',
})
```

- [ ] **Step 6: Write `apps/api/src/db/client.ts`**

```ts
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { type NodePgDatabase, drizzle } from 'drizzle-orm/node-postgres'
import { Pool } from 'pg'
import * as schema from './schema.ts'

export type Db = NodePgDatabase<typeof schema>

/** The transaction handle drizzle hands the callback. Named once so nothing re-derives it. */
export type Tx = Parameters<Parameters<Db['transaction']>[0]>[0]

export interface DbHandle {
  db: Db
  pool: Pool
  close: () => Promise<void>
}

/** apps/api/drizzle — the committed .sql files plus meta/_journal.json. */
export const MIGRATIONS_FOLDER = resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle')

/**
 * One pool, one drizzle handle, one way to close them. `max` is small by default because the
 * compose service runs with max_connections=30 and this is a single-user ledger.
 */
export function openDb(connectionString: string, max = 10): DbHandle {
  const pool = new Pool({ connectionString, max })
  const db = drizzle(pool, { schema })
  return { db, pool, close: () => pool.end() }
}

export function requireEnv(name: string): string {
  const value = process.env[name]
  if (value === undefined || value.trim() === '') {
    throw new Error(
      `${name} is not set. Copy .env.example to .env and run \`docker compose up -d db\`. ` +
        'A ledger with no database is not a degraded mode worth having.',
    )
  }
  return value
}
```

This file imports `./schema.ts`, which Task 3 writes. It will not typecheck until then — that is expected and step 7 works around it deliberately.

- [ ] **Step 7: Write the connection test**

Create `apps/api/src/db/client.test.ts`:

```ts
import { sql } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import { TEST_APP_URL, TEST_OWNER_URL, TEST_RESEARCH_URL, refusal } from './testing.ts'

/**
 * Decision A, asserted rather than assumed: the request pool must not be able to turn the
 * immutability triggers off. `SET session_replication_role = replica` is the statement an
 * attacker used to flip a committed report back to draft and then delete it, and only a
 * superuser may issue it.
 */
describe('the two-role split', () => {
  it('connects as coinpicks_owner, which owns the tables', async () => {
    const h = openDb(TEST_OWNER_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'coinpicks_owner', sup: false })
    await h.close()
  })

  it('connects as coinpicks_app, which is not a superuser and cannot enter replica mode', async () => {
    const h = openDb(TEST_APP_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'coinpicks_app', sup: false })

    const e = await refusal(h.db.execute(sql`SET session_replication_role = replica`))
    expect(e.code).toBe('42501')
    expect(e.message).toBe('permission denied to set parameter "session_replication_role"')
    await h.close()
  })

  it('connects as research, which is not a superuser either', async () => {
    const h = openDb(TEST_RESEARCH_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'research', sup: false })
    await h.close()
  })
})
```

Create `apps/api/src/db/testing.ts` with just the three DSNs for now — Task 3 adds the fixtures to the same file:

```ts
/**
 * Where the DB tests connect. Overridable for CI, which runs Postgres as a service rather
 * than as the compose container.
 */
export const TEST_OWNER_URL =
  process.env.TEST_DATABASE_URL_OWNER ??
  'postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks_test'

export const TEST_APP_URL =
  process.env.TEST_DATABASE_URL ??
  'postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks_test'

export const TEST_RESEARCH_URL =
  process.env.TEST_RESEARCH_DATABASE_URL ??
  'postgresql://research:research@localhost:5433/coinpicks_test'

export interface DriverError {
  /** The SQLSTATE: '23514' for a CHECK, '23505' for a unique index, '42501' for a
   *  privilege refusal, 'CP001' for one of ours. */
  code: string
  message: string
  /** The constraint that refused it, when Postgres names one. */
  constraint: string | undefined
}

/**
 * Asserts a statement was refused, and returns the DRIVER's error rather than the wrapper's.
 *
 * `await expect(p).rejects.toThrow(/permission denied/)` looks right and never matches.
 * drizzle 0.45.3 wraps every driver error in DrizzleQueryError at seven call sites in
 * pg-core/session.js; confirmed live that the wrapper's own `code` is undefined and its
 * message is `Failed query: update report_scores set ...`, while the real message, the
 * SQLSTATE and the constraint name sit on `.cause`. A test matching the wrapper's message
 * would pass for the wrong reason or fail for no reason, so walk the chain.
 *
 * The same walk is what the commit route needs in production, and Task 7 lifts it into
 * reports/errors.ts as `sqlstateOf`.
 */
export async function refusal(promise: Promise<unknown>): Promise<DriverError> {
  try {
    await promise
  } catch (error) {
    let cursor: unknown = error
    for (let depth = 0; cursor != null && depth < 10; depth += 1) {
      const node = cursor as {
        code?: unknown
        message?: unknown
        constraint?: unknown
        cause?: unknown
      }
      if (typeof node.code === 'string' && /^[0-9A-Z]{5}$/.test(node.code)) {
        return {
          code: node.code,
          message: String(node.message),
          constraint: typeof node.constraint === 'string' ? node.constraint : undefined,
        }
      }
      cursor = node.cause
    }
    throw new Error(`no SQLSTATE anywhere in the error chain: ${String(error)}`)
  }
  throw new Error('expected the statement to be refused, but it succeeded')
}
```

- [ ] **Step 8: Run the test and see it fail on the missing schema**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test
```
Expected: FAIL — `Failed to resolve import "./schema.ts" from "src/db/client.ts"`. That is the honest state: the client exists, the schema does not. Task 3 closes it. Do **not** stub `schema.ts` to make this pass.

- [ ] **Step 9: Commit**

```bash
cd /home/dev/projects/trade-god
git add -A
git commit -m "feat: the database dependencies and the two-role split

The app pool must not be able to disable the guard that protects the ledger.
A session owning the tables can SET session_replication_role = replica and edit
a committed report with every trigger installed and silent; a NOSUPERUSER
non-owner is refused. coinpicks_owner migrates and goes away, coinpicks_app
serves. The test for it fails until schema.ts lands in the next task."
```

---

### Task 3: The schema and the first migration

Seven tables, eight enums, and a wall of CHECK constraints that exists because **a type in TypeScript is not a constraint in Postgres**. Three decisions in here are corrections to the reconciled design and will look wrong to someone who has not read why:

- **Every `report_scores` column except `report_id` is nullable**, and the derived-value CHECKs are wrapped in `CASE WHEN product_passed IS NULL THEN true ELSE ... END`. The naive version made `scoring_version` and the five product columns `NOT NULL`, which was reproduced live: `INSERT INTO report_scores (report_id) ...` → `null value in column "scoring_version" violates not-null constraint`. A half-finished report has to survive a browser reload, so the table holds the draft; `product_passed IS NOT NULL` is the sentinel meaning "the frozen gate ran", and the identities only bite from that moment.
- **`accrual_assessed` is a generated column, not a boolean the editor sets.** Without it, a blank accrual section is bit-identical to a measured zero: `?? 0` in the gate satisfies `assertNonNegative`, `zeroFactor` resolves to `'segmentRevenueUsd'`, and `PURE_PREMIUM` — the framework's harshest verdict, narrowed by ruling on 2026-09-21 to mean *zero forced flow* — commits immutably about a coin nobody assessed. Deriving it from the four inputs makes absence and zero different states by construction, and `rs_premium_needs_assessment` then forbids a verdict without an assessment.
- **`forward_returns.return_fraction` is generated from two stored prices.** The old `return_pct` was a fraction wearing a percentage's name, guarded by a one-sided `CHECK (return_pct >= -1)` that catches a percentage-scaled *loss* and passes every percentage-scaled *gain*. `research/forward_returns.py` does not exist yet, so the unit is still choosable — and a computed column cannot disagree with the numbers it came from. The prices also satisfy §8's rule that every number is verified (say where) or a guess (say so); the quotient alone satisfied neither.

Also deliberate, and each one closes a confirmed finding: `reports` carries a **coin identity snapshot** (`coins` has no guard and re-pointing it re-points every forward return ever computed); `report_team` keys uniqueness on a generated `name_key` (one person listed under two roles entered as two rows and inflated `teamWeightedScore`, a frozen formula, into a plausible wrong number); `accrual_zero_factor`'s labels are **camelCase verbatim from `AccrualResult`** so there is no mapping to get wrong; and there is **no `UNIQUE (coin_id, version)`** — `version` is the CAS token, so two reports on one coin would collide on their first save.

**Files:**
- Create: `apps/api/src/db/schema.ts`
- Create: `apps/api/drizzle/0000_init.sql` + `apps/api/drizzle/meta/` (generated, both committed)
- Create: `apps/api/src/db/global-setup.ts`
- Modify: `apps/api/src/db/testing.ts` (add the fixtures)
- Modify: `apps/api/vitest.config.ts`
- Test: `apps/api/src/db/schema.test.ts`

**Interfaces:**
- Consumes: `openDb`, `MIGRATIONS_FOLDER` from `./client.ts`.
- Produces, from `apps/api/src/db/schema.ts`:
  - tables `coins`, `reports`, `reportScores`, `reportTeam`, `citations`, `chainFacts`, `forwardReturns`
  - enums `reportStatus`, `citationStatus`, `citationOrigin`, `liquidityTier`, `provenanceLabel`, `accrualZeroFactor`, `discoveryPremiumKind`, `chainFactKind`
  - row types `CoinRow`, `ReportRow`, `ReportScoresRow`, `ReportTeamRow`, `CitationRow`, `ChainFactRow`, `ForwardReturnRow`
  - insert types `NewCoin`, `NewReport`, `NewReportTeam`, `NewCitation`, `NewChainFact`, `NewForwardReturn`
- Produces, from `apps/api/src/db/testing.ts`: `DraftReport`, `createDraftReport(db: Db): Promise<DraftReport>`, `scoreAsDropped(db: Db, reportId: string): Promise<void>`, `commitReportRow(db: Db, reportId: string): Promise<void>`
- Produces, from `apps/api/src/db/global-setup.ts`: `setup(): Promise<void>`

- [ ] **Step 1: Point vitest at a global setup that rebuilds the test database**

Replace `apps/api/vitest.config.ts` with:

```ts
import { defineConfig } from 'vitest/config'

// Node environment, not jsdom: nothing here touches the DOM, and the frozen formulas must
// stay importable without a browser shim ever being involved.
//
// globalSetup rebuilds coinpicks_test from the committed migrations ONCE per run, and it is
// not optional. The immutability triggers refuse TRUNCATE on five tables and refuse DELETE
// on a committed report's rows, so there is no per-test reset short of rebuilding the
// schema. Tests therefore scope every query by ids they created themselves.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globalSetup: ['./src/db/global-setup.ts'],
  },
})
```

Create `apps/api/src/db/global-setup.ts`:

```ts
import { sql } from 'drizzle-orm'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { MIGRATIONS_FOLDER, openDb } from './client.ts'
import { TEST_OWNER_URL } from './testing.ts'

/**
 * Rebuilds `coinpicks_test` from apps/api/drizzle, once per `pnpm test`.
 *
 * DROP SCHEMA rather than TRUNCATE on purpose. `*_no_truncate` refuses TRUNCATE and
 * `*_immutable` refuses DELETE on a committed report's rows, so the usual between-tests
 * reset is impossible by construction — which is the point of the design, so the harness is
 * built around it rather than against it. coinpicks_owner owns coinpicks_test, and the owner
 * of a database is a member of pg_database_owner, which owns schema public.
 */
export async function setup(): Promise<void> {
  const owner = openDb(TEST_OWNER_URL, 1)
  try {
    await owner.db.execute(sql`DROP SCHEMA IF EXISTS drizzle CASCADE`)
    await owner.db.execute(sql`DROP SCHEMA IF EXISTS public CASCADE`)
    await owner.db.execute(sql`CREATE SCHEMA public`)
    await migrate(owner.db, { migrationsFolder: MIGRATIONS_FOLDER })
  } catch (error) {
    throw new Error(
      'could not rebuild coinpicks_test. Run:\n' +
        '  docker compose up -d db\n' +
        '  pnpm --filter @coinpicks/api run db:bootstrap\n' +
        `cause: ${(error as Error).message}`,
      { cause: error },
    )
  } finally {
    await owner.close()
  }
}
```

- [ ] **Step 2: Write the failing schema test**

Create `apps/api/src/db/schema.test.ts`:

```ts
import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import { TEST_OWNER_URL, createDraftReport, refusal } from './testing.ts'

// The OWNER connection, not the app role. coinpicks_app holds no table privileges until the
// grant migration lands in Task 5, and the CHECK constraints under test here are the
// database's, not the privilege system's. Task 5 switches to the app role and proves that the
// triggers bind it too.
const h = openDb(TEST_OWNER_URL, 4)
afterAll(() => h.close())

describe('the day-one draft path', () => {
  it('stores a coin, a report and an all-NULL scores row', async () => {
    const { reportId } = await createDraftReport(h.db)
    const r = await h.db.execute<{ status: string; version: number; accrual_assessed: boolean }>(
      sql`SELECT r.status, r.version, s.accrual_assessed
            FROM reports r JOIN report_scores s ON s.report_id = r.id
           WHERE r.id = ${reportId}`,
    )
    expect(r.rows[0]).toEqual({ status: 'draft', version: 1, accrual_assessed: false })
  })

  it('stores a citation and a team member against the draft', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO citations (report_id, field, url, quote, origin)
      VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'a quote', 'human')`)
    await h.db.execute(sql`
      INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
      VALUES (${reportId}, 1, '  Alice   Chen ', ARRAY['Founder','Head of Product'],
              true, 5, 3, 0, 'Ran a $40M book at a prior firm.')`)
    const r = await h.db.execute<{ name_key: string }>(
      sql`SELECT name_key FROM report_team WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.name_key).toBe('alice chen')
  })
})

describe('the domains Postgres enforces, not TypeScript', () => {
  it('refuses a sub-score above its own maximum', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`UPDATE report_scores SET narrative_mutation = 4 WHERE report_id = ${reportId}`),
    )
    expect(e.constraint).toBe('rs_narrative_mutation_range')
  })

  it('refuses a fraction typed on a 0-100 scale', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`UPDATE report_scores SET accrual_pct = 50 WHERE report_id = ${reportId}`),
    )
    expect(e.constraint).toBe('rs_accrual_pct_unit')
  })

  it("refuses NaN, which Postgres sorts ABOVE every real value so '>= 0' alone lets it through", async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`UPDATE report_scores SET accrual_segment_revenue_usd = 'NaN'::float8
                        WHERE report_id = ${reportId}`),
    )
    expect(e.constraint).toBe('rs_segment_revenue_nonneg')
  })

  it('refuses the same person entered twice under a whitespace and case variant', async () => {
    const { reportId } = await createDraftReport(h.db)
    const insert = (position: number, name: string, isFounder: boolean) =>
      h.db.execute(sql`
        INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
        VALUES (${reportId}, ${position}, ${name}, ARRAY['Founder'], ${isFounder},
                3, 1, 0, 'Prior role, with a number in it.')`)
    await insert(1, 'Alice Chen', true)
    const e = await refusal(insert(2, '  alice   CHEN ', false))
    expect(e.constraint).toBe('rt_report_name_key_uniq')
  })

  it('refuses two founders on one report', async () => {
    const { reportId } = await createDraftReport(h.db)
    const insert = (position: number, name: string) =>
      h.db.execute(sql`
        INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
        VALUES (${reportId}, ${position}, ${name}, ARRAY['Founder'], true,
                3, 1, 0, 'Prior role, with a number in it.')`)
    await insert(1, 'Alice Chen')
    const e = await refusal(insert(2, 'Bob Diaz'))
    expect(e.constraint).toBe('rt_one_founder_per_report')
  })

  it('refuses an off-grid forward-return horizon', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO forward_returns
          (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
        VALUES (${reportId}, 60, 2.0, 2.25, 'research/warehouse klines_1d', now())`),
    )
    expect(e.constraint).toBe('fr_horizon_frozen')
  })

  it('computes return_fraction from the two prices rather than storing a typed number', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO forward_returns
        (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
      VALUES (${reportId}, 30, 2.0, 2.25, 'research/warehouse klines_1d', now())`)
    const r = await h.db.execute<{ return_fraction: number }>(
      sql`SELECT return_fraction FROM forward_returns WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.return_fraction).toBeCloseTo(0.125, 12)
  })

  it('refuses a second coin row for the same (chain, contract address)', async () => {
    const address = `0x${randomUUID().replace(/-/g, '')}`
    const insert = () =>
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, contract_address, address_sources)
        VALUES ('TST', 'Test Coin', 'ethereum', ${address},
                '["https://a.example","https://b.example"]'::jsonb)`)
    await insert()
    const e = await refusal(insert())
    expect(e.constraint).toBe('coins_chain_address_uniq')
  })

  it('requires two address sources once there is an address to have sourced', async () => {
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, contract_address, address_sources)
        VALUES ('TST', 'Test Coin', 'ethereum', ${`0x${randomUUID().replace(/-/g, '')}`},
                '["https://only-one.example"]'::jsonb)`),
    )
    expect(e.constraint).toBe('coins_address_sources_min_2')
  })

  it('does not require them for a native asset, which has no address', async () => {
    await expect(
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, address_sources)
        VALUES ('ETH', 'Ether', 'ethereum', '[]'::jsonb)`),
    ).resolves.toBeDefined()
  })
})
```

Add the fixtures to `apps/api/src/db/testing.ts`, below the three DSNs:

```ts
import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import type { Db } from './client.ts'

export interface DraftReport {
  coinId: string
  reportId: string
}

/**
 * A fresh coin and a fresh draft report, with ids nobody else in the suite will use — the
 * test database is shared and vitest runs files in parallel.
 */
export async function createDraftReport(db: Db): Promise<DraftReport> {
  const coinId = randomUUID()
  const reportId = randomUUID()
  await db.execute(sql`
    INSERT INTO coins (id, symbol, name, chain, contract_address, address_sources)
    VALUES (${coinId}, 'TST', 'Test Coin', 'ethereum', ${`0x${coinId.replace(/-/g, '')}`},
            '["https://a.example","https://b.example"]'::jsonb)`)
  await db.execute(sql`INSERT INTO reports (id, coin_id) VALUES (${reportId}, ${coinId})`)
  // Task 4 deletes the next statement: the reports_seed_scores trigger does it instead.
  await db.execute(sql`INSERT INTO report_scores (report_id) VALUES (${reportId})`)
  return { coinId, reportId }
}

/**
 * The least a report can carry and still be commitable: a product gate that FAILED.
 * A dropped project still commits — a ledger holding only passes is survivorship bias in
 * the exact dataset built to test the framework — and rs_gate_completeness requires the
 * downstream sections only when the gate passed.
 */
export async function scoreAsDropped(db: Db, reportId: string): Promise<void> {
  await db.execute(sql`
    UPDATE report_scores
       SET scoring_version = 'test', product_ease = 5, product_hair_fire = 5,
           product_exclusivity = 5, product_total = 15, product_passed = false
     WHERE report_id = ${reportId}`)
}

/** The status flip, in rule 4's compare-and-swap form. */
export async function commitReportRow(db: Db, reportId: string): Promise<void> {
  await db.execute(sql`
    UPDATE reports SET status = 'committed', committed_at = now(), version = version + 1
     WHERE id = ${reportId} AND status = 'draft'`)
}
```

`refusal()` is already in this file from Task 2 — do not add a second copy.

- [ ] **Step 3: Run the test and read the failure**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test
```
Expected: FAIL at import — `Failed to resolve import "./schema.ts" from "src/db/client.ts"`. Once `schema.ts` exists but before `drizzle-kit generate` has run, the failure moves to globalSetup: `could not rebuild coinpicks_test ... cause: ENOENT ... drizzle/meta/_journal.json`. Both are the right failures.

- [ ] **Step 4: Write `apps/api/src/db/schema.ts`**

```ts
import { type SQLWrapper, sql } from 'drizzle-orm'
import {
  bigint,
  boolean,
  check,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from 'drizzle-orm/pg-core'

/*
 * CoinPicks schema. Drizzle is the ONLY DDL author. Seven tables, no user_id anywhere:
 * loopback, one user, no auth.
 *
 * WHY double precision AND NOT numeric, for every money / fraction / derived figure: the
 * frozen core computes in IEEE-754 float64. annualHolderFlow({segmentRevenueUsd: 1,
 * captureShare: 0.1, accrualPct: 0.2}) returns 0.020000000000000004. Verified on 16.13:
 * float8 reproduces that exactly, numeric computes 0.02 — so rs_gross_flow_is_product below
 * would REJECT a row the authoritative TypeScript produced. Schema rule 5 mandates
 * timestamptz and jsonb; it is silent on the numeric type, and rescore parity decides it.
 *
 * WHY the explicit Infinity bounds: Postgres does not use IEEE comparison semantics.
 * 'NaN'::float8 > 1 is TRUE and 'NaN'::float8 >= 0 is TRUE, so `>= 0` alone does NOT
 * reproduce assertNonNegative(). `x BETWEEN 0 AND 1` does exclude NaN, because NaN sorts
 * above every real value.
 */

/** Number.isFinite(), in SQL: NaN and both infinities fail it. */
const finite = (c: SQLWrapper) => sql`${c} > '-Infinity'::float8 AND ${c} < 'Infinity'::float8`

/** assertNonNegative(): finite and >= 0. */
const nonNegativeFinite = (c: SQLWrapper) => sql`${c} >= 0 AND ${c} < 'Infinity'::float8`

/** A fraction in [0, 1] — the 2026-09-21 ruling on captureShare and accrualPct. */
const unitFraction = (c: SQLWrapper) => sql`${c} BETWEEN 0 AND 1`

/** Rejects '' and '   ' wherever the spec requires prose to actually exist. */
const nonBlank = (c: SQLWrapper) => sql`length(btrim(${c})) > 0`

/** Same, but tolerant of NULL — for use inside the gate-completeness CASE. */
const present = (c: SQLWrapper) => sql`length(btrim(coalesce(${c}, ''))) > 0`

// ---------------------------------------------------------------------------
// Enums. Schema rule 1: pgEnum, never text().$type<>().
// pgEnums are APPEND-ONLY from the first commit. Each of these is a closed set taken from a
// frozen formula or from the spec, so that cost is already paid.
// ---------------------------------------------------------------------------

export const reportStatus = pgEnum('report_status', ['draft', 'committed'])

export const citationStatus = pgEnum('citation_status', [
  'unverified',
  'verified',
  'near_miss',
  'failed',
  'unverifiable_js',
  'waived',
])

export const citationOrigin = pgEnum('citation_origin', ['human', 'model'])

/** Section 2.2: Low | Medium | High, assigned by the human; there is no formula. One
 *  canonical casing, and the UI maps the framework's Low/Medium/High onto it. */
export const liquidityTier = pgEnum('liquidity_tier', ['low', 'medium', 'high'])

/** Section 6: every vendor figure is labelled. A vendor number is never silently promoted
 *  to a verified fact. */
export const provenanceLabel = pgEnum('provenance_label', ['verified', 'vendor_claim'])

/*
 * accrual.ts `AccrualResult.zeroFactor`, camelCase VERBATIM. An earlier revision used
 * snake_case labels and a mapping in the commit route; the mapping was never written, and
 * compiling the commit path against it produced
 *   TS2322: Type '"accrualPct" | "segmentRevenueUsd" | "captureShare" | null' is not
 *   assignable to type '"segment_revenue_usd" | ...'
 * while the database rejected the camelCase label outright. No mapping means no mapping to
 * get wrong, and tsc now checks the assignment for free.
 */
export const accrualZeroFactor = pgEnum('accrual_zero_factor', [
  'segmentRevenueUsd',
  'captureShare',
  'accrualPct',
])

/** accrual.ts `PremiumResult['kind']`, verbatim including case. */
export const discoveryPremiumKind = pgEnum('discovery_premium_kind', [
  'MULTIPLE',
  'ISSUANCE_NEGATIVE',
  'PURE_PREMIUM',
])

/** The five chain modules of spec section 5 (Phase A.2). */
export const chainFactKind = pgEnum('chain_fact_kind', [
  'pool_census',
  'safety',
  'issuance',
  'holders',
  'accrual',
])

// ---------------------------------------------------------------------------
// coins
// ---------------------------------------------------------------------------

export const coins = pgTable(
  'coins',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    symbol: text('symbol').notNull(),
    name: text('name').notNull(),
    /** Nullable: not every researched coin is listed on CoinGecko. */
    coingeckoId: text('coingecko_id'),
    /** text, not an enum: coins are researched before the A.2 chain layer exists, and
     *  adding a chain should not be a migration. */
    chain: text('chain').notNull(),
    /** Nullable: a native asset has no contract. */
    contractAddress: text('contract_address'),
    addressSources: jsonb('address_sources').$type<string[]>().notNull().default([]),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    check('coins_symbol_not_blank', nonBlank(t.symbol)),
    check('coins_name_not_blank', nonBlank(t.name)),
    check('coins_chain_not_blank', nonBlank(t.chain)),
    /*
     * CASE, not AND. jsonb_array_length() RAISES on a non-array and Postgres does not
     * guarantee AND short-circuits — written right-to-left the AND form fails with
     * "cannot get array length of a non-array", a raw function error rather than a
     * constraint violation. CASE never evaluates the untaken arm. The >= 2 rule is about
     * verifying an ADDRESS, so a native asset with none is exempt.
     */
    check(
      'coins_address_sources_min_2',
      sql`CASE
            WHEN jsonb_typeof(${t.addressSources}) <> 'array' THEN false
            WHEN ${t.contractAddress} IS NULL THEN true
            ELSE jsonb_array_length(${t.addressSources}) >= 2
          END`,
    ),
    /** One coin row per (chain, address), or the ledger splits one coin's history in two.
     *  Partial: a native asset carries NULL and Postgres treats NULLs as distinct. */
    uniqueIndex('coins_chain_address_uniq')
      .on(t.chain, sql`lower(${t.contractAddress})`)
      .where(sql`${t.contractAddress} IS NOT NULL`),
    index('coins_symbol_idx').on(t.symbol),
  ],
)

// ---------------------------------------------------------------------------
// reports
// ---------------------------------------------------------------------------

export const reports = pgTable(
  'reports',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    coinId: uuid('coin_id')
      .notNull()
      .references(() => coins.id, { onDelete: 'restrict' }),
    /*
     * Rule 4: the COMPARE-AND-SWAP token, not a revision number. Every draft mutation is
     * UPDATE ... WHERE id = $1 AND version = $2, 409 on zero rows.
     *
     * There is deliberately NO unique constraint on (coin_id, version). The discarded SQLite
     * plan declared UNIQUE (coin_id, version) under the older reading where `version`
     * numbered a coin's reports. Rule 4 overturned that: re-researching a coin creates a NEW
     * reports row, and each report independently walks 1, 2, 3..., so the constraint would
     * make the second report's first save collide with the first report's first save — as a
     * unique-violation inside the commit transaction, after the verifier has already written
     * its results. Reports are distinguished by id; their order is created_at / committed_at.
     */
    version: integer('version').notNull().default(1),
    status: reportStatus('status').notNull().default('draft'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    committedAt: timestamp('committed_at', { withTimezone: true }),
    /*
     * THE COIN IDENTITY SNAPSHOT, written by coinpicks_assert_commitable() at the moment of
     * commit and frozen by reports_immutable thereafter.
     *
     * `coins` has no immutability guard and cannot have a useful one: a token legitimately
     * migrates contract, and the old reports should keep naming the contract they were
     * actually researched against rather than blocking the migration. Without this snapshot,
     * `UPDATE coins SET symbol='SCAM', contract_address='0xdeadbeef'` — CONFIRMED to succeed
     * live — silently re-points every committed report on that coin, and every forward
     * return ever computed from the (chain, contract_address) join, while the committed
     * report's own bytes stay unchanged so nothing looks wrong.
     *
     * contract_address is nullable here for the same reason it is on coins: a native asset
     * has none. symbol and chain are the pair the CHECK keys off.
     */
    coinSymbol: text('coin_symbol'),
    coinChain: text('coin_chain'),
    coinContractAddress: text('coin_contract_address'),
  },
  (t) => [
    check('reports_version_positive', sql`${t.version} >= 1`),
    /** Section 10: every commit snapshots the report immutably WITH ITS TIMESTAMP. A
     *  committed row without one has no ledger date to join on. */
    check(
      'reports_committed_at_iff_committed',
      sql`(${t.status} = 'committed') = (${t.committedAt} IS NOT NULL)`,
    ),
    check(
      'reports_identity_snapshot_iff_committed',
      sql`(${t.status} = 'committed')
          = (${t.coinSymbol} IS NOT NULL AND ${t.coinChain} IS NOT NULL)`,
    ),
    index('reports_coin_id_idx').on(t.coinId),
    /** The ledger reads committed rows in commit order. */
    index('reports_committed_idx').on(t.committedAt).where(sql`${t.status} = 'committed'`),
  ],
)

// ---------------------------------------------------------------------------
// report_scores — one row per report, created by the reports_seed_scores trigger
//
// EVERY column here except report_id is nullable, and accrual_assessed is generated. This
// table holds the DRAFT: a half-finished report has to survive a browser reload. The
// containment guarantee of spec 8.1 is unchanged and restated exactly: the frozen formulas
// are evaluated in exactly one place, and no LLM-reachable code path writes this table.
// `product_passed IS NOT NULL` is the sentinel meaning "the frozen gate ran".
// ---------------------------------------------------------------------------

export const reportScores = pgTable(
  'report_scores',
  {
    reportId: uuid('report_id')
      .primaryKey()
      .references(() => reports.id, { onDelete: 'cascade' }),

    /** Rule 3. Written by the commit route from SCORING_VERSION in scoring/ranges.ts.
     *  Nullable at column level and NOT NULL by trigger at the moment of commit, which is
     *  what "conditionally NOT NULL" has to mean in SQL. */
    scoringVersion: text('scoring_version'),

    overviewSentence: text('overview_sentence'),
    riskNotes: text('risk_notes'),

    // -- Product gate: productGate() / ProductGateResult ----------------------
    productEase: integer('product_ease'),
    productHairFire: integer('product_hair_fire'),
    productExclusivity: integer('product_exclusivity'),
    productTotal: integer('product_total'),
    productPassed: boolean('product_passed'),
    productEaseRationale: text('product_ease_rationale'),
    productHairFireRationale: text('product_hair_fire_rationale'),
    productExclusivityRationale: text('product_exclusivity_rationale'),

    // -- Liquidity: no formula, the human tiers. Every measured figure carries the
    //    section 6 provenance quartet, and the tier carries its own timestamp so a tier
    //    cannot be justified by numbers that postdate and contradict it.
    liquidityTier: liquidityTier('liquidity_tier'),
    liquidityTierAssignedAt: timestamp('liquidity_tier_assigned_at', { withTimezone: true }),
    liquidityJustification: text('liquidity_justification'),
    liquidityDepth2pctUsd: doublePrecision('liquidity_depth_2pct_usd'),
    liquidityDepthSource: text('liquidity_depth_source'),
    liquidityDepthUrl: text('liquidity_depth_url'),
    liquidityDepthLabel: provenanceLabel('liquidity_depth_label'),
    liquidityDepthMeasuredAt: timestamp('liquidity_depth_measured_at', { withTimezone: true }),
    liquidityTopPoolTvlUsd: doublePrecision('liquidity_top_pool_tvl_usd'),
    liquidityTopPoolSource: text('liquidity_top_pool_source'),
    liquidityTopPoolUrl: text('liquidity_top_pool_url'),
    liquidityTopPoolLabel: provenanceLabel('liquidity_top_pool_label'),
    liquidityTopPoolMeasuredAt: timestamp('liquidity_top_pool_measured_at', {
      withTimezone: true,
    }),
    /** framework/03 needs "no pool" distinguishable from "not measured" — the tier rule
     *  depends on the difference. */
    liquidityNoDexPool: boolean('liquidity_no_dex_pool').notNull().default(false),
    /** Pools left after the 5%-deviation poison-pair drop (section 5) — Phase A.2. */
    liquiditySurvivingPools: integer('liquidity_surviving_pools'),

    // -- Narrative: narrativeTotal() over NARRATIVE_MAX -----------------------
    narrativeMaturity: integer('narrative_maturity'),
    narrativeSmartMoney: integer('narrative_smart_money'),
    /** 0-6 HERE. product_hair_fire is 0-10. Two distinct fields, neither derived from the
     *  other (section 2.1). */
    narrativeHairFire: integer('narrative_hair_fire'),
    narrativeCommunication: integer('narrative_communication'),
    narrativeLineage: integer('narrative_lineage'),
    narrativeMutation: integer('narrative_mutation'),
    narrativeTotal: integer('narrative_total'),
    /** Section 2.3 requires a 1-2 sentence rationale per sub-score. Without a column the
     *  commit gate cannot enforce it at all. These are NOT the deleted *_draft_reason
     *  columns: they hold the HUMAN's "My Decision" prose. */
    narrativeMaturityRationale: text('narrative_maturity_rationale'),
    narrativeSmartMoneyRationale: text('narrative_smart_money_rationale'),
    narrativeHairFireRationale: text('narrative_hair_fire_rationale'),
    narrativeCommunicationRationale: text('narrative_communication_rationale'),
    narrativeLineageRationale: text('narrative_lineage_rationale'),
    narrativeMutationRationale: text('narrative_mutation_rationale'),

    // -- Team: teamWeightedScore(). A MEAN, so explicitly not an integer. Per-person
    //    H/M/L live in report_team; memberScore() is h+m+l and is NOT stored, because a
    //    stored sum is a second place to drift.
    teamWeightedScore: doublePrecision('team_weighted_score'),

    // -- Value accrual: AccrualInput -----------------------------------------
    accrualSegmentRevenueUsd: doublePrecision('accrual_segment_revenue_usd'),
    accrualCaptureShare: doublePrecision('accrual_capture_share'),
    /** A fraction in [0, 1] DESPITE THE NAME, which tracks the frozen table's `accrual_pct`
     *  deliberately (ruled 2026-09-21). */
    accrualPct: doublePrecision('accrual_pct'),
    accrualAnnualIssuanceUsd: doublePrecision('accrual_annual_issuance_usd'),
    /*
     * GENERATED, not a flag the editor sets. An unfilled accrual section must not be
     * indistinguishable from a measured zero: with all four inputs NULL, the shortest
     * expression that satisfies the compiler in the gate is `?? 0`, zero is in range, and
     * discoveryPremium() then returns PURE_PREMIUM — the framework's harshest verdict,
     * narrowed by the 2026-09-21 ruling to mean ZERO FORCED FLOW — about a coin nobody
     * assessed, immutably. Deriving the flag from the inputs makes absence and zero
     * different states that no code path can conflate, and rs_premium_needs_assessment
     * below forbids a verdict without an assessment.
     */
    accrualAssessed: boolean('accrual_assessed')
      .notNull()
      .generatedAlwaysAs(
        sql`accrual_segment_revenue_usd IS NOT NULL
            AND accrual_capture_share IS NOT NULL
            AND accrual_pct IS NOT NULL
            AND accrual_annual_issuance_usd IS NOT NULL`,
      ),
    /** Section 1 allows accrual to be absent — "or the finding that none exists" — so the
     *  completeness CHECK cannot simply require the inputs. It requires this instead. */
    accrualAbsentReason: text('accrual_absent_reason'),
    accrualRationale: text('accrual_rationale'),

    // -- Value accrual: AccrualResult ----------------------------------------
    accrualGrossAnnualFlowUsd: doublePrecision('accrual_gross_annual_flow_usd'),
    accrualNetAnnualFlowUsd: doublePrecision('accrual_net_annual_flow_usd'),
    /** "One zero anywhere zeroes the product" — WHICH one. NULL = no zero factor. */
    accrualZeroFactor: accrualZeroFactor('accrual_zero_factor'),
    /** Section 1: "the contract address that makes it true (or the finding that none
     *  exists)". chain/accrual.ts — Phase A.2. */
    accrualContractAddress: text('accrual_contract_address'),
    accrualFinding: text('accrual_finding'),
    /** Named `trailing_90d` and never annualised: a trailing-90-day dollar figure sitting
     *  beside two annual dollar figures, all suffixed `_usd`, is a 4x unit error waiting
     *  for the first ledger query that treats them as comparable. Phase A.2. */
    accrualMeasuredTrailing90dUsd: doublePrecision('accrual_measured_trailing_90d_usd'),

    // -- Discovery premium: discoveryPremium() -------------------------------
    /** The `marketCapUsd` argument, with the same provenance quartet the liquidity figures
     *  carry. It is the single most volatile input in the report — it moves 20% in a week —
     *  and the ledger joins a premium multiple against forward returns, so it has to be
     *  possible to say what price the multiple was struck at. */
    discoveryMarketCapUsd: doublePrecision('discovery_market_cap_usd'),
    discoveryMarketCapSource: text('discovery_market_cap_source'),
    discoveryMarketCapUrl: text('discovery_market_cap_url'),
    discoveryMarketCapLabel: provenanceLabel('discovery_market_cap_label'),
    discoveryMarketCapMeasuredAt: timestamp('discovery_market_cap_measured_at', {
      withTimezone: true,
    }),
    /*
     * PremiumResult is a three-way discriminated union. It lands as a discriminant column
     * plus exactly ONE payload column — the MULTIPLE arm's `multiple`. ISSUANCE_NEGATIVE's
     * payload (gross, net) is already stored above and PURE_PREMIUM has none, so the union
     * costs two columns rather than four.
     */
    discoveryPremiumKind: discoveryPremiumKind('discovery_premium_kind'),
    discoveryPremiumMultiple: doublePrecision('discovery_premium_multiple'),

    /** How much of this report's evidence was waived, so a ledger query can stratify
     *  committed reports by it. That number is a finding about the framework, not
     *  bookkeeping. Written at commit. */
    waivedCitationCount: integer('waived_citation_count'),
  },
  (t) => [
    // -- Ranges: assertIntegerRange() reproduced. Rejected, never clamped. -----
    // These bounds also live in scoring/{ranges,product,narrative}.ts. Task 9 pins the two
    // copies together with a test that reads the generated .sql.
    check('rs_product_ease_range', sql`${t.productEase} BETWEEN 0 AND 10`),
    check('rs_product_hair_fire_range', sql`${t.productHairFire} BETWEEN 0 AND 10`),
    check('rs_product_exclusivity_range', sql`${t.productExclusivity} BETWEEN 0 AND 10`),
    check('rs_narrative_maturity_range', sql`${t.narrativeMaturity} BETWEEN 0 AND 7`),
    check('rs_narrative_smart_money_range', sql`${t.narrativeSmartMoney} BETWEEN 0 AND 6`),
    check('rs_narrative_hair_fire_range', sql`${t.narrativeHairFire} BETWEEN 0 AND 6`),
    check('rs_narrative_communication_range', sql`${t.narrativeCommunication} BETWEEN 0 AND 5`),
    check('rs_narrative_lineage_range', sql`${t.narrativeLineage} BETWEEN 0 AND 4`),
    check('rs_narrative_mutation_range', sql`${t.narrativeMutation} BETWEEN 0 AND 3`),
    check('rs_team_weighted_range', sql`${t.teamWeightedScore} BETWEEN 0 AND 10`),
    check('rs_segment_revenue_nonneg', nonNegativeFinite(t.accrualSegmentRevenueUsd)),
    check('rs_capture_share_unit', unitFraction(t.accrualCaptureShare)),
    check('rs_accrual_pct_unit', unitFraction(t.accrualPct)),
    check('rs_annual_issuance_nonneg', nonNegativeFinite(t.accrualAnnualIssuanceUsd)),
    check('rs_gross_flow_nonneg', nonNegativeFinite(t.accrualGrossAnnualFlowUsd)),
    check('rs_net_flow_finite', finite(t.accrualNetAnnualFlowUsd)),
    check('rs_market_cap_nonneg', nonNegativeFinite(t.discoveryMarketCapUsd)),
    check('rs_premium_multiple_nonneg', nonNegativeFinite(t.discoveryPremiumMultiple)),
    check('rs_measured_90d_nonneg', nonNegativeFinite(t.accrualMeasuredTrailing90dUsd)),
    check('rs_depth_2pct_nonneg', nonNegativeFinite(t.liquidityDepth2pctUsd)),
    check('rs_top_pool_tvl_nonneg', nonNegativeFinite(t.liquidityTopPoolTvlUsd)),
    check('rs_surviving_pools_nonneg', sql`${t.liquiditySurvivingPools} >= 0`),
    check('rs_waived_count_nonneg', sql`${t.waivedCitationCount} >= 0`),
    check('rs_scoring_version_not_blank', nonBlank(t.scoringVersion)),

    /** Rule 3, as a database fact: a scored row names its framework version and a draft
     *  does not. This is what makes `scoring_version` conditionally NOT NULL. */
    check(
      'rs_scored_row_names_its_version',
      sql`(${t.productPassed} IS NULL) = (${t.scoringVersion} IS NULL)`,
    ),

    /*
     * Arithmetic identities, each gated on the scored sentinel.
     *
     * The gate is not decoration. Without it, an operator who types a 0 into
     * accrual_segment_revenue_usd on a half-finished draft trips
     * rs_zero_factor_matches_inputs — a derived column the commit route has not written
     * yet — and cannot save. Reproduced on the naive version. From the moment
     * product_passed is set, every identity below is enforced for the life of the row.
     */
    check(
      'rs_product_total_is_sum',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.productTotal} = ${t.productEase} + ${t.productHairFire} + ${t.productExclusivity}
          END`,
    ),
    check(
      'rs_product_passed_matches_threshold',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.productPassed} = (${t.productTotal} >= 16)
          END`,
    ),
    check(
      'rs_narrative_total_is_sum',
      sql`CASE WHEN ${t.productPassed} IS NULL OR ${t.narrativeTotal} IS NULL THEN true ELSE
            ${t.narrativeTotal} = ${t.narrativeMaturity} + ${t.narrativeSmartMoney}
              + ${t.narrativeHairFire} + ${t.narrativeCommunication}
              + ${t.narrativeLineage} + ${t.narrativeMutation}
          END`,
    ),
    check(
      'rs_gross_flow_is_product',
      sql`CASE WHEN ${t.accrualGrossAnnualFlowUsd} IS NULL THEN true ELSE
            ${t.accrualGrossAnnualFlowUsd}
              = ${t.accrualSegmentRevenueUsd} * ${t.accrualCaptureShare} * ${t.accrualPct}
          END`,
    ),
    check(
      'rs_net_flow_is_gross_minus_issuance',
      sql`CASE WHEN ${t.accrualNetAnnualFlowUsd} IS NULL THEN true ELSE
            ${t.accrualNetAnnualFlowUsd}
              = ${t.accrualGrossAnnualFlowUsd} - ${t.accrualAnnualIssuanceUsd}
          END`,
    ),
    /** `factors.find(f => input[f] === 0) ?? null` — same first-match precedence, in SQL,
     *  so the stored label cannot disagree with the inputs beside it. */
    check(
      'rs_zero_factor_matches_inputs',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.accrualZeroFactor} IS NOT DISTINCT FROM (
              CASE
                WHEN ${t.accrualSegmentRevenueUsd} = 0 THEN 'segmentRevenueUsd'
                WHEN ${t.accrualCaptureShare} = 0 THEN 'captureShare'
                WHEN ${t.accrualPct} = 0 THEN 'accrualPct'
                ELSE NULL
              END)::accrual_zero_factor
          END`,
    ),
    /*
     * discoveryPremium()'s branch order, in SQL — INCLUDING the noise floor that Task 8
     * adds to the TypeScript. `net > 0` alone is not the MULTIPLE condition: with segment
     * revenue $100,000,000, capture 0.07, accrual 0.01 and issuance $70,000 — a token
     * forcing exactly as much to holders as it prints — float64 leaves
     * gross = 70000.00000000001 and net = 1.455e-11, and the naive branch commits
     * kind='MULTIPLE' with a payback multiple of 3.4e21. Verified live on 16.13, both that
     * the residue occurs and that this CHECK refuses the verdict.
     *
     * PURE_PREMIUM requires gross = 0 — the 2026-09-21 ruling that it was over-applied.
     */
    check(
      'rs_premium_kind_matches_flows',
      sql`${t.discoveryPremiumKind} IS NOT DISTINCT FROM (
            CASE
              WHEN ${t.accrualNetAnnualFlowUsd} IS NULL THEN NULL
              WHEN ${t.accrualNetAnnualFlowUsd} > 0
                   AND ${t.accrualNetAnnualFlowUsd} >= ${t.accrualGrossAnnualFlowUsd} * 1e-9
                THEN 'MULTIPLE'
              WHEN ${t.accrualGrossAnnualFlowUsd} > 0 THEN 'ISSUANCE_NEGATIVE'
              ELSE 'PURE_PREMIUM'
            END)::discovery_premium_kind`,
    ),
    /** Only the MULTIPLE arm carries a multiple, so a stale non-NULL multiple cannot sit
     *  beside a PURE_PREMIUM verdict — permanently, since the row is immutable the moment
     *  it is wrong. */
    check(
      'rs_premium_multiple_iff_multiple',
      sql`(${t.discoveryPremiumKind} = 'MULTIPLE') = (${t.discoveryPremiumMultiple} IS NOT NULL)`,
    ),
    /** The frozen formula itself: market_cap / net_annual_flow. An identity rather than a
     *  bound, so no invented ceiling can reject a row the frozen core produced. CASE, not
     *  a bare comparison: float8 division by zero RAISES in Postgres and a CHECK is not
     *  guaranteed to short-circuit. */
    check(
      'rs_premium_multiple_is_quotient',
      sql`CASE WHEN ${t.discoveryPremiumMultiple} IS NULL THEN true ELSE
            ${t.discoveryPremiumMultiple}
              = ${t.discoveryMarketCapUsd} / ${t.accrualNetAnnualFlowUsd}
          END`,
    ),
    check(
      'rs_premium_needs_assessment',
      sql`${t.accrualAssessed} OR ${t.discoveryPremiumKind} IS NULL`,
    ),

    // -- Provenance: a figure and the story of where it came from arrive together ------
    check(
      'rs_depth_provenance_complete',
      sql`(${t.liquidityDepth2pctUsd} IS NOT NULL) = (
            ${t.liquidityDepthSource} IS NOT NULL AND ${t.liquidityDepthUrl} IS NOT NULL
            AND ${t.liquidityDepthLabel} IS NOT NULL
            AND ${t.liquidityDepthMeasuredAt} IS NOT NULL)`,
    ),
    check(
      'rs_top_pool_provenance_complete',
      sql`(${t.liquidityTopPoolTvlUsd} IS NOT NULL) = (
            ${t.liquidityTopPoolSource} IS NOT NULL AND ${t.liquidityTopPoolUrl} IS NOT NULL
            AND ${t.liquidityTopPoolLabel} IS NOT NULL
            AND ${t.liquidityTopPoolMeasuredAt} IS NOT NULL)`,
    ),
    check(
      'rs_market_cap_provenance_complete',
      sql`(${t.discoveryMarketCapUsd} IS NOT NULL) = (
            ${t.discoveryMarketCapSource} IS NOT NULL AND ${t.discoveryMarketCapUrl} IS NOT NULL
            AND ${t.discoveryMarketCapLabel} IS NOT NULL
            AND ${t.discoveryMarketCapMeasuredAt} IS NOT NULL)`,
    ),
    /** "No DEX pool" and "TVL not measured" stay different states. */
    check(
      'rs_no_dex_pool_excludes_tvl',
      sql`NOT (${t.liquidityNoDexPool} AND ${t.liquidityTopPoolTvlUsd} IS NOT NULL)`,
    ),
    check(
      'rs_tier_assigned_at_iff_tier',
      sql`(${t.liquidityTier} IS NULL) = (${t.liquidityTierAssignedAt} IS NULL)`,
    ),
    /** The tier is a human judgment about two measurements. It may not predate them: an
     *  operator who assigns 'high', then re-pulls depth that has halved, must not commit a
     *  tier contradicted by the numbers printed beside it. */
    check(
      'rs_tier_not_older_than_its_inputs',
      sql`(${t.liquidityTierAssignedAt} IS NULL
           OR ${t.liquidityDepthMeasuredAt} IS NULL
           OR ${t.liquidityTierAssignedAt} >= ${t.liquidityDepthMeasuredAt})
          AND (${t.liquidityTierAssignedAt} IS NULL
           OR ${t.liquidityTopPoolMeasuredAt} IS NULL
           OR ${t.liquidityTierAssignedAt} >= ${t.liquidityTopPoolMeasuredAt})`,
    ),

    /*
     * Section 2.1: "A failed gate ends the report — later sections stay locked." So every
     * downstream column is nullable at column level and required only when the gate PASSED.
     * A dropped project still commits: that decision is a ledger row, and the ledger needs
     * the 0-15 population to have anything to compare a pass against.
     *
     * Note what this buys and what it does not: it records the rejected population and its
     * product totals. It does NOT cure survivorship bias for the narrative or team scores,
     * because those only exist on a report whose product gate passed.
     */
    check(
      'rs_gate_completeness',
      sql`CASE WHEN ${t.productPassed} THEN
            ${present(t.overviewSentence)}
            AND ${present(t.productEaseRationale)}
            AND ${present(t.productHairFireRationale)}
            AND ${present(t.productExclusivityRationale)}
            AND ${t.liquidityTier} IS NOT NULL
            AND ${present(t.liquidityJustification)}
            AND ${t.liquidityDepth2pctUsd} IS NOT NULL
            AND (${t.liquidityTopPoolTvlUsd} IS NOT NULL OR ${t.liquidityNoDexPool})
            AND ${t.narrativeMaturity} IS NOT NULL
            AND ${t.narrativeSmartMoney} IS NOT NULL
            AND ${t.narrativeHairFire} IS NOT NULL
            AND ${t.narrativeCommunication} IS NOT NULL
            AND ${t.narrativeLineage} IS NOT NULL
            AND ${t.narrativeMutation} IS NOT NULL
            AND ${t.narrativeTotal} IS NOT NULL
            AND ${present(t.narrativeMaturityRationale)}
            AND ${present(t.narrativeSmartMoneyRationale)}
            AND ${present(t.narrativeHairFireRationale)}
            AND ${present(t.narrativeCommunicationRationale)}
            AND ${present(t.narrativeLineageRationale)}
            AND ${present(t.narrativeMutationRationale)}
            AND ${t.teamWeightedScore} IS NOT NULL
            AND ${present(t.accrualRationale)}
            AND ${present(t.riskNotes)}
            AND ${t.waivedCitationCount} IS NOT NULL
            AND CASE WHEN ${t.accrualAssessed}
                  THEN ${t.accrualGrossAnnualFlowUsd} IS NOT NULL
                       AND ${t.accrualNetAnnualFlowUsd} IS NOT NULL
                       AND ${t.discoveryMarketCapUsd} IS NOT NULL
                       AND ${t.discoveryPremiumKind} IS NOT NULL
                  ELSE ${present(t.accrualAbsentReason)}
                END
          ELSE true END`,
    ),
  ],
)
```

Continuing the same file, `apps/api/src/db/schema.ts`, directly after the `reportScores` block:

```ts
// ---------------------------------------------------------------------------
// report_team
// ---------------------------------------------------------------------------

export const reportTeam = pgTable(
  'report_team',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /** Presentation order only — framework/06 mandates Founder, Head of Product, Head of
     *  Marketing, standouts, advisors. It is NOT an identity: inserting a newly-found
     *  co-founder at position 1 renumbers everyone. Citations key on `id`, never on this
     *  (see the citations.field note below). teamWeightedScore() is order-independent. */
    position: integer('position').notNull(),
    name: text('name').notNull(),
    /*
     * The person's identity within the report. framework/05 lets one person hold two roles,
     * and entering them twice weights that person 5+1 inside a frozen formula: a team of
     * three people listed as four rows passes both of teamWeightedScore()'s guards and
     * returns (Alice x 5 + Alice + Bob) / 7 instead of the honest "team must have 3 to 5
     * people, got 2". Whitespace and case variants slip past a naive name constraint, so
     * the key is normalised before it is uniquified.
     *
     * '[[:space:]]+', never '\s+': a drizzle sql template eats a single backslash and
     * silently emits 's+', which normalises the letter s. The POSIX class has no escape to
     * get wrong.
     */
    nameKey: text('name_key')
      .notNull()
      .generatedAlwaysAs(sql`lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')))`),
    /** An array, so one person holding two roles is one row. */
    roles: text('roles').array().notNull(),
    isFounder: boolean('is_founder').notNull(),
    h: integer('h').notNull(),
    m: integer('m').notNull(),
    l: integer('l').notNull(),
    /** Section 2.4: one sentence about PRIOR experience, carrying a financial metric.
     *  Neither half is machine-checkable; only non-emptiness is. */
    summary: text('summary').notNull(),
  },
  (t) => [
    check('rt_h_range', sql`${t.h} BETWEEN 0 AND 5`),
    check('rt_m_range', sql`${t.m} BETWEEN 0 AND 3`),
    check('rt_l_range', sql`${t.l} BETWEEN 0 AND 2`),
    check('rt_position_positive', sql`${t.position} >= 1`),
    check('rt_name_not_blank', nonBlank(t.name)),
    check('rt_roles_not_empty', sql`array_length(${t.roles}, 1) >= 1`),
    check('rt_summary_not_blank', nonBlank(t.summary)),
    uniqueIndex('rt_report_position_uniq').on(t.reportId, t.position),
    uniqueIndex('rt_report_name_key_uniq').on(t.reportId, t.nameKey),
    /** AT MOST one founder, as a database fact. "Exactly one" and "3-5 people" are
     *  cardinality ACROSS rows: teamWeightedScore() throws on both inside the commit
     *  transaction, and the rule-2 trigger then freezes the set. A row-level CHECK cannot
     *  see siblings. */
    uniqueIndex('rt_one_founder_per_report').on(t.reportId).where(sql`${t.isFounder}`),
    index('rt_report_id_idx').on(t.reportId),
  ],
)

// ---------------------------------------------------------------------------
// citations
// ---------------------------------------------------------------------------

export const citations = pgTable(
  'citations',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /*
     * The report field this citation backs, e.g. 'narrative_maturity'. Left as text: team
     * rows and accrual inputs are citable too, and a pgEnum here would need a migration for
     * every newly citable field. The vocabulary is owned by the commit gate.
     *
     * A team citation is 'team:' || report_team.id — the row's uuid, NEVER its position.
     * Position is reorderable, so keying on it silently reattaches every team citation to
     * the person's neighbour the moment a co-founder is inserted at position 1.
     */
    field: text('field').notNull(),
    url: text('url').notNull(),
    quote: text('quote').notNull(),
    status: citationStatus('status').notNull().default('unverified'),
    /*
     * What the VERIFIER last said, recorded even when the human has waived. Without it,
     * 'waived over a JS-rendered page that could not be checked' and 'waived over a quote
     * the fetch proved is not on the page' are indistinguishable at the commit gate — and
     * section 7's waiver plainly exists for the first. The commit gate refuses a waiver
     * whose last_outcome is 'failed'.
     */
    lastOutcome: citationStatus('last_outcome'),
    /** Section 8.2. NO DEFAULT on purpose: a model row must not inherit 'human' by
     *  omission, which is the one mislabel that would corrupt the selection-rate question
     *  this column exists to answer. */
    origin: citationOrigin('origin').notNull(),
    finderProvider: text('finder_provider'),
    finderModel: text('finder_model'),
    /** Section 8.2: NULL = an unselected candidate — offered, verified, not taken. The
     *  commit gate counts only selected rows, as both a blocker and a credential. */
    selectedAt: timestamp('selected_at', { withTimezone: true }),
    verifiedAt: timestamp('verified_at', { withTimezone: true }),
    httpStatus: integer('http_status'),
    matchedOffset: integer('matched_offset'),
    /** Section 7: the only escape from the gate, and it has to be recorded. */
    waiverReason: text('waiver_reason'),
    /** Not in section 4.2. Section 8.2 wants selection rate by provider answerable later;
     *  without an offered-at time a candidate has no age to measure. */
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    check('ct_field_not_blank', nonBlank(t.field)),
    check('ct_url_not_blank', nonBlank(t.url)),
    check('ct_quote_not_blank', nonBlank(t.quote)),
    check('ct_http_status_range', sql`${t.httpStatus} BETWEEN 100 AND 599`),
    check('ct_matched_offset_nonneg', sql`${t.matchedOffset} >= 0`),
    /** Section 7: "an explicit waived status with a RECORDED waiver_reason". */
    check(
      'ct_waiver_reason_iff_waived',
      sql`(${t.status} = 'waived') = (${t.waiverReason} IS NOT NULL AND length(btrim(${t.waiverReason})) > 0)`,
    ),
    /** Section 8.2: finder provenance belongs to model candidates and only to them. */
    check(
      'ct_finder_fields_iff_model',
      sql`(${t.origin} = 'model') = (${t.finderProvider} IS NOT NULL AND ${t.finderModel} IS NOT NULL)`,
    ),
    /** 'unverified' means the verifier has not run; every other state means it has.
     *  `OR status = 'waived'` is not sloppiness: a human waiving a permanently dead or
     *  paywalled URL never got a successful fetch, and the strict biconditional would force
     *  the waive route to fabricate a verified_at to satisfy a constraint. */
    check(
      'ct_verified_at_iff_resolved',
      sql`(${t.status} = 'unverified') = (${t.verifiedAt} IS NULL) OR ${t.status} = 'waived'`,
    ),
    /** last_outcome is what the machine found. 'waived' is a human decision and is never a
     *  fetch result, so it cannot appear here. */
    check('ct_last_outcome_not_waived', sql`${t.lastOutcome} <> 'waived'`),
    index('ct_report_id_idx').on(t.reportId),
    /** The commit gate's query: this report's SELECTED citations and their statuses. */
    index('ct_report_selected_idx')
      .on(t.reportId, t.status)
      .where(sql`${t.selectedAt} IS NOT NULL`),
    /** Section 8.2: "did the evidence finder actually help?" */
    index('ct_finder_idx').on(t.finderProvider, t.finderModel).where(sql`${t.origin} = 'model'`),
  ],
)

// ---------------------------------------------------------------------------
// chain_facts — Phase A.2
//
// Deliberately NOT covered by the immutability triggers, and that is an open item rather
// than a conclusion: rule 2 names four tables, chain_facts is A.2, and rows with a NULL
// report_id would be freely mutable while their siblings were frozen. Recorded in
// agents/decisions.md so the next reader does not "complete" the trigger set by accident.
// ---------------------------------------------------------------------------

export const chainFacts = pgTable(
  'chain_facts',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    coinId: uuid('coin_id')
      .notNull()
      .references(() => coins.id, { onDelete: 'restrict' }),
    /** Section 4.2 writes it `report_id?`: a fact can be pulled for a coin before any report
     *  exists. */
    reportId: uuid('report_id').references(() => reports.id, { onDelete: 'cascade' }),
    kind: chainFactKind('kind').notNull(),
    chain: text('chain').notNull(),
    /** EVERY row carries block_number and fetched_at — the framework's "verified (say where)
     *  or a guess (say so)". bigint because a block height is not a 32-bit quantity in
     *  principle; mode 'number' is exact to 2^53. */
    blockNumber: bigint('block_number', { mode: 'number' }).notNull(),
    fetchedAt: timestamp('fetched_at', { withTimezone: true }).notNull(),
    /** Rule 5: jsonb. Its shape varies by `kind`, so only the container is constrained. */
    payload: jsonb('payload').notNull(),
  },
  (t) => [
    check('cf_block_number_nonneg', sql`${t.blockNumber} >= 0`),
    check('cf_chain_not_blank', nonBlank(t.chain)),
    check('cf_payload_is_object', sql`jsonb_typeof(${t.payload}) = 'object'`),
    index('cf_coin_kind_idx').on(t.coinId, t.kind),
    index('cf_report_id_idx').on(t.reportId),
  ],
)

// ---------------------------------------------------------------------------
// forward_returns — the only table the Python `research` role may write
// ---------------------------------------------------------------------------

export const forwardReturns = pgTable(
  'forward_returns',
  {
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /** Section 13: FROZEN at 30/90/180/365 days from commit date. "Retrofitting horizons
     *  onto existing commits is fine; comparing across changed horizons is not" — which is
     *  the failure this CHECK exists to make impossible. */
    horizonDays: integer('horizon_days').notNull(),
    /*
     * The two prices and where they came from. The earlier design stored only the quotient,
     * in a column called `return_pct` that held a fraction, guarded by CHECK (>= -1): that
     * catches a percentage-scaled LOSS (-12.5 fails) and passes every percentage-scaled
     * GAIN (+12.5 stores clean), so the guard worked on half the distribution and
     * research/forward_returns.py — which does not exist yet — had even odds of failing
     * silently into an unrecoverable mixed-unit ledger column.
     *
     * Storing the prices fixes the unit by construction and satisfies section 8's rule that
     * every number is verified (say where) or a guess (say so), which a bare quotient could
     * not.
     */
    priceAtCommitUsd: doublePrecision('price_at_commit_usd').notNull(),
    priceAtHorizonUsd: doublePrecision('price_at_horizon_usd').notNull(),
    priceSource: text('price_source').notNull(),
    pricedAt: timestamp('priced_at', { withTimezone: true }).notNull(),
    /** GENERATED: it cannot disagree with the prices it came from, and the research role
     *  cannot write it at all ("column can only be updated to DEFAULT"). A FRACTION —
     *  0.125 is +12.5% — and the name now says so. */
    returnFraction: doublePrecision('return_fraction')
      .notNull()
      .generatedAlwaysAs(sql`(price_at_horizon_usd / price_at_commit_usd) - 1`),
    computedAt: timestamp('computed_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.reportId, t.horizonDays] }),
    check('fr_horizon_frozen', sql`${t.horizonDays} IN (30, 90, 180, 365)`),
    /** Strictly positive: it is the divisor. */
    check(
      'fr_commit_price_positive',
      sql`${t.priceAtCommitUsd} > 0 AND ${t.priceAtCommitUsd} < 'Infinity'::float8`,
    ),
    check('fr_horizon_price_nonneg', nonNegativeFinite(t.priceAtHorizonUsd)),
    check('fr_price_source_not_blank', nonBlank(t.priceSource)),
  ],
)

// ---------------------------------------------------------------------------
// Row types. The commit path, the gate and the routes all import from here, so a renamed
// column is a compile error rather than a runtime surprise.
// ---------------------------------------------------------------------------

export type CoinRow = typeof coins.$inferSelect
export type ReportRow = typeof reports.$inferSelect
export type ReportScoresRow = typeof reportScores.$inferSelect
export type ReportTeamRow = typeof reportTeam.$inferSelect
export type CitationRow = typeof citations.$inferSelect
export type ChainFactRow = typeof chainFacts.$inferSelect
export type ForwardReturnRow = typeof forwardReturns.$inferSelect

export type NewCoin = typeof coins.$inferInsert
export type NewReport = typeof reports.$inferInsert
export type NewReportTeam = typeof reportTeam.$inferInsert
export type NewCitation = typeof citations.$inferInsert
export type NewChainFact = typeof chainFacts.$inferInsert
export type NewForwardReturn = typeof forwardReturns.$inferInsert
```

- [ ] **Step 5: Generate the migration and read the SQL**

```bash
cd /home/dev/projects/trade-god/apps/api
pnpm db:generate --name init
```
Expected, on stdout:
```
7 tables
chain_facts 8 columns 2 indexes 2 fks
citations 16 columns 3 indexes 1 fks
coins 8 columns 2 indexes 0 fks
forward_returns 8 columns 0 indexes 1 fks
report_scores 62 columns 0 indexes 1 fks
report_team 11 columns 4 indexes 1 fks
reports 9 columns 2 indexes 1 fks
[✓] Your SQL migration file ➜ drizzle/0000_init.sql
```

Then read `apps/api/drizzle/0000_init.sql` and confirm three things by eye, because they are the ones a silent Drizzle change would break:

```bash
grep -n "GENERATED ALWAYS AS" drizzle/0000_init.sql
grep -n "accrual_zero_factor\" AS ENUM" drizzle/0000_init.sql
grep -n "product_total\" >= 16" drizzle/0000_init.sql
```
Expected: three `GENERATED ALWAYS AS (...) STORED` columns (`return_fraction`, `accrual_assessed`, `name_key`); the enum reading `ENUM('segmentRevenueUsd', 'captureShare', 'accrualPct')`; and the product threshold present as a literal `16`.

- [ ] **Step 6: Run the suite**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test
```
Expected: `Test Files 6 passed (6)` — the four scoring files, `client.test.ts` (3 tests) and `schema.test.ts` (12 tests), for **46 tests passed**. If globalSetup reports `could not rebuild coinpicks_test`, run `pnpm --filter @coinpicks/api run db:bootstrap` and retry.

- [ ] **Step 7: Typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: the seven-table schema and its first migration

Every domain the frozen core enforces is a CHECK here too, because a type in
TypeScript is not a constraint in Postgres. Three shapes are deliberate and
will look wrong without the reason: report_scores holds the nullable DRAFT with
its identities gated on the scored sentinel, accrual_assessed is generated so a
blank section can never read as a measured zero, and forward_returns computes
its fraction from two stored prices so the unit cannot be typed wrong."
```

---

### Task 4: The immutability triggers

Schema rule 2, and the one piece of SQL that makes *"a committed report is never edited"* true against a stray `psql`, a GUI client or an agent with shell access. Drizzle's DSL cannot express a trigger, so this is a `generate --custom` migration that `schema.ts` never re-emits.

**Six things here are corrections to the naive version. Do not "fix" any of them back.**

1. **`DECLARE parent_id reports.id%TYPE`**, not `text`. The naive version declared `text` against `uuid` primary keys; plpgsql does not catch that at `CREATE FUNCTION` time, so it passes migration and then **every** `INSERT`/`UPDATE`/`DELETE` on `report_scores`, `report_team` and `citations` dies at runtime with `operator does not exist: uuid = text`. `%TYPE` is correct whichever id type wins and stops the two decisions having to stay in sync.
2. **`report_id` is immutable, unconditionally, checked before anything else.** The naive trigger inspected only `NEW.report_id` on UPDATE, so moving a row *out of* a committed report was permitted. Confirmed live: three ordinary `UPDATE`s left a committed report holding 0 scores, 0 team and 1 of 2 citations — still `status='committed'` with its `committed_at` intact — while a draft inherited its 27/30 product total and its verified citations and could be committed itself. A child row belongs to one report for its whole life, so the refusal is unconditional rather than status-conditional, and the status lookup then uses **OLD** for UPDATE and DELETE and NEW only for INSERT.
3. **The missing-parent branch returns OLD for DELETE.** PostgreSQL removes the parent row *before* running the FK cascade, so the child trigger's lookup finds nothing and the naive `RAISE ... CP404` made `ON DELETE CASCADE` dead: "discard this draft" was impossible for any draft with a single citation. The obvious fix — deleting the raise — makes an orphan freely deletable, which is exactly the state finding 2's attack leaves rows in. So: allowed for DELETE only, where a parent can only be absent during a cascade the `reports` trigger already permitted.
4. **The children fire on INSERT, and there are statement-level `BEFORE TRUNCATE` triggers.** Rule 2 says "BEFORE UPDATE OR DELETE". Under the literal wording, `INSERT INTO citations ... WHERE report_id = <a committed one>` returned `INSERT 0 1` — adding a citation to a committed report is editing it by any honest reading — and `TRUNCATE citations` succeeded with every row trigger installed, because TRUNCATE does not fire row triggers at all. Task 10 amends rule 2 in `CLAUDE.md` and the spec to match.
5. **`coinpicks_assert_commitable()` fires on `BEFORE INSERT OR UPDATE OF status`.** Nothing at the database asserted that a committed report had ever been scored: a draft whose `report_scores` row was entirely NULL committed fine, and `INSERT INTO reports (..., status, committed_at) VALUES (..., 'committed', now())` produced a **born-committed** row with zero scores and zero citations, permanently frozen and impossible to ever fill because the child triggers correctly refuse INSERT on a committed parent. Including INSERT is what makes that row impossible. The same trigger writes the coin identity snapshot, so the commit route cannot forget to.
6. **Every trigger gets `ENABLE ALWAYS`.** An ORIGIN trigger is silenced by `SET session_replication_role = replica`. Confirmed both halves live: default, the replica-mode UPDATE returned `UPDATE 1` and the committed row changed; after `ENABLE ALWAYS`, the same session was refused with CP001 and the row was unchanged.

`reports_seed_scores` is new and is not a guard: it creates the `report_scores` row in the same statement that creates the report. The design never said who inserted that row, and the commit transaction only ever `UPDATE`s it — so a forgotten insert would have been a zero-row update and a `SCORES_MISSING` blocker at the worst possible moment. A trigger makes the 1:1 invariant structural.

**Files:**
- Create: `apps/api/drizzle/0001_immutability_triggers.sql` (via `drizzle-kit generate --custom`)
- Modify: `apps/api/src/db/testing.ts` (drop the manual `report_scores` insert)
- Test: `apps/api/src/db/immutability.test.ts`

**Interfaces:**
- Consumes: the seven tables from `0000_init.sql`.
- Produces, in the database: functions `coinpicks_reports_immutable()`, `coinpicks_report_child_immutable()`, `coinpicks_refuse_truncate()`, `coinpicks_seed_report_scores()`, `coinpicks_assert_commitable()`, `coinpicks_citation_claim_changed()`; twelve triggers, all `tgenabled = 'A'`. SQLSTATEs: `CP001` refused as immutable, `CP002` not commitable, `CP404` parent missing.

- [ ] **Step 1: Write the failing attack suite**

Create `apps/api/src/db/immutability.test.ts`:

```ts
import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  TEST_OWNER_URL,
  commitReportRow,
  createDraftReport,
  refusal,
  scoreAsDropped,
} from './testing.ts'

// The OWNER connection. Two reasons, and the second is the interesting one: coinpicks_app has
// no table privileges until Task 5, and coinpicks_app will never hold TRUNCATE anyway — so
// the *_no_truncate triggers exist precisely to stop the role that CAN truncate, which is
// this one. Testing them from the app role would assert `permission denied` and prove nothing
// about the trigger.
const h = openDb(TEST_OWNER_URL, 4)
afterAll(() => h.close())

/** A coin, a report, a citation, a founder — then scored and committed. */
async function committedReport() {
  const { coinId, reportId } = await createDraftReport(h.db)
  const citationId = randomUUID()
  await h.db.execute(sql`
    INSERT INTO citations (id, report_id, field, url, quote, origin)
    VALUES (${citationId}, ${reportId}, 'narrative_maturity', 'https://example.test/a',
            'a quote', 'human')`)
  await h.db.execute(sql`
    INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
    VALUES (${reportId}, 1, 'Alice Chen', ARRAY['Founder'], true, 5, 3, 0,
            'Ran a $40M book at a prior firm.')`)
  await scoreAsDropped(h.db, reportId)
  await commitReportRow(h.db, reportId)
  return { coinId, reportId, citationId }
}

describe('the scores row is seeded with the report', () => {
  it('exists without anyone inserting it', async () => {
    const { reportId } = await createDraftReport(h.db)
    const r = await h.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(1)
  })
})

describe('a report cannot be committed unscored', () => {
  it('refuses the flip when report_scores is empty', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(commitReportRow(h.db, reportId))
    expect(e.code).toBe('CP002')
    expect(e.message).toMatch(/report_scores row is missing or unscored/)
  })

  it('refuses a born-committed INSERT, which nothing could ever fill', async () => {
    const { coinId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO reports (coin_id, status, committed_at, coin_symbol, coin_chain)
        VALUES (${coinId}, 'committed', now(), 'TST', 'ethereum')`),
    )
    expect(e.code).toBe('CP002')
  })

  it('snapshots the coin identity at commit, so re-pointing the coin cannot re-point it', async () => {
    const { coinId, reportId } = await committedReport()
    await h.db.execute(sql`
      UPDATE coins SET symbol = 'SCAM', name = 'Other Token', contract_address = '0xdeadbeef'
       WHERE id = ${coinId}`)
    const r = await h.db.execute<{ coin_symbol: string; coin_chain: string }>(
      sql`SELECT coin_symbol, coin_chain FROM reports WHERE id = ${reportId}`,
    )
    expect(r.rows[0]).toEqual({ coin_symbol: 'TST', coin_chain: 'ethereum' })
  })
})

describe('a committed report is refused every write', () => {
  it('refuses UPDATE and DELETE on the report itself', async () => {
    const { reportId } = await committedReport()
    const u = await refusal(
      h.db.execute(sql`UPDATE reports SET version = 99 WHERE id = ${reportId}`),
    )
    expect(u.code).toBe('CP001')
    expect(u.message).toMatch(/is committed; UPDATE on reports is refused/)
    const d = await refusal(h.db.execute(sql`DELETE FROM reports WHERE id = ${reportId}`))
    expect(d.code).toBe('CP001')
  })

  it('refuses INSERT, UPDATE and DELETE on every child table', async () => {
    const { reportId, citationId } = await committedReport()
    for (const statement of [
      sql`UPDATE report_scores SET narrative_total = 31 WHERE report_id = ${reportId}`,
      sql`DELETE FROM report_scores WHERE report_id = ${reportId}`,
      sql`INSERT INTO citations (report_id, field, url, quote, origin)
          VALUES (${reportId}, 'narrative_lineage', 'https://example.test/late', 'late', 'human')`,
      sql`UPDATE citations SET quote = 'TAMPERED' WHERE id = ${citationId}`,
      sql`DELETE FROM citations WHERE id = ${citationId}`,
      sql`UPDATE report_team SET h = 0 WHERE report_id = ${reportId}`,
      sql`DELETE FROM report_team WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(h.db.execute(statement))
      expect(e.code).toBe('CP001')
    }
  })

  it('refuses re-parenting its children onto a draft — the attack that gutted it', async () => {
    const { reportId } = await committedReport()
    const draft = await createDraftReport(h.db)
    for (const statement of [
      sql`UPDATE report_scores SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
      sql`UPDATE report_team SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
      sql`UPDATE citations SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(h.db.execute(statement))
      expect(e.code).toBe('CP001')
      expect(e.message).toMatch(/report_id is immutable/)
    }
    const left = await h.db.execute<{ scores: number; team: number; cits: number }>(sql`
      SELECT (SELECT count(*)::int FROM report_scores WHERE report_id = ${reportId}) AS scores,
             (SELECT count(*)::int FROM report_team   WHERE report_id = ${reportId}) AS team,
             (SELECT count(*)::int FROM citations     WHERE report_id = ${reportId}) AS cits`)
    expect(left.rows[0]).toEqual({ scores: 1, team: 1, cits: 1 })
  })

  it('refuses re-parenting between two DRAFTS as well', async () => {
    const a = await createDraftReport(h.db)
    const b = await createDraftReport(h.db)
    const citationId = randomUUID()
    await h.db.execute(sql`
      INSERT INTO citations (id, report_id, field, url, quote, origin)
      VALUES (${citationId}, ${a.reportId}, 'narrative_maturity', 'https://example.test/a',
              'a quote', 'human')`)
    const e = await refusal(
      h.db.execute(sql`UPDATE citations SET report_id = ${b.reportId} WHERE id = ${citationId}`),
    )
    expect(e.code).toBe('CP001')
  })
})

describe('a draft is still fully editable', () => {
  it('can be discarded even though it has children', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO citations (report_id, field, url, quote, origin)
      VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'a quote', 'human')`)
    await h.db.execute(sql`DELETE FROM reports WHERE id = ${reportId}`)
    const r = await h.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM citations WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(0)
  })

  it('resets a citation that has been repointed at a different claim', async () => {
    const { reportId } = await createDraftReport(h.db)
    const citationId = randomUUID()
    await h.db.execute(sql`
      INSERT INTO citations (id, report_id, field, url, quote, origin, status, waiver_reason,
                             verified_at, http_status)
      VALUES (${citationId}, ${reportId}, 'narrative_maturity', 'https://example.test/a',
              'the old quote', 'human', 'waived', 'page is JS-rendered', now(), 200)`)
    await h.db.execute(sql`
      UPDATE citations SET quote = 'a different claim entirely' WHERE id = ${citationId}`)
    const r = await h.db.execute<{
      status: string
      waiver_reason: string | null
      verified_at: Date | null
      http_status: number | null
    }>(sql`SELECT status, waiver_reason, verified_at, http_status FROM citations
            WHERE id = ${citationId}`)
    expect(r.rows[0]).toEqual({
      status: 'unverified',
      waiver_reason: null,
      verified_at: null,
      http_status: null,
    })
  })
})

describe('TRUNCATE is refused on every ledger table', () => {
  it.each(['reports', 'report_scores', 'report_team', 'citations', 'forward_returns'])(
    'refuses TRUNCATE %s',
    async (table) => {
      const e = await refusal(h.db.execute(sql.raw(`TRUNCATE ${table}`)))
      expect(e.code).toBe('CP001')
      expect(e.message).toMatch(/append-only ledger/)
    },
  )
})

describe('the guards survive replica mode', () => {
  it('has all twelve triggers at ENABLE ALWAYS', async () => {
    const r = await h.db.execute<{ tgname: string; tgenabled: string }>(sql`
      SELECT t.tgname, t.tgenabled
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE NOT t.tgisinternal AND n.nspname = 'public'
       ORDER BY t.tgname`)
    expect(r.rows.map((x) => x.tgname)).toEqual([
      'citations_immutable',
      'citations_no_truncate',
      'citations_reset_verification',
      'forward_returns_no_truncate',
      'report_scores_immutable',
      'report_scores_no_truncate',
      'report_team_immutable',
      'report_team_no_truncate',
      'reports_assert_commitable',
      'reports_immutable',
      'reports_no_truncate',
      'reports_seed_scores',
    ])
    expect(r.rows.every((x) => x.tgenabled === 'A')).toBe(true)
  })
})
```

Then delete one line from `apps/api/src/db/testing.ts` — the trigger does this now:

```ts
  // Task 4 deletes the next statement: the reports_seed_scores trigger does it instead.
  await db.execute(sql`INSERT INTO report_scores (report_id) VALUES (${reportId})`)
```

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/db/immutability.test.ts
```
Expected: FAIL. The first failure is `expected the statement to be refused, but it succeeded` from the seeded-scores test's sibling cases, and `schema.test.ts` now fails too — `null value in column ... report_scores` is not the error, because there is no `report_scores` row at all and the day-one test's JOIN returns zero rows. Both are exactly the state the trigger migration fixes.

- [ ] **Step 3: Create the custom migration file**

```bash
cd /home/dev/projects/trade-god/apps/api
pnpm exec drizzle-kit generate --custom --name immutability_triggers
```
Expected: `Prepared empty file for your custom SQL migration!` and `[✓] Your SQL migration file ➜ drizzle/0001_immutability_triggers.sql`. The file contains one comment line, and `drizzle/meta/_journal.json` has gained a second entry tagged `0001_immutability_triggers`.

- [ ] **Step 4: Write the trigger SQL**

Replace the whole contents of `apps/api/drizzle/0001_immutability_triggers.sql` with the following. **The `--> statement-breakpoint` markers are load-bearing**: the migrator splits on them and on nothing else, which is what makes the semicolons inside the `$$` bodies safe. Never put a marker inside a `$$` body, and never add one anywhere else.

```sql
-- Schema rule 2. Drizzle's DSL cannot express a trigger, so this file is hand-written and
-- schema.ts never re-emits it. Verified statement by statement against PostgreSQL 16.13.
--
-- SQLSTATEs, all in a private class so they cannot be confused with a real FK RESTRICT:
--   CP001  refused: this row belongs to a committed report, or is a ledger table
--   CP002  refused: this report is not in a state that may be committed
--   CP404  refused: the parent report does not exist

CREATE OR REPLACE FUNCTION coinpicks_reports_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- OLD.status, never NEW.status. Testing NEW would refuse the commit flip itself
  -- (draft -> committed), which is the one update that must be allowed.
  IF OLD.status = 'committed' THEN
    RAISE EXCEPTION 'report % is committed; % on reports is refused', OLD.id, TG_OP
      USING ERRCODE = 'CP001';
  END IF;
  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_report_child_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  -- %TYPE, never a literal type. Declaring `text` against uuid keys passes CREATE FUNCTION
  -- and then kills EVERY child write at runtime with "operator does not exist: uuid = text",
  -- because PostgreSQL has no implicit text->uuid cast and plpgsql binds the variable as a
  -- parameter. Reproduced live.
  parent_id     reports.id%TYPE;
  parent_status reports.status%TYPE;
BEGIN
  -- FIRST, and unconditionally. The naive trigger inspected only NEW.report_id on UPDATE, so
  -- moving a row OUT of a committed report was permitted: three ordinary UPDATEs left a
  -- committed report holding 0 scores, 0 team and 1 of 2 citations while a draft inherited
  -- its numbers and its verified citations. A child row belongs to one report for its whole
  -- life; there is no legitimate re-parent in this design.
  IF TG_OP = 'UPDATE' AND NEW.report_id IS DISTINCT FROM OLD.report_id THEN
    RAISE EXCEPTION 'report_id is immutable; % on % may not re-parent a row',
      TG_OP, TG_TABLE_NAME USING ERRCODE = 'CP001';
  END IF;

  -- OLD for UPDATE and DELETE, NEW only for INSERT: the question is where the row IS, not
  -- where it is going.
  parent_id := CASE TG_OP WHEN 'INSERT' THEN NEW.report_id ELSE OLD.report_id END;

  -- FOR KEY SHARE, not a bare SELECT. A bare read sees this transaction's own snapshot, so a
  -- writer racing a commit reads 'draft', is allowed through, and commits first -- leaving a
  -- permanently immutable report carrying a row its gate never saw. FOR KEY SHARE conflicts
  -- with the FOR UPDATE the commit transaction holds, so that writer blocks here and re-reads
  -- 'committed' afterwards. It does NOT conflict with FOR NO KEY UPDATE, so ordinary
  -- concurrent draft edits are not serialised by it.
  SELECT r.status INTO parent_status FROM reports r WHERE r.id = parent_id FOR KEY SHARE;

  IF NOT FOUND THEN
    -- PostgreSQL removes the parent row BEFORE running the FK cascade, so a cascading delete
    -- always lands here. Raising unconditionally -- which the naive version did -- made
    -- ON DELETE CASCADE dead and "discard this draft" impossible for any draft with one
    -- citation. Allowing it unconditionally would make an orphaned child freely deletable,
    -- which is the state the re-parent attack above leaves rows in. So: DELETE only.
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'report % does not exist', parent_id USING ERRCODE = 'CP404';
  END IF;

  IF parent_status = 'committed' THEN
    RAISE EXCEPTION 'report % is committed; % on % is refused',
      parent_id, TG_OP, TG_TABLE_NAME USING ERRCODE = 'CP001';
  END IF;

  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- TRUNCATE does not fire FOR EACH ROW triggers at all. Verified on 16.13: with every row
  -- trigger in place, `TRUNCATE citations` returned TRUNCATE TABLE. A statement-level trigger
  -- is the only thing that stops it.
  RAISE EXCEPTION 'TRUNCATE on % is refused: this table is an append-only ledger',
    TG_TABLE_NAME USING ERRCODE = 'CP001';
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_seed_report_scores() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- The 1:1 invariant, made structural. The design never said who created this row and the
  -- commit transaction only ever UPDATEs it, so a route that forgot would produce a zero-row
  -- update and a SCORES_MISSING blocker at the worst possible moment.
  INSERT INTO report_scores (report_id) VALUES (NEW.id);
  RETURN NULL;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_assert_commitable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  scored boolean;
  c      coins%ROWTYPE;
BEGIN
  -- Rule 3, at the database. Without this a report committed with scoring_version,
  -- product_passed and product_total all NULL -- and an INSERT could mint a born-committed
  -- row with no scores and no citations, permanently frozen and impossible to ever fill,
  -- because the child triggers correctly refuse INSERT on a committed parent.
  SELECT s.product_passed IS NOT NULL AND s.scoring_version IS NOT NULL
    INTO scored
    FROM report_scores s
   WHERE s.report_id = NEW.id;

  IF NOT FOUND OR NOT scored THEN
    RAISE EXCEPTION
      'report % cannot be committed: its report_scores row is missing or unscored', NEW.id
      USING ERRCODE = 'CP002';
  END IF;

  -- The coin identity snapshot. Written HERE rather than by the commit route so it cannot be
  -- forgotten. `coins` has no guard -- UPDATE coins SET symbol='SCAM', contract_address=...
  -- was confirmed to succeed against a live committed report -- and re-pointing a coin
  -- re-points every forward return ever computed from the (chain, contract_address) join
  -- while the committed report's own bytes stay unchanged, so nothing looks wrong.
  SELECT * INTO c FROM coins WHERE id = NEW.coin_id FOR KEY SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'coin % does not exist', NEW.coin_id USING ERRCODE = 'CP404';
  END IF;

  NEW.coin_symbol           := c.symbol;
  NEW.coin_chain            := c.chain;
  NEW.coin_contract_address := c.contract_address;
  RETURN NEW;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_citation_claim_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- A waiver, a verification and an http_status belong to the claim they were granted for.
  -- Citations are freely editable while the report is a draft, and nothing otherwise tied a
  -- waiver to its text: quote fails, operator waives, operator later fixes the quote or
  -- repoints the URL, and the commit path discards the fresh 'failed' outcome because the row
  -- says 'waived'. The report then commits on a claim never mechanically confirmed anywhere,
  -- with an http_status and matched_offset that look current.
  NEW.status         := 'unverified';
  NEW.last_outcome   := NULL;
  NEW.waiver_reason  := NULL;
  NEW.verified_at    := NULL;
  NEW.http_status    := NULL;
  NEW.matched_offset := NULL;
  RETURN NEW;
END $$;
--> statement-breakpoint
-- reports itself: UPDATE and DELETE only. INSERT is how re-researching a coin works -- a new
-- reports row, not a new version of the old one.
CREATE TRIGGER reports_immutable
  BEFORE UPDATE OR DELETE ON reports
  FOR EACH ROW EXECUTE FUNCTION coinpicks_reports_immutable();
--> statement-breakpoint
-- `OF status` deliberately: on a committed row, `UPDATE reports SET version = 1234` does not
-- mention status, so this does not fire and reports_immutable refuses it with the message the
-- operator should see.
CREATE TRIGGER reports_assert_commitable
  BEFORE INSERT OR UPDATE OF status ON reports
  FOR EACH ROW WHEN (NEW.status = 'committed')
  EXECUTE FUNCTION coinpicks_assert_commitable();
--> statement-breakpoint
CREATE TRIGGER reports_seed_scores
  AFTER INSERT ON reports
  FOR EACH ROW EXECUTE FUNCTION coinpicks_seed_report_scores();
--> statement-breakpoint
-- The children include INSERT. Without it, `INSERT INTO citations ... report_id = <a
-- committed one>` returned INSERT 0 1 on 16.13, which is editing a committed report by any
-- honest reading.
CREATE TRIGGER report_scores_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON report_scores
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
CREATE TRIGGER report_team_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON report_team
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
CREATE TRIGGER citations_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON citations
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
-- Fires AFTER citations_immutable, because PostgreSQL runs BEFORE ROW triggers in name order
-- and 'citations_i...' sorts before 'citations_r...'. A committed report is therefore refused
-- with CP001 rather than having its citation quietly reset.
CREATE TRIGGER citations_reset_verification
  BEFORE UPDATE ON citations
  FOR EACH ROW WHEN (NEW.url IS DISTINCT FROM OLD.url OR NEW.quote IS DISTINCT FROM OLD.quote)
  EXECUTE FUNCTION coinpicks_citation_claim_changed();
--> statement-breakpoint
CREATE TRIGGER reports_no_truncate
  BEFORE TRUNCATE ON reports
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER report_scores_no_truncate
  BEFORE TRUNCATE ON report_scores
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER report_team_no_truncate
  BEFORE TRUNCATE ON report_team
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER citations_no_truncate
  BEFORE TRUNCATE ON citations
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
-- forward_returns is the OUTCOME half of the ledger. The reports half being immutable is only
-- half a ledger if the answers they are graded against can be wiped.
CREATE TRIGGER forward_returns_no_truncate
  BEFORE TRUNCATE ON forward_returns
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
-- ENABLE ALWAYS, every one. The default is ORIGIN, and `SET session_replication_role =
-- replica` silences an ORIGIN trigger: confirmed live that the replica-mode UPDATE returned
-- UPDATE 1 and the committed row changed, and that after ENABLE ALWAYS the same session was
-- refused with CP001 and the row was unchanged.
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_immutable;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_assert_commitable;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_seed_scores;
--> statement-breakpoint
ALTER TABLE report_scores ENABLE ALWAYS TRIGGER report_scores_immutable;
--> statement-breakpoint
ALTER TABLE report_team ENABLE ALWAYS TRIGGER report_team_immutable;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_immutable;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_reset_verification;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_no_truncate;
--> statement-breakpoint
ALTER TABLE report_scores ENABLE ALWAYS TRIGGER report_scores_no_truncate;
--> statement-breakpoint
ALTER TABLE report_team ENABLE ALWAYS TRIGGER report_team_no_truncate;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_no_truncate;
--> statement-breakpoint
ALTER TABLE forward_returns ENABLE ALWAYS TRIGGER forward_returns_no_truncate;
```

- [ ] **Step 5: Run the suite and watch every attack be refused**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test
```
Expected: `Test Files 7 passed (7)` — the four scoring files plus `client`, `schema` and `immutability`, for **62 tests passed** (31 + 3 + 12 + 16). If the trigger file fails to apply, globalSetup reports it as `could not rebuild coinpicks_test ... cause: <the psql error>`; the most likely cause is a stray `--> statement-breakpoint` inside a `$$` body, which produces `unterminated dollar-quoted string`.

- [ ] **Step 6: Read the trigger state out of the catalog by hand, once**

```bash
docker exec coinpicks-db psql -U coinpicks -d coinpicks_test \
  -c "select tgrelid::regclass as tbl, tgname, tgenabled from pg_trigger where not tgisinternal order by 1,2;"
```
Expected: twelve rows, `tgenabled` = `A` on every one. `A` is ENABLE ALWAYS; an `O` on any row means replica mode can silence it and the migration did not fully apply.

- [ ] **Step 7: Typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: the immutability triggers, with the six corrections the attacks forced

Six defects were reproduced live against 16.13 and are closed by construction
here, not documented as caveats: a text-vs-uuid DECLARE that killed every child
write, a re-parent that gutted a committed report with three ordinary UPDATEs,
a dead ON DELETE CASCADE that made discarding a draft impossible, INSERT and
TRUNCATE holes the literal reading of rule 2 left open, a report that could
commit having never been scored, and no ENABLE ALWAYS so replica mode silenced
the lot."
```

---

### Task 5: The GRANT migration and the privilege wall

Grants are lost when a table is recreated, so they belong in the migration chain rather than in a script someone remembers to re-run. This is the second half of decision A: the roles exist (Task 2), and here they are given exactly what they may do.

Two departures from the design's grant list, both closing confirmed findings:

- **`research` gets column-level UPDATE on `forward_returns`.** The unrestricted grant was tested live: `UPDATE forward_returns SET return_pct = 99.0` succeeded, and so did `UPDATE forward_returns SET horizon_days = 365`, silently moving a 30-day observation into the 365-day slot. `report_id` and `horizon_days` are the join key and are now immutable **by privilege**. `return_fraction` is generated, so it cannot be written at all — Postgres answers `column "return_fraction" can only be updated to DEFAULT`. The documented `INSERT ... ON CONFLICT (report_id, horizon_days) DO UPDATE` pattern still works; it was run end to end against this grant.
- **`research` gets `SELECT` on `forward_returns` too.** The spec's list said "SELECT on five tables, INSERT/UPDATE on forward_returns. Nothing else," which would leave the script unable to see which horizons it has already priced. It is a read of rows it wrote itself. Recorded in `agents/decisions.md` in Task 10 rather than done quietly.

`REVOKE TEMPORARY ON DATABASE` goes through `format()` and `current_database()` so this migration applies identically to `coinpicks` and to `coinpicks_test`.

This is also where the tests start using the request pool. Tasks 3 and 4 connect as `coinpicks_owner`, because until this migration lands `coinpicks_app` holds no table privileges at all; from here on the app role is the one under test, and the first case below asserts the composite claim the whole design rests on — **the immutability trigger fires against the request pool, and the request pool cannot turn it off.**

**Files:**
- Create: `apps/api/drizzle/0002_role_grants.sql` (via `drizzle-kit generate --custom`)
- Test: `apps/api/src/db/privileges.test.ts`

**Interfaces:**
- Consumes: the roles from `scripts/bootstrap-roles.sql`, the tables from `0000_init.sql`.
- Produces: `coinpicks_app` holds DML on the seven tables and nothing else; `research` holds SELECT on six and column-scoped INSERT/UPDATE on `forward_returns`.

- [ ] **Step 1: Write the failing privilege test**

Create `apps/api/src/db/privileges.test.ts`:

```ts
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  TEST_APP_URL,
  TEST_RESEARCH_URL,
  commitReportRow,
  createDraftReport,
  refusal,
  scoreAsDropped,
} from './testing.ts'

const app = openDb(TEST_APP_URL, 4)
const research = openDb(TEST_RESEARCH_URL, 2)
afterAll(async () => {
  await app.close()
  await research.close()
})

/** A committed report with one priced 30-day horizon, so research has something to read. */
async function pricedReport() {
  const { reportId } = await createDraftReport(app.db)
  await scoreAsDropped(app.db, reportId)
  await commitReportRow(app.db, reportId)
  await app.db.execute(sql`
    INSERT INTO forward_returns
      (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
    VALUES (${reportId}, 30, 2.0, 2.25, 'research/warehouse klines_1d', now())`)
  return reportId
}

describe('the request pool is bound by the guard it cannot reach', () => {
  it('is refused every write against a report it committed itself', async () => {
    const reportId = await pricedReport()
    const e = await refusal(
      app.db.execute(sql`UPDATE report_scores SET narrative_total = 31
                          WHERE report_id = ${reportId}`),
    )
    expect(e.code).toBe('CP001')
    expect(e.message).toMatch(/is committed; UPDATE on report_scores is refused/)
  })

  it('cannot drop a trigger, disable one, or drop a constraint', async () => {
    for (const statement of [
      sql`DROP TRIGGER citations_immutable ON citations`,
      sql`ALTER TABLE citations DISABLE TRIGGER citations_immutable`,
      sql`ALTER TABLE citations DROP CONSTRAINT ct_quote_not_blank`,
      sql`DROP FUNCTION coinpicks_report_child_immutable() CASCADE`,
      sql`DROP TABLE citations`,
    ]) {
      const e = await refusal(app.db.execute(statement))
      expect(e.code).toBe('42501')
      expect(e.message).toMatch(/must be owner of/)
    }
  })

  it('cannot create a table, so it cannot replace one either', async () => {
    const e = await refusal(app.db.execute(sql`CREATE TABLE cp_smuggled (x int)`))
    expect(e.code).toBe('42501')
    expect(e.message).toMatch(/permission denied for schema public/)
  })
})

describe('the research role reads the ledger and writes only its outcome', () => {
  it('reads the five report tables', async () => {
    const reportId = await pricedReport()
    const r = await research.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(1)
  })

  it('cannot write any report table', async () => {
    const reportId = await pricedReport()
    for (const statement of [
      sql`UPDATE report_scores SET product_total = 31 WHERE report_id = ${reportId}`,
      sql`UPDATE reports SET status = 'draft' WHERE id = ${reportId}`,
      sql`INSERT INTO citations (report_id, field, url, quote, origin)
          VALUES (${reportId}, 'f', 'https://example.test/q', 'q', 'human')`,
      sql`DELETE FROM coins`,
      sql`SELECT * FROM chain_facts`,
    ]) {
      const e = await refusal(research.db.execute(statement))
      expect(e.code).toBe('42501')
      expect(e.message).toMatch(/permission denied for table/)
    }
  })

  it('recomputes a horizon in place, the documented ON CONFLICT DO UPDATE way', async () => {
    const reportId = await pricedReport()
    await research.db.execute(sql`
      INSERT INTO forward_returns
        (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
      VALUES (${reportId}, 30, 2.0, 3.0, 'research/warehouse klines_1d', now())
      ON CONFLICT (report_id, horizon_days) DO UPDATE
        SET price_at_commit_usd  = excluded.price_at_commit_usd,
            price_at_horizon_usd = excluded.price_at_horizon_usd,
            price_source         = excluded.price_source,
            priced_at            = excluded.priced_at,
            computed_at          = now()`)
    const r = await research.db.execute<{ return_fraction: number }>(
      sql`SELECT return_fraction FROM forward_returns WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.return_fraction).toBeCloseTo(0.5, 12)
  })

  it('cannot move an observation into a different horizon or onto a different report', async () => {
    const reportId = await pricedReport()
    for (const statement of [
      sql`UPDATE forward_returns SET horizon_days = 365 WHERE report_id = ${reportId}`,
      sql`UPDATE forward_returns SET report_id = gen_random_uuid() WHERE report_id = ${reportId}`,
      sql`DELETE FROM forward_returns WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(research.db.execute(statement))
      expect(e.code).toBe('42501')
    }
  })

  it('cannot write the derived fraction at all', async () => {
    const reportId = await pricedReport()
    const e = await refusal(
      research.db.execute(
        sql`UPDATE forward_returns SET return_fraction = 99 WHERE report_id = ${reportId}`,
      ),
    )
    expect(e.message).toMatch(/can only be updated to DEFAULT/)
  })
})
```

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/db/privileges.test.ts
```
Expected: FAIL. The first failure is `permission denied for table coins` thrown out of `pricedReport()` — `coinpicks_app` holds nothing at all in `coinpicks_test` until this task's migration lands, and neither does `research`. The two `cannot drop a trigger` / `cannot create a table` cases pass already, because owning nothing is the one thing that is true from the start.

- [ ] **Step 3: Create and write the grant migration**

```bash
cd /home/dev/projects/trade-god/apps/api
pnpm exec drizzle-kit generate --custom --name role_grants
```
Expected: `[✓] Your SQL migration file ➜ drizzle/0002_role_grants.sql`, and a third entry in `drizzle/meta/_journal.json`.

Replace the whole contents of `apps/api/drizzle/0002_role_grants.sql` with:

```sql
-- The privilege wall. In the migration chain rather than in a script, because grants are
-- lost when a table is recreated and a migration is the only thing guaranteed to run
-- alongside the DDL that recreated it.
--
-- This runs as coinpicks_owner, which owns every table here.

GRANT USAGE ON SCHEMA public TO coinpicks_app, research;
--> statement-breakpoint
-- The request pool: DML on the seven tables and nothing else. No TRUNCATE (which is a
-- separate privilege, and the *_no_truncate triggers are the second line), no REFERENCES,
-- no ownership, no CREATE.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  coins, reports, report_scores, report_team, citations, chain_facts, forward_returns
  TO coinpicks_app;
--> statement-breakpoint
-- Python's boundary is a GRANT, not a convention. chain_facts is deliberately absent: the
-- spec's list excludes it, and adding SELECT later is one line.
GRANT SELECT ON TABLE coins, reports, report_scores, report_team, citations TO research;
--> statement-breakpoint
-- SELECT so forward_returns.py can see which horizons it has already priced -- a read of
-- rows it wrote itself.
GRANT SELECT, INSERT ON TABLE forward_returns TO research;
--> statement-breakpoint
-- COLUMN-LEVEL, and that is the point. With the unrestricted grant the design proposed,
-- `UPDATE forward_returns SET horizon_days = 365` succeeded as this role and silently moved
-- a 30-day observation into the 365-day slot. report_id and horizon_days are the join key
-- the whole ledger question rests on, and they are now immutable by privilege rather than by
-- trust. return_fraction is generated, so no grant could make it writable.
GRANT UPDATE (price_at_commit_usd, price_at_horizon_usd, price_source, priced_at, computed_at)
  ON TABLE forward_returns TO research;
--> statement-breakpoint
-- format() + current_database() so this migration is identical in coinpicks and in
-- coinpicks_test. A hard-coded database name would fail in one of them.
DO $$
BEGIN
  EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END $$;
--> statement-breakpoint
-- Redundant on PostgreSQL 15+ and stated anyway: PUBLIC must not be able to create objects
-- next to the ledger.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

- [ ] **Step 4: Run the whole suite**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test
```
Expected: `Test Files 8 passed (8)`, **70 tests passed** (62 + 8).

- [ ] **Step 5: Typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: the privilege wall, as a migration

Grants die with the table they were granted on, so they belong beside the DDL.
research gets column-level UPDATE on forward_returns: the unrestricted grant let
it rewrite horizon_days, silently moving a 30-day observation into the 365-day
slot, and the join key the ledger question rests on should not be editable by
the process that only computes the answer."
```

---

### Task 6: `server.ts` — migrate as owner, assert the guards, downgrade, serve

Decision A's third sentence: *server.ts opens the owner pool, migrates, closes it, then serves on the app pool.* The owner DSN exists for about fifty milliseconds per boot and never touches a request.

Between the migrator and the port there is a guard check, because two failure modes here are otherwise completely silent:

- A new migration containing `DROP TRIGGER citations_immutable ON citations`, or `CREATE OR REPLACE FUNCTION coinpicks_report_child_immutable() ... BEGIN RETURN NEW; END`, runs at boot with no review gate and no output anyone reads. `CREATE OR REPLACE` is what the trigger migration already uses, so a replacement would look idiomatic. For a single user writing their own migrations this is not an attack; it is an accident with no detection at all.
- Drizzle's migrator selects the **single most recent** applied row and applies a file only when its journal timestamp is newer. The `hash` column is inserted and never compared, and a file whose `when` is older than the newest applied row is skipped **silently and permanently**, exiting 0.

Ten lines each, and they turn both from silent into loud.

There is no Hono here on purpose. The HTTP framework arrives with the editor in build-order step 4; this plan's dependency surface is the database.

**Files:**
- Create: `apps/api/src/db/integrity.ts`
- Create: `apps/api/src/server.ts`
- Test: `apps/api/src/db/integrity.test.ts`

**Interfaces:**
- Consumes: `openDb`, `requireEnv`, `MIGRATIONS_FOLDER`, `Db` from `./client.ts`.
- Produces, from `apps/api/src/db/integrity.ts`:
  - `const REQUIRED_TRIGGERS: readonly string[]` (the twelve names)
  - `const GUARD_FUNCTIONS: readonly string[]` (the three that raise CP001)
  - `assertGuardsInstalled(db: Db): Promise<void>`
  - `assertJournalFullyApplied(db: Db): Promise<number>` — returns how many are applied
  - `assertNotSuperuser(db: Db): Promise<void>`

- [ ] **Step 1: Write the failing integrity test**

Create `apps/api/src/db/integrity.test.ts`:

```ts
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './integrity.ts'
import { TEST_APP_URL, TEST_OWNER_URL } from './testing.ts'

const app = openDb(TEST_APP_URL, 2)
const owner = openDb(TEST_OWNER_URL, 2)
afterAll(async () => {
  await app.close()
  await owner.close()
})

describe('the boot checks', () => {
  it('passes against a correctly migrated database', async () => {
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(3)
    await expect(assertNotSuperuser(app.db)).resolves.toBeUndefined()
  })

  it('refuses to serve when a trigger has been disabled', async () => {
    await owner.db.execute(sql`ALTER TABLE citations DISABLE TRIGGER citations_immutable`)
    try {
      await expect(assertGuardsInstalled(owner.db)).rejects.toThrow(
        /citations_immutable is 'D', not ENABLE ALWAYS/,
      )
    } finally {
      await owner.db.execute(sql`ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_immutable`)
    }
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
  })

  it('refuses to serve when a guard function has been gutted', async () => {
    await owner.db.execute(sql`
      CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
      LANGUAGE plpgsql AS $fn$ BEGIN RETURN NULL; END $fn$`)
    try {
      await expect(assertGuardsInstalled(owner.db)).rejects.toThrow(
        /coinpicks_refuse_truncate\(\) no longer raises CP001/,
      )
    } finally {
      await owner.db.execute(sql`
        CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
          RAISE EXCEPTION 'TRUNCATE on % is refused: this table is an append-only ledger',
            TG_TABLE_NAME USING ERRCODE = 'CP001';
        END $fn$`)
    }
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
  })

  it('refuses to serve when a committed migration was never applied', async () => {
    await owner.db.execute(sql`
      DELETE FROM drizzle.__drizzle_migrations
       WHERE created_at = (SELECT max(created_at) FROM drizzle.__drizzle_migrations)`)
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        /3 migrations are committed but 2 are applied/,
      )
    } finally {
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES ('restored-by-integrity-test', (SELECT max(created_at) + 1
                                                 FROM drizzle.__drizzle_migrations))`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(3)
  })
})
```

Note this file is the one place in the suite that mutates shared state, and it repairs what it breaks in a `finally` and then re-asserts the repair. Keep it that way.

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/db/integrity.test.ts
```
Expected: FAIL — `Failed to resolve import "./integrity.ts"`.

- [ ] **Step 3: Write `apps/api/src/db/integrity.ts`**

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { sql } from 'drizzle-orm'
import { type Db, MIGRATIONS_FOLDER } from './client.ts'

/**
 * Every trigger the ledger's immutability depends on. `tgenabled` must be 'A' — ENABLE
 * ALWAYS. An 'O' (the default, ORIGIN) is silenced by `SET session_replication_role =
 * replica`, which was confirmed live to flip a committed report back to draft and delete it.
 */
export const REQUIRED_TRIGGERS = [
  'citations_immutable',
  'citations_no_truncate',
  'citations_reset_verification',
  'forward_returns_no_truncate',
  'report_scores_immutable',
  'report_scores_no_truncate',
  'report_team_immutable',
  'report_team_no_truncate',
  'reports_assert_commitable',
  'reports_immutable',
  'reports_no_truncate',
  'reports_seed_scores',
] as const

/**
 * The three functions that raise CP001. Checked for the string rather than for a hash of the
 * body: a hash would have to be re-pinned every time a comment is reflowed, and a literal
 * that cries wolf gets deleted. A body that no longer contains 'CP001' is a gutted guard,
 * which is the failure worth being loud about.
 */
export const GUARD_FUNCTIONS = [
  'coinpicks_report_child_immutable',
  'coinpicks_refuse_truncate',
  'coinpicks_reports_immutable',
] as const

/** Runs between the migrator and the port. Ten lines, one millisecond, and it turns a
 *  dropped trigger from silent into a refusal to start. */
export async function assertGuardsInstalled(db: Db): Promise<void> {
  const problems: string[] = []

  const triggers = await db.execute<{ tgname: string; tgenabled: string }>(sql`
    SELECT t.tgname, t.tgenabled
      FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE NOT t.tgisinternal AND n.nspname = 'public'`)
  const state = new Map(triggers.rows.map((row) => [row.tgname, row.tgenabled]))
  for (const name of REQUIRED_TRIGGERS) {
    const enabled = state.get(name)
    if (enabled === undefined) problems.push(`trigger ${name} is missing`)
    else if (enabled !== 'A') problems.push(`trigger ${name} is '${enabled}', not ENABLE ALWAYS`)
  }

  // LIKE 'coinpicks%' without an underscore wildcard: escaping a backslash through a drizzle
  // sql template is exactly the trap that turned '\s+' into 's+' in an earlier draft.
  const functions = await db.execute<{ proname: string; prosrc: string }>(sql`
    SELECT p.proname, p.prosrc
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname LIKE 'coinpicks%'`)
  const bodies = new Map(functions.rows.map((row) => [row.proname, row.prosrc]))
  for (const name of GUARD_FUNCTIONS) {
    const body = bodies.get(name)
    if (body === undefined) problems.push(`function ${name}() is missing`)
    else if (!body.includes('CP001')) problems.push(`function ${name}() no longer raises CP001`)
  }

  if (problems.length > 0) {
    throw new Error(
      `the immutability guards are not intact, refusing to serve:\n  ${problems.join('\n  ')}`,
    )
  }
}

/**
 * Drizzle's migrator selects the single most recent applied row and applies a file only when
 * its journal timestamp is newer. The `hash` column is inserted and never compared, so an
 * already-applied file can be edited silently; worse, a file whose `when` is OLDER than the
 * newest applied row is skipped permanently and the migrator exits 0. For a project whose
 * product is an immutable ledger, a migration that silently did not run is worth shouting
 * about.
 */
export async function assertJournalFullyApplied(db: Db): Promise<number> {
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
}

/** Decision A, asserted at every boot: the request pool is not the migrator's role and is
 *  not a superuser, so nothing it can send can silence a trigger. */
export async function assertNotSuperuser(db: Db): Promise<void> {
  const who = await db.execute<{ rolname: string; rolsuper: boolean }>(
    sql`SELECT rolname, rolsuper FROM pg_roles WHERE rolname = current_user`,
  )
  const row = who.rows[0]
  if (row === undefined) throw new Error('current_user has no pg_roles row')
  if (row.rolsuper) {
    throw new Error(
      `the request pool is connected as ${row.rolname}, a SUPERUSER. A superuser can SET ` +
        'session_replication_role = replica and silence every immutability trigger. Point ' +
        'DATABASE_URL at coinpicks_app. Refusing to serve.',
    )
  }
}
```

- [ ] **Step 4: Run the integrity test**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/db/integrity.test.ts
```
Expected: `Test Files 1 passed (1) / Tests 4 passed (4)`.

- [ ] **Step 5: Write `apps/api/src/server.ts`**

```ts
import { createServer } from 'node:http'
import { sql } from 'drizzle-orm'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { MIGRATIONS_FOLDER, openDb, requireEnv } from './db/client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './db/integrity.ts'

const PORT = Number(process.env.PORT ?? 8787)

/*
 * Boot, in the order decision A requires and no other.
 *
 * The owner pool exists for the length of the migration and is closed before the app pool is
 * opened. It is not kept around "just in case": a session that owns the tables can DROP
 * TRIGGER in one statement, and if it is not open, nothing a request can reach is able to.
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

/*
 * node:http, not Hono. The HTTP framework and the RPC surface arrive with the editor in
 * build-order step 4; this plan's dependency surface is the database, and /health is the
 * only route that exists before there is anything to edit.
 */
const server = createServer((request, response) => {
  if (request.url !== '/health') {
    response.writeHead(404, { 'content-type': 'application/json' }).end('{"error":"not found"}')
    return
  }
  // SELECT 1 on the APP pool, and the migration count from the boot check. The app role has
  // no USAGE on the `drizzle` schema and must not be given any: /health is not worth widening
  // the request pool's reach by one schema.
  app.db
    .execute(sql`SELECT 1`)
    .then(() => {
      response
        .writeHead(200, { 'content-type': 'application/json' })
        .end(JSON.stringify({ ok: true, migrations: appliedMigrations }))
    })
    .catch((error: unknown) => {
      response
        .writeHead(503, { 'content-type': 'application/json' })
        .end(JSON.stringify({ ok: false, error: String(error) }))
    })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`coinpicks api on http://127.0.0.1:${PORT}, pool user coinpicks_app`)
})
```

- [ ] **Step 6: Boot it for real**

```bash
cd /home/dev/projects/trade-god
cp -n .env.example .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks|" .env
grep -q '^DATABASE_URL_OWNER=' .env || echo 'DATABASE_URL_OWNER=postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks' >> .env
pnpm --filter @coinpicks/api run start &
sleep 2
curl -s http://127.0.0.1:8787/health; echo
kill %1
```
Expected: `coinpicks api on http://127.0.0.1:8787, pool user coinpicks_app` on stdout, then `{"ok":true,"migrations":3}`. Task 10 rewrites `.env.example` properly; this step only proves the boot order.

Then prove the downgrade actually happened:

```bash
docker exec coinpicks-db psql -U coinpicks -d coinpicks \
  -c "select usename, count(*) from pg_stat_activity where datname='coinpicks' group by 1;"
```
Run it while the server is up. Expected: `coinpicks_app` only. If `coinpicks_owner` appears, the owner pool was not closed.

- [ ] **Step 7: Typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm typecheck && pnpm test
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: boot as the owner, verify the guards, then downgrade and serve

The owner DSN lives for one migration and is closed before the port opens, so
nothing a request can reach is able to DROP TRIGGER. Between the two there is a
check, because the two ways this silently goes wrong -- a migration that gutted
a guard, and a migration that drizzle skipped because its journal timestamp was
older than the newest applied row -- both exit 0 today."
```

---

### Task 7: The compare-and-swap helper

Schema rule 4, in one place. Every draft mutation is `UPDATE ... WHERE id = $1 AND version = $2`, 409 on zero rows — two browser tabs on one draft would otherwise be silent last-write-wins.

`casBumpVersion` must be the **first statement** of any transaction that mutates a draft, for two reasons and both matter. It is the staleness check: zero rows updated means someone moved the report on since the editor loaded it, and SQL does not treat that as an error, so this function does. And it is the lock: the UPDATE takes a `FOR NO KEY UPDATE` row lock on `reports`, so taking it first means every writer locks the same row in the same order and two editors cannot deadlock against each other.

`sqlstateOf` is here because the naive `error.code === 'CP001'` check is **dead code**. Drizzle 0.45.3 wraps every driver error in `DrizzleQueryError` at seven call sites in `pg-core/session.js`; confirmed live that `e.code` is `undefined`, `e.cause.code` is `CP001`, and `e.message` is `Failed query: insert into citations ...`. Every CP001 handler written against the naive shape would never fire, and a lost race would surface as a 500 carrying the raw INSERT statement.

**Files:**
- Create: `apps/api/src/reports/errors.ts`
- Create: `apps/api/src/reports/cas.ts`
- Test: `apps/api/src/reports/cas.test.ts`

**Interfaces:**
- Consumes: `Tx` from `../db/client.ts`, `reports` from `../db/schema.ts`.
- Produces, from `apps/api/src/reports/errors.ts`: `SQLSTATE_REPORT_COMMITTED` (`'CP001'`), `SQLSTATE_REPORT_UNSCORED` (`'CP002'`), `SQLSTATE_REPORT_MISSING` (`'CP404'`), `sqlstateOf(error: unknown): string | undefined`, and the classes `ReportNotFoundError` (404), `StaleVersionError` (409), `AlreadyCommittedError` (409).
- Produces, from `apps/api/src/reports/cas.ts`: `casBumpVersion(tx: Tx, reportId: string, expectedVersion: number): Promise<number>`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/src/reports/cas.test.ts`:

```ts
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from '../db/client.ts'
import { TEST_APP_URL, commitReportRow, createDraftReport, scoreAsDropped } from '../db/testing.ts'
import { casBumpVersion } from './cas.ts'
import {
  AlreadyCommittedError,
  ReportNotFoundError,
  StaleVersionError,
  sqlstateOf,
} from './errors.ts'

const h = openDb(TEST_APP_URL, 4)
afterAll(() => h.close())

describe('casBumpVersion', () => {
  it('bumps the version and returns the new one', async () => {
    const { reportId } = await createDraftReport(h.db)
    const v = await h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))
    expect(v).toBe(2)
  })

  it('refuses a token that has already been spent', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))
    await expect(h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))).rejects.toBeInstanceOf(
      StaleVersionError,
    )
  })

  it('says "already committed" rather than "stale", because the editor must do something different', async () => {
    const { reportId } = await createDraftReport(h.db)
    await scoreAsDropped(h.db, reportId)
    await commitReportRow(h.db, reportId)
    await expect(h.db.transaction((tx) => casBumpVersion(tx, reportId, 2))).rejects.toBeInstanceOf(
      AlreadyCommittedError,
    )
  })

  it('says "not found" for an id that never existed', async () => {
    await expect(
      h.db.transaction((tx) =>
        casBumpVersion(tx, '00000000-0000-0000-0000-000000000000', 1),
      ),
    ).rejects.toBeInstanceOf(ReportNotFoundError)
  })

  /**
   * Two tabs, one draft, the same token. The second must block on the first's row lock and
   * then match zero rows — not overwrite it. Verified live: T2's UPDATE stays pending while
   * T1 is open, returns rowCount 0 once T1 commits, and the final version is 2, so exactly
   * one write landed.
   */
  it('lets exactly one of two concurrent writers through', async () => {
    const { reportId } = await createDraftReport(h.db)
    const a = await h.pool.connect()
    const b = await h.pool.connect()
    try {
      const CAS = `update reports set version = version + 1
                     where id = $1 and version = $2 and status = 'draft'
                   returning version`
      await a.query('begin')
      await b.query('begin')

      const first = await a.query(CAS, [reportId, 1])
      expect(first.rowCount).toBe(1)

      const second = b.query(CAS, [reportId, 1])
      let settled = false
      void second.then(() => {
        settled = true
      })
      await new Promise((r) => setTimeout(r, 250))
      expect(settled).toBe(false) // still blocked on A's row lock

      await a.query('commit')
      expect((await second).rowCount).toBe(0) // the editor gets a 409
      await b.query('commit')
    } finally {
      a.release()
      b.release()
    }

    const final = await h.db.execute<{ version: number }>(
      sql`SELECT version FROM reports WHERE id = ${reportId}`,
    )
    expect(final.rows[0]?.version).toBe(2)
  })
})

describe('sqlstateOf', () => {
  it('finds the SQLSTATE that drizzle buried under DrizzleQueryError', async () => {
    const { reportId } = await createDraftReport(h.db)
    await scoreAsDropped(h.db, reportId)
    await commitReportRow(h.db, reportId)
    try {
      await h.db.execute(sql`
        INSERT INTO citations (report_id, field, url, quote, origin)
        VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'q', 'human')`)
      expect.unreachable('the trigger should have refused this')
    } catch (error) {
      expect((error as { code?: unknown }).code).toBeUndefined() // the wrapper carries none
      expect(sqlstateOf(error)).toBe('CP001')
    }
  })

  it('returns undefined for an error that is not a database error', () => {
    expect(sqlstateOf(new Error('nope'))).toBeUndefined()
    expect(sqlstateOf(undefined)).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/reports/cas.test.ts
```
Expected: FAIL — `Failed to resolve import "./cas.ts"`.

- [ ] **Step 3: Write `apps/api/src/reports/errors.ts`**

```ts
/**
 * Commit-path errors. Each maps to exactly one HTTP status, so the route's catch is a closed
 * set. No parameter properties anywhere in here: Node 26 strips types and would refuse the
 * file (see Global Constraints).
 */

/** Raised by the immutability triggers: this row belongs to a committed report. */
export const SQLSTATE_REPORT_COMMITTED = 'CP001'

/** Raised by coinpicks_assert_commitable(): the report has not been scored. */
export const SQLSTATE_REPORT_UNSCORED = 'CP002'

/** Raised by the child trigger when the parent report row is missing. */
export const SQLSTATE_REPORT_MISSING = 'CP404'

/**
 * The SQLSTATE of a database error, wherever drizzle has buried it.
 *
 * `(error as {code?: string}).code === 'CP001'` looks right and is dead code: drizzle 0.45.3
 * wraps every driver error in DrizzleQueryError, which sets no `code` of its own and puts
 * the pg error on `.cause`. Confirmed live — the wrapper's `code` is undefined, its message
 * is `Failed query: insert into citations (...) values (...)`, and `cause.code` is 'CP001'.
 * Every handler written against the naive shape would never fire and a lost race would reach
 * the operator as a 500 carrying the raw statement.
 */
export function sqlstateOf(error: unknown): string | undefined {
  let cursor: unknown = error
  for (let depth = 0; cursor != null && depth < 10; depth += 1) {
    const node = cursor as { code?: unknown; cause?: unknown }
    if (typeof node.code === 'string' && /^[0-9A-Z]{5}$/.test(node.code)) return node.code
    cursor = node.cause
  }
  return undefined
}

export function isReportCommittedError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_COMMITTED
}

export function isReportUnscoredError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_UNSCORED
}

export function isReportMissingError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_MISSING
}

export class ReportNotFoundError extends Error {
  readonly httpStatus = 404
  readonly reportId: string

  constructor(reportId: string) {
    super(`report ${reportId} does not exist`)
    this.name = 'ReportNotFoundError'
    this.reportId = reportId
  }
}

/**
 * The client's compare-and-swap token did not match. The editor must reload and re-apply; it
 * must never retry with the same token.
 */
export class StaleVersionError extends Error {
  readonly httpStatus = 409
  readonly reportId: string
  readonly expectedVersion: number
  readonly actualVersion: number

  constructor(reportId: string, expectedVersion: number, actualVersion: number) {
    super(
      `report ${reportId} moved on: client holds version ${expectedVersion}, ` +
        `database has ${actualVersion}`,
    )
    this.name = 'StaleVersionError'
    this.reportId = reportId
    this.expectedVersion = expectedVersion
    this.actualVersion = actualVersion
  }
}

/** Distinct from stale on purpose: the editor's answer is "start a new report", not
 *  "reload". Re-researching a coin creates a new reports row. */
export class AlreadyCommittedError extends Error {
  readonly httpStatus = 409
  readonly reportId: string

  constructor(reportId: string) {
    super(`report ${reportId} is already committed and is immutable`)
    this.name = 'AlreadyCommittedError'
    this.reportId = reportId
  }
}
```

- [ ] **Step 4: Write `apps/api/src/reports/cas.ts`**

```ts
import { and, eq, sql } from 'drizzle-orm'
import type { Tx } from '../db/client.ts'
import { reports } from '../db/schema.ts'
import { AlreadyCommittedError, ReportNotFoundError, StaleVersionError } from './errors.ts'

/**
 * Rule 4, in one place: UPDATE ... WHERE id = $1 AND version = $2, 409 on zero rows.
 *
 * This MUST be the first statement of any transaction that mutates a draft — the report, its
 * scores, its team rows or its citations. Two reasons, and both matter:
 *
 *  - it is the staleness check. Zero rows updated means someone else moved the report on
 *    since the editor loaded it. SQL does not treat that as an error, so this function does.
 *  - it is the lock. The UPDATE takes a FOR NO KEY UPDATE row lock on `reports`, which
 *    serialises it against every other writer's CAS. Taking it first means every writer locks
 *    the same row in the same order, so two editors cannot deadlock against each other.
 *
 * It bumps `version` on every successful call, so a client's token is good for exactly one
 * write.
 */
export async function casBumpVersion(
  tx: Tx,
  reportId: string,
  expectedVersion: number,
): Promise<number> {
  const bumped = await tx
    .update(reports)
    .set({ version: sql`${reports.version} + 1` })
    .where(
      and(
        eq(reports.id, reportId),
        eq(reports.version, expectedVersion),
        eq(reports.status, 'draft'),
      ),
    )
    .returning({ version: reports.version })

  const row = bumped[0]
  if (row !== undefined) return row.version

  // Zero rows. Read the row back to say WHY, because the editor's next move differs for each:
  // reload (stale), start a new report (committed), or report a bug (missing).
  const current = await tx
    .select({ version: reports.version, status: reports.status })
    .from(reports)
    .where(eq(reports.id, reportId))
    .limit(1)

  const actual = current[0]
  if (actual === undefined) throw new ReportNotFoundError(reportId)
  if (actual.status === 'committed') throw new AlreadyCommittedError(reportId)
  throw new StaleVersionError(reportId, expectedVersion, actual.version)
}
```

- [ ] **Step 5: Run the whole suite, typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: the compare-and-swap helper, and an SQLSTATE lookup that works

Two tabs on one draft were silent last-write-wins; one CAS in one place makes
the loser a 409. sqlstateOf walks the cause chain because drizzle wraps every
driver error in DrizzleQueryError, whose own code is undefined -- so the obvious
error.code === 'CP001' check never fires and a lost race reaches the operator as
a 500 quoting the raw INSERT."
```

---

### Task 8: The accrual noise floor

Decision B, taken by the owner on 2026-09-21. **The frozen formula `market_cap ÷ net_annual_flow` is untouched.** The three-way verdict taxonomy around it — `MULTIPLE | ISSUANCE_NEGATIVE | PURE_PREMIUM` — is this implementation's own and was already amended once today (the `PURE_PREMIUM` narrowing), so the floor goes there.

The problem, swept rather than hypothesised: `net = gross - issuance` in float64 branches on `net > 0` with no materiality floor. Across 960 combinations of round operator inputs where issuance equals gross to the cent — the exact case the framework's flagship example is about — **120 (12.5%) leave a non-zero float residue instead of 0**. Concretely: segment revenue $100,000,000, capture 0.07, accrual 0.01, issuance $70,000 gives `gross = 70000.00000000001`, `net = 1.4551915228366852e-11`, `kind = 'MULTIPLE'`, `multiple = 3.4359738368e+21`. A token forcing exactly as much to holders as it prints, committed immutably as having positive holder flow at a payback multiple of 3.4 sextillion.

The floor is keyed on **gross alone**, not on gross and issuance: `AccrualResult` does not carry issuance, and it does not need to. When `|net|` is genuinely near zero, `gross ≈ issuance`, so `gross` is the right scale; when issuance dwarfs gross, `net ≈ -issuance` is nowhere near zero and the test does not fire. Keeping `annualHolderFlow`'s stored `net` exactly `gross - issuance` is what lets `rs_net_flow_is_gross_minus_issuance` stay an identity.

`rs_premium_kind_matches_flows` in Task 3 already reproduces this branch in SQL, so the database refuses the naive verdict even if someone later reverts this function.

**Files:**
- Modify: `apps/api/src/scoring/accrual.ts`
- Test: `apps/api/src/scoring/accrual.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `discoveryPremium` keeps its exact signature, `(marketCapUsd: number, flow: AccrualResult) => PremiumResult`. New export: `const NET_FLOW_NOISE_FLOOR_RATIO = 1e-9`.

- [ ] **Step 1: Add the failing test**

Append to `apps/api/src/scoring/accrual.test.ts`, inside the existing `describe('discoveryPremium', ...)` block:

```ts
  // Swept, not hypothesised: 120 of 960 combinations of round operator inputs where issuance
  // equals gross to the cent leave a non-zero float residue instead of 0. Without a floor
  // this exact row commits as MULTIPLE with a payback multiple of 3.4e21.
  it('does not call float64 debris a positive holder flow', () => {
    const breakEven = annualHolderFlow({
      segmentRevenueUsd: 100_000_000,
      captureShare: 0.07,
      accrualPct: 0.01,
      annualIssuanceUsd: 70_000,
    })
    expect(breakEven.grossAnnualFlowUsd).toBe(70_000.00000000001)
    expect(breakEven.netAnnualFlowUsd).toBe(1.4551915228366852e-11)

    const verdict = discoveryPremium(50_000_000_000, breakEven)
    expect(verdict.kind).toBe('ISSUANCE_NEGATIVE')
    expect(verdict).toMatchObject({
      grossAnnualFlowUsd: 70_000.00000000001,
      netAnnualFlowUsd: 1.4551915228366852e-11,
    })
  })

  it('still reports a real flow a billion times smaller than gross', () => {
    // The floor is a ratio, not an absolute: a genuine $1m net against $1m gross is nowhere
    // near it, and neither is a thin but real margin.
    expect(discoveryPremium(50_000_000, flow(14_000_000, 10_000_000)).kind).toBe('MULTIPLE')
    expect(discoveryPremium(1_000_000, flow(1_000_000, 1)).kind).toBe('MULTIPLE')
  })
```

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/scoring/accrual.test.ts
```
Expected: FAIL — `expected 'MULTIPLE' to be 'ISSUANCE_NEGATIVE'` on the first new case. The second new case passes already; it is there to pin that the fix does not overreach.

- [ ] **Step 3: Add the floor**

In `apps/api/src/scoring/accrual.ts`, add the constant above `discoveryPremium`:

```ts
/**
 * Below this fraction of gross flow, a positive `net` is float64 debris from
 * `gross - issuance` rather than money reaching holders.
 *
 * Swept: across 960 combinations of round operator inputs where issuance equals gross to the
 * cent — the framework's flagship "earns as much as it prints" case — 120 leave a non-zero
 * residue. $100m revenue x 0.07 capture x 0.01 accrual less $70,000 issuance gives
 * gross = 70000.00000000001 and net = 1.455e-11, which the unguarded branch published as
 * kind='MULTIPLE' at a payback multiple of 3.4e21, immutably.
 *
 * Keyed on gross alone, and that is deliberate: AccrualResult does not carry issuance, and
 * when |net| is genuinely near zero then gross is approximately issuance anyway, so gross is
 * the right scale. When issuance dwarfs gross, net is approximately -issuance — nowhere near
 * zero — and this never fires.
 *
 * The FROZEN formula (market_cap / net_annual_flow) is untouched. This is the verdict
 * taxonomy around it, which is this implementation's own and which the 2026-09-21
 * PURE_PREMIUM ruling already amended once. Ruled again 2026-09-21. The database reproduces
 * the same branch in report_scores' rs_premium_kind_matches_flows.
 */
export const NET_FLOW_NOISE_FLOOR_RATIO = 1e-9
```

and change the `MULTIPLE` branch of `discoveryPremium` from

```ts
  if (flow.netAnnualFlowUsd > 0) {
```

to

```ts
  const isNoise =
    Math.abs(flow.netAnnualFlowUsd) < flow.grossAnnualFlowUsd * NET_FLOW_NOISE_FLOOR_RATIO

  if (flow.netAnnualFlowUsd > 0 && !isNoise) {
```

Nothing else in the function changes: the `ISSUANCE_NEGATIVE` and `PURE_PREMIUM` arms, the `assertNonNegative` on the market cap and the `Number.isFinite` loop all stay exactly as they are.

- [ ] **Step 4: Run, typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "fix: a break-even token is not a 3.4-sextillion-multiple MULTIPLE

net = gross - issuance in float64 leaves a residue in 120 of 960 round-input
combinations where the two are equal to the cent, and the unguarded branch
published that residue as positive holder flow. The frozen formula is untouched;
the floor goes in the verdict taxonomy, which is ours, and report_scores
reproduces the same branch so the database refuses it too."
```

---

### Task 9: `SCORING_VERSION`, and the test that stops the DDL and the formulas drifting apart

Schema rule 3 names a constant in `scoring/ranges.ts` that does not exist: `grep -rn SCORING_VERSION apps/` returns nothing. The commit route writes it into every scored row, and the ledger's fatal failure mode is silently comparing rows scored under two framework versions and calling the difference signal.

The constant alone is an honour system, and the CHECK constraints in Task 3 now reproduce the same frozen numbers in a second place. Two guards, fifteen lines:

- **The fingerprint.** Every frozen number in one object, asserted against a literal. Change the 16, a narrative maximum, the founder weight or a range and the suite fails with a message saying to bump `SCORING_VERSION` in the same commit or revert. A refactor that moves code without touching a number leaves it alone — which is why this is a table of values rather than a hash of the directory.
- **The DDL pin.** The test reads the generated `0000_init.sql` and asserts the CHECK constraints contain exactly the numbers the TypeScript exports. A bump then has to be made in both places or the suite says which one was missed.

**Files:**
- Modify: `apps/api/src/scoring/ranges.ts`
- Test: `apps/api/src/scoring/frozen-surface.test.ts`

**Interfaces:**
- Consumes: `NARRATIVE_MAX`, `NARRATIVE_TOTAL_MAX` from `./narrative.ts`, `PRODUCT_GATE_THRESHOLD` from `./product.ts`.
- Produces: `SCORING_VERSION = 'coinpicks-2026-09-21'` from `apps/api/src/scoring/ranges.ts`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/src/scoring/frozen-surface.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './product.ts'
import { SCORING_VERSION } from './ranges.ts'

/**
 * Rule 3's mechanism, not just its intention.
 *
 * The ledger groups by scoring_version, so two framework revisions silently sharing one
 * label corrupts a comparison rather than a row — which is worse, because it survives every
 * integrity check in the schema and cannot be repaired afterwards: committed rows are
 * immutable by construction.
 *
 * This is a table of frozen VALUES rather than a hash of scoring/, on purpose. A hash would
 * fail on a comment reflow and split the ledger for nothing.
 */
const FROZEN_SURFACE = {
  productGateThreshold: 16,
  productSubScoreMax: 10,
  narrativeMaturityMax: 7,
  narrativeSmartMoneyMax: 6,
  narrativeHairFireMax: 6,
  narrativeCommunicationMax: 5,
  narrativeLineageMax: 4,
  narrativeMutationMax: 3,
  narrativeTotalMax: 31,
  teamHMax: 5,
  teamMMax: 3,
  teamLMax: 2,
  teamFounderWeight: 5,
  teamMinPeople: 3,
  teamMaxPeople: 5,
  forwardReturnHorizons: [30, 90, 180, 365],
} as const

describe('the frozen surface', () => {
  it('has not moved since SCORING_VERSION was last set', () => {
    // If this fails, a frozen number changed. Bump SCORING_VERSION in the SAME commit, or
    // revert the number. Do not update this literal on its own.
    expect({
      productGateThreshold: PRODUCT_GATE_THRESHOLD,
      narrativeMaturityMax: NARRATIVE_MAX.maturity,
      narrativeSmartMoneyMax: NARRATIVE_MAX.smartMoney,
      narrativeHairFireMax: NARRATIVE_MAX.hairFire,
      narrativeCommunicationMax: NARRATIVE_MAX.communication,
      narrativeLineageMax: NARRATIVE_MAX.lineage,
      narrativeMutationMax: NARRATIVE_MAX.mutation,
      narrativeTotalMax: NARRATIVE_TOTAL_MAX,
    }).toEqual({
      productGateThreshold: FROZEN_SURFACE.productGateThreshold,
      narrativeMaturityMax: FROZEN_SURFACE.narrativeMaturityMax,
      narrativeSmartMoneyMax: FROZEN_SURFACE.narrativeSmartMoneyMax,
      narrativeHairFireMax: FROZEN_SURFACE.narrativeHairFireMax,
      narrativeCommunicationMax: FROZEN_SURFACE.narrativeCommunicationMax,
      narrativeLineageMax: FROZEN_SURFACE.narrativeLineageMax,
      narrativeMutationMax: FROZEN_SURFACE.narrativeMutationMax,
      narrativeTotalMax: FROZEN_SURFACE.narrativeTotalMax,
    })
  })

  it('names a version the ledger can group by', () => {
    expect(SCORING_VERSION).toBe('coinpicks-2026-09-21')
  })
})

describe('the DDL reproduces the same numbers', () => {
  const ddl = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle/0000_init.sql'),
    'utf8',
  )

  const NARRATIVE_COLUMNS: Record<keyof typeof NARRATIVE_MAX, string> = {
    maturity: 'narrative_maturity',
    smartMoney: 'narrative_smart_money',
    hairFire: 'narrative_hair_fire',
    communication: 'narrative_communication',
    lineage: 'narrative_lineage',
    mutation: 'narrative_mutation',
  }

  it('bounds every narrative sub-score at its frozen maximum', () => {
    for (const key of Object.keys(NARRATIVE_MAX) as (keyof typeof NARRATIVE_MAX)[]) {
      const expected = `"report_scores"."${NARRATIVE_COLUMNS[key]}" BETWEEN 0 AND ${NARRATIVE_MAX[key]}`
      expect(ddl, `missing CHECK: ${expected}`).toContain(expected)
    }
  })

  it('bounds every product sub-score at 0..10 and gates at the frozen threshold', () => {
    for (const column of ['product_ease', 'product_hair_fire', 'product_exclusivity']) {
      expect(ddl).toContain(
        `"report_scores"."${column}" BETWEEN 0 AND ${FROZEN_SURFACE.productSubScoreMax}`,
      )
    }
    expect(ddl).toContain(
      `"report_scores"."product_passed" = ("report_scores"."product_total" >= ${PRODUCT_GATE_THRESHOLD})`,
    )
  })

  it('bounds the three team rungs at H 0..5, M 0..3, L 0..2', () => {
    expect(ddl).toContain(`"report_team"."h" BETWEEN 0 AND ${FROZEN_SURFACE.teamHMax}`)
    expect(ddl).toContain(`"report_team"."m" BETWEEN 0 AND ${FROZEN_SURFACE.teamMMax}`)
    expect(ddl).toContain(`"report_team"."l" BETWEEN 0 AND ${FROZEN_SURFACE.teamLMax}`)
  })

  it('freezes the four forward-return horizons', () => {
    expect(ddl).toContain(
      `"forward_returns"."horizon_days" IN (${FROZEN_SURFACE.forwardReturnHorizons.join(', ')})`,
    )
  })
})
```

- [ ] **Step 2: Run it and see it fail**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test src/scoring/frozen-surface.test.ts
```
Expected: FAIL — `SyntaxError: The requested module './ranges.ts' does not provide an export named 'SCORING_VERSION'`.

- [ ] **Step 3: Add the constant**

Append to `apps/api/src/scoring/ranges.ts`:

```ts
/**
 * The framework revision every committed report is scored under. Schema rule 3: the commit
 * route writes this into report_scores.scoring_version, and every ledger query groups by it.
 *
 * FORMAT: a date, not a semver and not a content hash of this directory. A hash would bump on
 * a refactor that moved code without changing a number, splitting the ledger into two
 * incomparable populations for nothing.
 *
 * BUMP POLICY: change this ONLY when a frozen formula, range, weight or threshold changes —
 * never for a refactor, a comment or a test. frozen-surface.test.ts fails when one of those
 * numbers moves, and the fix is to bump this constant deliberately in the same commit.
 */
export const SCORING_VERSION = 'coinpicks-2026-09-21'
```

- [ ] **Step 4: Run, typecheck, lint, commit**

```bash
cd /home/dev/projects/trade-god/apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "feat: SCORING_VERSION, and a test that stops it drifting

Rule 3 names a constant that did not exist, and the CHECK constraints now
reproduce the frozen numbers in a second place. A forgotten bump is the exact
failure rule 3 exists to prevent -- two framework revisions sharing one label,
which corrupts a comparison rather than a row and survives every integrity check
in the schema. A value table, not a directory hash: a refactor must not split
the ledger."
```

---

### Task 10: Documentation, `.env.example`, CI, and the decisions log

Two of the five non-negotiable schema rules are amended by this plan and the amendments must land in writing, or the next reader will "restore" the literal wording and re-open a verified hole.

**Files:**
- Modify: `CLAUDE.md` (the Postgres section, rules 2 and 3)
- Modify: `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` (§4.3 rule 2, §8.1)
- Modify: `.env.example`
- Modify: `.github/workflows/ci.yml`
- Modify: `agents/decisions.md`, `agents/roadmap.md`
- Do **not** modify: the spec's `## Normative formulas (frozen)` section. It is byte-frozen.

**Interfaces:**
- Consumes: everything built in Tasks 1–9.
- Produces: no code.

- [ ] **Step 1: Amend rule 2 in `CLAUDE.md`**

Replace the "**2. A `BEFORE UPDATE OR DELETE` trigger** …" bullet under "Five schema rules that are not negotiable" with:

```markdown
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
```

- [ ] **Step 2: Amend rule 3 and the Postgres preamble in `CLAUDE.md`**

Replace the `DATABASE_URL` line and rule 3 with:

```markdown
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

3. **`report_scores.scoring_version`**, written by the commit route from `SCORING_VERSION` in
   `scoring/ranges.ts` (`'coinpicks-2026-09-21'`; bump only when a frozen formula, range,
   weight or threshold changes). Nullable at column level and NOT NULL **by trigger** at the
   moment of commit — a draft has not been scored under any framework version, and
   `coinpicks_assert_commitable()` refuses a commit without one.
   `apps/api/src/scoring/frozen-surface.test.ts` fails if a frozen number moves without a
   deliberate bump, and pins the CHECK constraints against the same numbers.
```

- [ ] **Step 3: Add the runtime rule to `CLAUDE.md`'s Stack section**

Append to the "Stack" section, after the catalog-pin paragraph:

```markdown
**Node 26 strips types; it does not transform them.** `--experimental-transform-types` no
longer exists on v26.8.1 — `node --help` lists only `--experimental-strip-types`. So no
parameter properties, no `enum`, no `namespace`, no decorators anywhere under `apps/`, and
every relative import carries an explicit `.ts`. `tsconfig.base.json` sets
`erasableSyntaxOnly` and `moduleResolution: "nodenext"` so either slip is a compile error
rather than a green typecheck over code that cannot boot.
```

- [ ] **Step 4: Amend §4.3 rule 2 and §8.1 in the spec**

In `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md`:

- Replace §4.3 rule 2's first sentence, *"A `BEFORE UPDATE OR DELETE` trigger on `reports`, `report_scores`, `report_team` and `citations`, raising when the parent report's `status = 'committed'`"*, with: *"Immutability triggers on `reports`, `report_scores`, `report_team` and `citations`, raising when the parent report's `status = 'committed'`. The children fire on `INSERT OR UPDATE OR DELETE`; statement-level `BEFORE TRUNCATE` triggers cover those four and `forward_returns`; every trigger is `ENABLE ALWAYS`; and a child's `report_id` is immutable unconditionally. Amended 2026-09-21 — the literal earlier wording left INSERT, TRUNCATE, replica mode and re-parenting open, all four reproduced live on PostgreSQL 16.13."*
- Replace §8.1's second bullet, *"That table is written in exactly one place — the commit transaction (§3.3) — from values a human typed"*, with: *"The frozen formulas are evaluated in exactly one place — the commit transaction (§3.3) — and no LLM-reachable code path writes that table. `report_scores` also holds the operator's in-progress draft, because a half-finished report has to survive a browser reload; `product_passed IS NOT NULL` is the sentinel meaning the frozen gate has run, and every derived-value constraint keys off it. Amended 2026-09-21."*

Leave the `## Normative formulas (frozen)` section untouched.

- [ ] **Step 5: Rewrite the database block of `.env.example`**

Replace the `# ---- database` block with:

```bash
# ------------------------------------------------------------------ database
# TWO DSNs, deliberately. server.ts opens the owner pool, runs the migrations,
# asserts the immutability guards are intact, closes it, and only then opens the
# app pool and takes the port.
#
# coinpicks_owner owns every table. A session that owns them can DROP TRIGGER in
# one statement, and a superuser can SET session_replication_role = replica and
# edit a committed report with every trigger installed and silent. Neither is
# something a request should be able to reach, so the owner DSN lives for about
# fifty milliseconds per boot.
#
# Absent: the API refuses to start. That is deliberate — a ledger with no
# database is not a degraded mode worth having.
#
# Create the roles once (and rebuild coinpicks_test) with:
#   docker compose up -d db
#   pnpm --filter @coinpicks/api run db:bootstrap
DATABASE_URL_OWNER=postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks
DATABASE_URL=postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks

# The same database seen through the GRANT-limited `research` role: SELECT on
# coins/reports/report_scores/report_team/citations, SELECT+INSERT on
# forward_returns, and UPDATE on its five outcome columns only — report_id and
# horizon_days are the ledger's join key and are immutable by privilege, and
# return_fraction is a generated column no grant can make writable.
# research/forward_returns.py does NOT exist yet — it is build-order step 6.
RESEARCH_DATABASE_URL=postgresql://research:research@localhost:5433/coinpicks

# Where the api listens. Loopback only, one user, no auth.
PORT=8787
```

- [ ] **Step 6: Give CI the roles**

In `.github/workflows/ci.yml`, in the `typescript` job, replace the `env:` block with

```yaml
    env:
      DATABASE_URL_OWNER: postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks
      DATABASE_URL: postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks
```

and insert this step immediately after `- run: pnpm install --frozen-lockfile`:

```yaml
      - name: Bootstrap the database roles
        # Not a Drizzle migration: CREATE ROLE is cluster-scoped while a migration applies
        # once per database, and coinpicks_test would have no roles. psql is preinstalled on
        # ubuntu-latest. This is the only superuser connection in the pipeline.
        run: psql "$SUPERUSER_URL" -v ON_ERROR_STOP=1 -f apps/api/scripts/bootstrap-roles.sql
        env:
          SUPERUSER_URL: postgresql://coinpicks:coinpicks@localhost:5433/postgres
```

`pnpm install --frozen-lockfile` needs the regenerated `pnpm-lock.yaml` from Task 2 to be committed — it is, or CI fails on that line before it reaches this one.

- [ ] **Step 7: Record the decisions**

Append to `agents/decisions.md`, dated 2026-09-21:

```markdown
## 2026-09-21 — schema, triggers and the role split (build-order step 3)

- **Three roles, two DSNs, one process.** Confirmed live: a session owning the tables can
  `SET session_replication_role = replica` and then flip a committed report to draft and
  delete it, with every trigger installed and silent, and can `DROP TRIGGER` outright. A
  NOSUPERUSER non-owner is refused all of it and the triggers still fire against it. The cost
  is a second DSN in `.env`; accepted, because it is the only thing that makes "the app
  cannot disable its own guard" literally true.
- **Schema rule 2 amended.** The children fire on INSERT as well as UPDATE/DELETE; there are
  statement-level BEFORE TRUNCATE triggers on five tables; every trigger is ENABLE ALWAYS;
  and a child's `report_id` is immutable unconditionally. All four holes were reproduced on
  PostgreSQL 16.13 under the literal earlier wording.
- **Spec §8.1 amended.** `report_scores` holds the draft. The containment guarantee is
  restated without the literal single-writer claim, which could not survive a browser reload.
- **A report whose product gate FAILS does get committed**, with `product_passed = false` and
  the downstream sections required empty. A ledger holding only passes is survivorship bias
  in the exact dataset built to test the framework. What it buys is the rejected population
  and its product totals; it does NOT cure survivorship bias for narrative or team scores,
  which only exist on a report that passed.
- **`SCORING_VERSION = 'coinpicks-2026-09-21'`.** A date, not a semver and not a content hash
  of `scoring/` — a hash would bump on a refactor and split the ledger for nothing. Bump only
  when a frozen formula, range, weight or threshold changes; `frozen-surface.test.ts` fails
  when one moves.
- **Sub-noise net flow counts as zero** (the `MULTIPLE | ISSUANCE_NEGATIVE | PURE_PREMIUM`
  taxonomy, not the frozen formula). 120 of 960 round-input combinations where issuance
  equals gross to the cent left a float residue that published as a 3.4e21 payback multiple.
- **`forward_returns` stores two prices**, and `return_fraction` is generated from them. The
  old `return_pct` held a fraction under a percentage's name, guarded by a one-sided CHECK
  that caught percentage-scaled losses and passed percentage-scaled gains.
- **`research` also gets SELECT on `forward_returns`.** The spec's list said "nothing else",
  which would leave `forward_returns.py` unable to see which horizons it had already priced.
  A read of rows it wrote itself.
- **`chain_facts` is deliberately NOT under the trigger set.** Rule 2 names four tables,
  chain_facts is Phase A.2, and rows with a NULL `report_id` would be freely mutable while
  their siblings were frozen. Open: a committed report's on-chain evidence can still be
  rewritten. Do not "complete" the trigger set without ruling on this.
```

Append to `agents/roadmap.md`: `- 2026-09-21 — build-order step 3 complete: schema, three migrations, twelve ENABLE ALWAYS triggers, the role split, CAS. Next: step 4, the minimal editor.`

- [ ] **Step 8: Full green, then commit**

```bash
cd /home/dev/projects/trade-god
python -m pytest -q
cd apps/api && pnpm test && pnpm typecheck
cd /home/dev/projects/trade-god && pnpm check --write && pnpm check
git add -A
git commit -m "docs: record the two amended schema rules and the role split

Rules 2 and 3 as written left four holes that were reproduced live, so the
wording has to change with the code -- otherwise the next reader restores the
literal version and reopens them. Also the two DSNs, the CI bootstrap step, and
the decisions that were the owner's to make rather than mine."
```
Expected: `111 passed` from pytest; `Test Files 11 passed (11)` from vitest with **89 tests passed**; typecheck silent; Biome clean.

---

## What this plan deliberately hands to build-order step 6 (the commit gate)

These are confirmed findings against the commit path. The commit route is not in this plan, and inventing half of it here would make both plans wrong. Each one is written out so step 6 inherits the fix rather than the bug, and the **schema already carries the column each needs**.

1. **`readReportRows` must filter on `selected_at IS NOT NULL`, identically to phase 1.** The design's phase 4 read every citation for the report, including unselected model candidates. §8.2 is explicit that an unselected candidate is "never a commit blocker and never a commit credential", and both halves broke: a verified-but-rejected candidate satisfied a field's coverage count, and an unselected `failed` candidate blocked a commit the human had correctly selected around. The index `ct_report_selected_idx` exists for exactly this query. Regression test: a report whose only citation for a field is an unselected verified candidate must fail the gate with `CITATION_MISSING`.
2. **Refuse a waiver whose `last_outcome = 'failed'`**, with its own blocker code, while still allowing one over `unverifiable_js` or `near_miss` — that is what §7's waiver is for. `citations.last_outcome` exists and `persistVerifications` must always write it, waived or not. The likeliest corruption in a one-user tool is the operator learning that waiving works.
3. **Write `waived_citation_count` at commit**, so a ledger query can stratify committed reports by how much of their evidence was waived.
4. **Never `?? 0` a scored column in the gate.** Each NULL input is a named blocker with the field in it. `accrual_assessed` makes absence visible to SQL; only the gate can make it visible to the operator.
5. **Require a selected verified citation for `product_hair_fire` and `product_exclusivity`.** framework/02 §1 says to test the product yourself *if it is available* — which is true of Ease of Use and only Ease of Use. §2 Hair-on-Fire asks for evidence of real demand and §3 Exclusivity is entirely external (its worked examples are a Coinbase integration, an SEC lawsuit outcome and an Ethereum Foundation fork approval). Leave `product_ease` exempt and have `product_ease_rationale` say it was a self-test.
6. **Cite a team member as `'team:' || report_team.id`, never by position.** Position is reorderable; the uuid is not.
7. **`httpStatusFor` must map `CP404` to 404 and `ScoreRangeError` to a named 422 blocker.** As designed, both fell through to 500 — an opaque server error on the one action the whole app exists to perform. Use `sqlstateOf` from `reports/errors.ts`; `error.code` is always undefined.
8. **Check the existence of the `report_scores` row BEFORE calling `evaluateGate`**, not after. The design's `SCORES_MISSING` blocker sat two statements too late to be reachable. With `reports_seed_scores` in place the row always exists, so the check downgrades to a bare invariant assertion — but it must still be in the right place.
9. **Evaluate the liquidity freshness window against the commit clock**, not against `attemptStartedAt`. With ten citations at a 30s timeout, `attemptStartedAt` can be five minutes before the row becomes immutable.

## Open, and the owner's to rule on — not blocking this plan

| # | Question | Where it bites |
|---|---|---|
| 1 | **What is the liquidity freshness window?** The framework gives an anecdote (stored liquidity rotting 12x in two weeks, `framework/00-how-we-think.md:99`) and no number. The schema now carries `liquidity_depth_measured_at`, `liquidity_top_pool_measured_at` and `liquidity_tier_assigned_at`, so the question is finally answerable — but whatever is chosen re-defines what "fresh" meant for reports committed under the old value, so it wants setting once, before report #1. | step 6's gate constant |
| 2 | **Should `chain_facts` rows with a `report_id` freeze on commit?** Left mutable here, so a committed report's on-chain evidence can still be rewritten. The same child function works unchanged if it is added, but rows with `report_id IS NULL` would then be freely mutable while their siblings are not. | Phase A.2 |
| 3 | **Does the verifier's `near_miss` closest-matching span get persisted?** §7 says the verifier computes it; §4.2 lists only `matched_offset`. No column was invented, so re-adjudicating a stored near_miss means re-fetching — which the commit path does anyway. | step 5 |
| 4 | **The vendor response cache is an eighth table.** §6 requires one with a per-endpoint TTL. It is not in these seven, and it should not be folded into `chain_facts`: a cache is truncatable-at-any-time infrastructure, `chain_facts` is evidence attached to reports, and `chain_facts` requires `chain` + `block_number NOT NULL` which a CoinGecko depth response does not have. | step 5 / Phase A.2 |
| 5 | **`spec §5` attributes the 12x liquidity-rot claim to "the framework's error log".** The claim is real and lives at `framework/00-how-we-think.md:99`; it appears nowhere in `doctrine/research/ERROR-LOG.md`. A one-line correction to the spec, not a design change. | housekeeping |

## Known limits of the guard, for the runbook rather than the code

- **An owner who means it can still drop a trigger.** `ENABLE ALWAYS` closes replica mode and the two-role split closes the request path, but `coinpicks_owner` owns the tables by construction — it has to, to migrate them. The boot check in Task 6 turns that from silent into a refusal to start, which is the most that can be done without a second machine.
- **Drizzle's migrator never checks the recorded hash**, and compares only against the single newest applied row. An already-applied file can be edited silently, and a file whose journal timestamp is older than the newest applied row is skipped permanently, exit code 0. `apps/api/drizzle/` is only as immutable as git discipline makes it; `assertJournalFullyApplied` catches the count mismatch and nothing catches the edit.
- **A committed report cannot be deleted by any means short of dropping the schema.** That is the point, and it is why the test harness rebuilds `coinpicks_test` per run instead of truncating.
