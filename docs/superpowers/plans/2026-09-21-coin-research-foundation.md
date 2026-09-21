# Coin Research Platform — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave the repo describing what it actually is, and build the deterministic scoring core that every later plan depends on.

**Architecture:** Archive the retired Python trading stack to `legacy/`, relocate the one research-owned module out of it, rewrite the repo's self-description, then build a pnpm workspace in which `apps/api` (Hono + Drizzle + Postgres) owns every frozen formula, every write and every outbound request, and `apps/web` (TanStack Start) is a form that posts the operator's inputs and reads back the server's verdict.

**Tech Stack:** pnpm 10.33.0 workspace, `packages: ["apps/*"]`. Runtime is Node v26.8.1 — **not Bun**; Node executes a `.ts` file directly here with no flag and no loader, and this repo has no workspace package that publishes raw `.ts`.

- `apps/api` — hono 4.13.8, @hono/zod-validator 0.9.1, drizzle-orm 0.45.3, drizzle-kit 0.31.11 (dev), pg 8.23.0 via `drizzle-orm/node-postgres`, zod 4.6.5, openai 7.20.0, viem 2.56.8 (Phase A.2)
- `apps/web` — @tanstack/react-start 1.168.57, @tanstack/react-router 1.170.38, react/react-dom 19.3.0, vite 8.3.0, tailwindcss + @tailwindcss/vite 4.3.3
- shared — @biomejs/biome 2.5.14
- **Catalog pins in `pnpm-workspace.yaml` are a deliberate deviation from "always latest", and must be stated as such wherever these versions are listed:** typescript 5.9.3 (latest is 7.0.2, the Go-native compiler, a fresh major) and vitest 4.1.11 (latest is 5.0.1, days old). `hc<AppType>` plus Drizzle's `$inferSelect` are two of the heaviest type-level workloads in the ecosystem, and the sibling repo's decisions log records that unpinned TypeScript across workspaces is what produces Hono's "Type instantiation is excessively deep" across an RPC boundary. Revisit the week after report #1 commits.
- Deliberately absent: shadcn, any component library, Better Auth, Redis, S3, BullMQ, a git-hook gate, jscpd, fallow. Those belong to a deployed product with customers.
- Postgres: ONE docker compose service, `postgres:16-alpine`, bound `127.0.0.1:5433:5432` — not 5432, which an unrelated container (`medi-pal-db-1`, postgres:17.2) already holds on this machine — on a fresh named volume `coinpicks_data`, never the old `trade-god_postgres_data`. `DATABASE_URL=postgresql://coinpicks:coinpicks@localhost:5433/coinpicks`. Drizzle is the only DDL author; Alembic stops being this repo's migration tool.
- Deployment: loopback only, one user, no auth. Daily run is `docker compose up -d db`, then `pnpm dev` (api on 8787, web on 5173 proxying `/api`).

**Spec:** `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` — superseded in part by the 2026-09-21 stack decision above and by the EvidenceFinder decision (the LLM proposes `{url, quote, why}` candidates for the deterministic verifier and never proposes a number; every `*_draft` column is gone; the human types every score).

## Plan 1 status, 2026-09-21

| Task | Status |
|---|---|
| Task 1 — archive the retired trading stack | **DONE** (2026-09-21) |
| Task 2 — rewrite the repo's self-description | **DONE** (2026-09-21) — delivered from the stack + EvidenceFinder decisions; the code block under the task is a superseded record of what was planned |
| Task 3 — Electron + React scaffold | **DISCARDED** — see the salvage note on the task |
| Task 4 — SQLite schema | **DISCARDED** — the seven-table shape survives as Drizzle |
| Tasks 5 & 6 — frozen scoring core | **NEXT**, and they run first, before any framework scaffolding |

## Global Constraints

- **Framework formulas are frozen.** Every weight, range, and threshold comes from the spec's "Normative formulas (frozen)" section and is reproduced exactly. Never adjust one because it looks better calibrated — raise it with the user instead.
- **Ranges are rejected, never clamped.** An out-of-range score throws; it is not silently coerced.
- Narrative sub-scores may be **fractional** (the framework's own worked example scores Communication 4.5/5). Do not constrain them to integers.
- Commits never carry AI attribution — no `Co-Authored-By` trailers, no generated-with footers.
- Commits land on `main` directly (this is a personal repo; the user has said branches are unnecessary here).
- `research/` and `tests/research/` must keep passing throughout. Run `python -m pytest tests/research -q` after any move that touches them.
- **All network access, all database writes, and every frozen formula live server-side, in `apps/api`.** `apps/web` is a form: it posts the operator's inputs and renders the server's verdict. It never scores, never fetches a third-party URL, and never holds a key. `apps/api/package.json` declares `exports "." -> "./src/app.ts"`, so `apps/web` cannot import `narrativeTotal()` even by accident — the module resolver, not a convention, enforces the one-copy rule.

---

### Task 1: Archive the retired Python trading stack — DONE 2026-09-21

> **DONE, 2026-09-21.** Executed in the working tree. Two corrections to the record below:
>
> 1. **A step that was not planned happened, and mattered.** `tests/intraday/test_strategy_core.py` was not archived with the rest of `tests/intraday/` — it moved to `tests/research/test_strategy_core.py` and was repointed at `research.signals.intraday.strategy_core`, so the one surviving module keeps its coverage instead of losing it to `legacy/`.
> 2. **The final suite is 111 passed** (it was 182 before the move, of which 108 were already `tests/research`), not "the same count as Step 1".
>
> Also executed and not in the step list below: 24 tracked `charts_out/` PNGs were deleted alongside `swing-logs.txt` and `bot.log`. `research/v2_eval/` was archived as planned — worth recording that it had *already* been broken since 2026-07-16 (`run.py` lines 53-64 import `app.swing.backtest_replay`), nothing tested it, and the suite stayed green over a dead module for two months.

The intraday engine, its API, its Postgres models, and its Docker stack are all retired. `research/` must survive, which means the one module it imports has to move with it.

**Files:**
- Move: `app/intraday/` → `legacy/app/intraday/` (except `strategy.py`)
- Move: `app/intraday/strategy.py` → `research/signals/intraday/strategy_core.py`
- Move: `app/api/`, `app/db/`, `app/config.py` → `legacy/app/`
- Move: `alembic/`, `alembic.ini`, `docker-compose.yml`, `Dockerfile`, `api_main.py`, `intraday_main.py` → `legacy/`
- Move: `tests/intraday/`, `tests/api/` → `legacy/tests/` — **except** `tests/intraday/test_strategy_core.py` → `tests/research/test_strategy_core.py`, repointed at `research.signals.intraday.strategy_core`
- Move: `research/v2_eval/` → `legacy/research/v2_eval/` (already broken — imports `app.swing.backtest_replay`, archived 2026-07-16)
- Modify: `research/signals/intraday/mr_vwap_strategy.py:18`
- Modify: `research/signals/intraday/families.py:45`
- Delete: `swing-logs.txt`, `bot.log`, and the 24 tracked `charts_out/` PNGs

**Interfaces:**
- Consumes: nothing.
- Produces: `research/signals/intraday/strategy_core.py` exporting `Z_ENTRY`, `Z_RECOVER`, `build_weights`, `zscore` — identical contents to the archived `app/intraday/strategy.py`.

- [ ] **Step 1: Confirm the current research suite is green before moving anything**

Run: `python -m pytest tests/research -q`
Expected: PASS. If it is already failing, stop and report — this task must not be the thing that hides a pre-existing break.

- [ ] **Step 2: Relocate the strategy module and repoint its two importers**

```bash
git mv app/intraday/strategy.py research/signals/intraday/strategy_core.py
sed -i 's|from app\.intraday\.strategy import|from research.signals.intraday.strategy_core import|' \
  research/signals/intraday/mr_vwap_strategy.py research/signals/intraday/families.py
grep -rn "strategy_core" research/signals/intraday/
```
Expected: both files now import from `research.signals.intraday.strategy_core`.

- [ ] **Step 3: Run the research suite to prove the relocation is clean**

Run: `python -m pytest tests/research -q`
Expected: PASS, same count as Step 1.

- [ ] **Step 4: Archive everything else**

```bash
mkdir -p legacy/app legacy/tests legacy/research
git mv app/intraday legacy/app/intraday
git mv app/api legacy/app/api
git mv app/db legacy/app/db
git mv app/config.py legacy/app/config.py
git mv alembic legacy/alembic
git mv alembic.ini api_main.py intraday_main.py docker-compose.yml Dockerfile legacy/
git mv tests/intraday legacy/tests/intraday
git mv tests/api legacy/tests/api
git mv research/v2_eval legacy/research/v2_eval
git rm -f swing-logs.txt bot.log
rmdir app 2>/dev/null || true
```

- [ ] **Step 5: Stop pytest collecting the archived tests**

Open `pyproject.toml`, find the `[tool.pytest.ini_options]` block, and ensure `testpaths` lists only `tests` and that `norecursedirs` includes `legacy`. If `testpaths` names `tests/intraday` or `tests/api` explicitly, remove those entries.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, collecting only `tests/research` and `tests/conftest.py`. No import errors mentioning `app.`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: archive the retired trading stack, move strategy core into research

The intraday engine, its API, Postgres models and Docker stack no longer run.
research/ owned the only live consumer of strategy.py, so it moves there."
```

---

### Task 2: Rewrite the repo's self-description — DONE 2026-09-21

> **DONE, 2026-09-21 — but NOT from the code block below, which is a SUPERSEDED record of what was planned.** `CLAUDE.md`, `README.md`, `agents/CONTEXT.md`, `agents/decisions.md` and `agents/roadmap.md` are all written, and all of them describe the pnpm-workspace stack. The delivered text took its facts from the header block and Global Constraints of **this plan**, plus the spec at `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` as amended by the stack and EvidenceFinder decisions.
>
> Why the block below is not what was written: its `CLAUDE.md` describes the Electron desktop app, `desktop/src/main/`, SQLite and a drafter writing to `*_draft` columns — every one of which the same-day stack decision replaced. Its `agents/decisions.md` entry "Electron, not Tauri; TypeScript, not Python" is likewise stale in its first half and still correct in its second.
>
> The text is left in place on purpose, struck through as a record of what was planned rather than deleted — the framework sections, the directory table and the Research Warehouse section are all still reusable prose.

`CLAUDE.md` currently tells every session that a live intraday paper engine is the system. It isn't. This task replaces it and seeds the `agents/` paper trail per the `new-project` skill's doc formats.

**Files:**
- Modify: `CLAUDE.md` (full rewrite)
- Create: `agents/CONTEXT.md`
- Create: `agents/roadmap.md`
- Create: `agents/decisions.md`

**Interfaces:**
- Consumes: Task 1's final directory layout.
- Produces: documentation only. No code depends on this.

- [ ] **Step 1: Rewrite `CLAUDE.md`**

Replace the entire file with:

> **SUPERSEDED record — this is not the `CLAUDE.md` that was written.** The delivered file describes the pnpm workspace (`apps/api` + `apps/web`, Postgres 16 + Drizzle on 5433, an EvidenceFinder that proposes candidates). Everything below that says `desktop/src/main/`, SQLite or `*_draft` is dead text kept for its reusable prose.

```markdown
# Trade-God — Project Context for Claude

## What this is
A **local desktop research platform** implementing the CoinPicks fundamental analysis framework
for crypto tokens. Single user, local only — no host, no auth, no Docker.

It produces one immutable, point-in-time report per researched coin: a Product gate result, a
liquidity tier grounded in on-chain reserves, a Narrative score /31, a Team weighted score /10, a
value-accrual computation, and citations whose quotes are **mechanically verified** to appear at
their source URL.

**This repo used to be an automated trading system.** That era ended 2026-09-21 — see
`agents/decisions.md`. All of it is archived in `legacy/`.

**Tech:** Electron 34, React 19, TypeScript 5.7, better-sqlite3, viem, Vitest, Biome, pnpm.
Plus Python 3.12 for the offline research warehouse.

---

## Directory Structure
```
desktop/              # The application
├── src/main/         # Node: db, chain reads, vendor fetches, drafter, citation verifier
├── src/preload/      # typed IPC surface
└── src/renderer/     # React + Tailwind + shadcn
research/             # Python parquet warehouse (dev machine only) + signal research
agents/               # Paper trail: CONTEXT.md, roadmap.md, decisions.md, handoff.md
docs/superpowers/     # specs/ and plans/
legacy/               # Every retired system. Not collected by tests, not imported.
```

---

## The frozen formulas

The CoinPicks framework formulas are **normative**. Implement them exactly; never adjust a weight
or threshold because an alternative looks better calibrated. A modified formula tests a different
framework and makes the ledger's verdict meaningless — raise discrepancies with the user instead.

Full table with source lesson IDs:
`docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` → "Normative formulas (frozen)".

---

## Conventions

- All network and disk access lives in `desktop/src/main/`. The renderer never calls `fetch`,
  never holds a key.
- Scores are **rejected** when out of range, never clamped.
- The LLM writes only to `*_draft` columns. It can never write a committed value.
- A report cannot be committed while any citation is unverified — the only escape is an explicit
  waiver with a recorded reason.
- Every on-chain fact is stored with its `block_number` and `fetched_at`.
- Liquidity is re-pulled live at decision time, never read from a stored figure.

---

## How to run

```bash
cd desktop && pnpm install && pnpm dev     # the app
cd desktop && pnpm test                    # Vitest
cd desktop && pnpm check                   # Biome
python -m pytest -q                        # the Python research suite
```

---

## Research Warehouse (`research/`, dev machine only)

Point-in-time market data — parquet per dataset per symbol under gitignored `research/warehouse/`.
Never ships anywhere. Feeds the forward-return ledger.

```bash
python -m research.backfill --top 100          # resumable
python -m research.check                       # gap/staleness report
```

**Rules:** run backfills from the DEV machine only. All endpoints are unsigned (no API keys).
Known quirks: Binance funding timestamps carry ms jitter; ICPUSDT premium index has a genuine
77-day hole (2022-07-12 → 2022-09-27); OI/L-S endpoints are END-anchored.

---

## Session convention

When a session ends with "let's continue tomorrow" (or similar), overwrite `agents/handoff.md`
with: what was done, current state, and the next session's plan. Record hard decisions in
`agents/decisions.md` as they happen, not at the end.

## Git

- Commits land on `main` directly — personal repo, no branch ceremony needed.
- Never add AI attribution: no `Co-Authored-By: Claude …` trailers, no generated-with footers.
- Run the touched suite before calling anything done.
```

- [ ] **Step 2: Create `agents/CONTEXT.md`**

> **SUPERSEDED record — this is not the `agents/CONTEXT.md` that was written.** The delivered vocabulary retires "drafter"; the EvidenceFinder proposes **candidates**, and the `**Draft**` entry below names `*_draft` columns that no longer exist.

```markdown
# CONTEXT — canonical vocabulary

Terms used across this project. Use these words; avoid the listed synonyms.

**Report** — one immutable, versioned, point-in-time analysis of one coin. Never edited; a change
produces a new version. _Avoid_: "analysis", "writeup".

**Committed** — a report that passed the commit gate. Only a human writes committed values.
_Avoid_: "finalized", "saved", "published".

**Draft** — an LLM-proposed value, stored in a `*_draft` column with a one-line reason. Never
counts toward anything. _Avoid_: "suggestion", "AI score".

**Commit gate** — the check that blocks committing: no empty decisions, no unverified citations,
no out-of-range values.

**Citation** — a `{url, quote}` pair attached to a specific scored field, carrying a verification
status. A citation is *verified* only when the quote was mechanically found at that URL.
_Avoid_: "source", "reference" (those are the URL alone).

**Waiver** — an explicit, reasoned override letting one unverifiable citation through the gate.

**Product gate** — `ease + hairFire + exclusivity >= 16`. Fails close the report.

**Narrative score** — the /31 total across six sub-scores.

**Team weighted score** — `(founder × 5 + Σ others) ÷ (5 + N_others)`, out of 10.

**Accrual flow** — annual dollars *forced* to token holders by a mechanism. Governance, exposure,
and alignment are not mechanisms. _Avoid_: "yield", "revenue" (those are the protocol's, not the
holder's).

**Pure premium** — a token with no positive net accrual flow at any price. Tradable, never ownable.

**Pool census** — enumerating every pool for a token, reading reserves on-chain, and discarding
those whose price deviates beyond threshold from the TVL-weighted median.

**Poison pair** — a pool advertising large liquidity at a fake price. The thing a census removes.

**Ledger** — the accumulated committed reports joined to forward returns. The thing that will
eventually say whether any of these scores predict anything.

**Pillar** *(Phase B, not built)* — one claim about the market backed by its own report.

**Signal** *(Phase B, not built)* — `((P − 50) ÷ 50) × Quality × Impact`, range ±10.
```

- [ ] **Step 3: Create `agents/decisions.md`**

```markdown
# Decisions

Hard, costly-to-reverse decisions only. Dated. Newest first.

## 2026-09-21 — Retire automated trading; pivot to fundamental research tooling

The pre-registered OOS run measured the surviving strategy at **−15.19% return, profit factor
0.986, Sharpe −0.29 over 2,791 trades** (−25.2% under stress, max drawdown 36–41%). Training-set
profit factor was 1.021. The 66-day paper run that looked positive was ~1.8 months drawn from a
~6%-monthly-volatility distribution, evaluated at three sequential check-ins, with its entire gain
concentrated in ~10 of 312 trades (ex-top-10: −$0.26).

AWS closed the account hosting the engine, destroying the paper telemetry and its Telegram audit
trail. We chose not to reconstruct it: 1.8 months of noise adds nothing to a 2,791-trade OOS
sample. Four systems (DCA, swing v1, swing v2, intraday) now all measure negative.

**Reversal cost:** high. All trading code is archived in `legacy/`, infrastructure is gone.

## 2026-09-21 — Framework formulas are frozen

CoinPicks formulas are implemented exactly as published, never tuned. The purpose of this tool is
to *test* the framework; a modified formula tests something else, and the ledger's verdict would
be about a method nobody uses. Discrepancies get raised, not patched.

**Reversal cost:** low mechanically, total epistemically — retuning invalidates every prior
committed report as comparable evidence.

## 2026-09-21 — Electron, not Tauri; TypeScript, not Python

`~/projects/klickbrain` planned Tauri (`docs/PROJECT.md:551`) and shipped Electron at v0.8.3 with
full packaging. Decision validated by execution, so it is reused. Once the app is Electron, a
Python backend buys nothing — and viem has Multicall3 built in where web3.py needs it bolted on.
Python stays for the offline warehouse only.

**Reversal cost:** high once the UI exists.

## 2026-09-21 — Local only, no hosted service

The authoring workflow is a desk activity and needs no uptime. Running locally is also what allows
drafting to use the Claude Code subscription instead of API billing. No host also means no host to
lose.

**Reversal cost:** moderate — would require auth, hosting, and a different drafting path.
```

- [ ] **Step 4: Create `agents/roadmap.md`**

```markdown
# Roadmap

## Goal
A research tool that makes the deterministic parts of the CoinPicks framework deterministic, makes
its citation requirement mechanical, and accumulates enough point-in-time reports to test whether
the framework's scores predict anything.

## Phase A — coin research pipeline

- [ ] **Plan 1 — Foundation.** Archive the retired stack, rewrite repo docs, Electron + React
      scaffold, SQLite schema, frozen-formula scoring core.
      `docs/superpowers/plans/2026-09-21-coin-research-foundation.md`
- [ ] **Plan 2 — Evidence.** Citation verifier (the commit gate), vendor adapters
      (CoinGecko, GeckoTerminal, DeFiLlama, Artemis), viem chain layer (pool census, safety,
      issuance, holders, accrual-contract discovery).
- [ ] **Plan 3 — Workflow.** `Drafter` interface (Claude CLI subscription primary, API key
      fallback), typed IPC, report editor, commit gate UI.
- [ ] **Plan 4 — Ledger.** `research/forward_returns.py` against the parquet warehouse,
      calibration view.

## Phase B — market direction (not started)
Pillar reports and the `Signal = ((P − 50) ÷ 50) × Quality × Impact` machinery over five locked
windows (1M/3M/6M/1Y/3Y), aggregating by pillar weight into a per-window call.

## Explicitly not planned
Trade execution of any kind. Alerting or any deployed service. Solana. Wallet clustering.
```

- [ ] **Step 5: Verify the docs describe reality**

```bash
ls agents/
grep -c "intraday paper engine" CLAUDE.md || echo "0 — good, stale description is gone"
ls desktop 2>/dev/null || echo "desktop/ not yet created — expected, Task 3 creates it"
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md agents/
git commit -m "docs: describe what this repo now is

CLAUDE.md described a live paper-trading engine that no longer exists. Seeds the
agents/ paper trail with the vocabulary and the decisions behind the pivot."
```

---

### Task 3: Scaffold the Electron + React application — DISCARDED 2026-09-21

> **DISCARDED, 2026-09-21.** There is no Electron app. The scaffold is a pnpm workspace with `apps/api` (Hono) and `apps/web` (TanStack Start), and nothing below builds it. **Salvaged from this task:** the Tailwind v4 setup (`@tailwindcss/vite`, the single `@import "tailwindcss"` line, no `tailwind.config.js`) carries over to `apps/web` unchanged; the strict `tsconfig` pair — one for the Node side, one for the browser side, both with `strict`, `noUncheckedIndexedAccess` and `verbatimModuleSyntax` — carries over as `apps/api/tsconfig.json` and `apps/web/tsconfig.json`; the Vitest config carries over as-is; and the script names (`dev`, `build`, `test`, `typecheck`, `check`) stay the same in every workspace package, so muscle memory survives the stack change. Everything Electron-specific — `electron-vite`, the `main`/`preload`/`renderer` split, `contextIsolation`, the IPC surface — is gone.
>
> Body left in place beneath this notice.

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/electron.vite.config.ts`
- Create: `desktop/tsconfig.json`, `desktop/tsconfig.node.json`, `desktop/tsconfig.web.json`
- Create: `desktop/biome.json`
- Create: `desktop/src/main/index.ts`
- Create: `desktop/src/preload/index.ts`
- Create: `desktop/src/renderer/index.html`, `desktop/src/renderer/main.tsx`, `desktop/src/renderer/App.tsx`
- Create: `desktop/vitest.config.ts`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a `pnpm dev` that opens a window, and a `pnpm test` that runs Vitest against `src/main/`.

- [ ] **Step 1: Create the package manifest**

```bash
mkdir -p desktop/src/{main,preload,renderer}
cd desktop
```

Write `desktop/package.json`:

```json
{
  "name": "coin-research-desktop",
  "version": "0.1.0",
  "description": "CoinPicks fundamental research platform",
  "main": "out/main/index.js",
  "private": true,
  "type": "module",
  "imports": { "#/*": "./src/renderer/*" },
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit -p tsconfig.node.json && tsc --noEmit -p tsconfig.web.json",
    "check": "biome check --write"
  },
  "dependencies": {
    "better-sqlite3": "^11.0.0",
    "clsx": "^2.1.1",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwind-merge": "^3.5.0",
    "viem": "^2.21.0",
    "zod": "^4.0.0"
  },
  "devDependencies": {
    "@biomejs/biome": "2.4.5",
    "@electron/rebuild": "^3.7.0",
    "@tailwindcss/vite": "^4.1.18",
    "@types/better-sqlite3": "^7.6.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "electron": "^34.0.0",
    "electron-vite": "^5.0.0",
    "tailwindcss": "^4.1.18",
    "typescript": "^5.7.0",
    "vite": "^7.0.0",
    "vitest": "^3.0.0"
  },
  "pnpm": { "onlyBuiltDependencies": ["better-sqlite3", "electron", "esbuild"] }
}
```

- [ ] **Step 2: Create the build config**

Write `desktop/electron.vite.config.ts`:

```ts
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'

export default defineConfig({
  main: { plugins: [externalizeDepsPlugin()] },
  preload: { plugins: [externalizeDepsPlugin()] },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    resolve: { alias: { '#': resolve(__dirname, 'src/renderer') } },
    plugins: [react(), tailwindcss()],
    build: { rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') } },
  },
})
```

Write `desktop/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
})
```

- [ ] **Step 3: Create the main process, preload, and renderer entry**

Write `desktop/src/main/index.ts`:

```ts
import { join } from 'node:path'
import { app, BrowserWindow } from 'electron'

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.on('ready-to-show', () => win.show())

  if (process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
```

Write `desktop/src/preload/index.ts`:

```ts
import { contextBridge } from 'electron'

// The typed IPC surface grows in Plan 3. It exists now so contextIsolation
// is wired correctly from the first commit.
contextBridge.exposeInMainWorld('api', {})
```

Write `desktop/src/renderer/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Coin Research</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./main.tsx"></script>
  </body>
</html>
```

Write `desktop/src/renderer/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Write `desktop/src/renderer/App.tsx`:

```tsx
export default function App() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Coin Research</h1>
      <p className="text-neutral-500">No reports yet.</p>
    </main>
  )
}
```

Write `desktop/src/renderer/styles.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 4: Create the TypeScript and Biome configs**

Write `desktop/tsconfig.json`:

```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.node.json" }, { "path": "./tsconfig.web.json" }]
}
```

Write `desktop/tsconfig.node.json`:

```json
{
  "include": ["src/main/**/*", "src/preload/**/*", "electron.vite.config.ts", "vitest.config.ts"],
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "target": "ES2022",
    "strict": true,
    "skipLibCheck": true,
    "types": ["node"]
  }
}
```

Write `desktop/tsconfig.web.json`:

```json
{
  "include": ["src/renderer/**/*"],
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "target": "ES2022",
    "jsx": "react-jsx",
    "lib": ["ES2022", "DOM"],
    "strict": true,
    "skipLibCheck": true,
    "paths": { "#/*": ["./src/renderer/*"] }
  }
}
```

Write `desktop/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.4.5/schema.json",
  "formatter": { "enabled": true, "indentStyle": "space", "indentWidth": 2, "lineWidth": 100 },
  "linter": { "enabled": true, "rules": { "recommended": true } },
  "files": { "includes": ["src/**/*"] }
}
```

- [ ] **Step 5: Ignore build output**

Append to the repo root `.gitignore`:

```
desktop/node_modules/
desktop/out/
desktop/dist/
desktop/*.tsbuildinfo
```

- [ ] **Step 6: Install and verify the app runs**

```bash
cd desktop && pnpm install && pnpm typecheck
```
Expected: installs cleanly, typecheck passes.

```bash
cd desktop && pnpm dev
```
Expected: a window opens showing "Coin Research" and "No reports yet." Close it.

- [ ] **Step 7: Commit**

```bash
git add desktop .gitignore
git commit -m "feat: scaffold the Electron + React desktop app

contextIsolation on and nodeIntegration off from the first commit; the preload
surface is empty but real so IPC has a correct home in Plan 3."
```

---

### Task 4: SQLite schema — DISCARDED 2026-09-21

> **DISCARDED, 2026-09-21.** The database is Postgres 16 and Drizzle is its only DDL author: `apps/api/src/db/schema.ts` declares every column, `drizzle-kit generate` writes plain `.sql` under `apps/api/drizzle/` plus `meta/_journal.json` (both committed), and the API applies them at boot from `server.ts` before the port is taken. **Salvaged from this task:** the seven-table SQL below is the surviving artifact — `coins`, `reports`, `report_scores`, `report_team`, `citations`, `chain_facts`, `forward_returns` carry over as the *shape* of the Drizzle schema, minus every `*_draft` / `*_draft_reason` column pair, which are deleted outright now that the LLM is an EvidenceFinder and the human types every score.
>
> Five things change in the translation, none of them negotiable: (1) `pgEnum`, never `text().$type<>()`, for `reports.status` and `citations.status` — `$type<T>()` is a TypeScript fiction, not a database constraint; (2) a `BEFORE UPDATE OR DELETE` trigger on `reports`, `report_scores`, `report_team` and `citations` that raises when the parent report is `committed` — Drizzle's DSL cannot express it, so it needs `drizzle-kit generate --custom` and a hand-written `.sql` that `schema.ts` never re-emits, and it is what makes "a committed report is never edited" true against a stray `psql`, a GUI client or an agent with shell access; (3) `report_scores.scoring_version`, written by the commit route from a constant in `scoring/ranges.ts`, because the ledger's fatal failure is silently comparing rows scored under two framework versions; (4) `reports.version` integer NOT NULL with compare-and-swap writes (`UPDATE ... WHERE id=$1 AND version=$2`, 409 on zero rows) — two browser tabs on one draft would otherwise be silent last-write-wins, a hole Electron's single-instance lock used to cover for free; (5) `timestamptz` for every timestamp and `jsonb` for `coins.address_sources` and `chain_facts.payload`, because the archived `app/db/models.py` stored every timestamp as `String(50)` and the ledger join is a date join.
>
> `citations` also gains `origin` in `{human, model}`, `finder_provider`, `finder_model`, and a nullable `selected_at` — a row with `selected_at IS NULL` is an unselected candidate, and the commit gate counts only selected ones.
>
> Body left in place beneath this notice.

**Files:**
- Create: `desktop/src/main/db/schema.sql`
- Create: `desktop/src/main/db/index.ts`
- Test: `desktop/src/main/db/index.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `openDatabase(path: string): Database` from `db/index.ts`, where `Database` is `better-sqlite3`'s type. Calling it applies the schema idempotently. `:memory:` is a valid path, used by tests.

- [ ] **Step 1: Write the failing test**

Write `desktop/src/main/db/index.test.ts`:

```ts
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { openDatabase } from './index'

describe('openDatabase', () => {
  it('creates every table the spec names', () => {
    const db = openDatabase(':memory:')
    const names = db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table'")
      .all()
      .map((r) => (r as { name: string }).name)

    for (const t of [
      'coins',
      'reports',
      'report_scores',
      'report_team',
      'citations',
      'chain_facts',
      'forward_returns',
    ]) {
      expect(names).toContain(t)
    }
  })

  it('is idempotent — reopening the same file re-applies the schema cleanly', () => {
    const file = join(mkdtempSync(join(tmpdir(), 'coinres-')), 'test.db')
    const first = openDatabase(file)
    first.prepare("INSERT INTO coins (id, symbol, name, chain) VALUES ('c1', 'ARB', 'Arbitrum', 'arbitrum')").run()
    first.close()

    const second = openDatabase(file)
    const count = second.prepare('SELECT COUNT(*) AS n FROM coins').get() as { n: number }
    expect(count.n).toBe(1) // schema re-applied without dropping data
    second.close()
  })

  it('enforces the citation status enum', () => {
    const db = openDatabase(':memory:')
    db.prepare("INSERT INTO coins (id, symbol, name, chain) VALUES ('c1', 'ARB', 'Arbitrum', 'arbitrum')").run()
    db.prepare("INSERT INTO reports (id, coin_id, version, status) VALUES ('r1', 'c1', 1, 'draft')").run()

    expect(() =>
      db
        .prepare(
          "INSERT INTO citations (id, report_id, field, url, quote, status) VALUES ('x1', 'r1', 'narrative_maturity', 'https://e.com', 'q', 'bogus')",
        )
        .run(),
    ).toThrow()
  })

  it('rejects a report status outside draft/committed', () => {
    const db = openDatabase(':memory:')
    db.prepare("INSERT INTO coins (id, symbol, name, chain) VALUES ('c1', 'ARB', 'Arbitrum', 'arbitrum')").run()
    expect(() =>
      db.prepare("INSERT INTO reports (id, coin_id, version, status) VALUES ('r1', 'c1', 1, 'whatever')").run(),
    ).toThrow()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd desktop && pnpm vitest run src/main/db/index.test.ts`
Expected: FAIL — cannot resolve `./index`.

- [ ] **Step 3: Write the schema**

Write `desktop/src/main/db/schema.sql`:

```sql
-- DISCARDED 2026-09-21 — DO NOT RUN. SQLite is gone (Postgres 16 + Drizzle), and every *_draft / *_draft_reason column below is deleted in the current design.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS coins (
  id               TEXT PRIMARY KEY,
  symbol           TEXT NOT NULL,
  name             TEXT NOT NULL,
  coingecko_id     TEXT,
  chain            TEXT NOT NULL,
  contract_address TEXT,
  address_sources  TEXT NOT NULL DEFAULT '[]',
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
  id           TEXT PRIMARY KEY,
  coin_id      TEXT NOT NULL REFERENCES coins(id),
  version      INTEGER NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('draft', 'committed')),
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  committed_at TEXT,
  UNIQUE (coin_id, version)
);

-- Every scored field is paired with the LLM's draft and its one-line reason.
-- Draft columns are the only ones the drafter may write.
CREATE TABLE IF NOT EXISTS report_scores (
  report_id                     TEXT PRIMARY KEY REFERENCES reports(id),

  product_ease                  REAL, product_ease_draft                  REAL, product_ease_draft_reason                  TEXT,
  product_hairfire              REAL, product_hairfire_draft              REAL, product_hairfire_draft_reason              TEXT,
  product_exclusivity           REAL, product_exclusivity_draft           REAL, product_exclusivity_draft_reason           TEXT,

  liquidity_tier                TEXT CHECK (liquidity_tier IN ('low', 'medium', 'high')),
  liquidity_depth_2pct_usd      REAL,
  liquidity_top_pool_tvl_usd    REAL,
  liquidity_surviving_pools     INTEGER,

  narrative_maturity            REAL, narrative_maturity_draft            REAL, narrative_maturity_draft_reason            TEXT,
  narrative_smart_money         REAL, narrative_smart_money_draft         REAL, narrative_smart_money_draft_reason         TEXT,
  narrative_hairfire            REAL, narrative_hairfire_draft            REAL, narrative_hairfire_draft_reason            TEXT,
  narrative_communication       REAL, narrative_communication_draft       REAL, narrative_communication_draft_reason       TEXT,
  narrative_lineage             REAL, narrative_lineage_draft             REAL, narrative_lineage_draft_reason             TEXT,
  narrative_mutation            REAL, narrative_mutation_draft            REAL, narrative_mutation_draft_reason            TEXT,

  accrual_segment_revenue_usd   REAL,
  accrual_capture_share         REAL,
  accrual_pct                   REAL,
  accrual_annual_issuance_usd   REAL,
  accrual_contract_address      TEXT,
  accrual_measured_90d_usd      REAL
);

CREATE TABLE IF NOT EXISTS report_team (
  id         TEXT PRIMARY KEY,
  report_id  TEXT NOT NULL REFERENCES reports(id),
  position   INTEGER NOT NULL,
  name       TEXT NOT NULL,
  role       TEXT NOT NULL,
  is_founder INTEGER NOT NULL CHECK (is_founder IN (0, 1)),
  h          REAL NOT NULL,
  m          REAL NOT NULL,
  l          REAL NOT NULL,
  summary    TEXT NOT NULL,
  UNIQUE (report_id, position)
);

CREATE TABLE IF NOT EXISTS citations (
  id             TEXT PRIMARY KEY,
  report_id      TEXT NOT NULL REFERENCES reports(id),
  field          TEXT NOT NULL,
  url            TEXT NOT NULL,
  quote          TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'unverified'
                 CHECK (status IN ('unverified','verified','near_miss','failed','unverifiable_js','waived')),
  verified_at    TEXT,
  http_status    INTEGER,
  matched_offset INTEGER,
  waiver_reason  TEXT
);
CREATE INDEX IF NOT EXISTS idx_citations_report ON citations(report_id);

CREATE TABLE IF NOT EXISTS chain_facts (
  id           TEXT PRIMARY KEY,
  coin_id      TEXT NOT NULL REFERENCES coins(id),
  report_id    TEXT REFERENCES reports(id),
  kind         TEXT NOT NULL
               CHECK (kind IN ('pool_census','safety','issuance','holders','accrual')),
  chain        TEXT NOT NULL,
  block_number INTEGER NOT NULL,
  fetched_at   TEXT NOT NULL,
  payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chain_facts_coin ON chain_facts(coin_id, kind);

CREATE TABLE IF NOT EXISTS forward_returns (
  report_id    TEXT NOT NULL REFERENCES reports(id),
  horizon_days INTEGER NOT NULL,
  return_pct   REAL NOT NULL,
  computed_at  TEXT NOT NULL,
  PRIMARY KEY (report_id, horizon_days)
);
```

- [ ] **Step 4: Write the opener**

Write `desktop/src/main/db/index.ts`:

```ts
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import Database from 'better-sqlite3'

export type DB = Database.Database

export function openDatabase(path: string): DB {
  const db = new Database(path)
  db.pragma('journal_mode = WAL')
  db.pragma('foreign_keys = ON')

  const here = dirname(fileURLToPath(import.meta.url))
  db.exec(readFileSync(join(here, 'schema.sql'), 'utf8'))

  return db
}
```

- [ ] **Step 5: Make the schema reachable at runtime**

`schema.sql` is not TypeScript, so electron-vite will not copy it. Add to `desktop/electron.vite.config.ts`, inside the `main` block:

```ts
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        output: { assetFileNames: '[name][extname]' },
      },
    },
    assetsInclude: ['**/*.sql'],
  },
```

For Vitest (which runs the TS directly from `src/`), the relative read already resolves. Confirm both paths work in Step 6.

- [ ] **Step 6: Run the tests**

Run: `cd desktop && pnpm vitest run src/main/db/index.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add desktop/src/main/db desktop/electron.vite.config.ts
git commit -m "feat: SQLite schema for point-in-time coin reports

Draft columns sit beside every scored field so the drafter has somewhere to write
that is structurally not a committed value. Citation and report statuses are CHECK
constraints, not conventions."
```

---

### Task 5: Scoring core — ranges, product gate, narrative

> **These two tasks are next, and they run BEFORE any framework scaffolding.** Not inside `apps/api` as a Hono app, not after a database exists — in a bare `typescript` + `vitest` package at `apps/api/`, with no Hono, no Drizzle, no Postgres and no React anywhere near it. The frozen formulas are the only code in this project that cannot be wrong: every later number, every ledger row and the whole question of whether these scores predict anything reads through them. Nothing should block them, and nothing about a route handler or a migration can teach us anything about whether `narrativeTotal()` is right. `apps/api/src/scoring/` imports nothing from the rest of the app and never will; the scaffolding grows around it afterwards.
>
> The formulas are evaluated at exactly one moment in the finished system: inside `POST /reports/:id/commit`, in the same transaction that writes `report_scores` and flips `reports.status`. Every downstream consumer — the ledger view, the API, Python's `forward_returns.py` — reads the stored number and never recomputes it. Re-derivation, when it is genuinely needed, runs the authoritative TypeScript via `node apps/api/scripts/rescore.ts`.

The first two frozen formulas. Ranges reject rather than clamp.

**Files:**
- Create: `apps/api/src/scoring/ranges.ts`
- Create: `apps/api/src/scoring/product.ts`
- Create: `apps/api/src/scoring/narrative.ts`
- Test: `apps/api/src/scoring/product.test.ts`, `apps/api/src/scoring/narrative.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ScoreRangeError` (class, fields `field: string`, `value: number`, `min: number`, `max: number`)
  - `assertRange(field: string, value: number, min: number, max: number): void`
  - `productGate(input: ProductGateInput): ProductGateResult` where `ProductGateInput = { ease: number; hairFire: number; exclusivity: number }` and `ProductGateResult = { total: number; passed: boolean }`
  - `PRODUCT_GATE_THRESHOLD: 16`
  - `narrativeTotal(input: NarrativeInput): number` where `NarrativeInput = { maturity, smartMoney, hairFire, communication, lineage, mutation }` (all `number`)
  - `NARRATIVE_MAX` (const object), `NARRATIVE_TOTAL_MAX: 31`

- [ ] **Step 1: Write the failing tests**

Write `apps/api/src/scoring/product.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { PRODUCT_GATE_THRESHOLD, productGate } from './product'
import { ScoreRangeError } from './ranges'

describe('productGate', () => {
  it('sums the three sub-scores', () => {
    expect(productGate({ ease: 7, hairFire: 6, exclusivity: 5 }).total).toBe(18)
  })

  it('passes at exactly 16 — the framework boundary', () => {
    expect(productGate({ ease: 6, hairFire: 5, exclusivity: 5 }).passed).toBe(true)
  })

  it('fails at 15', () => {
    expect(productGate({ ease: 5, hairFire: 5, exclusivity: 5 }).passed).toBe(false)
  })

  it('exposes the threshold as 16', () => {
    expect(PRODUCT_GATE_THRESHOLD).toBe(16)
  })

  it('rejects out-of-range input rather than clamping', () => {
    expect(() => productGate({ ease: 11, hairFire: 5, exclusivity: 5 })).toThrow(ScoreRangeError)
    expect(() => productGate({ ease: -1, hairFire: 5, exclusivity: 5 })).toThrow(ScoreRangeError)
  })

  it('names the offending field in the error', () => {
    try {
      productGate({ ease: 5, hairFire: 99, exclusivity: 5 })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect((e as ScoreRangeError).field).toBe('hairFire')
      expect((e as ScoreRangeError).value).toBe(99)
    }
  })
})
```

Write `apps/api/src/scoring/narrative.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { NARRATIVE_TOTAL_MAX, narrativeTotal } from './narrative'
import { ScoreRangeError } from './ranges'

const FULL = { maturity: 7, smartMoney: 6, hairFire: 6, communication: 5, lineage: 4, mutation: 3 }

describe('narrativeTotal', () => {
  it('maxes at 31', () => {
    expect(narrativeTotal(FULL)).toBe(31)
    expect(NARRATIVE_TOTAL_MAX).toBe(31)
  })

  it('reproduces the framework ARB worked example: 3+6+6+4.5+4+3 = 26.5', () => {
    expect(
      narrativeTotal({
        maturity: 3,
        smartMoney: 6,
        hairFire: 6,
        communication: 4.5,
        lineage: 4,
        mutation: 3,
      }),
    ).toBe(26.5)
  })

  it('rejects a sub-score above its own maximum', () => {
    expect(() => narrativeTotal({ ...FULL, mutation: 4 })).toThrow(ScoreRangeError)
    expect(() => narrativeTotal({ ...FULL, lineage: 5 })).toThrow(ScoreRangeError)
  })

  it('names the offending sub-score', () => {
    try {
      narrativeTotal({ ...FULL, mutation: 4 })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect((e as ScoreRangeError).field).toBe('mutation')
    }
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && pnpm vitest run src/scoring`
Expected: FAIL — cannot resolve `./product`, `./narrative`, `./ranges`.

- [ ] **Step 3: Implement**

Write `apps/api/src/scoring/ranges.ts`:

```ts
export class ScoreRangeError extends Error {
  constructor(
    readonly field: string,
    readonly value: number,
    readonly min: number,
    readonly max: number,
  ) {
    super(`${field} must be between ${min} and ${max}, got ${value}`)
    this.name = 'ScoreRangeError'
  }
}

/** Rejects out-of-range values. Never clamps — a clamped score is a silently wrong report. */
export function assertRange(field: string, value: number, min: number, max: number): void {
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new ScoreRangeError(field, value, min, max)
  }
}
```

Write `apps/api/src/scoring/product.ts`:

```ts
import { assertRange } from './ranges'

/** Framework: 16+ moves on, 0–15 drops the project. Frozen. */
export const PRODUCT_GATE_THRESHOLD = 16

export interface ProductGateInput {
  ease: number
  hairFire: number
  exclusivity: number
}

export interface ProductGateResult {
  total: number
  passed: boolean
}

export function productGate(input: ProductGateInput): ProductGateResult {
  assertRange('ease', input.ease, 0, 10)
  assertRange('hairFire', input.hairFire, 0, 10)
  assertRange('exclusivity', input.exclusivity, 0, 10)

  const total = input.ease + input.hairFire + input.exclusivity
  return { total, passed: total >= PRODUCT_GATE_THRESHOLD }
}
```

Write `apps/api/src/scoring/narrative.ts`:

```ts
import { assertRange } from './ranges'

/**
 * Frozen sub-score maxima. Note hairFire is 0–6 HERE (inside Narrative) but
 * 0–10 in the Product gate — two distinct fields, neither derived from the other.
 */
export const NARRATIVE_MAX = {
  maturity: 7,
  smartMoney: 6,
  hairFire: 6,
  communication: 5,
  lineage: 4,
  mutation: 3,
} as const

export const NARRATIVE_TOTAL_MAX = 31

export type NarrativeInput = Record<keyof typeof NARRATIVE_MAX, number>

export function narrativeTotal(input: NarrativeInput): number {
  let total = 0
  for (const field of Object.keys(NARRATIVE_MAX) as (keyof typeof NARRATIVE_MAX)[]) {
    assertRange(field, input[field], 0, NARRATIVE_MAX[field])
    total += input[field]
  }
  return total
}
```

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && pnpm vitest run src/scoring`
Expected: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/scoring
git commit -m "feat: product gate and narrative scoring, frozen formulas

Ranges reject rather than clamp. Narrative sub-scores are fractional — the
framework's own ARB example scores Communication 4.5/5."
```

---

### Task 6: Scoring core — team weighting, accrual, discovery premium

The two formulas with real subtlety: the founder 5× weighting, and the multiplication chain whose zeros must be attributable.

**Files:**
- Create: `apps/api/src/scoring/team.ts`
- Create: `apps/api/src/scoring/accrual.ts`
- Test: `apps/api/src/scoring/team.test.ts`, `apps/api/src/scoring/accrual.test.ts`

**Interfaces:**
- Consumes: `assertRange`, `ScoreRangeError` from `./ranges` (Task 5).
- Produces:
  - `TeamMember = { name: string; isFounder: boolean; h: number; m: number; l: number }`
  - `memberScore(m: TeamMember): number`
  - `teamWeightedScore(members: TeamMember[]): number`
  - `AccrualInput = { segmentRevenueUsd, captureShare, accrualPct, annualIssuanceUsd }` (all `number`)
  - `AccrualResult = { grossAnnualFlowUsd: number; netAnnualFlowUsd: number; zeroFactor: 'segmentRevenueUsd' | 'captureShare' | 'accrualPct' | null }`
  - `annualHolderFlow(input: AccrualInput): AccrualResult`
  - `PremiumResult = { kind: 'MULTIPLE'; multiple: number } | { kind: 'PURE_PREMIUM' }`
  - `discoveryPremium(marketCapUsd: number, netAnnualFlowUsd: number): PremiumResult`

- [ ] **Step 1: Write the failing tests**

Write `apps/api/src/scoring/team.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { ScoreRangeError } from './ranges'
import { type TeamMember, memberScore, teamWeightedScore } from './team'

const member = (name: string, isFounder: boolean, h: number, m: number, l: number): TeamMember => ({
  name,
  isFounder,
  h,
  m,
  l,
})

describe('memberScore', () => {
  it('sums H + M + L to a max of 10', () => {
    expect(memberScore(member('a', false, 5, 3, 2))).toBe(10)
  })

  it('rejects H above 5, M above 3, L above 2', () => {
    expect(() => memberScore(member('a', false, 6, 0, 0))).toThrow(ScoreRangeError)
    expect(() => memberScore(member('a', false, 0, 4, 0))).toThrow(ScoreRangeError)
    expect(() => memberScore(member('a', false, 0, 0, 3))).toThrow(ScoreRangeError)
  })
})

describe('teamWeightedScore', () => {
  it("reproduces the framework's worked example: founder 8, others 7/5/6 -> 7.25", () => {
    const team = [
      member('founder', true, 5, 3, 0), // 8
      member('product', false, 4, 3, 0), // 7
      member('marketing', false, 4, 1, 0), // 5
      member('advisor', false, 4, 2, 0), // 6
    ]
    // (8*5 + 7 + 5 + 6) / (5 + 3) = 58 / 8
    expect(teamWeightedScore(team)).toBe(7.25)
  })

  it('weights the founder 5x — swapping founder and a peer changes the result', () => {
    const founderStrong = [
      member('f', true, 5, 3, 2), // 10
      member('a', false, 0, 0, 0),
      member('b', false, 0, 0, 0),
    ]
    const founderWeak = [
      member('f', true, 0, 0, 0),
      member('a', false, 5, 3, 2), // 10
      member('b', false, 0, 0, 0),
    ]
    expect(teamWeightedScore(founderStrong)).toBeCloseTo(50 / 7)
    expect(teamWeightedScore(founderWeak)).toBeCloseTo(10 / 7)
  })

  it('requires exactly one founder', () => {
    expect(() =>
      teamWeightedScore([
        member('f1', true, 1, 1, 1),
        member('f2', true, 1, 1, 1),
        member('c', false, 1, 1, 1),
      ]),
    ).toThrow(/exactly one founder/i)

    expect(() =>
      teamWeightedScore([
        member('a', false, 1, 1, 1),
        member('b', false, 1, 1, 1),
        member('c', false, 1, 1, 1),
      ]),
    ).toThrow(/exactly one founder/i)
  })

  it('requires 3 to 5 people', () => {
    expect(() =>
      teamWeightedScore([member('f', true, 1, 1, 1), member('a', false, 1, 1, 1)]),
    ).toThrow(/3 to 5/i)
  })
})
```

Write `apps/api/src/scoring/accrual.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { annualHolderFlow, discoveryPremium } from './accrual'

describe('annualHolderFlow', () => {
  it('multiplies the chain then subtracts issuance', () => {
    const r = annualHolderFlow({
      segmentRevenueUsd: 1_000_000_000,
      captureShare: 0.02,
      accrualPct: 0.5,
      annualIssuanceUsd: 4_000_000,
    })
    expect(r.grossAnnualFlowUsd).toBe(10_000_000)
    expect(r.netAnnualFlowUsd).toBe(6_000_000)
    expect(r.zeroFactor).toBeNull()
  })

  it("reports the framework's losing case: earns 10M, issues 50M", () => {
    const r = annualHolderFlow({
      segmentRevenueUsd: 100_000_000,
      captureShare: 1,
      accrualPct: 0.1,
      annualIssuanceUsd: 50_000_000,
    })
    expect(r.netAnnualFlowUsd).toBe(-40_000_000)
  })

  it('names which multiplicand was zero rather than returning a bare 0', () => {
    expect(
      annualHolderFlow({
        segmentRevenueUsd: 1_000_000,
        captureShare: 0.1,
        accrualPct: 0,
        annualIssuanceUsd: 0,
      }).zeroFactor,
    ).toBe('accrualPct')

    expect(
      annualHolderFlow({
        segmentRevenueUsd: 0,
        captureShare: 0.1,
        accrualPct: 0.1,
        annualIssuanceUsd: 0,
      }).zeroFactor,
    ).toBe('segmentRevenueUsd')
  })
})

describe('discoveryPremium', () => {
  it('returns the multiple when net flow is positive', () => {
    const r = discoveryPremium(50_000_000, 10_000_000)
    expect(r).toEqual({ kind: 'MULTIPLE', multiple: 5 })
  })

  it('returns PURE_PREMIUM when nothing is forced to holders', () => {
    expect(discoveryPremium(50_000_000, 0).kind).toBe('PURE_PREMIUM')
    expect(discoveryPremium(50_000_000, -1).kind).toBe('PURE_PREMIUM')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && pnpm vitest run src/scoring/team.test.ts src/scoring/accrual.test.ts`
Expected: FAIL — cannot resolve `./team`, `./accrual`.

- [ ] **Step 3: Implement**

Write `apps/api/src/scoring/team.ts`:

```ts
import { assertRange } from './ranges'

export interface TeamMember {
  name: string
  isFounder: boolean
  h: number
  m: number
  l: number
}

/** H (0–5) + M (0–3) + L (0–2), max 10. Frozen. */
export function memberScore(member: TeamMember): number {
  assertRange('h', member.h, 0, 5)
  assertRange('m', member.m, 0, 3)
  assertRange('l', member.l, 0, 2)
  return member.h + member.m + member.l
}

/**
 * (founder x 5 + sum of others) / (5 + count of others). Frozen.
 * The founder counts as five scores; everyone else counts as one.
 */
export function teamWeightedScore(members: TeamMember[]): number {
  if (members.length < 3 || members.length > 5) {
    throw new Error(`team must have 3 to 5 people, got ${members.length}`)
  }

  const founders = members.filter((x) => x.isFounder)
  if (founders.length !== 1) {
    throw new Error(`team must have exactly one founder, got ${founders.length}`)
  }

  const founderScore = memberScore(founders[0])
  const others = members.filter((x) => !x.isFounder).map(memberScore)
  const sumOthers = others.reduce((a, b) => a + b, 0)

  return (founderScore * 5 + sumOthers) / (5 + others.length)
}
```

Write `apps/api/src/scoring/accrual.ts`:

```ts
export interface AccrualInput {
  segmentRevenueUsd: number
  captureShare: number
  accrualPct: number
  annualIssuanceUsd: number
}

export interface AccrualResult {
  grossAnnualFlowUsd: number
  netAnnualFlowUsd: number
  /**
   * The framework: "These steps multiply. One zero anywhere zeroes the product."
   * A bare 0 hides which step failed, so name it.
   */
  zeroFactor: 'segmentRevenueUsd' | 'captureShare' | 'accrualPct' | null
}

export function annualHolderFlow(input: AccrualInput): AccrualResult {
  const factors = ['segmentRevenueUsd', 'captureShare', 'accrualPct'] as const
  const zeroFactor = factors.find((f) => input[f] === 0) ?? null

  const grossAnnualFlowUsd = input.segmentRevenueUsd * input.captureShare * input.accrualPct

  return {
    grossAnnualFlowUsd,
    netAnnualFlowUsd: grossAnnualFlowUsd - input.annualIssuanceUsd,
    zeroFactor,
  }
}

export type PremiumResult = { kind: 'MULTIPLE'; multiple: number } | { kind: 'PURE_PREMIUM' }

/**
 * The framework: a token with zero forced flow at any price is "100% premium,
 * pure narrative, tradable but never ownable."
 */
export function discoveryPremium(marketCapUsd: number, netAnnualFlowUsd: number): PremiumResult {
  if (netAnnualFlowUsd <= 0) return { kind: 'PURE_PREMIUM' }
  return { kind: 'MULTIPLE', multiple: marketCapUsd / netAnnualFlowUsd }
}
```

- [ ] **Step 4: Run the full suite**

Run: `cd apps/api && pnpm test`
Expected: PASS — all scoring tests green. (There are no db tests: Tasks 5-6 run in a bare
typescript + vitest package, and Task 4's SQLite schema is DISCARDED.)

- [ ] **Step 5: Typecheck and check**

Run: `cd apps/api && pnpm typecheck && pnpm check`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/scoring
git commit -m "feat: team weighting and value-accrual scoring, frozen formulas

Founder counts as five scores. The accrual chain names which multiplicand was
zero instead of returning a bare zero, per the framework's multiplication rule."
```

---

## Done when

- `python -m pytest -q` passes and collects only `tests/research`.
- `cd apps/api && pnpm test && pnpm typecheck && pnpm check` all pass against the bare scoring package.
- Both `apps/api/src/scoring/` modules import nothing from the rest of the app, and `apps/web` cannot reach them.
- Both framework worked examples are pinned by tests: team → 7.25, ARB narrative → 26.5.

**Next, in the settled build order** (1 archive [DONE] · 2 frozen scoring core = Tasks 5 & 6 above): **3** schema + migrations + the immutability trigger → **4** the minimal editor → **5** the citation verifier → **6** the commit gate + ledger view → **7** bench three models on one real coin → **8** wire the EvidenceFinder. The **viem chain layer is Phase A.2**, after report #1 — it is not pulled forward, and the editor is not skipped.
