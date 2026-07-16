# mr_vwap Strategy Backtest — Findings (Phase 2b)

**Run date:** 2026-07-15 (dev machine, warehouse-only)
**Verdict: REJECTED — both variants.** The Phase 2a survivor does not survive as a tradable
strategy. The pre-agreed fallback applies: Phase 3 builds the paper-first engine; no live money
without shadow validation.

## 1. Protocol

Pre-registered in `docs/superpowers/plans/2026-07-16-mr-vwap-2b-backtest.md` (commit `894c9c5`).
All code committed before any real-data run: engine asymmetric costs `df69469`, strategy
`17752b7`, train runner `78f21fa`/`47d46a2`, OOS evaluator `b2e4feb`/`f5ae459`. Train phase ran
first (< 2025-07-01 only); the OOS year was unsealed exactly once, after the diagnostics review,
via `python -m research.signals.intraday.mr_vwap_oos`. No deviations; no re-runs.

## 2. Train phase (frozen before unseal)

| Variant | Train result | Frozen params |
|---|---|---|
| next_bar (taker, base case) | **NOT VIABLE** — no eligible combo (n_trades ≥ 100 ∧ return > 0) in the 18-combo grid | — |
| maker_limit | Viable; frozen H=32 bars (8h), horizon exit, K=10, no cliff | Sharpe +0.47, PF 1.021, return +25.1% over 2.5y, DD 26.5% |

The taker variant failing even in-sample **confirms findings caveat #6**: with next-bar entry at
taker costs, the z<-3 bounce cannot pay 16 bps round trip. Exactly the pre-registered expectation.

**Pre-unseal diagnostics (maker_limit, train):** 2,844 distinct episodes across 21 symbols;
concentration healthy (top-2 symbols = 31% of |PnL|); 15/30 positive months; edge_t = 0.74
(statistically indistinguishable from zero); train DD 26.5% already above the 20% OOS gate;
5m translation of the frozen params: **negative** (PF 0.973, −13.8% on the 5.5-month train
slice, descriptive, no PIT). Red flags were recorded but per protocol could not alter the
frozen params.

## 3. OOS verdict (single unseal, 2025-07-01 → 2026-07-15)

| Gate (pre-registered) | maker_limit baseline | Pass? |
|---|---|---|
| Net PF ≥ 1.15 | 0.986 | ❌ |
| ≥ 100 OOS trades | 2,791 | ✅ |
| ≥ 2 of 3 windows positive | W1 −10.4%, W2 −11.4%, W3 +6.8% (1/3) | ❌ |
| Max drawdown ≤ 20% | 36.1% | ❌ |
| **passes** | | **❌ REJECTED** |

Stress costs (2+2 entry / 5+10 exit): PF 0.970, DD 40.7% — strictly worse, as expected.

## 4. Interpretation

- The maker variant's weak in-sample edge (PF 1.02) was regime luck, not structure: it lost
  money through the first two OOS windows and recovered only in the last. The train-phase
  red flags (edge_t 0.74, coin-flip months, negative 5m translation) pointed here.
- Combined with 2a caveat #6 (52% of the raw signal edge sits in the untradable first bar and
  bid-ask bounce), the honest conclusion: **the deep-oversold VWAP bounce is real as a market
  phenomenon but not capturable at retail costs with bar-level execution** — not with taker
  fills, and not with strict-trade-through maker fills either.
- The maker fill model was, if anything, generous (assumed certain fill on trade-through, no
  queue competition), so reality is worse than these numbers.

## 5. Decision (pre-agreed tree)

FAIL → **Phase 3: build the paper-first intraday engine anyway** (per the user's 2026-07-15
decision): `app/intraday/`, paper mode first-class, kill-switches, error alerting; retire both
legacy bots. Candidates run in shadow mode on live data — the one validation that cannot be
overfit. **No live money without ~4 weeks of positive shadow PnL**, which no current candidate
is expected to achieve; the engine's near-term value is honest live measurement (including
real maker fill rates and queue behavior, which no warehouse backtest can provide) and being
ready if a future pre-registered edge-hunt (new hypothesis families: liquidations, order-book
imbalance, cross-exchange gaps) produces a genuine candidate.

## 6. Evidence

`research/signals/intraday/output/2b/`: combo_log.csv (all 36 runs), frozen_params.json,
diag_per_symbol.csv, diag_monthly.csv, diag_summary.json, oos_results.csv, oos_verdicts.json.
Multiple-testing ledger note: one grid (18 combos × 2 variants), one freeze, one unseal —
no iteration occurred after OOS data was touched.
