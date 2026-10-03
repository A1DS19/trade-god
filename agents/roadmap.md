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

The question: can a model trained on this warehouse beat holding BTC after costs, at
daily-to-weekly horizons?

- [ ] **1. Pre-registration spec.**
      - File: `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`.
      - Fixes, before any real-data run: universe, features, target, model, trial budget, costs,
        gates, the sealed OOS window, and the stop conditions.
      - The owner reviews it before any plan is written.
- [ ] **2. Point-in-time universe.**
      - Closes Phase C's open gap: today's top 100 is survivorship bias.
      - Backfill every USDT perp, including delisted ones, from Binance's public archive.
      - Rank by trailing quote volume and apply eligibility from the next day.
- [ ] **3. Features and labels,** as frozen in the spec. Every one is tested against look-ahead the
      way `siglib`'s contract tests already are.
- [ ] **4. Train-only search.**
      - Purged and embargoed walk-forward.
      - Every trial counted.
      - Costs from `research/siglib/costs.py`.
- [ ] **5. Freeze, then unseal.**
      - Commit `frozen_params.json` first; the OOS evaluation is a separate, later commit.
      - The unseal is one-shot and judged mechanically against the gates, with BTC buy-and-hold
        and a slow trend rule as baselines.
- [ ] **6. Verdict.**
      - If it fails, it is recorded like Phases C, 2a and 2b, and the lab picks its next question.
      - If it passes, a forward paper record starts. Its length and pass rule are fixed in the spec.

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
