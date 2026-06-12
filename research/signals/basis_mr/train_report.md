# basis_mr — Premium-index mean reversion: train report

**Verdict: NOT VIABLE for OOS evaluation (viable = false).** The event study finds a
real, large, statistically strong conditional anomaly — but it is one-sided
(discounts revert, premiums do not), too fast and too thin per trade to clear
10 bps/side costs, survivorship-suspect, and the tradable symmetric strategy
shows no plateau anywhere in a 270-point grid (best train PF 1.03 vs the 1.2
pooled-OOS promotion bar).

All PnL through `research/siglib` (next-bar execution, baseline costs
5+5 bps/side, funding accrued with longs-pay-positive sign, 60-day
eligibility). Parameter selection used **only data strictly before
2023-07-01** (the earliest OOS start); nothing on/after that date was loaded
during the event study or grid search. 39 symbols have any data in that
window.

---

## 1. Event study (train < 2023-07-01)

Premium-index close, rolling percentile over M hours, eligible symbols only.
Mean forward returns in bps (t-stats descriptive only — overlapping horizons,
no Newey-West). Full tables: `output/event_study_train.csv`. M=720 shown;
M=168/336 are qualitatively identical.

| bucket (pctile) | n (24h) | 1h | 4h | 8h | 24h | 72h |
|---|---|---|---|---|---|---|
| [0, 0.2%] | 1,586 | **+74.9** (t 7.8) | +121.6 | +135.1 | **+197.9** (t 7.2) | +114.9 |
| (0.2, 0.5%] | 2,895 | +24.3 (t 4.9) | +49.4 | +57.0 | +104.0 (t 5.9) | +143.0 |
| (0.5, 1%] | 5,430 | +5.8 | +21.4 | +43.8 | +92.1 (t 8.0) | +142.6 |
| (25, 75%] mid | 366,374 | +0.7 | +3.0 | +5.6 | +17.1 | +55.2 |
| (98, 99%] | 8,817 | −5.1 (t −3.4) | −6.3 | −2.6 | +22.4 | +122.5 |
| (99.5, 99.8%] | 3,226 | −5.6 (t −2.2) | −4.8 | −5.3 | +10.7 | +142.8 |
| (99.8, 100%] | 3,575 | +0.3 (t 0.1) | +4.6 | −1.4 | +32.9 | **+214.3** |

Two findings:

1. **Discount extremes revert, hard.** Deepest bucket: +75 bps next hour,
   +198 bps over 24h vs +17 bps unconditional — a 10x conditional edge,
   monotone in depth, present at every M. This is a real anomaly in this
   sample.
2. **Premium extremes do NOT revert.** The rich tail is worth −5 bps at 1–4h
   (barely beats nothing) and turns strongly *positive* by 24h (+33 bps) and
   72h (+214 bps): premium spikes are bullish momentum. The pre-registered
   symmetric hypothesis is half wrong. Shorts also only collect ~0.5–0.6
   units of funding over 3.8y on the whole short book — not nearly enough to
   carry the momentum bleed.

Same picture in z-score space (M=336): z < −4 → +71 bps@1h (n=1,919);
z > +4 → −2.3 bps@1h then positive at 4h+.

## 2. Multiple-testing ledger

| batch | combos | file |
|---|---|---|
| v1 grid (evicting top-K construction — see §3) | 81 | `output/combo_log_v1_evicting_construction.csv` |
| v3 grid (final slot construction, both exit modes) | 270 | `output/combo_log.csv` |
| **total parameter combinations evaluated** | **351** | |

Grid: M ∈ {168, 336, 720} × P ∈ {0.95, 0.98, 0.99, 0.995, 0.998} ×
exit_mode ∈ {median, horizon} × H ∈ {24, 72, 168} × K ∈ {3, 5, 10}.
Plus non-selection diagnostics (per-leg splits, majors-only subset,
per-symbol attribution) run only on already-chosen/representative points.

## 3. Construction note (v1 → v3)

The v1 portfolio construction re-ranked all active positions every bar by a
refreshing |z| score; cap eviction churned 30–36% of gross **per hour**
(turnover ≈ 11,800 over 3.8y, trade cost ≈ 11.8x gross) and every combo
compounded to ≈ −99%. Rewritten as a slot machine: a position keeps its slot
until its own exit; new candidates are admitted to free slots by |z| at
entry. This is an implementation fix, not signal information — both grids are
logged. Exit modes (both inside the pre-registered family "exit at median or
fixed horizon"): `median` = percentile crosses 0.5 (or timeout); `horizon` =
pure time exit H hours after the last bar in the entry zone.

Key economics found while diagnosing (M=336, P=0.99, K=3, train):
median-exit holds are hours long, gross +9.09 sum vs 10.18 cost — **8.9 bps
gross edge per side traded vs 10 bps cost**. Horizon exits hold longer and
gross goes *negative* (−0.28 at H=24, −2.13 at H=72) because the short leg's
momentum bleed compounds. The anomaly is real but lives inside the cost
envelope.

## 4. Grid landscape and frozen parameters

Of 270 v3 combos on W1 train: **5 positive total return, 52 of 270 positive
Sharpe, best PF 1.029**. The 5 winners are isolated, disconnected corners:

| M | P | exit | H | K | ret | PF | maxDD | sharpe |
|---|---|---|---|---|---|---|---|---|
| 720 | 0.98 | horizon | 72 | 3 | +0.93 | 1.024 | 0.88 | +0.64 |
| 720 | 0.98 | horizon | 168 | 3 | +0.55 | 1.022 | 0.94 | +0.58 |
| 336 | 0.995 | median | 24 | 3 | +0.43 | 1.029 | 0.95 | +0.56 |
| 168 | 0.95 | horizon | 72 | 5 | +0.52 | 1.018 | 0.84 | +0.50 |
| 168 | 0.95 | horizon | 72 | 10 | +0.17 | 1.014 | 0.69 | +0.36 |

Pre-registered mechanical selection (max Sharpe s.t. n_trades ≥ 100,
ret > 0, prefer all-positive-Sharpe neighborhood): **no combo has an
all-positive neighborhood** → global best taken and flagged
`cliff = true`.

**Frozen: M=720, P=0.98, exit_mode=horizon, horizon_hours=72, max_k=3**
(`params.json`).

Sensitivity (cliff, not plateau) — frozen point's own H×K slice:

| H \ K | 3 | 5 | 10 |
|---|---|---|---|
| 24 | −0.91 | −0.90 | −0.90 |
| 72 | **+0.93** | −0.26 | −0.58 |
| 168 | +0.55 | −0.68 | −0.86 |

One step in K (3→5) flips +93% to −26%; one step in H (72→24) flips to −91%.
This is a noise peak, not a strategy.

## 5. Frozen params on train windows (baseline costs unless noted)

| window | ret | PF | maxDD | trades | sharpe | stress ret (10 bps slip) | long leg ret | short leg ret |
|---|---|---|---|---|---|---|---|---|
| W1 train (<2023-07) | +92.9% | 1.024 | 87.7% | 2,288 | +0.64 | +42.4% | +447.9% (PF 1.045) | −71.4% (PF 0.988) |
| W2 train (<2024-07) | +53.8% | 1.019 | 87.7% | 2,765 | +0.53 | +6.4% | +585.9% (PF 1.041) | −82.6% (PF 0.984) |
| W3 train (<2025-07) | **−61.4%** | 1.008 | 90.7% | 3,234 | +0.22 | −75.0% | +257.8% (PF 1.029) | −92.1% (PF 0.978) |

(W2/W3 are supersets of W1; the frozen point doesn't even survive its own
extended train period.) Episode stats (W1): 545 episodes, avg hold 160h, avg
2.6 open positions, 54% of held bars long. Funding contributed +0.48
(received) on W1 — real but small. Every short leg is net negative in every
window; the entire edge is the long/discount side.

## 6. Survivorship

The universe is TODAY'S top-100 by volume, so every symbol survived to 2026.
Buy-the-crash on survivors is precisely the trade this biases upward. Bound:
rerunning the frozen params on 12 incumbent majors (BTC, ETH, BNB, XRP, ADA,
DOGE, LTC, LINK, BCH, ETC, TRX, XLM — listed 2019-20, whose presence in any
2026 top-100 was never conditional on 2020-23 performance):

- **Majors-only W1 train: −77.7%, PF 0.996, Sharpe −0.11** (vs +92.9% full
  universe).
- Per-symbol attribution: top 3 names (SOL +0.80 gross, UNI +0.42, BCH +0.36)
  supply 37% of positive gross; the winners are exactly the survivor-tilted
  mid-caps.

The headline train number is substantially a survivorship artifact.

## 7. Conclusion

- The conditional anomaly (deep premium discounts → strong positive forward
  returns) is real in-sample and worth knowing about, but the pre-registered
  symmetric percentile strategy is **not viable**: no train edge that could
  plausibly clear the promotion criteria (pooled OOS PF ≥ 1.2 vs train PF
  1.02 at the cherry-picked peak; stress slippage erases half of it before
  OOS degradation).
- True-negative drivers: (i) edge is one-sided — rich premiums are momentum,
  so the mandated short leg is a permanent tax (PF 0.978–0.988 everywhere);
  (ii) per-side gross edge ≈ 9 bps vs 10 bps cost; (iii) the long-side edge
  is concentrated in survivor mid-caps and flips negative on incumbents.
- What might be worth a NEW pre-registration (not claimed here): long-only
  deep-discount reversion ([0,0.5%] bucket, +75–198 bps at 1–24h) evaluated
  on a point-in-time universe, and/or maker-fill execution to drop the cost
  envelope below the gross edge.
