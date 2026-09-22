# Where we left off
_2026-09-22_

## This session

Build-order **step 3 finished** and **step 4 is half built**. Eleven commits, `main` green
throughout except one deliberate red across a task boundary.

- **Plan 2 completed** (Tasks 5–10): the privilege wall, `server.ts`'s migrate-assert-downgrade-serve
  boot, compare-and-swap, the accrual noise floor, `SCORING_VERSION` with the test that pins the
  formulas to the DDL, and the amended schema rules. Commits `7f19498` → `96b1eb0`.
- **Verified the whole stack rebuilds from nothing** — `docker compose down -v`, then up,
  bootstrap, boot. Every previous green had been on a database built up incrementally by the same
  session that wrote it. 7 tables, 12/12 `ENABLE ALWAYS`, 28 grants, `coinpicks_app`-only
  connections.
- **Plan 3 written, audited, revised** (`c883ed8`): 8 tasks, 79 steps, the minimal editor.
- **Plan 3 Tasks 1–4 executed**: `c75bd30`, `a7d66aa`, `f36f4f9`, `fbaef42`.

### The owner's rulings this session
1. **Keep `@tanstack/react-start`.** The first draft of Plan 3 proposed dropping it. Both its
   reasons were wrong: the Biome objection is one exclude line (`../profe` already does it), and
   Start turned out to be what closes the worst defect — its `importProtection` stops the build
   when a value import would ship the ORM to the browser, which plain Vite cannot do at all.
2. **One required-field list, generated both ways** — `db/gate-fields.ts` generates the
   `rs_gate_completeness` CHECK *and* the editor's blocker list.
3. **Explicit Save per section**, one CAS bump per section patch, not per field.
4. **Sub-noise net flow counts as zero** in the accrual verdict taxonomy.
5. I drive the browser walks in Tasks 5/7; walks write to the dev database and clean up after.

### What got caught by running things rather than reading them
- `rs_gate_completeness` was **inert on a draft** (`CASE WHEN product_passed` … and that is only
  written at commit). A passed row with a NULL sub-score was accepted, because `total = a+b+c` is
  NULL when any operand is and a CHECK accepts NULL.
- Postgres **rounds into an integer column and the CHECK passes the rounded value**:
  `INSERT (ease integer) VALUES (7.5),(8.5),(0.4)` stored `{0,8,9}`. The frozen
  `assertIntegerRange` must run *before* the database; the CHECK cannot defend the integer ruling
  alone.
- `integrity.test.ts` was **passing over a genuinely broken database** — it restored a deleted
  migration row with an invented hash at `max(created_at)+1`, so the count added up. The guard
  compares the applied *set* now.
- The **leak guard was watched failing three ways** before being trusted. The one that matters: a
  value import inside `createServerFn` leaves the CLIENT bundle with **zero** needles while the
  server bundle carries 25 — a client-only scan would have said all clear.
- **`strictPort` caught a real collision**: 5173 is held by the sibling repo's dev server, which
  answers 200. Vite refused to start rather than drift to 5174 and let a curl at 5173 be answered
  by someone else. Same shape as the 8787 episode.

## State

- Branch `main`, working tree clean, **not pushed**.
- `apps/api`: **119 tests / 14 files**. `apps/web`: **13 tests / 2 files**. pytest: **111**.
  Typecheck silent, Biome clean over 61 files.
- Postgres up as `coinpicks-db` on 127.0.0.1:5433, four migrations applied, three roles.
  Dev database holds **0 coins, 0 reports** — nothing from the verification walks survived.
- `apps/web` exists and builds: client 583,071 bytes over 5 JS files, server 254,242.
  `pnpm dev` starts both apps; the API is 8789, the web app 5173 (**taken on this machine** —
  use `--port 5174` while the sibling dev server runs).
- No servers left running.

## Next session

1. **Plan 3 Task 5** — the editor shell and the section-save model, 11 steps, at plan line 4103.
   It replaces the `reports.$reportId.tsx` stub entirely and adds `editor/{fields,common,
   ProductSection,RiskSection}.tsx`.
2. Then Task 6 (the blocker list, 4 steps), Task 7 (the four remaining sections, 16 steps), Task 8
   (docs/CI/decisions, 8 steps).
3. **Open the editor yourself before Task 8.** I am checking my own work on the browser walks, and
   the plan has no component render tests by design. Thirty seconds in the real screen will surface
   what no plan thought to specify — and the spec's own claim is that the editor *is* the product.

## Open items

- **The leak guard rides on an unpinned transitive.** `importProtection` comes from
  `@tanstack/start-plugin-core`, which resolved to **1.171.47** while `@tanstack/react-start` is
  pinned at 1.168.57. Pinning one does not pin the other; the bundle scan is the backstop, kept
  deliberately for that reason.
- **Should the web dev port move to 5174 by default?** The API moved to 8789 for exactly this
  reason. Undecided; `strictPort` makes the collision loud either way.
- Five open questions recorded in Plan 2's own text, of which the **liquidity freshness window**
  is the one that wants a number before report #1 — whatever is chosen redefines what "fresh"
  meant for anything committed earlier.
- `.env` still holds the trading era's Binance keys, Telegram token and a Claude API key. Backed
  up to `.env.trading-era.bak` (gitignored). Worth revoking at the source.
- Three dead docker volumes: `trade-god_postgres_data`, `trade-god_klines_cache`,
  `trade-god_swing_data`.
