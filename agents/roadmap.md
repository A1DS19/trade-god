# Roadmap

## Goal
A research tool that makes the deterministic parts of the CoinPicks framework deterministic, makes
its citation requirement mechanical, and accumulates enough point-in-time reports to test whether
the framework's scores predict anything. The honest possible answer is "no". That is a result worth
having, and the system is built so that answer would be legible rather than deniable.

**Phase A has exactly two sub-phases**, and the spec's Decisions table is the normative statement of
them: **A.1** = frozen scoring, editor, verifier, commit gate, ledger. **A.2** = the viem chain
layer. There is no A.3 — the spec's Decisions table scopes Phase A as A.1 and A.2 only. An earlier
draft of this file invented one for the forward-return join, the
`research` GRANT and `rescore.ts`; those are not a phase, they are how A.1's ledger step (6) gets
finished, and they are folded back into it below.

---

## Phase A.1 — report #1

The eight steps, in order. Nothing here is parallelisable in a useful way; each step is the next
one's floor.

- [x] **1. Archive the trading stack.** `app/{intraday,api,db,config.py}`, `alembic/` (six
      migrations, 001–006), the two root entrypoints `api_main.py` and `intraday_main.py`
      (`main.py` and `swing_main.py` went in July), `docker-compose.yml`, `Dockerfile` and
      `tests/{intraday,api}/` to `legacy/`. `app/intraday/strategy.py` went to
      `research/signals/intraday/strategy_core.py` instead — it is the one module `research/` still
      imports — and its test moved with it to `tests/research/test_strategy_core.py`.
      `research/v2_eval/` went to `legacy/` too; it had been broken since 2026-07-16 (it imports
      `app.swing.backtest_replay`) and nothing tested it, so the suite stayed green over a dead
      module. Suite after the move: **111 passed**, and `tests/` now holds only `tests/research/`
      and `conftest.py`.
- [ ] **2. Frozen scoring core.** `apps/api/src/scoring/{ranges,product,narrative,team,accrual}.ts`
      — pure functions, no imports from the rest of the app, reject out-of-range instead of
      clamping, fractional narrative sub-scores allowed. Built in a bare `typescript` + `vitest`
      package before any Hono, Drizzle or Postgres exists (Plan 1, Tasks 5 and 6). Tested first and
      hardest; this is a money path. The framework's two worked examples are the acceptance test:
      team → 7.25, ARB narrative → 26.5.
      - [x] **Prerequisite, done 2026-09-21:** the seven framework lessons are vendored into
            `framework/` with a provenance README. A frozen formula with no checked-in provenance
            is a formula that stops being auditable the first time someone cleans out Downloads.
- [ ] **3. Schema, migrations, and the trigger.** `apps/api/src/db/schema.ts`; `drizzle-kit
      generate` output committed under `apps/api/drizzle/` with `meta/_journal.json`; applied at
      boot from `server.ts` before the port is taken. Then `--custom` for the hand-written
      `BEFORE UPDATE OR DELETE` trigger on `reports`, `report_scores`, `report_team`, `citations`.
      **The trigger gets written on day 2 or it never gets written.** The other four non-negotiable
      schema rules travel with it: `pgEnum` rather than `$type<>()`, `report_scores.scoring_version`,
      `reports.version` compare-and-swap, and `timestamptz` + `jsonb`.
- [ ] **4. Minimal editor.** `apps/web` — enough UI to type a coin, its scores and its citations,
      with compare-and-swap saves against `reports.version` (409 on a stale write). Minimal means
      minimal; the UI is the disposable layer.
- [ ] **5. Citation verifier.** Deterministic quote-at-URL check producing `verified` /
      `near_miss` / `failed` / `unverifiable_js`. This is the gate's teeth and it runs before a
      human ever sees a candidate.
- [ ] **6. Commit gate and ledger view.** `POST /reports/:id/commit`: one transaction that
      re-checks every precondition, evaluates the frozen formulas, writes `report_scores` with its
      `scoring_version`, and flips `status`. Its e2e test gets **real Postgres or it does not
      run** — a memory store has no transactions, no CHECK constraints and no triggers, so a green
      run against one proves nothing about atomicity or immutability.

      The ledger is what the gate is for, so the join is part of this step rather than a later
      phase:
      - [ ] `research/forward_returns.py` — **does not exist yet.** psycopg 3.2.13, select
            committed reports, compute 30/90/180/365-day returns from the parquet warehouse,
            `INSERT ... ON CONFLICT (report_id, horizon_days) DO UPDATE`. Horizons are frozen.
      - [ ] The `research` Postgres role: `SELECT` on
            `coins`/`reports`/`report_scores`/`report_team`/`citations`, `INSERT, UPDATE` on
            `forward_returns`, nothing else. Python owns no table's shape, and that is enforced by
            a GRANT rather than by good manners.
      - [ ] `node apps/api/scripts/rescore.ts` — re-deriving a committed number runs the
            authoritative TypeScript. Python never recomputes a score.
      - [ ] Refresh the warehouse before the first join. OI and long/short are trailing-30-day
            only; nothing earlier in A.1 needs them, this does.

      The join is worth running long before it is worth *believing*. One report tells you the
      plumbing works; the verdict needs a cohort.
- [ ] **7. Bench three models on one real coin section.** `kimi-k3`, `deepseek-v4.1-flash`,
      `qwen3.8-max` through the DashScope international endpoint. Record the result and only then
      pin `DEFAULT_PROVIDER` — the in-code constant in `apps/api/src/evidence/providers.ts`, whose
      environment override is `COINPICKS_MODEL_PROVIDER`. Never pin a default on price or on vibes.
- [ ] **8. Wire the EvidenceFinder.** Candidates only: `{url, quote, why}`, verified before
      display, `selected_at` set by the human, `origin='model'`. Plus the test asserting that no
      LLM-reachable path writes to `report_scores`.

**Honest sizing: 9–10 working days to report #1**, chain layer excluded.

---

## Phase A.2 — the chain layer

- [ ] `apps/api/src/chain/`, viem 2.56.8, **same Node process — no sidecar**: pool census, safety
      checks, issuance, holder distribution, accrual-contract discovery, Multicall3 batching, and
      the poison-pair drop (discard any pool priced more than 5% from the TVL-weighted median).

Deliberately after report #1. A report can be written with vendor liquidity figures and a note;
it cannot be written without scores, citations and a commit gate.

---

## Phase B — market direction (recorded, not built)

Pillar reports and the `Signal = ((P − 50) ÷ 50) × Quality × Impact` machinery over five locked
windows (1M / 3M / 6M / 1Y / 3Y), aggregating by pillar weight into a per-window call.

Written down so the schema does not accidentally foreclose it. Not designed, not scheduled, and
not to be started before A.1's ledger has produced a cohort worth aggregating.

---

## Explicitly not planned

Trade execution of any kind. Alerting, or any deployed service. Auth or multi-user anything.
Solana. Wallet clustering.
