# Intraday Edge-Hunt — Findings (Phase 2a)

**Run date:** 2026-07-15 (dev machine, warehouse-only — no network)
**Verdict:** 1 SURVIVOR of 6 families — `mr_vwap` (short-horizon mean reversion vs VWAP, long side only).

## 1. Protocol

Pre-registered in `docs/superpowers/plans/2026-07-15-intraday-edge-hunt.md` (commit `b073f50`).
All rule/family/CLI code was committed **before** this run: harness + survivor rule `e146e75`/`8b5ba04`,
families `17ed720`/`d9f2e36`, CLI `24288ed`. Data: `klines_15m` + `funding`, strictly before
`TRAIN_END = 2025-07-01` — 24 of 30 intraday-universe symbols had train data (6 listed after ~2025-05),
87,552 bars. OOS (2025-07-01 → 2026-07-15) remains sealed for Phase 2b.

Survivor rule (mechanical): for ≥1 pre-declared (extreme bucket, horizon) pair — directional edge
> 0.0016 (round-trip cost), |t| ≥ 3 (descriptive), count ≥ 500, split-half sign consistency.
No deviations from the pre-registered protocol occurred.

## 2. Verdict table

| Family | Verdict | Best pair (bucket @ bars) | dir. edge | t | count | halves (h1/h2) | Failed on |
|---|---|---|---|---|---|---|---|
| **mr_vwap** | **SURVIVOR** | z<-3 @ 16 (4h) | **+0.171%** | 8.0 | 10,560 | +0.291% / +0.078% | — |
| funding_window | REJECTED | f>+.1% @ 32 (8h) | +0.260% | −1.4 | 2,871 | +0.21% / +3.9% (dir.) | \|t\| < 3 |
| vol_impulse | REJECTED | i>1.5 @ 32 | +0.239% | 0.9 | 60 | +0.80% / −0.006% | count, t, split-half |
| breakout | REJECTED | break_up @ 96 (24h) | +0.071% | 13.4 | 67,242 | −0.03% / +0.16% | edge < cost, split-half |
| time_of_day | REJECTED | h21 @ 4 (1h) | +0.063% | 17.2 | 67,256 | +0.066% / +0.061% | edge < cost |
| squeeze | REJECTED | .4-.6 @ 16 | −0.346% | 311* | 142,150 | −0.31% / −0.34% | hypothesis contradicted |

\* abs-mode t-stat on massively overlapping windows — meaningless magnitude, listed for completeness.

## 3. Per-family notes

- **mr_vwap (SURVIVOR, long side only).** Deep oversold (z<-3 vs 24h VWAP) bounces: positive edge at
  every horizon (1/4/16/32 bars), crossing the cost hurdle only at 16 bars (4h). The passing pair
  clears the hurdle by a **thin 7% cushion** (0.171% vs 0.16%). Split halves are both positive but
  decay ~4× (0.29% → 0.078%) — the raw h2 edge alone would NOT clear costs. The **short side is
  inverted**: z>3 (deep overbought) shows +0.18% CONTINUATION at 16–32 bars — shorting overbought
  loses; consistent with this system's live experience with shorts. Only the long side proceeds.
- **funding_window.** The economically largest near-miss (+0.26% short drift after extreme positive
  funding) but t = −1.4 and the h2 half is dominated by outliers (−3.9% mean) — a few crash events,
  not a stable effect. Honest reject; Phase C daily-carry rejection stands at intraday too.
- **vol_impulse.** Extreme signed impulse (|i|>1.5) fires only 60–131 times in 2.5 years — too rare
  to test (pre-registered count gate did its job). Volume-only proxy; no historical OI exists.
- **breakout.** Statistically real continuation (t=13) but 0.07% — under half the cost hurdle, and
  sign-unstable across halves. 15m breakout momentum cannot pay retail costs.
- **time_of_day.** Hour-21-UTC drift is the most stable pattern in the scan (t=17, halves nearly
  identical) but at 0.063%/hour it is 2.5× below costs. Real, uncapturable.
- **squeeze.** Hypothesis contradicted: compressed vol predicts LESS subsequent movement than the
  middle buckets, not expansion. Cleanly falsified.

## 4. Known caveats

1. **Survivorship-biased universe** — top-30 selected on 2026-07-15 volume. This flatters
   dip-buying signals specifically (coins that ultimately thrived make oversold bounces look
   better), so the mr_vwap edge is treated as an upper bound. Phase 2b must gate on point-in-time
   universe snapshots where possible.
2. **Overlap-inflated t-stats** — descriptive ranking devices only (the reason the bar is 3, not 2).
3. **Family 5 is volume-only** — Binance serves ~30 trailing days of OI; no OI history exists in train.
4. **Funding staleness** — rate assigned at bar open (conservative by ≤1 bar).
5. **Edge decay** — the surviving pair's second-half edge (0.078%) is below the cost hurdle on its
   own; the effect may be fading. This is the primary risk Phase 2b's OOS windows will adjudicate.

## 5. Phase 2b scope

**Proceeds:** `mr_vwap` long side only — strategy backtest built on the verified `siglib` engine
(entry: z<-3; horizon region ~4h; long-only), evaluated against the pre-registered pass bar
(net PF ≥ 1.15, ≥ 100 OOS trades, positive in ≥ 2 of 3 OOS windows over 2025-07→2026-07-15,
max DD ≤ 20%) at baseline (5+3 bps/side) and stress costs, with a 5m robustness check and
point-in-time universe gating.

**Does not proceed:** all five rejected families; the z>3 short side (edge is continuation, not
reversion — and a fresh momentum hypothesis on it would be post-hoc, outside this pre-registration).

If the mr_vwap backtest fails the OOS bar, the pre-agreed fallback applies: build the Phase 3
engine anyway and paper-trade the best candidate — no live money without shadow validation.
