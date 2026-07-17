# Swing Live Validation Plan

Snapshot of where the swing strategy stands, what to expect forward, how to
monitor it, and when to intervene.

Written 2026-04-11 after a full day of validation work that uncovered
several issues with the previous benchmarks. Pair with
`docs/swing_strategy_current.md` §12 (the honest benchmark tables).

---

## TL;DR

- **Live bot state:** 0 trades since the current 9-coin / ADX=32 / MIN_CONFIDENCE=0.80 config was deployed (2026-04-08). The 62 pre-existing trades in the DB are from a *different* LLM-era strategy and should be ignored for forward analysis.
- **Honest forward-looking ROI:** **15–22% annual** (not the 22.90% / 76.75% in-sample numbers). Walk-forward validation exposed a ~41pp overfit premium.
- **Trust anchors:** DOGE and IOTA are the only coins that survived walk-forward testing. The other 7 in the live universe are speculative.
- **Validation window:** 15–30 live trades for meaningful signal. At current frequency (~2–4 trades/month aggregate) that's **6–12 months**.
- **Action now:** let it run. Check periodically. Don't touch anything until tripwires trigger or enough data accumulates.

---

## Current state (snapshot 2026-04-11)

| Field | Value |
|---|---|
| Universe | DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA |
| Capital | $67.50 (9 × $7.50 mid-sizing) |
| Leverage | 5× |
| Live trades (current config) | **0** |
| Open positions | 0 |
| Last cycle | HOLD across all 9 coins, most ADX < 32 or daily EMA unaligned |
| Market regime | Choppy/sideways with bullish DI bias but no daily confirmation |

The bot is correctly holding. The restrictive config means we'll see weeks with zero trades in regimes like this. That's working as designed.

---

## Honest forward expectations

**Use 15–22% annual as the planning range. NOT 63% or 76%.**

| Estimate | Annual ROI | Where it comes from |
|---|---:|---|
| **Best honest forward** | **~22%** | Walk-forward #2 OOS on 2025-2026 (clean train/test split) |
| With drift haircut | 15–20% | 22% minus a conservative adjustment for the training-test gap widening in forward deployment |
| Pessimistic | 5–10% | Midpoint of WF#1 failure (4%) and WF#2 pass (22%) |
| In-sample ceiling | 63–77% | `docs/swing_strategy_current.md` §12a numbers — *NOT a forecast* |

**Drawdown expectation:** 25–40% of capital at some point. The strategy has 25% stop-loss hit rate. Strings of 4–5 stop-outs in choppy weeks are within the normal distribution. Don't panic unless drawdown exceeds **30% of capital** (see hard-stop tripwire below).

**Trade frequency:** ~2–4 trades/month aggregate across all 9 coins. Entire weeks with zero signals will be common. That's the cost of the strictness that produces the edge.

---

## Live monitoring queries

**Always filter with `?since=2026-04-08T00:00:00Z`** to exclude pre-config-change data. The endpoints are on `http://54.169.100.56:8000`.

### Quick checks

```bash
# Aggregate stats for the current-config window
curl -sS "http://54.169.100.56:8000/swing/stats?since=2026-04-08T00:00:00Z"

# All closed trades under current config
curl -sS "http://54.169.100.56:8000/swing/trades?since=2026-04-08T00:00:00Z&limit=500"

# Open positions (no filter needed — only current-config positions can be open)
curl -sS "http://54.169.100.56:8000/swing/trades?status=open"

# Health
curl -sS "http://54.169.100.56:8000/health"
```

### Useful filters

```bash
# Trades for a specific coin
curl -sS "http://54.169.100.56:8000/swing/trades?coin=DOGE&since=2026-04-08T00:00:00Z"

# Longs only
curl -sS "http://54.169.100.56:8000/swing/trades?direction=long&since=2026-04-08T00:00:00Z"

# Shorts only
curl -sS "http://54.169.100.56:8000/swing/trades?direction=short&since=2026-04-08T00:00:00Z"

# Rolling last 24h stats
curl -sS "http://54.169.100.56:8000/swing/stats?since=$(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)"
```

### Swing agent logs

```bash
docker compose logs -f swing                              # live tail
docker compose logs --timestamps swing > /tmp/swing.txt   # dump for analysis
```

The HOLD reasons tell you which gate is blocking entries. Typical pattern during chop: `ADX=27.3<32, -DI=12.1<=+DI=27.2 | daily=mixed`.

---

## Validation tripwires

Agree on these NOW, before emotions get involved after seeing real losses.

### Checkpoint 1 — first 5 trades
**Goal:** sanity check, no disasters.
- **Pass:** ≥ 1 winner out of 5
- **Fail:** 0 winners → investigate immediately. This is below the 5th percentile of the backtest distribution.

### Checkpoint 2 — first 15 trades
**Goal:** first real edge signal.
- **Pass:** PF > 1.5 AND WR > 45%
- **Fail on PF:** losses are larger than expected — check for systemic slippage or fill issues
- **Fail on WR:** entries are worse than expected — check whether funding/OI/L-S are meaningfully diverging from backtest neutral assumption

### Checkpoint 3 — first 30 trades
**Goal:** statistical significance begins.
- **Target:** annual-equivalent ROI in [8%, 38%] range
- **Below 5%:** strategy isn't working live despite backtest. Decide between de-risking and stopping.
- **Above 38%:** probably lucky streak; don't add capital.

### Hard stop — max drawdown tripwire
**If live drawdown ≥ 30% of capital, stop the bot immediately and investigate.**

Don't wait for statistical significance. 30% DD is already close to the backtest's worst-case and beyond typical psychological tolerance. Shutting off and investigating is cheaper than riding it further.

---

## Decision tree at each milestone

### After ~5 trades
- Any winners at all? → continue
- 0 winners, all SL hits → STOP, check for bugs in live execution vs backtest

### After ~15 trades
- PF > 1.5 and annual-equivalent ROI > 10% → **continue as-is**
- PF 1.0–1.5 → **keep running but no capital increase**
- PF < 1.0 → **de-risk to DOGE + IOTA only** (the 2 walk-forward-robust coins)

### After ~30 trades — the real decision
- **Edge holds (ROI ≥ 15% annual):** consider implementing **quarterly re-screening** — every 3 months, re-run the top-100 screen with a 4-year training window ending at the deployment date, update COINS. This operationalizes the only walk-forward result that passed (WF#2 with continuous training).
- **Edge marginal (ROI 5–15%):** **de-risk to DOGE + IOTA only**. Smaller surface area, higher confidence. Matches what walk-forward actually validated.
- **Edge broken (ROI < 5%):** **stop, investigate**. Likely causes: backtest under-modeled slippage/funding/OI, or the screen-time market regime has ended.

### After 90+ days with zero trades
Strategy isn't getting signals in this regime. Three options:
1. Keep waiting (regime will eventually change)
2. Run a dry-run of `ADX=30` in backtest on the most recent 3 months — if it would have produced 3–5 trades with reasonable PnL, consider lowering the gate as an experiment
3. Accept that the edge is real but opportunity-sparse, and deploy less capital to avoid idle funds

Don't lower MIN_CONFIDENCE below 0.80 — that degrades trade quality, which is the opposite of what we want.

---

## Things NOT to do

- **Don't widen filters to speed up trade frequency.** Lower ADX or lower MIN_CONFIDENCE dilutes the edge. You'll get faster data on a worse strategy — no useful information.
- **Don't add capital until 30+ live trades match backtest expectations.** The $67.50 size is experiment scale, not production scale. Don't treat it as production until it earns that trust.
- **Don't add new coins based on sentiment or market news.** If you want to change the universe, run the screener first. Walk-forward any additions. Document the reasoning.
- **Don't panic during drawdowns below 30%.** The backtest says 37% DD is within the historical distribution. Only the 30% hard-stop matters for intervention.
- **Don't extrapolate the 76.75% 1-year number in any planning context.** It's in-sample, selection-biased. Use 15–22% everywhere — in your head, in plans, in any conversation.
- **Don't retune the strategy based on short live samples.** Anything below 15 trades is noise. Resist the urge to tweak.
- **Don't quietly revert the DOT removal or re-add other marginal coins.** If you want to, run walk-forward validation first.

---

## Open threads (pick up when you have time)

Ordered by information value, not effort:

| Thread | Value | Effort | Unlocks |
|---|---|---|---|
| **Live-vs-backtest reconciliation** after trades accumulate | High | 1 hr | Direct validation that backtest predicts live |
| **Historical funding/OI/L-S loaded into backtest** (instead of neutralized) | High | 1–2 days | Biggest simulation gap — tells us if backtest is honest about real-market signals |
| **Quarterly re-screening automation** | High | 2–3 hrs | Operationalizes the only walk-forward-validated finding |
| **Bootstrap PF confidence intervals** on the 117 backtest trades | Medium | 30 min | Honest error bars on backtest PF |
| **Coin exclusion sensitivity** (drop each coin, measure edge) | Medium | 15 min | Identifies load-bearing coins, concentration risk |
| **Reproduce April 2026 screening** for the 5 "mystery" coins | Medium | 1 hr | Answers how 1000SHIB/RUNE/1000FLOKI/TURBO/IP were originally selected |
| **Forward-walk test of WF#2 methodology**: screen 2022-2025, test 2025-Q2 only | Medium | 1 hr | Shorter gap, tests if the WF#2 pass generalizes |

**Skip for now:** bootstrapping and coin exclusion add marginal information over what we already have. Do them only if live data starts diverging from backtest in confusing ways.

---

## Key commits this session (branch `docs/walk-forward-validation`)

| Commit | What |
|---|---|
| `a4d02ea` | HOLD-gate unit tests + CLAUDE.md swing section refresh |
| `26b501c` | V2_MIN_CONFIDENCE 0.85→0.80 (was under-reporting live by ~21%) |
| `999eabb` | Remove DOT (net-negative at true live threshold) |
| `4a4a258` | Parameterize V2_MIN_ADX_ENTRY via env var |
| `b4c952b` | `--rate-limit-delay` CLI param for large-universe runs |
| `8c213a5` | `/swing/trades` and `/swing/stats` API endpoints |
| `de5cf10` | Walk-forward validation + honest §12 benchmarks |

---

## Cross-references

- `docs/swing_strategy_current.md` — strategy spec, §12a in-sample / §12b OOS benchmarks
- `docs/coin_screening_and_selection.md` — screening methodology from 2026-04-09
- `docs/swing_tuning_notes_2026-04-03.md` — historical exit-strategy tuning context
- `CLAUDE.md` — project overview, config reference (updated 2026-04-11)
- `app/swing/config.py` — live config + coin-selection notes block
- `app/swing/backtest_replay/` — backtest engine, strategy, screener, stats

---

## One-sentence summary

You have a strategy with probably-real 15–22% annual edge on DOGE + IOTA and speculative upside from 7 other coins, running flat while the market chops, and the only thing to do now is wait for live trades to validate or invalidate the backtest.
