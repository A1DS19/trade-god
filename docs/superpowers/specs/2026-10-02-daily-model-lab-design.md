# Model Lab, Experiment 1 — Design (pre-registration)

**Date:** 2026-10-02
**Status:** Design approved by the owner one section at a time, in conversation on 2026-10-02.
This written spec is awaiting the owner's review. Every constant below is fixed before any
real-data run; a change after that run is a new experiment, not an edit.

## Context

The repo became a model lab on 2026-10-02 (`agents/decisions.md`). The evidence behind that is
`docs/superpowers/specs/2026-10-02-trading-model-research-findings.md`:

- **Seconds-scale trading is ruled out.** At retail fees, a round trip costs more than the
  predictable move.
- **Short horizons don't survive costs.** The only after-cost evidence for trained models sits at
  daily-to-weekly horizons, and it is small, decaying and contested.

This repo has already measured parts of this:

- **Cross-sectional momentum (Phase C).** It was real but thin: out-of-sample PF 1.034, with all
  of its edge in the long leg, which survivorship flatters.
- **A 15-minute mean-reversion edge (Phase 2b).** It was smaller than its costs, at −15.19%
  out-of-sample.

What Phase C lacked, and this experiment adds:
- a point-in-time universe that includes delisted contracts;
- a trained model instead of a one-line rule;
- a judgment against the owner's real alternative, which is holding spot BTC.

## Goal

Answer one question with a pre-registered, mechanical verdict: **can a model trained on this
data beat holding spot BTC after costs, at daily-to-weekly horizons?** Three arms race on
identical rules. Alongside them, a forward-only test measures whether TypeSafe's Jev model helps
at decision time.

"No edge found" is an acceptable result, and the most likely one. The gates are built to prefer a
false "no" over a false "yes".

**Out of scope:**
- seconds-scale or intraday trading;
- leverage and shorting;
- placing real orders;
- Jev in the historical test, because it has very likely read about the test period.

## Decisions (owner-approved, 2026-10-02)

| Topic | Decision |
|---|---|
| Win rule | **Risk-adjusted plus alpha:** a higher Sharpe than BTC, a drawdown no deeper, and positive alpha once BTC's own move is removed |
| Out-of-sample test | A one-shot historical walk-forward (contamination declared), then a 26-week live paper record before any money |
| Arms | BTC timing, ETH timing, cross-sectional ranker |
| Ranker universe | Top 50 by trailing 30-day quote volume, point-in-time |
| TypeSafe | Start recording now; tested forward-only as a veto |
| Sections 1–4 | Data, models, verdict rules, code/operations/tests, as written below |

---

## 1. Data

### 1.1 Sources and new datasets

All data comes from Binance's public archive (`data.binance.vision`): monthly zip files, each
checked against the archive's published `.CHECKSUM` before it is stored.

| Dataset (new) | Archive path | Coverage |
|---|---|---|
| `archive_spot_klines_1d` | `data/spot/monthly/klines/{BTCUSDT,ETHUSDT}/1d/` | 2017-08 → latest complete month |
| `archive_spot_klines_1h` | `data/spot/monthly/klines/{BTCUSDT,ETHUSDT}/1h/` | same |
| `archive_um_klines_1d` | `data/futures/um/monthly/klines/{SYM}/1d/` | every USDT-quoted USDⓈ-M perp in the archive listing, live and delisted |
| `archive_um_funding` | `data/futures/um/monthly/fundingRate/{SYM}/` | same symbols |
| `archive_um_premium_1d` | `data/futures/um/monthly/premiumIndexKlines/{SYM}/1d/` | same symbols |

- **Symbol list.** It comes from the archive's S3 listing under
  `data/futures/um/monthly/klines/`. Keep USDT-quoted names and drop dated delivery contracts
  (any name containing `_`). On 2026-10-02 this gave 900 symbols, against 219 in the existing
  warehouse.
- **Fetching.** The fetcher waits at least 0.2 s between requests, skips months already stored,
  and is resumable.
- **No interference.** The existing REST warehouse, its datasets and the 05:30 cron are not
  touched.
- **Reconciliation.** On every symbol and day where both the existing warehouse and the archive
  hold a perp daily close, the closes must match to within 1e-9 relative. A mismatch fails the
  data step.

**Exclusions** (`research/signals/model_lab/exclusions.py`):
- stablecoin and pegged-asset perps;
- index or composite contracts (for example `BTCDOMUSDT`).

The list is built from symbol names only, never from outcomes. It is committed and reviewed by
the owner in the data step, before any model run.

### 1.2 Point-in-time universe (ranker)

**Decision time** is Monday 00:00 UTC. Decisions use daily bars that closed by then, meaning
`open_time` ≤ the preceding Sunday 00:00.

A symbol is **eligible** on decision date *d* when all three hold:
- it has at least 60 daily bars before *d* (`siglib`'s `ELIGIBILITY_DAYS`);
- it has a close on *d* − 1;
- it is not excluded.

**Rank** by the trailing 30-day quote volume (the sum over the 30 daily bars ending *d* − 1). The
**top 50** form that week's universe. If fewer than 20 symbols are eligible, the book holds
nothing that week (a breadth guard for early history).

**Delisting.** When a held symbol's data ends, `siglib.run_backtest` forces its weight to zero.
The last close is Binance's settlement price, so a crash into delisting counts in full.

### 1.3 TypeSafe recorder inputs

- **Sources.** The list is fixed in the recorder's first commit, before its first run:
  - Binance's delisting announcements;
  - the RSS feeds of three major crypto outlets. Candidates: CoinDesk, The Block, Decrypt,
    Cointelegraph.

  Each candidate is checked for a reachable, parseable feed before the list is frozen.
- **Storage.** Items are stored append-only in `research/warehouse/newslog/`, deduplicated by URL,
  with fields `fetched_at` (UTC), the source's own `published_at`, `source`, `title`, `summary`.
- **Scope.** A day's state is every item fetched in the 24 hours before that run.

---

## 2. Arms

### 2.1 Timing (all arms)

- **BTC and ETH** decide every day at 00:00 UTC. They use daily bars, plus hourly bars for
  realised variance, that closed by then. A position earns from that close to the next.
- **The ranker** decides every Monday at 00:00 UTC.
- **Execution.** Every arm executes through `siglib.run_backtest` on a daily grid. Weights
  decided at bar *t* apply to bar *t* + 1, which is the engine's look-ahead contract.

### 2.2 BTC and ETH timing arms

There is one asset per arm: spot `BTCUSDT` or spot `ETHUSDT`. Positions are long-only, at 0–100%
exposure, with no funding.

**Label.** `y_t = 1` if `close[t+7] / close[t] − 1 > 0`, otherwise `0`.

**Direction.**
- A LightGBM binary classifier produces `p_t`.
- The signal is `s_t = 1` if `p_t > 0.5`, otherwise `0`.

**Volatility.**
- Daily realised variance `RV_t` is the sum of squared hourly log returns over the day.
- A HAR regression, refit with each quarterly retrain, forecasts mean daily RV over the next 7
  days:

  ```
  mean(RV[t+1..t+7]) = b0 + b_d·RV_t + b_w·mean(RV[t−6..t]) + b_m·mean(RV[t−29..t])
  ```

- `σ̂_t` is that forecast, annualised by √365.
- The size scale is `v_t = min(1, σ*_t / σ̂_t)`, where `σ*_t` is the median of `σ̂` over the
  trailing 365 days.

**Target exposure.** `e_t = s_t · v_t`.

**Rebalancing.**
- When `s_t` differs from yesterday's `s`, the arm moves to `e_t` immediately.
- Otherwise it moves only if `|e_t − current| > 0.2`, and keeps the current exposure if not.

**Features (21),** each computed at *t* from bars closed by *t*:

| Group | Features |
|---|---|
| Returns | log return over 1, 3, 7, 14, 30, 60, 90, 180 and 365 days |
| Trend | `close / SMA_n − 1` for n = 7, 20, 50, 100, 200 |
| Volatility | `RV_t`, the 7-day mean RV and the 30-day mean RV, each annualised |
| Drawdown | drawdown from the trailing 365-day high |
| Volume | 7-day mean quote volume ÷ 30-day mean quote volume |
| Flow | taker-buy share: 7-day taker-buy quote volume ÷ 7-day quote volume |
| Cross-asset | the other asset's 30-day log return |

**Training rows.** Rows with any missing feature are dropped. The first full row falls in
2018-08, after 365 days of spot history.

### 2.3 Cross-sectional ranker

Perps (`archive_um_*`), long-only, with funding charged.

- **Label.** The 7-day forward return from one Monday 00:00 close to the next, as a percentile
  within that week's universe (ties averaged).
- **Model.** A LightGBM regressor on the percentile label.
- **Book.**
  - Hold the 5 highest predicted scores, at a weight of 0.2 each (gross 1.0). Ties are broken by
    symbol name.
  - Hold them for the week; weights carry forward on the daily grid.
  - Funding is charged event by event.

**Features (25).** Each is computed per symbol at *d*, then turned into a percentile within that
week's universe. Missing values stay missing (LightGBM handles them), and percentiles are taken
over the symbols that have a value.

| Group | Features |
|---|---|
| Returns | log return over 1, 3, 7, 14, 30, 60, 90 days |
| Trend | `close / SMA_n − 1` for n = 7, 20, 50, 100, 200 |
| Volatility | 7-day and 30-day realised volatility of daily returns |
| Risk-adjusted momentum | 30-day return ÷ 30-day volatility |
| Volume | 7-day ÷ 30-day mean quote volume; log 30-day quote volume |
| Flow | 7-day taker-buy share |
| Range | position within the 30-day high–low range; largest daily return in 30 days |
| Funding and basis | mean funding over 7 and 30 days; mean daily premium-index close over 7 days |
| Market | beta to BTC from 90 days of daily returns |
| Age | days since the symbol's first archive bar |

### 2.4 Training and model selection (all arms)

**Refits.** Each model refits at the first decision date of every calendar quarter: the quarter's
first day for the BTC and ETH arms, and the first Monday on or after it for the ranker. It refits
on every row whose label window ended at least 7 days before the refit date
(`t + 7d ≤ refit − 7d`). This purges overlapping labels and adds a 7-day embargo. The same
quarterly refitting continues through the test windows; it is part of the strategy, not a
selection step.

**The only search.** Each arm gets two LightGBM settings, which makes **6 trials** in total, all
logged:

| | `num_leaves` | `max_depth` | `learning_rate` | `n_estimators` | `min_child_samples` | `subsample` | `colsample_bytree` | `reg_lambda` |
|---|---|---|---|---|---|---|---|---|
| S1 | 7 | 3 | 0.03 | 300 | 100 | 0.8 (`subsample_freq` 1) | 0.8 | 1.0 |
| S2 | 15 | 4 | 0.03 | 600 | 50 | 0.8 (`subsample_freq` 1) | 0.8 | 1.0 |

Both settings use `random_state = 20261002`, `deterministic = True` and a fixed thread count.
Every other constant in this spec is fixed and never searched: the 0.5 threshold, the 0.2 band,
the HAR windows, K = 5, the top 50, and the 7-day horizon.

**Selection.**
- The validation period is decision dates from 2021-07-01 to 2023-06-30. It covers two years,
  including the 2022 bear.
- On it, each arm keeps the setting whose book has the higher Sharpe of weekly net returns at
  baseline costs. A tie goes to S1.
- `study.py` asserts that it never loads a bar with `open_time ≥ 2023-07-01`.

**Freeze.** Each arm's `frozen_params.json` records the chosen setting and every constant. It is
committed in its own commit, before `oos_eval.py` runs.

---

## 3. Verdict

### 3.1 Test windows

| Window | Period |
|---|---|
| W1 | 2023-07-01 → 2024-07-01 |
| W2 | 2024-07-01 → 2025-07-01 |
| W3 | 2025-07-01 → 2026-10-01 |
| Pooled | 2023-07-01 → 2026-10-01 |

**Sealing.** The windows stay sealed until all three arms are frozen, then are unsealed once,
together.

**Declared contamination.**
- Phase C evaluated cross-sectional momentum on 2023-07-01 → 2026-06-01, and its results are
  known to the author of this spec.
- Phase 2b evaluated intraday mean reversion on 2025-07-01 → 2026-07-15.

The ranker's feature list follows the published literature (CTREND, Liu–Tsyvinski–Wu), not those
results, but the knowledge cannot be unlearned. This is why live paper trading is the second
gate.

### 3.2 Measurement

- **Weekly returns.** Daily net returns are compounded from Monday 00:00 to Monday 00:00 UTC, for
  every arm and for the benchmark.
- **Benchmark.** Spot `BTCUSDT` buy-and-hold: one entry cost, no funding.
- **Costs.**
  - Baseline: `CostModel()`, 10 bp per side. On spot this assumes the 7.5 bp BNB-discounted fee
    plus 2.5 bp slippage.
  - Stress: `STRESS`, 15 bp per side.
- **Sharpe.** Mean ÷ standard deviation of weekly returns, × √52. The risk-free rate is 0.
- **Max drawdown.** Taken on the daily equity curve, for both the arm and the benchmark.
- **Alpha.** An OLS regression `r_arm = α + β·r_BTC + ε` on weekly returns, with Newey-West
  standard errors at 4 lags.

### 3.3 Gates

An arm passes only if all six gates hold on the pooled window. They are computed mechanically by
`oos_eval.py` into `oos_verdicts.json`.

| Gate | Rule |
|---|---|
| G1 | Sharpe(arm) > Sharpe(BTC) |
| G2 | MaxDD(arm) ≤ MaxDD(BTC) |
| G3 | α > 0 and t(α) ≥ **2.39**: two-sided 5%, Bonferroni-corrected across three arms |
| G4 | α > 0 in at least 2 of W1, W2, W3, each regressed separately |
| G5 | Under `STRESS` costs, Sharpe(arm) > Sharpe(BTC) and α > 0 |
| G6 | Deflated Sharpe ratio ≥ 0.95 |

**How G6 is computed** (Bailey & López de Prado, 2014):
- **N = 6**, the trials in §2.4.
- **The benchmark Sharpe** comes from the variance of those 6 trials' validation Sharpe ratios,
  in weekly units.
- **The tested Sharpe, skewness, kurtosis and T** come from the arm's pooled weekly returns.
- **A sensitivity value** with N = 60 (adding Phase C's 54 combinations) is reported alongside,
  but not gated.

### 3.4 Stop rule

Before the unseal, each arm's frozen setting is checked against G1 and G2 on the validation
period, against BTC over the same period. An arm that fails either is recorded as **failed on
validation**. Its out-of-sample result is never computed.

### 3.5 Comparisons reported, not gated

Every comparison is reported per window and pooled, under both baseline and stress costs, with
turnover, trade count, cost and funding totals:

- **BTC and ETH arms:**
  - buy-and-hold of the arm's own asset;
  - the 200-day SMA filter;
  - volatility sizing alone (`s ≡ 1`), which shows whether the model's direction calls add
    anything;
  - direction alone (`v ≡ 1`).
- **Ranker:**
  - the equal-weight top 50, rebalanced weekly;
  - Phase C's rule (top 5 by 7-day volatility-normalised return, long-only, weekly), which shows
    whether the model beats a one-line rule;
  - BTC buy-and-hold.

### 3.6 After the verdict

**Failing arms** get a findings document, like Phase 2b's, plus an entry in
`agents/decisions.md` and `agents/roadmap.md`.

**Passing arms** start a **26-week live paper record** on the first Monday after the verdict
commit.
- The same frozen code runs on fresh data.
- Decisions are stored append-only, with their timestamps.
- The record passes when, over those 26 weeks, α > 0, Sharpe(arm) ≥ Sharpe(BTC), and every
  operational gap has a logged cause.

Real money comes only after that, as a slice of the under-$1,000 account. That is outside this
spec.

### 3.7 TypeSafe forward test

This test is independent of the arms' verdict. It starts when the recorder ships (phase 1) and
runs for 26 weeks.

**The daily job**, at 00:10 UTC:

1. **Fetch.** Fetch new items from the frozen sources and store them.
2. **Ask Jev.**
   - Send one request per asset in scope, `POST https://api.typesafe.ai/v1/systemone`.
   - The model id is pinned to the version current when phase 1 ships (`jev-1.13.0` at the
     earlier review) and is never the `jev-latest` alias. The id is stored with every answer.
   - The state is the asset name plus the last 24 hours of item titles and summaries, truncated
     to fit 32k tokens.
   - The three yes/no ("noul") questions are frozen as `JEV_QUESTIONS_VERSION = 1`:
     - **Q1:** "Do these items report a hack, exploit or theft of funds directly affecting
       {ASSET} or an exchange where it trades?"
     - **Q2:** "Do these items report a delisting, trading halt or suspension of {ASSET} on a
       major exchange?"
     - **Q3:** "Do these items report a government ban or enforcement action that directly
       restricts trading {ASSET}?"
   - **Veto** when max(p_Q1, p_Q2, p_Q3) ≥ 0.8.
   - Assets in scope are BTC, plus any arm holdings once that arm is in its paper phase.
3. **Mark two paper books at the daily spot close**, taken from Binance's public spot klines
   endpoint (unsigned).
   - **Hold BTC:** always 100%.
   - **Hold BTC with veto:** 0% on veto days, otherwise 100%, at 10 bp per side on each switch.
4. **Store everything:** the state text, the question texts, the model id, the raw response, the
   probabilities and the decision.

**Failure handling.** A failed or invalid Jev call means no veto that day, and it is logged.

**Readout at 26 weeks.** It is descriptive, with no gate:
- the veto count;
- both books' returns and drawdowns;
- BTC's 7-day return after each veto.

The readout decides whether Jev answers enter a later experiment as a feature, where they will
by then have a clean, point-in-time history. **Prerequisite:** `TYPESAFE_API_KEY` and confirmed
access. The earlier review found the site mentioning a waitlist while its console showed billing.

---

## 4. Code, operations, tests

### 4.1 Layout

The layout follows the repo's existing shape. All P&L goes through `siglib`.

```
research/archive_source.py            # archive listing, download, checksum, parse → store.upsert
research/archive_backfill.py          # CLI: python -m research.archive_backfill [--symbols ...]
research/siglib/stats.py              # sharpe, max_drawdown, nw_alpha, deflated_sharpe (reusable)
research/signals/model_lab/
├── exclusions.py                     # frozen exclusion list
├── universe.py                       # point-in-time top-50 panel
├── features.py                       # timing and ranker feature builders
├── labels.py                         # 7-day labels, percentile labels
├── walkforward.py                    # quarterly refit schedule, purge + embargo
├── models.py                         # LightGBM wrappers, HAR volatility model
├── arms.py                           # exposure / weights builders for the three arms + baselines
├── gates.py                          # G1–G6, stop rule
├── study.py                          # train-only: validation, trial log, freeze
├── oos_eval.py                       # one-shot joint unseal → oos_results.json, oos_verdicts.json
└── output/                           # combo_log.csv, frozen_params.json, reports
research/newslog/
├── sources.py                        # frozen feed list + fetchers
├── jev.py                            # Jev client: pinned model, explicit timeout, response checks
└── daily.py                          # CLI: fetch → ask → mark the two paper books
```

### 4.2 Dependencies

- **LightGBM**, at the latest stable version when the plan is written, with the version recorded
  in `frozen_params.json`.
- **Jev over plain HTTPS** (`urllib`), not its SDK. The earlier review found that the SDK
  validates no responses and retries silently. Every response is checked before storage:
  probabilities lie in [0, 1], and the question keys match.

### 4.3 Operations

- **Schedule.** `research.newslog.daily` runs from cron on this machine at 00:10 UTC.
- **Missed runs.** A missed run is logged as a gap and the book keeps its last position. Decisions
  are never backfilled.
- **Key.** `TYPESAFE_API_KEY` lives in `.env`, which is gitignored.
- **No exchange keys.** Nothing places orders.

### 4.4 Tests

The suite makes **no network calls**: archive files, feeds and Jev responses are recorded
fixtures.

- **Look-ahead.** Perturbing any data after *t* never changes a feature, label boundary,
  universe membership or decision at or before *t*.
- **Null and power tests.** On random-walk prices the full pipeline finds no alpha (G3 fails). On
  prices with a planted signal it finds the signal. This proves it can detect an edge and does not
  invent one.
- **Universe.** A symbol never appears before its 60th day, and it leaves after its data ends.
- **Walk-forward.** No training row's label window overlaps the 7 days before a refit date.
- **Stats and gates.** Sharpe, drawdown, Newey-West alpha and deflated Sharpe are checked against
  hand-computed values, and each gate is checked at its boundary.
- **Archive.** The parser and checksum verification are tested, and reconciliation catches a
  planted mismatch.
- **Jev client.** Valid and invalid recorded responses are parsed. An invalid response triggers
  no veto and is logged.
- **Recorder.** Deduplication works, and storage is append-only, so a rerun on the same day adds
  nothing.

---

## Phases (each gated on the one before)

Each phase gets its own implementation plan, written when the phase before it is done.

1. **TypeSafe recorder and the two paper books.** These start recording; the phase needs the key.
2. **Archive datasets, reconciliation, exclusions, point-in-time universe and `siglib/stats.py`.**
   The owner reviews the exclusion list.
3. **BTC and ETH arms:** features, HAR, LightGBM, walk-forward, validation study, then freeze.
4. **Ranker:** features, model, validation study, then freeze.
5. **Joint unseal** with `oos_eval.py`, the verdict, and the findings document.
6. **Paper phase** for any passing arms, plus the TypeSafe 26-week readout.

## Accepted limits

- **Power.** About 3.25 years of weekly returns pin a Sharpe ratio only to about ±0.55. A real but
  modest edge can fail these gates, and that is deliberate.
- **Contamination.** It is declared in §3.1 and handled by the paper gate.
- **Jev.** Its answers can change between runs, so raw answers are stored. Its training cutoff
  makes it forward-only. Text written to persuade can steer it.
- **This machine must be on** for the daily job. Gaps are logged, never filled.
- **Instruments differ.** The BTC and ETH arms are judged on spot prices, and the ranker on perps.
  Their prices differ only by the small basis.
- **No market impact is modelled.** Positions under $1,000 do not move these markets.
