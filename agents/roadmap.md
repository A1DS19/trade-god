# Roadmap

## Goal

A model lab: train models on the warehouse, and judge each one under pre-registration against
holding BTC, after costs.
- The honest possible answer is "no edge". That is a result worth having, and every experiment is
  built so that answer would be legible rather than deniable.
- Real money waits for a forward record. Even then, it is a slice of under $1,000.

Ruling of 2026-10-02 (`agents/decisions.md`): CoinPicks is archived, there is no seconds-scale
trading, and the first experiment runs at daily-to-weekly horizons.

---

## Experiment 1 — the daily model lab

The question: can a model trained on this warehouse beat holding spot BTC after costs, at
daily-to-weekly horizons?
- **Three arms** race on identical, pre-registered rules: BTC timing, ETH timing, and a
  cross-sectional ranker over a point-in-time top 50 that includes delisted coins.
- **Alongside them,** a forward-only test of TypeSafe's Jev as a decision-time veto.
- **Spec:** `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`. Each phase below gets
  its own plan.

- [x] **0. Design.** Approved in conversation (2026-10-02); the written spec is committed for the
      owner's review.
- [ ] **1. TypeSafe recorder and the two paper books** ("hold BTC" and "hold BTC with veto").
      - Starts the forward record.
      - Needs `TYPESAFE_API_KEY` and confirmed access.
- [ ] **2. Data.**
      - Archive datasets (spot BTC/ETH since 2017-08; every USDT perp, live and delisted).
      - Reconciliation against the existing warehouse.
      - The exclusion list, which the owner reviews.
      - The point-in-time universe, and `siglib/stats.py`.
- [ ] **3. BTC and ETH arms:** features, HAR volatility, LightGBM, walk-forward, validation study,
      freeze.
- [ ] **4. Ranker:** features, model, validation study, freeze.
- [ ] **5. Joint unseal.**
      - One run of `oos_eval.py` for all three frozen arms.
      - Gates G1–G6; the verdict and a findings document.
- [ ] **6. After the verdict.**
      - A 26-week paper record for any passing arm.
      - The TypeSafe 26-week readout.

---

## Explicitly not planned

- Seconds-scale or intraday trading (ruled out 2026-10-02).
- Trade execution of any kind before a forward record exists.
- CoinPicks, archived in `legacy/coinpicks/`.
- Any deployed service.

---

## Archived: CoinPicks (2026-09-21 → 2026-10-02)

A fundamental-scoring research tool, built through build-order step 4 and then retired:
- the frozen scoring core;
- the schema with immutability triggers and the role split;
- the minimal editor, after four adversarial review rounds.

Steps 5–8 (verifier, commit gate and ledger, model bench, EvidenceFinder) were never built. The
automated-research reframe (`docs/superpowers/specs/2026-09-22-automated-research-design.md`) was
never approved. The code and its vocabulary are in `legacy/coinpicks/`, and the database volume
`coinpicks_data` is kept.

---

## Log

- 2026-09-21 — build-order step 3 complete: schema, three migrations, twelve ENABLE ALWAYS triggers, the role split, CAS. Next: step 4, the minimal editor.
- 2026-09-22 — step 4 complete: the minimal editor (Plan 3 Tasks 1–7), four adversarial review rounds, a description under every label. Plan 3 Task 8 (docs/CI) folds into Phase 0 of the automated-research plan.
- 2026-09-22 — reframed to automated research. Spec `docs/superpowers/specs/2026-09-22-automated-research-design.md` (`c55cf73`) awaits the owner's review; once approved, its Phases 0–5 replace steps 5–8 above and this roadmap is rewritten.
- 2026-10-02 — CoinPicks archived to `legacy/coinpicks/` (`3387d37`) after a three-track research pass (`docs/superpowers/specs/2026-10-02-trading-model-research-findings.md`). The repo becomes a model lab; Experiment 1 is the daily model lab.
