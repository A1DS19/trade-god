# Coin Research Platform — Design (Phase A)

**Date:** 2026-09-21 (revised the same day — see Revision history)
**Status:** Approved. Approach B "Instrument", Phase A coins-first, loopback-only. Stack re-decided
2026-09-21: pnpm workspace, Hono + Drizzle + PostgreSQL 16 API, TanStack Start web, Node 26 —
replacing the Electron + better-sqlite3 plan written earlier the same day.

## Revision history

**2026-09-21, pivot #1 — trading → research.** The pre-registered OOS run came back negative and
AWS closed the account holding the Lightsail box, destroying the paper telemetry. The quantitative
era ended. This document was written to specify a local **Electron + better-sqlite3** desktop app
implementing the CoinPicks framework, with the LLM demoted to a drafter writing into `*_draft`
columns.

**2026-09-21, pivot #2 — desktop app → local web stack.** Electron and better-sqlite3 are replaced
by a pnpm workspace: a Hono + Drizzle + Postgres API and a TanStack Start web app, both loopback
only. The LLM is demoted a second time — from a drafter that proposes numbers into `*_draft`
columns to an **EvidenceFinder** that proposes only citations, every one of which runs through the
deterministic verifier before a human ever sees it. Every `*_draft` column pair is deleted.

**Unchanged by both pivots:** the frozen formulas, the method (§2), the citation verifier (§7), the
vendor-provenance rule (§6), and the ledger (§10). Those are the document; the rest is plumbing.

## Context

trade-god's quantitative era is over. The pre-registered OOS run
(`research/signals/intraday/output/2b/oos_results.csv`) measured the surviving strategy at
**−15.19% return, profit factor 0.986, Sharpe −0.29 across 2,791 trades** at baseline costs
(−25.2% under stress). Training-set profit factor was 1.021. Five of six intraday families were
rejected outright; the survivor was negative out-of-sample. The 66-day paper run that looked
positive was ~1.8 months drawn from a distribution with ~6% monthly volatility, evaluated at three
sequential check-ins — and its entire gain sat in ~10 of 312 trades. The AWS account closure that
destroyed the paper telemetry is the occasion for this pivot, not its cause.

What survives and has value: the `research/` parquet warehouse (6M+ rows, point-in-time), and the
discipline that produced an honest rejection — pre-registration, sealed OOS, cost stress.

This project points that discipline at a different method: the CoinPicks fundamental research
framework. The framework's own materials are in `~/Downloads/Altcoin-Trading-System-STANDARD-2026-08-07/`
(`Research/framework/00`–`06`, `doctrine/research/`), transcribed from the Skool classroom.

Those seven lessons (`00-how-we-think`, `01-core-strategy`, `02-product-exclusivity`,
`03-liquidity-analysis`, `04-narrative-scoring`, `05-team-credibility`,
`06-one-page-report-template`) are **vendored into `framework/`** as of 2026-09-21, so the frozen
formulas have checked-in provenance that survives a Downloads clean. They are evidence, not code:
never edit them, and when an implementation disagrees with a lesson the implementation is wrong.

**The gap this fills.** The framework's "AI tool" is a prompt you paste into Claude Code with PDFs
attached. It asks the model to extract weights, validate that Quality is 0–1 ("if a value is >1 it
was typed on a 0–10 scale by mistake → divide it by 10"), check that exactly five windows exist,
range-check `|Signal| ≤ 10`, then compute weighted averages. That is arithmetic and schema
validation delegated to a language model, with a human trusting output they cannot verify. It also
demands every claim carry a Ctrl+F-able source quote — which an LLM will fabricate fluently, a risk
the framework acknowledges with its "No AI-only reports" rule but does not enforce.

This tool makes the deterministic parts deterministic and the verification mechanical.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Approach | B — "Instrument": deterministic core, LLM demoted to evidence finder, verification enforced in code |
| Phase A scope | Coin research pipeline. **A.1** = frozen scoring, editor, verifier, commit gate, ledger. **A.2** = the viem chain layer (§5) |
| Workspace | pnpm 10.33.0, `packages: ["apps/*"]`, Biome 2.5.14 |
| Runtime | Node **v26.8.1**. It executes a `.ts` file directly — no flag, no loader — which is why there is no build step and no Bun |
| API | `apps/api` — hono 4.13.8, @hono/zod-validator 0.9.1, zod 4.6.5, on port **8789** (8787 is held by an unrelated container on this machine; overridable via `PORT`) |
| Web | `apps/web` — @tanstack/react-start 1.168.57 on @tanstack/react-router 1.170.38, react/react-dom 19.3.0, vite 8.3.0, tailwindcss + @tailwindcss/vite 4.3.3, on port **5173** |
| Storage | PostgreSQL 16 (`postgres:16-alpine`), one docker compose service, bound `127.0.0.1:5433` |
| ORM / DDL | drizzle-orm 0.45.3 + drizzle-kit 0.31.11 (dev) over pg 8.23.0 via `drizzle-orm/node-postgres`. **Drizzle is the only DDL author** |
| Chain reads | viem 2.56.8 (Multicall3 built in) — Ethereum, Base, Arbitrum. Phase A.2, same Node process |
| LLM | openai 7.20.0 against one OpenAI-compatible endpoint. **EvidenceFinder only** — it proposes citations, never numbers (§8) |
| Deliberate version pins | `typescript 5.9.3` (latest is 7.0.2) and `vitest 4.1.11` (latest is 5.0.1), as catalog pins in `pnpm-workspace.yaml` |
| Deployment | Loopback only, one user, no auth, no host (§3.4) |
| Forward returns | Python `research/forward_returns.py` (psycopg 3.2.13) will write `forward_returns` and nothing else, enforced by a GRANT (§3.3). **Not written yet** — build-order step 6 |

**On the two pins**, which are a deliberate deviation from this repo's standing "always latest"
rule and are recorded as such: TypeScript 7.0.2 is the fresh Go-native compiler major and vitest
5.0.1 is days old, while `hc<AppType>` (Hono's RPC client) plus Drizzle's `$inferSelect` are two of
the heaviest type-level workloads in the ecosystem. The sibling repo's decisions log records that
unpinned TypeScript across workspaces is exactly what produces Hono's *"Type instantiation is
excessively deep and possibly infinite"* across an RPC boundary. Revisit the week after report #1
commits.

**Rejected:**

| Rejected | Why it lost |
|---|---|
| Electron + electron-vite | Its whole value was a local process with disk, network and an inherited Claude Code subscription. The CLI drafter is dropped (§13), so the subscription seam is gone; what is left is a shell around a web app that a browser already gives us. Note what Electron was silently providing: its single-instance lock made concurrent edits impossible for free, which is why `reports.version` compare-and-swap is now explicit (§4, rule 4). |
| `better-sqlite3` | No `pgEnum`, no `timestamptz`, no `jsonb`. The ledger join is a date join between two languages against one store; a real server is the simpler seam, and the immutability trigger (§4, rule 2) is the load-bearing constraint of this whole design. |
| Python / FastAPI backend | The frozen formulas must have exactly one implementation, and it must be the one the browser's types are derived from. A Python backend either duplicates them or makes the UI call out for arithmetic. viem also beats web3.py + multicall.py for chain reads. |
| TanStack Start server functions as the backend | Server functions are fine for the UI's own loading, but they are not a **boundary**: anything inside the web app's build graph can `import { narrativeTotal }`. A separate `apps/api` with an `exports` map makes "one copy of the formulas" a module-resolution error rather than a code-review habit. It also keeps migration-at-boot and the Python GRANT in one place. |
| Bun | Verified that Node v26.8.1 runs `.ts` directly with no flag and no loader. The sibling repo needs Bun only because one of its workspace packages publishes raw `.ts` with no build; this repo has no such package. A second runtime that buys nothing is a cost. |
| Tauri | Moot with Electron gone, but recorded: `klickbrain/desktop/docs/PROJECT.md:551` planned Tauri and shipped Electron at v0.8.3 — a decision validated by execution. |
| Hosted web app | Unchanged from pivot #1, for changed reasons (§3.4). |
| Watcher / alerting service | Out of scope; deliberately not scaffolded for (§12). |

**Not built, and named so nobody adds them by reflex:** shadcn or any component library, Better
Auth, Redis, S3, BullMQ, a git-hook gate, jscpd, fallow. Those belong to a deployed product with
customers. This has one user on loopback.

## Normative formulas (frozen)

**The formulas below are the rules, taken verbatim from the CoinPicks lessons. They are
authoritative and frozen.** The implementation reproduces them exactly. Weights, ranges, gates, and
thresholds are not tunable, not "improvable", and not to be adjusted because an alternative looks
better calibrated. If a formula appears wrong, that is raised with the user as a finding — it is
never silently changed in code.

This rule exists because the entire point of this tool is to *test* the framework honestly. A
modified formula tests a different framework, and the ledger's answer would be about something
nobody uses.

### Phase A — per-coin

| Quantity | Formula | Source lesson |
|---|---|---|
| Product gate | `ease(0–10) + hairfire(0–10) + exclusivity(0–10)`; **≥16 pass, 0–15 drop** | `md=fb82f6eb039d4e76bad5fda7171d17ef` |
| Narrative total | `maturity(0–7) + smart_money(0–6) + hairfire(0–6) + communication(0–5) + lineage(0–4) + mutation(0–3)` = **/31** | `md=00651b71cac24c7380957b4f7f7016e5` |
| Individual team score | `H(0–5) + M(0–3) + L(0–2)` = **/10** | `md=0e32e8d435954e15988a4880aa42b9dc` |
| Team weighted score | `(founder × 5 + Σ others) ÷ (5 + count(others))` | same |
| Gross annual holder flow | `segment_revenue_usd × capture_share × accrual_pct` | `00-how-we-think.md` §1 |
| Net annual holder flow | `gross − annual_issuance_usd` | same |
| Discovery premium | `market_cap ÷ net_annual_flow` | `00-how-we-think.md` §5 |
| Liquidity tier | **No formula.** ±2% depth + largest pool TVL → human assigns Low/Med/High | `md=d46fdc6a21a14a8399d2afb4491eebe3` |

Team worked example, used as a test fixture: founder 8, others 7/5/6 →
`(8×5 + 7+5+6) ÷ (5+3) = 58 ÷ 8 = 7.25`.

Multiplication rule (`00-how-we-think.md` §1): *"These steps multiply. One zero anywhere zeroes the
product."* Implementations return the offending multiplicand, not a bare zero.

### Phase B — pillar / market direction (recorded now, built later)

```
Signal = ( (P − 50) ÷ 50 ) × Quality × Impact
```

| Input | Range | Rule |
|---|---|---|
| `P` | 0–100 | Probability this pillar is **good for crypto by that window** — *not* "this event definitely happens by then." >50 bull, <50 bear, 50 coin-flip. |
| `Quality` | 0.5–1.0 | Strength of evidence. *"Quality changes how hard you lean — never which way."* Floor of 0.5 means worst evidence halves a signal, never flips it. |
| `Impact` | 1–10 | Market-moving power of the subject, set at subject selection. |

Output range is ±10. Windows are **exactly five and locked**: 1 month, 3 months, 6 months, 1 year,
3 years. Pillar weights are "% of my thesis" and sum to 100% across pillars; the per-window market
call is the weight-weighted aggregate of pillar signals.

Worked example, used as a test fixture (CLARITY Act, 6-month window): `P=62, Quality=0.85,
Impact=9` → `(62−50) ÷ 50 = 0.24` → `0.24 × 0.85 × 9 = +1.8` → **Bull**.

Validation rules the framework's own prompt asks a language model to remember, and which this
implementation enforces as schema constraints instead:

- `Quality` must be 0–1. A value >1 was typed on a 0–10 scale — reject it; do not silently divide.
- `Impact` must be 0–10.
- Exactly the five locked windows must be present; reject off-grid windows (2-year, 5-year).
- `|Signal|` ≤ 10 — anything larger is impossible under the formula and indicates bad input.
- Use the committed value, never the AI draft, whenever both exist.

Source: `md=399abaebc4b54f769d4e26dde6b92bd5` (Build Your Pillar Reports) and
`md=814a7190f2b941f1ad2946da0b9a5a5e` (Combining Pillar Reports Into a Working Theory). All lesson
URLs are under `https://www.skool.com/coinpicksgenesis/classroom/eed2ad74?`.

## 1. What Phase A produces

One deliverable per researched coin: a **committed, immutable, point-in-time report** carrying

- a Product gate result (pass/fail),
- a Liquidity tier grounded in on-chain reserves,
- a Narrative score `/31`,
- a Team weighted score `/10`,
- a value-accrual computation with the contract address that makes it true (or the finding that
  none exists),
- every non-trivial claim backed by a citation whose quote has been **mechanically confirmed to
  appear at that URL**.

And, accumulating across reports: a ledger that will eventually answer whether any of these scores
predict anything.

## 2. The method, as implemented

Faithful to `Research/framework/`. Ranges are enforced, not clamped.

### 2.1 Product gate (`02-product-exclusivity.md`)

| Input | Range |
|---|---|
| Ease of Use | 0–10 |
| Hair-on-Fire | 0–10 |
| Exclusivity Factor | 0–10 |

`total = ease + hairfire + exclusivity`; **`total >= 16` passes, 0–15 drops the project.**
A failed gate ends the report — later sections stay locked.

Note: Hair-on-Fire is scored 0–10 here but **0–6 in the final report, inside the Narrative
section**. Two distinct fields; the report field is not derived from the gate field.

### 2.2 Liquidity (`03-liquidity-analysis.md`)

Tier is `Low | Medium | High`, assigned by the human from two measured inputs: **±2% depth across
CEXs** (CoinGecko markets) and **largest DEX pool TVL** (measured on-chain, §5). The framework is
explicit that there is no formula — "make your best guess between low, medium, or high risk."
The tool measures; the human tiers.

### 2.3 Narrative (`04-narrative-scoring.md`) — `/31`

| Sub-score | Max |
|---|---|
| Narrative Maturity | 7 |
| Smart Money Compatibility | 6 |
| Hair-on-Fire Innovation | 6 |
| Narrative Communication | 5 |
| Narrative Lineage | 4 |
| Narrative Mutation | 3 |

Every sub-score requires a 1–2 sentence rationale **and** at least one verified citation.

### 2.4 Team (`05-team-credibility.md`) — `/10`

Per person: `H (0–5) + M (0–3) + L (0–2) = /10`. Then:

```
weighted = (founder_score * 5 + sum(other_scores)) / (5 + count(others))
```

Constraints enforced by the tool: exactly one founder; 3–5 people total; each person's summary is
**one sentence about prior experience, never the current project**; each carries at least one
financial metric from a prior role.

### 2.5 Value accrual (`00-how-we-think.md`)

```
gross_annual_flow = segment_revenue_usd * capture_share * accrual_pct
net_annual_flow   = gross_annual_flow - annual_issuance_usd
```

The framework states "these steps multiply — one zero anywhere zeroes the product." The
implementation therefore **reports which multiplicand was zero** rather than returning a bare 0.

`discovery_premium = market_cap / net_annual_flow`. The verdict it carries is three-way, not two:
`MULTIPLE` when net flow is positive; `ISSUANCE_NEGATIVE` when a real mechanism exists and issuance
eats it (gross > 0, net <= 0); and `PURE_PREMIUM` only when gross is zero — the framework reserves
"100% premium, pure narrative, tradable but never ownable" for a token with *zero forced flow*, and
a token earning $10M while issuing $50M is a different finding from one with no mechanism at all.

Two rulings govern this module, both dated 2026-09-21 and both recorded under *Findings raised, not
changed*: `capture_share` and `accrual_pct` are fractions in `[0, 1]` and the domain is enforced;
and the reserve/collateral branch is out of scope for A.1, so this figure is captioned as
**cash-flow accrual**, never as total holder value.

## 3. Architecture

### 3.1 The archive (done)

The trading era has been moved, not deleted. Executed in the working tree on 2026-09-21:

- `app/intraday/strategy.py` → `research/signals/intraday/strategy_core.py` — the one module
  `research/` actually needs.
- `tests/intraday/test_strategy_core.py` → `tests/research/test_strategy_core.py`, repointed at
  `research.signals.intraday.strategy_core`, so the surviving module keeps its coverage.
- `app/{intraday,api,db,config.py,__init__.py}` → `legacy/app/`.
- `alembic/`, `alembic.ini`, `api_main.py`, `intraday_main.py`, `docker-compose.yml`, `Dockerfile`
  → `legacy/`.
- `tests/{intraday,api}/` → `legacy/tests/`.
- `research/v2_eval/` → `legacy/research/v2_eval/`. It was **already broken**: `run.py:53-64` imports
  `app.swing.backtest_replay`, and `app/swing/` was archived on 2026-07-16. Nothing tested it, so
  the suite stayed green over a dead module for two months.
- `docs/{intraday_operations,testing}.md` → `legacy/docs/`, leaving `docs/` holding only
  `superpowers/{plans,specs}/`.
- Deleted: `swing-logs.txt`, `bot.log`, and 24 tracked `charts_out/` PNGs.
- `research/signals/intraday/{mr_vwap_strategy.py:18, families.py:45}` repointed to `strategy_core`.

Test suite after the move: **111 passed** (was 182, of which 108 were already `tests/research`).

Correction to carry: `alembic/versions/` held **six** migrations (001–006), not the five the old
`CLAUDE.md` claimed. Alembic is now archived; it stops being this repo's migration tool (§3.2).

### 3.2 The tree

```
trade-god/
├── apps/
│   ├── api/                       # NEW — Hono on Node 26, port 8789. The only writer.
│   │   ├── src/
│   │   │   ├── app.ts              # the package's single export
│   │   │   ├── server.ts           # applies migrations, THEN takes the port
│   │   │   ├── scoring/            # ranges.ts product.ts narrative.ts team.ts accrual.ts — frozen
│   │   │   ├── db/schema.ts        # every column; the only DDL author
│   │   │   ├── routes/             # coins, reports, citations, commit
│   │   │   ├── verify/             # the citation verifier (§7)
│   │   │   ├── sources/            # vendor adapters (§6)
│   │   │   ├── evidence/           # providers.ts, model.ts, the EvidenceFinder (§8)
│   │   │   └── chain/              # viem — Phase A.2 (§5)
│   │   ├── drizzle/                # generated .sql + meta/_journal.json — both committed
│   │   ├── scripts/rescore.ts      # re-derives a stored score from the authoritative TypeScript
│   │   └── package.json            # exports "." -> "./src/app.ts"
│   └── web/                        # NEW — TanStack Start, port 5173, proxies /api
├── research/                       # EXISTING — Python warehouse, unchanged
│   ├── signals/intraday/strategy_core.py   # the one module that survived the archive
│   └── forward_returns.py          # TO BE WRITTEN (step 6) — psycopg, forward_returns only
├── framework/                      # vendored CoinPicks lessons 00–06 — evidence, never edit
├── legacy/                         # the trading era, archived 2026-09-21 (§3.1)
├── tests/research/                 # Python tests — 111 passing
├── docker-compose.yml              # NEW — one service: postgres:16-alpine (the old one is in legacy/)
├── pnpm-workspace.yaml             # packages: ["apps/*"] + the catalog pins
└── docs/superpowers/{plans,specs}/  # all docs/ holds now — the ops runbooks moved to legacy/docs/
```

### 3.3 Four boundaries, each enforced by a mechanism rather than by discipline

**1. The module resolver keeps one copy of the formulas.** `apps/api/package.json` declares
`exports "." -> "./src/app.ts"`, so `apps/web` cannot `import { narrativeTotal }` — the resolver
refuses. The frozen functions live in `apps/api/src/scoring/{ranges,product,narrative,team,accrual}.ts`,
are pure, and import nothing from the rest of the app. They are evaluated at **exactly one moment**:
inside `POST /reports/:id/commit`, in the same transaction that writes `report_scores` and flips
`reports.status`. Every downstream consumer — the UI, the ledger, Python — reads the stored number.

Two rules that belong to the formulas themselves: ranges are **rejected, never clamped**; and
rubric sub-scores are **whole numbers** (ruled 2026-09-21). The decimal example this document
previously cited — ARB, Communication 4.5/5 — appears in none of the seven vendored lessons; it
originated in the implementation plan. See "Findings raised, not changed".

**2. Drizzle alone authors DDL.** `apps/api/src/db/schema.ts` declares every column; `drizzle-kit
generate` writes plain `.sql` under `apps/api/drizzle/` plus `meta/_journal.json`; both are
committed; `server.ts` applies them at boot **before** the port is taken. Alembic stops being this
repo's migration tool. Two DDL authors against one database is exactly the silent drift this repo's
standing lesson is about.

**3. One process touches the network and the database.** Everything — chain reads, vendor fetches,
the citation verifier, the model calls — lives in `apps/api`. `apps/web` is UI over a typed RPC
surface: no third-party `fetch` from the browser, no keys in the browser. This is the Electron
main/renderer split re-expressed as two processes instead of two contexts, and it is the reason the
split survived the stack change.

**4. Python's boundary is a GRANT, not a convention.** A `research` role with `SELECT` on
`coins`, `reports`, `report_scores`, `report_team`, `citations` and `INSERT, UPDATE` on
`forward_returns`. Nothing else. Python owns no table's shape.

### 3.4 Python's role

`research/` is unchanged and stays. It is the point-in-time parquet warehouse and the only thing
the trading era left that was worth keeping.

`research/forward_returns.py` does not exist yet — it is build-order step 6. When written it uses psycopg 3.2.13 (verified importable on this machine's system
Python 3.14.7). It selects committed reports, computes 30 / 90 / 180 / 365-day returns from the
warehouse, and writes `INSERT ... ON CONFLICT (report_id, horizon_days) DO UPDATE`.

**Python never recomputes a score.** Auditing a committed number means reading the stored row;
re-deriving one means running the authoritative TypeScript via `node apps/api/scripts/rescore.ts`.
A second implementation of a frozen formula is a second framework.

### 3.5 Deployment and the daily run

Loopback only, one user, no auth. This is **re-decided, not inherited** — the old reason ("so
drafting can use the Claude Code subscription") died with the CLI drafter. The reasons that survive
it:

- the ledger's integrity depends on a single writer;
- there is no `user_id` in any of the seven tables, and adding one later is a schema change, not a
  feature;
- the citation verifier fetches arbitrary third-party URLs on request, and a loopback-only service
  has no egress surface to abuse.

```bash
docker compose up -d db     # postgres:16-alpine on 127.0.0.1:5433
pnpm dev                    # api on 8789, web on 5173 proxying /api
```

## 4. Data model (PostgreSQL 16)

### 4.1 The database

One docker compose service, `postgres:16-alpine`, bound **`127.0.0.1:5433:5432`** — not 5432, which
is already held by an unrelated container (`medi-pal-db-1`, postgres:17.2) on this machine. A
**fresh** named volume `coinpicks_data`; never reuse `trade-god_postgres_data`, which still holds
the dead trading database and an `alembic_version` row at revision 006.

```
DATABASE_URL=postgresql://coinpicks:coinpicks@localhost:5433/coinpicks
```

### 4.2 The seven tables

Append-only where it matters. A committed report is never edited — and after rule 2 below, that
sentence is true against a stray `psql` session, a GUI client, or an agent with shell access, not
just against the application.

| Table | Key columns |
|---|---|
| `coins` | `id`, `symbol`, `name`, `coingecko_id`, `chain`, `contract_address`, `address_sources jsonb` (≥2 required), `created_at timestamptz` |
| `reports` | `id`, `coin_id`, `version integer NOT NULL`, `status report_status`, `created_at timestamptz`, `committed_at timestamptz` |
| `report_scores` | one row per report; one column per score, **no `*_draft` pair**; `scoring_version text NOT NULL` |
| `report_team` | `report_id`, `position`, `name`, `role`, `is_founder`, `h`, `m`, `l`, `summary` |
| `citations` | `id`, `report_id`, `field`, `url`, `quote`, `status citation_status`, `origin citation_origin`, `finder_provider`, `finder_model`, `selected_at timestamptz NULL`, `verified_at timestamptz`, `http_status`, `matched_offset`, `waiver_reason` |
| `chain_facts` | `id`, `coin_id`, `report_id?`, `kind`, `chain`, `block_number`, `fetched_at timestamptz`, `payload jsonb` |
| `forward_returns` | `report_id`, `horizon_days`, `return_pct`, `computed_at timestamptz`; PK `(report_id, horizon_days)` |

Every `chain_facts` row carries `block_number` and `fetched_at` — the framework's §8 rule that every
number is either verified (say where) or a guess (say so).

### 4.3 Five schema rules that are not negotiable

**1. `pgEnum`, never `text().$type<>()`.** `reports.status ∈ {draft, committed}` and
`citations.status ∈ {unverified, verified, near_miss, failed, unverifiable_js, waived}` are
database enums. `$type<T>()` is a TypeScript fiction — it constrains the ORM's inference and
nothing in the database. `citations.origin ∈ {human, model}` is an enum for the same reason.

**2. Immutability triggers** on `reports`, `report_scores`, `report_team` and `citations`,
raising when the parent report's `status = 'committed'`. The children fire on `INSERT OR
UPDATE OR DELETE`; statement-level `BEFORE TRUNCATE` triggers cover those four and
`forward_returns`; every trigger is `ENABLE ALWAYS`; and a child's `report_id` is immutable
unconditionally. Amended 2026-09-21 — the literal earlier wording left INSERT, TRUNCATE,
replica mode and re-parenting open, all four reproduced live on PostgreSQL 16.13. Drizzle's DSL cannot express a
trigger: this needs `drizzle-kit generate --custom` and a hand-written `.sql` that `schema.ts` never
re-emits. It is the one piece of SQL that makes "a committed report is never edited" true rather
than merely intended. **Write it on day 2 or it never gets written.**

**3. `report_scores.scoring_version`**, written by the commit route from a constant in
`scoring/ranges.ts`. The ledger's fatal failure mode is silently comparing rows scored under two
framework versions and calling the difference signal.

**4. `reports.version integer NOT NULL`, with compare-and-swap writes.** Every draft mutation is
`UPDATE ... WHERE id = $1 AND version = $2`, returning 409 on zero rows. Two browser tabs on one
draft would otherwise be silent last-write-wins — a hole Electron's single-instance lock used to
cover for free. `version` is the concurrency token, not a report revision number: re-researching a
coin creates a **new `reports` row**, because a committed report is immutable.

**5. `timestamptz` for every timestamp, `jsonb` for `coins.address_sources` and
`chain_facts.payload`.** The archived `app/db/models.py` stored every timestamp as `String(50)`.
The ledger join is a date join. Do not inherit that habit.

## 5. Chain layer (`apps/api/src/chain/`, viem) — **Phase A.2**

Same Node process as the API, no sidecar, no separate service. Deferred to A.2 because a report can
be researched, cited, scored and committed without it; the chain layer deepens the evidence, it does
not gate the pipeline.

| Module | Produces |
|---|---|
| `pools.ts` | Pool census: enumerate pools, read reserves on-chain via Multicall3, compute per-pool price, **drop pools whose price deviates more than 5% from the TVL-weighted median** (the framework's poison-pair trap), sum surviving depth, compute price impact for a stated position size in and out |
| `safety.ts` | Source verified?, proxy + upgrade admin, mint authority, owner / pause / blacklist selectors, deployer address, contract age |
| `issuance.ts` | Circulating vs total from chain, vesting contract balances, upcoming cliffs |
| `holders.ts` | Top-N holders, share held by top 10, exchange vs non-exchange, deployer still holding |
| `accrual.ts` | **Locate the contract that moves value to holders** (fee switch, burn address, revenue distributor, buyback wallet) and measure realised flow over the trailing 90 days |

`accrual.ts` is the highest-signal module. The framework's sharpest test — *"if this project's
business doubled tomorrow, one more dollar is forced to the token holder because ______"* — has an
on-chain answer or it has none. When no such contract is found, that is recorded as a **finding**,
not an absence of data.

Liquidity figures are re-pulled live at decision time and never read from a stored value: the
framework's error log records stored liquidity rotting 12× in two weeks.

## 6. Vendor adapters (`apps/api/src/sources/`)

CoinGecko (markets, ±2% depth, categories), GeckoTerminal (pool discovery), DeFiLlama (TVL, fees,
revenue, raises), Artemis (protocol revenue, P/S, DAU).

Every adapter returns `{ value, provenance }` where provenance carries `source`, `url`,
`fetched_at`, and a `verified | vendor_claim` label. Vendor numbers are never silently promoted to
verified facts. Responses cache to Postgres with a per-endpoint TTL.

**Team credibility has no usable API and stays manual** — the tool stores and verifies the
citations, it does not source them.

## 7. Citation verifier (`apps/api/src/verify/`) — the gate

1. Fetch the URL (real UA, timeout, same-host redirects followed).
2. Normalize both sides: unicode quotes, non-breaking spaces, soft hyphens, collapsed whitespace.
3. Assert the normalized quote is a substring of the normalized document.
4. On miss, compute the closest-matching span and return `near_miss` with it, so the human
   adjudicates rather than guesses.

PDFs are text-extracted. JS-rendered pages that yield no text return `unverifiable_js` — an honest
"cannot check," never a false negative.

**A report cannot reach `committed` while any selected citation is `unverified`, `near_miss`,
`failed`, or `unverifiable_js`.** The only escape is an explicit `waived` status with a recorded
`waiver_reason` — an absolute gate with no escape hatch gets routed around; a logged waiver stays
auditable. *Selected* is load-bearing: unselected model candidates (§8) are never a commit blocker
and never a commit credential.

Verification re-runs at commit time, not only at entry.

This is also the reason every model-proposed citation is verified **before it is displayed** (§8).
A candidate quote that does not appear at its URL should never reach a human's eyes with the
authority of having been offered.

## 8. The EvidenceFinder (`apps/api/src/evidence/`)

This replaces the drafting boundary of pivot #1 outright.

```ts
interface EvidenceFinder {
  find(claim: ClaimRequest): Promise<Array<{ url: string; quote: string; why: string }>>
}
```

The model proposes candidate `{url, quote, why}` for a claim the human has already written. Every
candidate runs through the deterministic verifier (§7) **before it is displayed**. It never proposes
a number. **Every `*_draft` / `*_draft_reason` column pair is deleted from `report_scores`. The
human types every score.**

### 8.1 The replacement containment guarantee, stated explicitly

Pivot #1's guarantee was *"the LLM writes only to `*_draft` columns, enforced by schema."* Those
columns are gone, so that guarantee is gone and needs a written replacement rather than an
assumption:

- **The model's reasoning has nowhere to persist.** The `citations` table has no column for the
  model's `why` prose. It is shown beside the candidate and dies with the request. Nothing a model
  wrote about *why* a number should be what it is can end up in a committed report.
- **A test asserts that no LLM-reachable code path writes to `report_scores`.** That table is
  written in exactly one place — the commit transaction (§3.3) — from values a human typed.
  `report_scores` also holds the operator's in-progress draft, because a half-finished report
  has to survive a browser reload; `product_passed IS NOT NULL` is the sentinel meaning the
  frozen gate has run, and every derived-value constraint keys off it. Amended 2026-09-21.

### 8.2 What `citations` gains

`origin ∈ {human, model}`, `finder_provider`, `finder_model`, and a nullable `selected_at`. A row
with `selected_at IS NULL` is an unselected candidate: offered, verified, not taken. The commit gate
counts only selected rows.

This also makes *"did the evidence finder actually help?"* answerable later, for free — selection
rate by provider and model, against a population of candidates that were all mechanically verified
first.

### 8.3 The provider seam

Lifted near-verbatim from the sibling repo's `/home/dev/projects/profe/apps/api/src/providers.ts`
(275 lines, **zero imports**) and its `model.ts` (313 lines), landing here as
`apps/api/src/evidence/{providers,model}.ts` — this repo has no `apps/api/src/providers.ts`. What
is lifted: a table of providers over one OpenAI-compatible client, strict `json_schema`, answers
re-parsed through the caller's own zod schema, a 90s timeout, and an `origin: "model" | "fixture"`
field so a keyless run can never be mistaken for a model draft.

The owner holds one funded DashScope international key serving 172 models across Qwen, Kimi,
DeepSeek and GLM — verified live on 2026-09-21, HTTP 200 against
`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.

`DEFAULT_PROVIDER` — the in-code constant in `apps/api/src/evidence/providers.ts`, which the
`COINPICKS_MODEL_PROVIDER` environment variable overrides at runtime — is deliberately **not pinned
yet**. The sibling repo's recorded blind bench put `qwen3.8-flash` last on 5/5 ballots (overall
2.0, against `deepseek-v4-flash` 4.6 and `kimi-k3` 4.4) with both Qwen tiers slowest. The default
gets decided by running one real coin section through `kimi-k3`, `deepseek-v4.1-flash` and
`qwen3.8-max` and recording the result (§14 step 7). Never pin
a default on price or on vibes.

### 8.4 Why the Claude Code CLI drafter is dropped

Its subscription auth from a spawned process **was verified to work** — the pivot-#1 open item is
*answered*, not mooted, and is recorded that way in §13. It is dropped anyway: a bare spawn inherits
the operator's global `CLAUDE.md`, skills and MCP config into the drafter's context (~27k
cache-creation tokens on a trivial prompt) and runs whatever model the operator's settings happen to
name. For a ledger whose entire purpose is testing whether a score predicts returns, a drafter that
changes when an unrelated config file is edited is an uncontrolled variable.

## 9. UI (`apps/web`, TanStack Start)

TanStack Start 1.168.57 on @tanstack/react-router 1.170.38, React 19.3.0, Vite 8.3.0, Tailwind 4.3.3
via `@tailwindcss/vite`. No component library: the whole UI is four views and one long form, and a
design system is a dependency to maintain, not a shortcut.

| View | Purpose |
|---|---|
| Coin list | Reports, status, grades, last verified |
| Report editor | Product gate → Liquidity → Narrative → Team → Accrual → Commit |
| Chain panel | Pool census table, safety flags, holder concentration, accrual contracts found (Phase A.2) |
| Ledger | Committed reports against forward returns; per-sub-score correlation once N is adequate |

**The editor is still the product.** What changed with the EvidenceFinder is what sits beside a
scored input: no longer a greyed number the model proposed, but *evidence* — candidate citations,
each already through the verifier, each with its status resolved before it is rendered. The input
itself is empty until a human types into it. That is the framework's "an empty My Decision box means
the work isn't done," and it is now literally true rather than approximately true.

**The Commit button is disabled and names exactly what blocks it** — empty decisions, unverified
selected citations, out-of-range values, a stale `version`.

React is warranted here specifically: per-field async verification state, a gate that must recompute
on every change, and a compare-and-swap write that can come back 409 while the user is typing.

Types cross the boundary through Hono's `hc<AppType>`, so a renamed column is a web-app type error
rather than a runtime surprise. That RPC client, together with Drizzle's `$inferSelect`, is why
TypeScript is pinned (see Decisions).

## 10. The ledger

Every commit snapshots the full report immutably with its timestamp. `research/forward_returns.py`
(step 6, not yet written)
runs offline against the existing parquet warehouse and writes `forward_returns` rows at the frozen
horizons — 30 / 90 / 180 / 365 days from commit date (§13) — through a role that can write nothing
else (§3.3).

This is the reason the project lives in this repo rather than a new one. The framework has never
been tested: nobody knows whether a 26.5/31 coin outperforms a 15/31 coin, or whether Smart Money
Compatibility predicts anything. With enough committed reports, that becomes a measurable question —
and the answer may be no, which is a result worth having.

**Standing caution, recorded deliberately:** this repo's history is four systems that produced a
confident number which turned out to be worthless. The scores this tool computes are unvalidated
until the ledger says otherwise. The UI must present them as judgments with evidence attached, never
as a verdict.

## 11. Testing

Following the repo's money-paths-first philosophy, here meaning **scoring and gating paths first**:

- Scoring core: exhaustive unit tests plus property tests asserting every range boundary rejects.
- Team weighting: the framework's worked example (`8,7,5,6 → 7.25`) as a fixture.
- Accrual: zero-multiplicand detection, `PURE_PREMIUM` verdict.
- Citation verifier: fixtures for exact match, whitespace variants, unicode quotes, PDF, JS-only
  page, 404, redirect, `near_miss`.
- Pool census: a recorded poison-pair fixture asserting the outlier pool is dropped (Phase A.2).
- Commit gate: every blocking condition individually asserted.
- Containment: a test asserting no LLM-reachable code path writes to `report_scores` (§8.1).

**The commit gate's end-to-end test gets a real Postgres or it does not run.** An in-memory store
has no transactions, no CHECK constraints and no triggers, so a green e2e against one proves nothing
about the two properties that matter here — the atomicity of the commit transaction and the
immutability of what it wrote.

## 12. Out of scope for Phase A

Pillar / market-direction / thesis pipeline (Phase B — the `Signal = ((P − 50) ÷ 50) × Quality ×
Impact` machinery over five locked windows). Solana. Any execution or order path. Wallet clustering
or entity resolution. Alerting, cron, or any deployed service. Nansen, Arkham, Token Terminal.

## 13. Open items

Exactly one item below is live.

| Item | State |
|---|---|
| Claude Code CLI subscription auth from a spawned process | **Answered: it works.** Verified from a spawned process. The CLI drafter was dropped anyway — a bare spawn inherits the operator's global `CLAUDE.md`, skills and MCP config (~27k cache-creation tokens on a trivial prompt) and runs whatever model the operator's settings name, which is an uncontrolled variable in a ledger (§8.4). Recorded as answered rather than deleted so the answer is not re-investigated. |
| Forward-return horizons | **Frozen at 30 / 90 / 180 / 365 days from commit date, as of 2026-09-21.** Retrofitting horizons onto existing commits is fine; comparing across changed horizons is not. |
| Paid vendor tiers | Start on free tiers (CoinGecko demo, GeckoTerminal, DeFiLlama, Artemis). Upgrade only when a rate limit actually bites. |
| Which model the EvidenceFinder defaults to | **OPEN — the live item.** `DEFAULT_PROVIDER` stays unpinned until one real coin section has run through `kimi-k3`, `deepseek-v4.1-flash` and `qwen3.8-max` and the result is written down (§14 step 7). |

## 14. Build order

1. **Archive** — done (§3.1).
2. **Frozen scoring core.** `apps/api/src/scoring/`, pure functions, full test suite. No database
   yet — the formulas are the thing this project exists to test, and they should be correct before
   anything can store their output.
3. **Schema, migrations, and the trigger.** `schema.ts`, `drizzle-kit generate`, then
   `generate --custom` for the immutability trigger. Day 2, per §4.3 rule 2.
4. **Minimal editor.** `apps/web`, one draft end to end.
5. **Citation verifier.**
6. **Commit gate + ledger view.**
7. **Bench the three models** on one real coin section; record the result; pin `DEFAULT_PROVIDER`.
8. **Wire the EvidenceFinder.**

Then **Phase A.2**: the viem chain layer (§5), in the same Node process.

**Honest sizing: 9–10 working days to report #1, chain layer excluded.**

Pending work that is not one of the eight steps:

- Vendor the seven framework lessons into `framework/` (Context), so the frozen formulas have
  checked-in provenance that survives a `~/Downloads` clean.
- Revisit the `typescript` and `vitest` catalog pins the week after report #1 commits (Decisions).

Working conventions for this repo: commits land on `main` directly — it is a personal repo and
branches are unnecessary here — and no AI attribution appears in a commit message or a PR
description, ever.

## Findings raised, not changed

The "Normative formulas (frozen)" section is reproduced above byte for byte. The following look
wrong or under-specified. **Nothing was changed.** They are recorded here for the user to rule on,
because a silently corrected formula tests a different framework and the ledger's answer would then
be about something nobody uses.

### RULED 2026-09-21 — was blocking, now answered

**`capture_share` and `accrual_pct` have unstated units.** `gross = segment_revenue_usd ×
capture_share × accrual_pct` is off by 100× depending on whether `accrual_pct` is a fraction
(`0.05`) or a percentage (`5`). The naming cuts both ways inside one expression — *share* reads as a
fraction, *pct* reads as a percent — and `framework/00-how-we-think.md:20-22` uses both words in
consecutive sentences: *"what **fraction** of that segment"* for capture, *"what **percentage** is
forced through the token"* for accrual.

**Ruling: both are fractions in `[0, 1]`, and the domain is enforced.** The arithmetic settles it —
the chain only yields dollars if both are fractions — and both are parts of a stated whole, so
neither can exceed 1. `annualHolderFlow` rejects anything outside `[0, 1]` rather than dividing by
100, because a `50` typed where `0.5` belongs is a silent two-orders-of-magnitude error inside a
report that is immutable once committed. The formula itself is untouched.

The TypeScript field keeps the name `accrualPct` despite meaning a fraction, to stay aligned with
the frozen table's `accrual_pct`. Renaming it for ergonomics would put the code's vocabulary out of
step with the framework's, which is a worse trade than a name that needs a comment — and the guard
already makes the misreading impossible rather than merely discouraged.

### RULED 2026-09-21 — `PURE_PREMIUM` was over-applied

`discovery_premium = market_cap ÷ net_annual_flow` is frozen and unchanged. The **verdict taxonomy**
around it was wrong: it returned `PURE_PREMIUM` for any `net ≤ 0`, but §5 of the lesson reserves
*"100% premium, pure narrative, tradable but never ownable"* for a token with **zero forced flow**.
A token earning $10M while issuing $50M — the lesson's own flagship example in §1 — has a real
mechanism that insiders are eating, which is a different finding from having no mechanism at all.

`PURE_PREMIUM` now requires `gross = 0`; a positive gross with a negative net returns
`ISSUANCE_NEGATIVE` carrying both figures. `discoveryPremium` takes the whole `AccrualResult`
rather than a bare net figure, so it cannot be called without the gross that tells the two apart.

### RULED 2026-09-21 — the reserve/collateral branch is out of scope for Phase A.1

`framework/00-how-we-think.md:57-61` describes a second value branch — *"the token must be bought
and held or locked for the system to function at all (gas floats, bonded collateral, required
staking). Value it by the size of the float"* — and states that **the branches ADD**. The frozen
formula table models only the cash-flow branch.

The consequence is real: a gas-float token with no fee share computes `gross = 0`, and therefore
reads as `PURE_PREMIUM`, for a coin the lesson explicitly places *inside* the set that passes the
accrual test. **Ruling: ship A.1 with the cash-flow branch only, and say so in the report** — the
accrual figure is captioned as cash-flow accrual, not as total holder value. Adding a term to a
frozen formula is a larger move than a bug fix, and the lesson gives no arithmetic for valuing a
float, so the term would have to be invented. Revisit when a researched coin is actually
reserve-branch.

### Recorded for a ruling — not blocking

1. **`Impact` range disagrees with itself (Phase B).** The input table gives `Impact` as **1–10**;
   the validation rules below it say *"`Impact` must be 0–10."* Those are different constraints, and
   the difference is load-bearing: `Impact = 0` zeroes any signal for that pillar regardless of `P`
   and `Quality`. Which one is the rule?

2. **`Quality` range disagrees with itself (Phase B).** The input table gives `Quality` as
   **0.5–1.0** with an explicit reason (*"Quality changes how hard you lean — never which way"*,
   floor of 0.5 so the worst evidence halves a signal rather than flipping it). The validation rules
   say *"`Quality` must be 0–1."* Enforced as written, the validation rule would accept
   `Quality = 0.2`, which the stated floor exists to forbid. The 0.5 floor and the 0–1 check cannot
   both be the constraint.

3. **One validation rule is now unreachable in Phase A.** *"Use the committed value, never the AI
   draft, whenever both exist."* Under the EvidenceFinder (§8) no AI draft of any number exists —
   the `*_draft` columns are deleted and the model never proposes a number. The rule is preserved
   verbatim and becomes live again only if Phase B ever admits a drafted number.
