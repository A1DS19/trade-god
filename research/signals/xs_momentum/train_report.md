# Cross-sectional momentum — train report (pre-registered protocol)

**Signal**: every B hours, rank eligible symbols by trailing R-day return
(optionally / realized vol); long top-K, short bottom-K, dollar-neutral,
gross 1.0, next-bar execution, 1h grid, siglib engine only.

**Discipline**: parameter selection used ONLY data with `open_time < 2023-07-01`
(the earliest OOS start), because one parameter set is frozen for all three
walk-forward windows — using any later data would contaminate W1's OOS. This
study never loads data ≥ 2025-07-01. OOS is run exclusively by the evaluator
via `signal.build_weights` + `params.json`.

- Combos evaluated and logged: **54** (R∈{7,14,30} × K∈{3,5,10} × B∈{24,72,168} × vol_norm∈{off,on}) — full log in `combo_log.csv`.
- Costs: baseline 10 bps/side (5 taker + 5 slippage); stress 15 bps/side; funding accrued event-by-event (longs pay positive).
- Eligibility: 60-day history rule (siglib), applied before ranking. Breadth guard (fixed, untuned): flat book if < max(2K, 10) valid symbols.

## 1. Event study (selection data < 2023-07-01, eligible symbols, XS deciles)

Conditional forward returns by cross-sectional momentum decile (0 = worst, 9 = best).
Full table: `event_study.csv`. Headline spreads (mean fwd return, D9 − D0):

| config | 24h | 72h | 168h |
|---|---|---|---|
| R=7 raw | +0.54% | +1.09% | +1.41% |
| R=14 raw | +0.40% | +0.95% | +2.15% |
| R=30 raw | +0.36% | +0.86% | +1.34% |
| R=14 vol-norm | +0.48% | +1.19% | +2.37% |
| R=7 vol-norm (frozen; table run post-freeze, descriptive) | +0.68% | +1.49% | +2.08% |

Frozen config (R=7, vol-norm) decile ladder at 24h:

| bucket | count | mean | median | t_stat |
|---|---|---|---|---|
| 0 | 59,467 | −0.028% | +0.024% | −1.26 |
| 1–7 | ~76–82k ea. | +0.15% … +0.25% | ~+0.07% | 6.7 … 12.3 |
| 8 | 77,169 | +0.354% | −0.015% | 13.10 |
| 9 | 89,389 | +0.651% | 0.000% | 23.23 |

Read: the edge is **tail-driven** — deciles 1–7 are an undifferentiated plateau;
separation lives in D9 (and weakly D0). This independently supports small K.
Caveat (per siglib): hourly observations overlap at multi-hour horizons, so
t-stats are NOT Newey-West corrected and overstate significance — ranking
devices only. Also note every decile's mean is positive at 168h: that is the
survivor-universe drift (§5), which the dollar-neutral book hedges out.

## 2. Grid search (54 combos, train < 2023-07-01, net of costs+funding)

53/54 combos net-positive; 46/54 positive in 2021-07→2022-07 (bear year),
53/54 in 2022-07→2023-07. Marginals (mean PF): vol_norm on beats off in 23/27
paired combos; K: 3 ≈ 5 > 10; B: 72 ≳ 24 > 168; R roughly flat. Top of the
plateau ranking (see `combo_log.csv` for all 54):

| R | K | B | vol | net ret | PF | maxDD | trades | sub1 | sub2 | plateau_pf |
|---|---|---|---|---|---|---|---|---|---|---|
| 7 | 3 | 24 | on | +1149% | 1.069 | 36.4% | 5545 | +56.7% | +41.2% | **1.0508** |
| 7 | 3 | 72 | on | +673% | 1.059 | 34.1% | 2863 | +21.0% | +33.9% | 1.0504 |
| 14 | 3 | 72 | on | +337% | 1.044 | 35.7% | 2133 | +15.5% | +70.8% | 1.0487 |
| 14 | 5 | 72 | on | +535% | 1.066 | 31.4% | 2908 | +55.8% | +42.9% | 1.0479 |

## 3. Frozen parameters (mechanical, pre-registered rule)

Rule: among combos with net return > 0 and ≥ 100 trades, maximize the
**plateau score** = mean PF over the combo plus all one-step grid neighbors
(anti-cliff device; a lone good point loses to a stable region).

**Frozen** (`params.json`): `lookback_days=7, k=3, rebalance_hours=24, vol_norm=true, leg="ls"`.

Why it's a plateau, not a cliff: its neighborhood (R 7→14, K 3→5, B 24→72,
vol toggle) holds PF 1.033–1.069, all net-positive; the entire vol-norm half
of the grid is positive. The single number that moves most across the
neighborhood is total return (concentration effect of K=3), not the sign.

## 4. Frozen params on cumulative train windows (`train_metrics.json`)

Dollar-neutral book, baseline costs:

| window | net ret | PF | maxDD | trades | turnover | funding paid | trade cost |
|---|---|---|---|---|---|---|---|
| W1 train (<2023-07) | +1150% | 1.069 | 36.4% | 5,545 | 927 | −6.6% (received) | 92.7% |
| W2 train (<2024-07) | +1359% | 1.057 | 36.4% | 7,396 | 1,236 | −5.9% | 123.6% |
| W3 train (<2025-07) | +1524% | 1.048 | 40.8% | 9,277 | 1,549 | −8.6% | 154.9% |

Stress (15 bps/side): W1 +686% / PF 1.057 / DD 40.1%; W2 +686% / 1.045 / 40.1%;
W3 +648% / 1.036 / 46.8%. Survives stress on train but the haircut is ~½ of
compounded return — cost sensitivity is the strategy's soft spot (cumulative
trade-cost line is ~93–155% of gross exposure; PF is only 1.05–1.07 on hourly
bars, so the OOS stress criterion is the binding one to watch.

Legs (baseline costs, each normalized to gross 1.0 — see §5 before believing):

| leg | W1 train | W2 train | W3 train |
|---|---|---|---|
| long-only | +8,706% | +24,960% | +41,087% (maxDD 86%) |
| short-only | −93.5% | −98.3% | −99.4% (received 53–64% funding, still ruinous) |

## 5. Survivorship bias (the central caveat)

The universe is TODAY's top-100 by volume. Every name in it survived; coins
that bled to delisting are absent.

- **Bound on the drift**: an equal-weight daily-rebalanced basket of all
  *eligible* universe symbols returned **+284%** (maxDD 80.5%) on the same
  selection window. Every decile's 168h mean forward return is positive.
  That drift is what inflates the long leg's absurd +8.7k% — discount it.
- **Direction of the biases**: long leg biased UP (survivor moonshots are in;
  the long book rides them). Short leg biased DOWN twice over — dead coins
  that would have been the best shorts are missing from both the book and the
  ranking, and bottom-decile *survivors* by definition rebounded. The measured
  short leg (−93%) is therefore pessimistic, but even its sign can't be
  trusted enough to run short-only.
- **The spread**: long-leg inflation and short-leg deflation push the
  dollar-neutral number in opposite directions, so its net bias is ambiguous
  but far smaller than either leg's. Per the pre-registered protocol, the
  dollar-neutral spread (and the short leg) are the trustworthy numbers; the
  long-only row should not be quoted.

## 6. Other caveats

- Breadth is thin early: 26 eligible symbols in 2021, 39 by 2023-07 (66 by
  2025-07) — K=3 is a 6-name book; idiosyncratic blowups matter, and the
  36–47% train maxDD says so.
- A missing hourly bar forces weight to 0 for that bar (engine semantics),
  costing a flicker of turnover; rare, identical across combos.
- Funding is roughly a small tailwind for the LS book (net received ~6–9%
  cumulative) — shorting high-momentum-down names tends to collect funding.
- Train windows are cumulative by construction (W2/W3 train contain earlier
  OOS calendar); frozen params were run there for reporting only, as the
  protocol allows. No OOS slice was computed or inspected by this study.
- Event-study configs were fixed pre-hoc at R∈{7,14,30} raw + R=14 vol-norm;
  the frozen-config (7, vol-norm) table was added post-freeze for description
  and played no role in selection.

## Verdict

Clear, tail-concentrated conditional edge in the event study; 53/54 grid
combos net-positive on train including the 2021-22 bear year; frozen combo
survives stress costs on train. **Viable for OOS evaluation** — with the
explicit expectation that OOS PF will be thinner than train (survivor-universe
ranking contamination shrinks OOS, and PF 1.05 leaves little room), and that
stress slippage is the most likely promotion-criterion failure point.
