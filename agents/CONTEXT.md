# CONTEXT — canonical vocabulary

Use these words, and avoid the listed synonyms. The CoinPicks vocabulary (report, commit gate,
citation, frozen formula, ledger, and so on) was archived with its code on 2026-10-02. It now lives
at `legacy/coinpicks/CONTEXT.md`.

## The data

**Warehouse** — the gitignored parquet store under `research/warehouse/`.
- One file per dataset per symbol: Binance USDⓈ-M perpetuals, each since its listing.
- A daily cron refreshes it.
- It is the only market data an experiment may read.

_Avoid_: "database", "the DB".

**Point-in-time (PIT)** — known at the moment it is used, never later.
- A PIT universe ranks symbols by what was observable on that date, including contracts that have
  since been delisted.
- A universe picked by today's ranking is survivorship bias.

_Avoid_: "historical" when PIT is meant.

**Eligibility** — the rule that admits a symbol to the universe on a date, by listing age and
liquidity rank.
- It is evaluated PIT and takes effect from the next day.
- In code: `eligible_mask`, `pit_top30_mask`.

## The experiment

**Experiment** — one pre-registered question with one verdict. A failed experiment is a result,
and it is recorded the same way as a passed one.

**Pre-registration** — committing the spec, gates and code **before** the first real-data run, so
the git log proves which came first.

**Train / OOS** — the two periods, split at `TRAIN_END`.
- Everything is chosen on train.
- **OOS** (out-of-sample) stays sealed until the freeze is committed.

**Freeze** — committing the parameters chosen on train (`frozen_params.json`) before OOS is
touched.

**Unseal** — the one-shot OOS evaluation of the frozen parameters, judged mechanically against the
pre-registered gates. A variant is never unsealed twice.

**Gate** — a pass/fail criterion fixed at pre-registration: profit factor, share of windows
positive, t-stat, stress survival, deflated Sharpe.

_Avoid_: "target", "goal".

**Trial** — one parameter, feature or model combination evaluated on train.
- Every trial is counted.
- The count matters because the deflated Sharpe and the probability of backtest overfitting both
  depend on how many were tried.

**Stress** — the pre-registered cost variant, with slippage doubled. A survivor must pass it too.

## Money

**bp** — basis point, 0.01%. Costs and edges are quoted in bp; always say whether per side or per
round trip.

**Round trip** — entry plus exit. At VIP-0 on Binance USDⓈ-M it costs 10 bp taker or 4 bp maker.

**Edge** — expected return per trade, net of the cost model. A gross edge is always called gross.

**Hurdle** — the round-trip cost an edge must clear before it counts as an edge.

**Forward record** — paper results accumulated in real time, after the freeze.
- It is the one kind of evidence that cannot have been overfit.
- Real money waits for one.

## Standing rulings

**Model lab** — this repo's purpose since 2026-10-02: train models and test them against the
warehouse, under pre-registration.

_Avoid_: "trading bot", "system".

**Seconds-scale trading** — ruled out on 2026-10-02.
- At retail fee tiers the round trip costs more than the predictable move.
- It is not re-opened without new evidence on the cost side. A better model is not new evidence.
