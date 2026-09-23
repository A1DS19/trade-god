# Decisions

Hard, costly-to-reverse decisions only. Dated, newest first, never edited in place — a decision
that stops being true gets a *new* entry above it that says so, and the old entry keeps its
original reasoning so the mistake stays legible.

2026-09-21 holds two pivots. Everything below the "earlier the same day" marker was decided in the
morning, against an Electron design that the afternoon replaced.

---

## 2026-09-22 — Reframed: automated research of the top 100, with signals the owner trades by hand

The owner's ruling: the point of this tool is to **automate** researching coins with the
`framework/` rules — not to be a form a human fills in. Decided in one session, question by
question:

- **Output: ranked signals** — buy candidate / hold / exit warning / needs review, each with
  confidence. The owner trades by hand. **Automatic trading waits** until the signals have a
  validated forward track record; the trading era's −15.19% out-of-sample result is why that order
  is not negotiable.
- **Universe: the warehouse's top-100 Binance USDT perps**, a 20-coin pilot first. Their prices are
  already in the warehouse, so every signal is measurable from day one. Recorded caveat: lesson 01
  targets coins with low liquidity relative to the cycle, which mostly sit below the top 100.
- **Pipeline.** Numbers come from data APIs, never from a model. A generative LLM with web search
  writes a sourced dossier. A claim reaches scoring only if its quote is found on the cited page
  (string match) AND Jev judges that the page supports it. Jev scores each sub-score against the
  lesson's own bands. The frozen formulas compute every total, unchanged. A versioned signal rule
  decides.
- **Signal rule v1:** the product gate (16+) is required; gate-passers rank by narrative, then team;
  the top N are buy candidates; an exit warning fires when a flagged coin fails the gate on
  re-research or its tier or premium worsens; a low-confidence Jev answer marks the coin "needs
  review" instead of signalling. Versioned like `SCORING_VERSION`, tuned only as a new version.
- **Liquidity tier** becomes a versioned rule over ±2% depth and pool TVL. Lesson 03 says "make
  your best guess"; a machine needs a rule, and the rule is recorded with every report.
- **Cadence:** numbers daily; full research weekly for candidates and flagged coins, monthly for the
  rest.
- **Validation is forward-only.** Web pages cannot be replayed for past dates, so a backtest would
  be look-ahead. The first 30-day read comes about a month after the first run.
- **Superseded:** "the human types every score" (the EvidenceFinder entry below) no longer holds for
  automated reports. Hand-written reports through the editor remain, as a comparison track in the
  ledger. The frozen formulas and their single evaluation point are unaffected.
- **Known limits, accepted:** Ease of Use is judged from docs and reviews, never hands-on; crypto
  marketing pages are exactly the input Jev's own documentation says can steer it.

**Reversal cost:** high once reports accumulate — the ledger's rows are only comparable within one
research version, one signal-rule version and one pinned Jev version.

## 2026-09-22 — Elysia on Bun; shadcn with the Spectral theme

- **Hono → Elysia, Node → Bun.** The owner's ruling. The recommendation had been to keep Hono,
  because Elysia's advantage is Bun and this repo ran Node; moving to Bun removes that objection.
  What it costs: the thirteen routes, the typed client (`hc` → Eden Treaty), the route-test harness
  and the server boot are rewritten. The frozen formulas, the schema, the migrations, the triggers
  and the role split carry over.
- **shadcn** (Base UI "base-nova" style, Tailwind v4, oklch tokens), as in the sibling repos. This
  reverses CLAUDE.md's "no shadcn or any component library". Theme: **Spectral** — indigo night,
  iris-violet primary, belief strips in a cool-to-violet spectrum with Jev's chosen band glowing;
  Unbounded over Hanken Grotesk.

## 2026-09-22 — the editor review, after Plan 3 Task 7

A five-lens review of the finished editor (each finding checked by a skeptic who tried to
reproduce it) confirmed defects the plan's own walk could not see, because `fill()` pastes and
a real operator types.

- **Sections re-seed in place, not by remount.** Plan 3 keyed each section on a seed token so a
  409 could not leave the loser's text in the boxes. The remount did that, and also emptied
  every evidence box in the section on its own successful Save — a hand-transcribed quote typed
  but not yet added vanished with a 200 and no message — dropped focus to `<body>`, and threw
  away the refusal the save produced. `useSection` now resets its form when the token moves
  (React's adjust-state-during-render pattern). The property the key existed for is kept; do
  not restore the `key`.
- **One write at a time per page, and a second is refused as `BUSY`, not queued.** The CAS token
  was read off the last render, so two actions inside one round trip sent the same spent
  version and this tab's own write came back `STALE_VERSION`, blamed on "another tab", wiping
  every section. A queue would send a body built from the screen as it stood *before* the first
  write's outcome — after a 409, text the database had just refused.
- **A measured-at before 2009-01-03 is refused** (owner's ruling). ~~`0026` for `2026` passed
  `z.iso.datetime`, saved with 200 and read back a century off, because JavaScript's `Date`
  maps years 0–99 onto the 1900s; an untouched re-save then wrote the corruption back.~~
  **[Corrected the same day, after the second review round: drizzle maps a timestamptz with
  `new Date(pgText)`, and V8 reads a year below 100 in that text form as two digits. `0026`
  becomes an Invalid Date — null on the wire — so the figure returns with four of five boxes
  filled and an untouched re-save is refused; `0050`–`0099` come back in the 1900s and an
  untouched re-save writes that into the row. The floor stands.]** **[Corrected again after the
  third round: the mechanism is not a two-digit year. Postgres's text form is not ISO, so V8's
  legacy parser reads it and takes a leading field of 12 or less as a month — `0001`–`0012`
  come back as a plausible 2022 date, `0013`–`0031` as null, `0032`–`0049` as 2032–2049 and
  `0050`–`0099` as the 1900s. Measured on Node v26.8.1. The floor stands.]** Wire validation,
  not a frozen formula.
- **A landed write's own answer is applied before the re-read.** Every write route answers
  `{ version }` plus the scores, team or citations it changed. Applying that first means a
  failed re-read still leaves the right CAS token and a section re-seeded from what was stored;
  without it the page kept a spent token, and a team form kept `id: null` for a person the
  database had just created, so the next team save re-created them and deleted their evidence.
- **Open, deliberately: five citable fields have no evidence box** — ±2% depth, top-pool TVL,
  capture share, token accrual, annual issuance. The API accepts citations on them; the editor
  cannot show or remove one. Which fields the commit gate demands evidence for is step 6's
  ruling, and the owner deferred it there.

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
- **Port 8789, not 8787.** The sibling project's API container holds 8787 permanently on this
  machine. Left at 8787 the server died with EADDRINUSE while that other service answered
  `/health` on the same port with a different application's shape entirely — a boot check
  reading green off someone else's process. Overridable via `PORT`.
- **The vitest suite runs files serially.** `integrity.test.ts` disables a real trigger to
  prove the boot check catches it, and every file shares one `coinpicks_test`. In parallel,
  `immutability.test.ts` could assert a committed report is protected during the window
  where the guard is off.

## 2026-09-21 — Rubric sub-scores are integers, and one cited worked example was never real

A post-build audit of `apps/api/src/scoring/` against the vendored lessons found that the example
this repo cited as the framework's own — ARB narrative, Communication 4.5/5, total 26.5 — appears
in **none** of the seven lessons, and nowhere in the original download. It was written by the
implementation plan and then quoted by the spec, by CLAUDE.md, by a test name and by this file as
though it were source. It was the only evidence anywhere for fractional sub-scores.

That mattered arithmetically, not just bibliographically. With decimals allowed, three one-decimal
sub-scores summing to exactly 16.0 can add in binary to 15.999999999999998 — 404 such triples
exist, every one of them failing a gate the lesson says to pass, and 35.8% of one-decimal narrative
combinations miss their decimal total. **Ruling: rubric sub-score inputs are whole numbers.** The
lessons state their scales as integer-contiguous bands and the gate partitions into "16+" / "0–15",
which only covers integers. Derived values — the team weighted score is a mean — are unaffected.

The wider lesson is the one this repo keeps re-learning: a confident, citable-looking number that
nobody checked. It survived a design spec, a 1420-line plan, a code review and four commits. The
framework lessons are now vendored under `framework/` precisely so the next such claim can be
grepped in one second.

Supersedes the fractional-sub-score clause of the frozen-formulas entry below.

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

## 2026-09-21 — The LLM is an EvidenceFinder, not a drafter **[SUPERSEDED 2026-09-22 for automated reports]**

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

## 2026-09-21 — Node, not Bun **[SUPERSEDED 2026-09-22]**

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

## 2026-09-21 — TanStack Start + Hono + Postgres, and specifically *not* TanStack Start's server as the backend **[Hono SUPERSEDED 2026-09-22 by Elysia]**

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

Concretely: ranges are rejected, never clamped. ~~Narrative sub-scores may be fractional — the
framework's own worked example scores Communication 4.5/5 — so they are never constrained to
integers.~~ **[Superseded 2026-09-21 — that example is not in any lesson; sub-scores are
integers. See the entry above.]** Every `report_scores` row carries the `scoring_version` it was computed under, because
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
