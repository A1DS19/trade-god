# Funding-rate carry — train report

**Verdict: NOT VIABLE (viable = false).** Frozen params are delivered per protocol, but the
train evidence argues against spending the OOS windows on this signal. Reasons in §6.

- Data: `research/warehouse/` via `research.siglib` only. Phase A (everything used for parameter
  selection) loaded with `end=2023-07-01` (the earliest OOS start) so no OOS-tainted data was
  even computed on. Phase B (report) loaded with `end=2025-07-01`; params were frozen before
  Phase B ran and were not revisited.
- Execution: next-bar, 1h grid, costs 10 bps/side baseline (stress 15 bps/side), funding accrued
  at each event on the live weight (longs pay positive funding), 60-day eligibility, gross 1.0
  split equally across open positions.
- Combos evaluated: **372** (324 pre-registered grid + 48 post-freeze train-only sensitivity
  extension, flagged `phase='ext'` in `combo_log.csv`; the extension could not and did not
  change the frozen params).

## 1. Signal definition

Per-event funding normalized to bps/8h equivalents (the universe mixes 8h/4h/1h funding
intervals), optionally trailing-mean over M events, forward-filled hourly (stale → flat after
48h). `abs` form: short when smoothed funding ≥ +X bps/8h, long when ≤ −X, exit on
`|funding| ≤ exit_frac·X` (hysteresis latch). `pct` form: 30d rolling percentile with a fixed
2 bps/8h sanity floor and 0.10 percentile exit buffer. Max K concurrent, ranked by |funding|;
optional trend72 filter (shorts need trailing 72h return ≤ 0, longs ≥ 0). Funding settling at
hour H is usable from the close of bar H (≥ settlement + jitter): conservative, no lookahead.

## 2. Event study (train < 2023-07-01; 39 eligible symbols; fwd PRICE returns, bps)

M=1 (current rate), bucket = bps/8h. t-stats are overlap-inflated (no Newey-West) — ranking
devices only.

| bucket | n (24h) | 24h mean | 24h t | 72h mean | 72h t | 168h mean | 168h t |
|---|---|---|---|---|---|---|---|
| < −20 | 1,786 | +186.9 | 6.9 | +195.6 | 4.8 | +973.5 | 15.3 |
| −20..−10 | 3,703 | +111.4 | 7.3 | +348.3 | 15.9 | +690.6 | 18.4 |
| −10..−5 | 8,988 | +168.8 | 19.9 | +327.0 | 23.1 | +582.6 | 31.2 |
| −2..2 (base) | 612,701 | +13.0 | 17.2 | +36.0 | 26.7 | +91.0 | 42.1 |
| 5..10 | 40,152 | +68.8 | 16.4 | +209.9 | 28.6 | +556.9 | 45.0 |
| 10..20 | 21,912 | +135.1 | 18.8 | +375.5 | 29.9 | +900.5 | 37.6 |
| > 20 | 6,896 | +36.4 | 3.0 | +204.9 | 7.8 | +469.9 | 10.7 |

**Reading:** the carry-reversion hypothesis needs extreme positive funding to precede flat-to-
falling prices. The opposite holds: 10–20 bps/8h funding precedes **+135 bps/24h further
upside** (vs +13 baseline), while a short collects only ~30–60 bps/day of funding. Both tails
are *continuation*, not reversion. The only reversion pocket is M=6-smoothed sustained >20
bps/8h (72h mean −186 bps, t=−5.2, n=4,592 — m6 table in `event_study_m6.csv`), but it is
0.8% of observations and its backtest cells (x=20, M=6) were mediocre (Sharpe ≤ 0.70, most
≤ 0.36). Negative-funding buckets show the biggest forward gains (+169 bps/24h at −10..−5)
— a real-looking squeeze effect, but it makes the strategy a *long-momentum* harvester, not
a carry collector, and that is precisely the direction survivorship inflates most (§5).

## 3. Selection (pre-registered rule, train W1 only)

Rule: eligible iff n_trades ≥ 100, total_return > 0, PF ≥ 1.1, stress return > 0; pick max
annualized Sharpe. Result: **3 of 324 eligible** — all the same cell modulo K
(`abs, x=20, M=1, exit_frac=1.0, trend72`, K∈{3,5,10}).

**Frozen (params.json):** `{form: abs, x: 20.0, m_events: 1, k_max: 3, exit_frac: 1.0, filter: trend72}`

Winner on W1 train (2019-09 → 2023-07): total +175.2%, PF 1.163, Sharpe 0.79, maxDD 47.2%,
702 trades, stress total +123.2%. Funding collected +30.9% cumulative; trade costs −41.8% —
the PnL is mostly price moves, not carry.

## 4. Frozen params on train windows (Phase B; baseline costs)

| window | total_return | PF | maxDD | n_trades | Sharpe | funding PnL | trade cost |
|---|---|---|---|---|---|---|---|
| W1_train (<2023-07) | +175.22% | 1.163 | 47.16% | 702 | 0.79 | +30.91% | −41.83% |
| W2_train (<2024-07) | +101.85% | 1.112 | 47.16% | 742 | 0.54 | +43.03% | −45.83% |
| W3_train (<2025-07) | +114.81% | 1.089 | 52.98% | 936 | 0.51 | +72.46% | −63.43% |

Stress (15 bps/side): +123.17% / +60.43% / +56.36%; PF 1.137 / 1.089 / 1.068.

Incremental periods implied by the expanding windows (params frozen *before* this was
computed): **2023-07→2024-07: −26.7%**; 2024-07→2025-07: +6.4%. The frozen signal already
lost a quarter of equity in the first year after its selection window.

Attribution over full W3 train: short side +10.8% (PF 1.055, Sharpe 0.19) vs long side
+94.0% (PF 1.097). The "carry short" leg — the economically motivated leg — is statistically
indistinguishable from zero over 5.8 years.

## 5. Survivorship

The universe is *today's* top-100 by volume. Only 39 symbols have pre-2023-07 history, and all
39 are survivors; coins that bled to delisting (which spend their decline paying/printing
extreme funding) are absent. Effects: (a) the long-negative-funding side — which produced ~90%
of train PnL — is inflated by construction (buying dips in coins known to have survived);
(b) the short side is *understated* but still ~flat, so the honest read is "shorts ≈ 0, longs
= survivor momentum". The baseline bucket drift (+91 bps/week on every observation) bounds the
ambient bias: a strategy long ~50% of the time inherits roughly +45 bps/week ≈ wide enough to
explain most of the long side's edge over baseline drift.

## 6. Sensitivity: cliff, not plateau — and why viable=false

x-sweep holding the winner's other params fixed (train W1, Sharpe / total return):

| x (bps/8h) | 3 | 5 | 8 | 12 | **20** | 30* | 40* | 60* |
|---|---|---|---|---|---|---|---|---|
| Sharpe | 0.28 | 0.43 | 0.25 | 0.49 | **0.79** | 0.34 | 0.17 | 0.15 |
| total | −31% | +23% | −20% | +55% | **+175%** | +24% | +4% | +3% |

(*post-freeze train-only extension.) The winner is a spike at x=20, decaying on both sides.
More red flags: the trend72 filter *hurts* on average across the grid (mean Sharpe −0.02 vs
+0.49 unfiltered) yet defines the only eligible cell; the `pct` form is uniformly negative
(54/54 combos, best total −27.9%); exit_frac=1.0 (no hysteresis) winning means the "hold while
crowded" mechanism added nothing.

Binding judgment against the promotion criteria:
1. **Pooled OOS PF ≥ 1.2 is unreachable in expectation** — the *best in-sample, selection-biased*
   PF across 372 combos is 1.163, and the frozen cell's PF decays to 1.089 by W3 train.
2. The frozen params are already known (legitimately, from expanding-train reporting) to have
   lost −26.7% over exactly W1's OOS year.
3. The conditional edge the hypothesis requires (reversion after extreme funding) is absent in
   the event study; what edge exists is survivorship-flavored long momentum with 47–53% maxDD.

A true negative: extreme funding on this universe marks *continuation*, and the carry
collected does not cover the adverse drift on the short side nor the costs of harvesting it.

## Files

- `study.py` — reproducible (Phase A/B; `--ext` for the sensitivity extension)
- `combo_log.csv` — all 372 combos with metrics (`eligible`, `phase` columns)
- `event_study_m1.csv`, `event_study_m6.csv` — full tables, horizons {1,4,8,24,72,168}h
- `params.json` — frozen params; `signal.py` — `build_weights(data, params)`
- `frozen_train_metrics.json` — Phase B numbers used above
