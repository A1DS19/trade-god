# Cross-sectional momentum — blind OOS evaluation

**Verdict: FAIL — not promoted.** Criterion 2 (pooled OOS profit factor ≥ 1.2)
fails decisively: pooled PF = **1.0336**. Criteria 1 and 3 pass.

Evaluator: blind (did not build the signal). Frozen artifacts evaluated as-is:
`signal.py` + `params.json` = `{lookback_days: 7, k: 3, rebalance_hours: 24,
vol_norm: true, leg: "ls"}`. All PnL via `research.siglib.run_backtest`
(next-bar execution, 1h grid, 60-day eligibility, funding event-by-event,
baseline 10 bps/side, stress 15 bps/side). Runner: `oos_eval.py`; raw numbers:
`oos_results.json`.

**Multiple-testing log**: this evaluation ran exactly **1** parameter
combination (the frozen set) — no search. (Train study logged 54 combos in
`combo_log.csv`; selection used train data only, per its report.) The
long-/short-leg runs below are an exact arithmetic decomposition of the same
frozen weights (verified: leg returns sum to the LS book to <1e-12), not extra
configurations.

## Per-window results (baseline costs)

| window | OOS period | net return | PF (hourly) | max DD | trades | turnover | funding paid | trade cost |
|---|---|---|---|---|---|---|---|---|
| W1 | 2023-07-01 → 2024-07-01 | **+16.75%** | 1.0191 | 34.5% | 1,851 | 309 | 0.8% | 30.9% |
| W2 | 2024-07-01 → 2025-07-01 | **+11.33%** | 1.0145 | 38.2% | 1,881 | 314 | −2.8% (received) | 31.4% |
| W3 | 2025-07-01 → 2026-06-01 | **+143.75%** | 1.0542 | 39.0% | 1,823 | 304 | 18.0% | 30.4% |
| **Pooled** | 2023-07-01 → 2026-06-01 | **+216.82%** | **1.0336** | 40.8% | 5,555 | 926 | 20.0% | 92.6% |

Stress (slippage doubled, 15 bps/side):

| window | net return | PF | max DD |
|---|---|---|---|
| W1 | **+0.04%** | 1.0071 | 36.6% |
| W2 | **−4.84%** | 1.0039 | 42.8% |
| W3 | +109.35% | 1.0474 | 40.9% |
| Pooled | **+99.28%** | 1.0243 | 45.3% |

## Promotion criteria (binding, applied exactly)

1. OOS net PnL > 0 in ≥ 2 of 3 windows → **3/3 positive — PASS**
2. Pooled OOS profit factor ≥ 1.2 → **1.0336 — FAIL** (PF per siglib's
   `BacktestResult.profit_factor`, hourly net bars — the only PF the
   pre-registered engine computes. Even the descriptive daily-aggregated PF is
   only 1.178 pooled; the criterion fails on any reasonable granularity.)
3. Pooled OOS positive under stress slippage → **+99.28% — PASS**

**1 of 3 criteria failed → signal FAILS.** The train report predicted exactly
this shape ("PF is only 1.05–1.07 on hourly bars"): OOS PF came in *below*
train PF (1.034 vs 1.069), i.e. the usual train→OOS shrinkage on top of an
already-thin margin.

## Anomalies and concentration (report these honestly)

- **One window dominates**: W3 contributes 124.2pp of the pooled 170.3pp
  arithmetic net PnL (**73%**). W1+W2 together are a near-flat grind
  (+16.8%/+11.3% compounded over two years against 34–38% drawdowns).
- **Stress positivity is entirely W3**: under stress, W1 = +0.04%,
  W2 = −4.84%. Criterion 3 passes pooled only because of W3. A 2023–2025-only
  evaluation would have failed stress too.
- **Monthly concentration**: no single month exceeds 50% of pooled PnL (best:
  2025-12 at +41.2pp = 24.2% of total; worst: 2024-04 at −22.8pp). But only
  19/35 months are positive and monthly swings of ±20–40pp on gross 1.0 are
  routine — the equity curve is violent (pooled maxDD 40.8% baseline, 45.3%
  stress).
- **All edge is in the long leg** (exact decomposition of the frozen LS book,
  baseline costs, pooled): long leg **+252.8pp** arithmetic net
  (+598.7% compounded, PF 1.047), short leg **−82.4pp** (−66.9% compounded,
  PF 0.979). The short leg lost money in W1 (−53.2pp) and W2 (−32.6pp) and was
  ~flat in W3 (+3.4pp). Dollar-neutrality did not deliver a two-sided edge OOS;
  the book is a costly hedged long-momentum bet.

## Survivorship bias (pre-registered caveat, quantified by direction)

The universe is TODAY's top-100 by volume: every ranked symbol survived to
2026. This inflates long-momentum results most — and the decomposition above
shows the OOS PnL is 100% long-leg. The bias on the dollar-neutral spread is
two-sided (long leg inflated, short leg doubly deflated — delisted coins that
would have been the best shorts are absent), so its net sign is ambiguous, but
the *realized* OOS profile (long leg carries everything, short leg bleeds)
matches the pattern survivorship inflation would produce. The true forward
expectation is plausibly below the +217% pooled headline; W3's outsized
contribution sits closest to the snapshot date, where survivor contamination
of the ranking is strongest. None of this changes the verdict — the signal
already fails on PF — but it argues against re-litigating the pass on
criteria 1/3.

## Bottom line

The signal is directionally real OOS (3/3 windows positive at baseline, pooled
positive under stress) but the per-bar edge is far too thin: pooled PF 1.034
vs the required 1.2, drawdowns of ~40% on gross 1.0, trade costs consuming
92.6pp (baseline) to 139pp (stress) of the pooled arithmetic PnL, 73% of PnL
from one window, and the entire edge confined to the survivorship-favored long
leg. **Not promoted.**
