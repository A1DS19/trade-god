# Model Lab Phase 3 — BTC and ETH Timing Arms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Experiment 1's BTC and ETH timing arms, run their train-only validation study (4 of
the experiment's 6 trials), and freeze each arm before a single sealed bar is read.

**Architecture:** Five small modules under `research/signals/model_lab/`, one job each:
- `labels.py` holds the 7-day up label.
- `walkforward.py` holds the quarterly refit schedule, with its purge and embargo.
- `features.py` builds daily RV from hourly bars, plus the 21 timing features.
- `models.py` holds the two pre-registered LightGBM settings and the HAR volatility forecast.
- `arms.py` walks the refits, turns each day's outputs into a held weight under the 0.2 band, and
  prices the book through `siglib.run_backtest`.

On top of these, `gates.py` adds the stop rule, and `study.py` runs the four trials, picks each
arm's setting and writes the freeze. The plan also amends `siglib.stats.weekly_returns`, which
now sums each week's daily returns instead of compounding them. That change is the owner's ruling
and is described below.

**Tech Stack:** Python 3.14.
- pandas 3.0.3, numpy 2.4.4 and pyarrow 24.0.0, all already pinned.
- **LightGBM 4.7.0 is new.** It is the latest stable release (2026-07-18), its wheels are
  `py3-none`, and it brings in scipy and narwhals. It runs through its native `lightgbm.train`,
  so no scikit-learn is needed.
- **Verified on 2026-10-12.** It installed into a scratch folder against this machine's pandas and
  numpy. The spec's parameter names resolve to LightGBM's own (for example `min_child_samples` to
  `min_data_in_leaf`, checked through its alias table and a fitted tree's leaf counts). Two fits
  give identical predictions.

**Spec:** `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`, §2.1–2.2, §2.4, §3.2,
§3.4 and §4.1–4.4.
- Task 1 writes into the spec everything this plan fixes that the spec left open (listed below).
  Approving this plan approves that text.
- The weekly-returns change (item 11) is the owner's ruling.

**How this plan was checked.** Every code block below was assembled into a scratch copy of the
repo:
- **The suite.** 241 tests pass. That is the 195 that exist today, one of them rewritten for summed
  weeks, plus 46 new ones.
- **Mutants.** 15 deliberate bugs were planted, one at a time, and every one was caught. They
  include a missing embargo, a refit that trains up to its own date, a feature that peeks a day
  ahead, HAR forecasts from a later refit, a non-strict band, threshold or tie-break, sizing above
  1, a book that misses its first day, and a study that loads the sealed windows.

## What this plan fixes before the first real-data run

| # | What the spec left open | This plan's answer | Why | Task |
|---|---|---|---|---|
| 1 | How daily RV treats missing hours (handed on by phase 2) | Squared log returns between consecutive hourly closes, counted on the day of the later bar; a return across missing hours stays in. A day with no hourly bar has no RV | The square of a 2-hour return carries both hours' variance, so the day's sum stays unbiased. Spot 1h has 28 gaps per asset, the longest 32 hours on 2018-02-08; every day still has a bar | 1, 5 |
| 2 | `t + 7d ≤ refit − 7d`: which t? | A row is daily bar t (its open_time), decided at its close (t + 1 day) and labelled at t + 8 days. A refit at R trains on it when t + 15 days ≤ R | The spec's t is the decision time | 1, 4 |
| 3 | "each annualised" for the three RV features | √(365 · mean daily RV), the units of σ̂ | A tree splits a monotone transform identically; this keeps one unit throughout | 1, 5 |
| 4 | "drawdown from the trailing 365-day high" | From the highest daily close over [t − 364, t] | The arms trade at closes | 1, 5 |
| 5 | How HAR is fitted, and where σ*'s history comes from | OLS with an intercept, under the same purge and embargo, refit every quarter from 2018-01-01. σ̂ is point-in-time: each day's value comes from the fit in force at its decision. A forecast below 0 counts as 0, which gives v = 1 | σ* needs 365 days of σ̂ before the first decision (2021-07-01) | 1, 6, 7 |
| 6 | Where the book starts, and what "current exposure" means | Flat at its first decision; "current" is the weight last decided | `run_backtest` ignores drift (its pre-drift convention) | 1, 7 |
| 7 | A decision whose features are incomplete | The run stops with an error naming the day | A silent flat day would hide a data hole | 1, 7 |
| 8 | LightGBM's version and how it is called | 4.7.0 through `lightgbm.train`, with the table's names (aliases), objective `binary`, `force_row_wise = True` and `num_threads = 1` | LightGBM's documentation asks for row- or column-wise forcing with `deterministic`; one thread is the simplest fixed count | 1, 3, 6 |
| 9 | Selection when a book has no Sharpe ratio | It ranks below a book that has one; a tie still goes to S1 | An arm that never trades must not win by default | 1, 9 |
| 10 | Where the trial log and the freeze live | `output/combo_log.csv` holds every trial; each arm gets `output/{btc,eth}/frozen_params.json`, with status `frozen` or `failed_on_validation` | Phase 4 appends its two trials to the same log; G6 needs all six | 1, 9 |
| 11 | **Weekly returns: compounded or summed (the owner's ruling)** | **Summed:** a week's return is the sum of its daily net returns | See below | 1, 2 |

**Why weekly returns are summed.**
- **The cause.** `run_backtest` applies a decided weight to every day's return, which is the same
  as rebalancing back to it daily at no cost. Compounding those days into weeks makes a book
  nonlinear in BTC's returns.
- **What that does to an arm with no skill.** Phase 2 found that a constant 50% BTC position
  passes G1, G2 and G4, with t(α) = 2.20 in W1, close to G3's 2.39. In this plan's scratch tests,
  half of a toy BTC series compounded to a Sharpe ratio of 43.7 against BTC's 41.2, with
  t(α) = 5.9.
- **What summing changes.** A book holding w of BTC is exactly w times BTC's week. Its Sharpe ratio
  then equals BTC's, so it fails G1, and its α is 0, so it fails G3–G5.
- **What stays the same.** Drawdown is still taken on the compounded daily equity curve (G2).
- **Where it reaches.** Phase 3's selection and stop rule use weekly Sharpe ratios, so the ruling
  is needed now, not only at the unseal.

**Power, measured on synthetic markets.** These use the plan's own pipeline and generator, with
5 seeds per row:

| A planted signal of … | BTC arm's hit rate | Book vs buy-and-hold Sharpe | Found? |
|---|---|---|---|
| 0 (random walk) | 0.44–0.55 | −1.6 to +0.2 | no, as it should be |
| 0.3%/day | 0.50–0.55 | −0.5 to +0.5 | no |
| 0.5%/day | 0.50–0.56 | +0.2 to +0.7 | weakly |
| 1%/day | 0.59–0.67 | +1.8 to +3.0 | yes, every seed |

The signal is a hidden regime visible in the taker-buy share. Overlapping 7-day labels leave about
200 independent samples per refit. An edge has to be large before this pipeline sees it. That is
what the spec's power limit predicts, and it is why "no edge found" is the likely outcome.

## Global Constraints

These are copied from the spec, and every task's requirements include them.

**Execution and costs**
- "Every arm executes through `siglib.run_backtest` on a daily grid. Weights decided at bar *t*
  apply to bar *t* + 1, which is the engine's look-ahead contract."
- "There is one asset per arm: spot `BTCUSDT` or spot `ETHUSDT`. Positions are long-only, at
  0–100% exposure, with no funding."
- "Baseline: `CostModel()`, 10 bp per side."

**The model**
- Label: "`y_t = 1` if `close[t+7] / close[t] − 1 > 0`, otherwise `0`."
- Direction: "The signal is `s_t = 1` if `p_t > 0.5`, otherwise `0`."
- HAR: "`mean(RV[t+1..t+7]) = b0 + b_d·RV_t + b_w·mean(RV[t−6..t]) + b_m·mean(RV[t−29..t])`".
- Sizing: "`σ̂_t` is that forecast, annualised by √365", and "`v_t = min(1, σ*_t / σ̂_t)`, where
  `σ*_t` is the median of `σ̂` over the trailing 365 days".
- "`e_t = s_t · v_t`."
- Rebalancing: "When `s_t` differs from yesterday's `s`, the arm moves to `e_t` immediately.
  Otherwise it moves only if `|e_t − current| > 0.2`, and keeps the current exposure if not."
- Features: the 21 of §2.2's table, "each computed at *t* from bars closed by *t*". "Rows with any
  missing feature are dropped."

**Training**
- "Each model refits at the first decision date of every calendar quarter … on every row whose
  label window ended at least 7 days before the refit date (`t + 7d ≤ refit − 7d`)."
- "The only search. Each arm gets two LightGBM settings … all logged." Both use
  "`random_state = 20261002`, `deterministic = True` and a fixed thread count". "Every other
  constant in this spec is fixed and never searched."
- Selection: "The validation period is decision dates from 2021-07-01 to 2023-06-30 … each arm
  keeps the setting whose book has the higher Sharpe of weekly net returns at baseline costs. A
  tie goes to S1."
- "`study.py` asserts that it never loads a bar with `open_time ≥ 2023-07-01`."
- "Each arm's `frozen_params.json` records the chosen setting and every constant. It is committed
  in its own commit, before `oos_eval.py` runs."

**Statistics**
- Stop rule: "each arm's frozen setting is checked against G1 and G2 on the validation period,
  against BTC over the same period. An arm that fails either is recorded as **failed on
  validation**."
- Sharpe is the "mean ÷ sample standard deviation (ddof = 1) of weekly returns, × √52 … An arm
  whose returns do not vary has no Sharpe ratio, and it fails every gate that uses one."
- "Max drawdown. Taken on the daily equity curve."

**Dependencies and tests**
- "LightGBM, at the latest stable version when the plan is written, with the version recorded in
  `frozen_params.json`."
- "The suite makes **no network calls**."
- "Look-ahead. Perturbing any data after *t* never changes a feature, label boundary … or decision
  at or before *t*." "Null and power tests." "No training row's label window overlaps the 7 days
  before a refit date."

**Repo rules**
- Pre-registration: Task 1's spec amendment is committed before the first real-data run (Task 10).
  Train is the only place choices are made, and every trial is counted.
- Commit straight to `main`, with **no AI attribution** and a concise, why-focused message.
- Chain test commands with `&&`. `python -m pytest -q` is green before anything is called done.

## Review Focus

These are the five inputs most likely to bite that no other test pins, each with what a reasonable
person would expect:

1. **Hourly gaps.** Spot 1h has 28 gaps per asset, among them 32 hours on 2018-02-08, plus 43
   off-the-hour bars from 2018-02-09 to 02-11. Expect the day's RV to keep the return across the
   gap, never to drop it or leave the day empty. Pinned in Task 5.
2. **A missing daily bar inside the decision window.** Expect the run to stop and name the day,
   not to hold a silent flat position. Pinned in Task 7.
3. **A probability of exactly 0.5**, which LightGBM returns when a model has no split and its
   training set is balanced. Expect the arm to stay out (`p > 0.5`, strictly). Pinned in Task 7.
4. **A HAR forecast below zero**, which OLS can extrapolate. Expect σ̂ = 0 and v = 1, never NaN,
   inf or a negative size. Pinned in Tasks 5 and 6.
5. **A setting whose book never trades.** Expect it to have no Sharpe ratio, to lose the selection
   to a setting that has one, and to fail G1. Pinned in Tasks 8 and 9.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md` | modify (Task 1) | everything this plan fixes, as spec text |
| `research/siglib/stats.py` | modify (Task 2) | weekly returns are summed |
| `requirements-research.txt` | modify (Task 3) | `lightgbm==4.7.0` |
| `research/siglib/data.py` | modify (Task 3) | `KLINE_COLS` gains `taker_buy_quote_volume` |
| `research/signals/model_lab/labels.py` | create (Task 4) | the 7-day up label |
| `research/signals/model_lab/walkforward.py` | create (Task 4) | refit dates, purge and embargo, the refit in force |
| `research/signals/model_lab/features.py` | create (Task 5) | daily grid, daily RV, the 21 features |
| `research/signals/model_lab/models.py` | create (Task 6) | LightGBM settings and fit; HAR; σ*, v |
| `research/signals/model_lab/arms.py` | create (Task 7) | rebalancing, the walk-forward decisions, the book |
| `research/signals/model_lab/gates.py` | create (Task 8) | the stop rule (G1, G2) |
| `research/signals/model_lab/study.py` | create (Task 9) | the validation study CLI and the freeze |
| `research/signals/model_lab/output/` | create (Task 10) | `combo_log.csv`, `{btc,eth}/frozen_params.json` |
| `tests/research/conftest.py` | modify (Task 7) | `make_spot_market`, a synthetic BTC/ETH spot market |
| `tests/research/test_siglib_stats.py` | modify (Task 2) | |
| `tests/research/test_siglib_data.py` | modify (Task 3) | |
| `tests/research/test_model_lab_walkforward.py` | create (Task 4) | |
| `tests/research/test_model_lab_features.py` | create (Task 5) | |
| `tests/research/test_model_lab_models.py` | create (Task 6) | |
| `tests/research/test_model_lab_arms.py` | create (Task 7) | |
| `tests/research/test_model_lab_gates.py` | create (Task 8) | |
| `tests/research/test_model_lab_study.py` | create (Task 9) | |
| `CLAUDE.md`, `agents/roadmap.md` | modify (Task 10) | the arms, the study command, the test count |

---

### Task 1: Write what this plan fixes into the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`

**Interfaces:** none (documentation). Later tasks implement this text. Where code and spec
disagree, the spec wins and the code is fixed.

- [ ] **Step 1: Record the amendment in the status lines.** After the line that ends
  `is fetched from them too; see §1.1.`, add the following. Use the date on which the owner
  approved this plan.

```markdown
**Amended 2026-10-12** (owner's approval of the phase 3 plan, and the owner's ruling on weekly
returns): §2.2, §2.4, §3.2 and §4.2 fix what the BTC and ETH arms need before any real-data run:
daily RV across missing hours, row and refit timing, HAR's fit and history, the book's first
day, incomplete rows, LightGBM's version and settings, selection without a Sharpe ratio, where
the freeze lives, and weekly returns summed rather than compounded.
```

- [ ] **Step 2: §2.2 Volatility.** Replace the bullet
  `` - Daily realised variance `RV_t` is the sum of squared hourly log returns over the day. ``
  with:

```markdown
- Daily realised variance `RV_t` is the sum of squared hourly log returns over the day. Each
  return runs between consecutive hourly closes and counts on the day of the later bar. A return
  across missing hours stays in, since its square carries their variance: spot 1h has 28 gaps per
  asset, the longest 32 hours on 2018-02-08. A day with no hourly bar has no RV.
```

  Then replace the bullet `` - `σ̂_t` is that forecast, annualised by √365. `` with:

```markdown
- HAR is fitted by OLS with an intercept, under §2.4's purge and embargo, at every quarter's first
  day from 2018-01-01 on, so that σ̂ exists point-in-time for the 365 days σ* needs before the
  first decision. Each day's σ̂ comes from the fit in force at its decision.
- `σ̂_t` is that forecast, annualised by √365: `√(365 · forecast)`. A forecast below 0, which only
  extrapolation can produce, counts as 0, so that `v_t = 1`.
```

- [ ] **Step 3: §2.2 Rebalancing, features and training rows.** After the bullet that ends
  `and keeps the current exposure if not.`, add:

```markdown
- The book starts flat at its first decision, and "current" is the weight last decided:
  `run_backtest` ignores drift.
```

  In the features table, replace the Volatility and Drawdown rows with:

```markdown
| Volatility | `RV_t`, the 7-day mean RV and the 30-day mean RV, each annualised as `√(365 · RV)` |
| Drawdown | the close's drawdown from the highest daily close over the trailing 365 days |
```

  After `2018-08, after 365 days of spot history.` add: `A decision whose row misses a feature
  stops the run with an error, rather than holding a silent flat day.`

- [ ] **Step 4: §2.4.** After `This purges overlapping labels and adds a 7-day embargo.` add:

```markdown
Here t is the decision time. A row is daily bar t′, keyed by its open_time: it is decided at
t′'s close, t′ + 1 day, and its label is known at t′ + 8 days, so a refit at R trains on it when
t′ + 15 days ≤ R.
```

  After `` Both settings use `random_state = 20261002`, `deterministic = True` and a fixed thread
  count. `` add:

```markdown
They run through LightGBM 4.7.0's native `lightgbm.train`, which accepts the table's names as
aliases (`n_estimators` sets the boosting rounds), with objective `binary`,
`force_row_wise = True` (LightGBM asks for it whenever `deterministic` is set) and
`num_threads = 1`.
```

  After `baseline costs. A tie goes to S1.` add: `A book whose returns do not vary has no Sharpe
  ratio, and it ranks below one that has.`

  After `` committed in its own commit, before `oos_eval.py` runs. `` add:

```markdown
It lives at `research/signals/model_lab/output/{arm}/frozen_params.json`, beside the trial log
`output/combo_log.csv` that every trial joins. An arm that fails the stop rule (§3.4) is frozen
with the status `failed_on_validation`.
```

- [ ] **Step 5: §3.2, the owner's ruling.** Replace the **Weekly returns** bullet with:

```markdown
- **Weekly returns.** Daily net returns are summed from Monday 00:00 to Monday 00:00 UTC, for
  every arm and for the benchmark (owner's ruling, 2026-10-12; they were compounded).
  `run_backtest` holds a decided weight at no cost every day, and compounding such days gave a
  constant fraction of BTC, with no skill, a higher Sharpe ratio than BTC's and a positive alpha:
  a constant 50% position passed G1, G2 and G4, with t(α) = 2.20 in W1. Summed, a book holding w
  of BTC is exactly w times BTC's week. Only complete weeks count. A window's leftover days at
  either end enter its daily drawdown, but no weekly statistic.
```

  Use the date of the owner's ruling.

- [ ] **Step 6: §4.2.** After `` with the version recorded in `frozen_params.json`. `` add:
  `` That is 4.7.0 (released 2026-07-18), pinned in `requirements-research.txt`. ``

- [ ] **Step 7: Check and commit.** Read §2.2, §2.4 and §3.2 through once. Nothing else in the
  spec may say "compounded", and §2.4's six trials must still add up.

```bash
grep -n "compound" docs/superpowers/specs/2026-10-02-daily-model-lab-design.md
git add docs/superpowers/specs/2026-10-02-daily-model-lab-design.md
git commit -m "docs: fix the timing arms' open definitions before their first run

Daily RV across missing hours, row and refit timing, HAR's history, the book's
start, LightGBM's pinned settings, and weekly returns summed (owner's ruling):
compounding gave a constant fraction of BTC a free Sharpe ratio and alpha."
```

  Expected from the grep: one line, the ruling's own "(…they were compounded)".

---

### Task 2: Weekly returns are summed

**Files:**
- Modify: `research/siglib/stats.py` (module docstring and `weekly_returns`)
- Modify: `tests/research/test_siglib_stats.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `stats.weekly_returns(daily: pd.Series) -> pd.Series`, with the same signature, index
  and complete-week rule; each value is now the sum of the week's seven daily returns.

- [ ] **Step 1: Write the failing tests.** In `tests/research/test_siglib_stats.py`, replace
  `test_weekly_returns_compound_complete_monday_weeks_only` with these two tests:

```python
def test_weekly_returns_sum_complete_monday_weeks_only():
    # Saturday 2024-01-06 through Tuesday 2024-01-23: two complete weeks between partial ends.
    returns = [0.01] * 18
    returns[12] = -0.02  # Thursday 2024-01-18, inside the second week
    weekly = stats.weekly_returns(_daily(5, returns))
    assert list(weekly.index) == [MONDAY + 7 * DAY_MS, MONDAY + 14 * DAY_MS]
    assert weekly.tolist() == pytest.approx([0.07, 0.04], rel=1e-12)


def test_a_constant_fraction_of_btc_scores_exactly_like_btc():  # no skill, so nothing to find
    btc = _daily(0, [0.03, -0.02, 0.05, -0.04, 0.01, 0.02, -0.03] * 6)
    btc.iloc[::5] += 0.01  # weeks that differ, so the Sharpe ratio exists
    half = stats.weekly_returns(0.5 * btc)
    assert stats.sharpe(half) == pytest.approx(stats.sharpe(stats.weekly_returns(btc)), rel=1e-12)
    assert stats.nw_alpha(half, stats.weekly_returns(btc)).alpha == 0.0
```

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_siglib_stats.py`
  Expected: 2 failed. The first gets `[0.0721…, 0.0403…]` (compounded), and the second gets
  unequal Sharpe ratios, 43.7 against 41.2.

- [ ] **Step 3: Implement.** In `research/siglib/stats.py`, replace the docstring bullet
  `- a week runs from Monday 00:00 to Monday 00:00 UTC, and only complete weeks count;` with:

```python
- a week runs from Monday 00:00 to Monday 00:00 UTC, its return is the sum of its daily returns,
  and only complete weeks count;
```

  Then replace `weekly_returns` with:

```python
def weekly_returns(daily: pd.Series) -> pd.Series:
    """Sum daily returns into Monday-to-Monday weeks, indexed by each week's Monday (ms).

    Summed, not compounded (spec §3.2, as amended). run_backtest holds a decided weight at no cost
    every day, and compounding such days turns a constant fraction of BTC into a higher Sharpe
    ratio than BTC's and a positive alpha, with no skill. Summed, a book holding w of BTC is
    exactly w times BTC's week. A week missing any of its seven days is dropped, so a window's
    leftover days at either end never form a partial week."""
    weeks = week_start(daily.index.to_numpy(dtype="int64"))
    grouped = daily.groupby(weeks)
    complete = grouped.size() == 7
    return grouped.sum()[complete]
```

- [ ] **Step 4: Run the suite.**

  Run: `python -m pytest -q`
  Expected: all pass (196). The Newey-West and deflated-Sharpe reference tests take weekly series
  directly, so they don't change.

- [ ] **Step 5: Commit.**

```bash
git add research/siglib/stats.py tests/research/test_siglib_stats.py
git commit -m "feat: sum weekly returns instead of compounding them

A constant fraction of BTC, rebalanced daily for free by run_backtest, compounded
into a higher Sharpe ratio than BTC's and a positive alpha with no skill. Summed,
it scores exactly like BTC (owner's ruling)."
```

---

### Task 3: LightGBM, and the taker-buy column the flow feature needs

**Files:**
- Modify: `requirements-research.txt`
- Modify: `research/siglib/data.py:18-19` (`KLINE_COLS`)
- Modify: `tests/research/test_siglib_data.py`

**Interfaces:**
- Produces: `lightgbm` importable at 4.7.0, and `siglib.data.KLINE_COLS` including
  `taker_buy_quote_volume`, so `load_klines` returns it. The archive spot files have stored the
  column since phase 2; `load_klines` dropped it.

- [ ] **Step 1: Write the failing test.** In `tests/research/test_siglib_data.py`, the `_klines`
  helper gains the column, after `"taker_buy_volume": [1.2] * len(times),`:

```python
            "taker_buy_quote_volume": [0.9] * len(times),
```

  Then append this test:

```python
def test_klines_carry_the_taker_buy_quote_volume(tmp_warehouse):  # the timing arms' flow feature
    _write(tmp_warehouse, "archive_spot_klines_1d", "BTCUSDT", _klines([BASE], [1.0]))
    df = data.load_klines("BTCUSDT", "1d", source="archive_spot_klines")
    assert df["taker_buy_quote_volume"].tolist() == [0.9]
```

- [ ] **Step 2: Run it to see it fail.**

  Run: `python -m pytest -q tests/research/test_siglib_data.py`
  Expected: 1 failed, with `KeyError: 'taker_buy_quote_volume'`.

- [ ] **Step 3: Implement.** In `research/siglib/data.py`:

```python
KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "quote_volume", "taker_buy_volume", "taker_buy_quote_volume", "trades"]
```

- [ ] **Step 4: Pin and install LightGBM.** Append to `requirements-research.txt`:

```text
# Experiment 1's arms (research/signals/model_lab/models.py), at the latest stable release when
# phase 3's plan was written (2026-10-12). Each arm's frozen_params.json records the version. Its
# native API needs no scikit-learn; it brings in scipy and narwhals.
lightgbm==4.7.0
```

  Run: `python -m pip install -r requirements-research.txt && python -c "import lightgbm; print(lightgbm.__version__)"`
  Expected: `4.7.0`. pip installs into the user site, as it did for the other pins.

- [ ] **Step 5: Run the suite.**

  Run: `python -m pytest -q`
  Expected: all pass (197).

- [ ] **Step 6: Commit.**

```bash
git add requirements-research.txt research/siglib/data.py tests/research/test_siglib_data.py
git commit -m "feat: pin LightGBM 4.7.0 and load taker-buy quote volume

The timing arms' flow feature is the 7-day taker-buy share of quote volume; the
archive stores the column but load_klines dropped it."
```

---

### Task 4: The 7-day label and the walk-forward schedule

**Files:**
- Create: `research/signals/model_lab/labels.py`
- Create: `research/signals/model_lab/walkforward.py`
- Test: `tests/research/test_model_lab_walkforward.py`

**Interfaces:**
- Produces:
  - `labels.HORIZON_DAYS = 7`, and `labels.up_label(close: pd.Series) -> pd.Series`. Values are
    1.0, 0.0 or NaN, and `close` sits on a complete daily grid.
  - `walkforward.EMBARGO_DAYS = 7`.
  - `walkforward.quarter_starts(start, end) -> list[int]`: epoch ms at 00:00 UTC, beginning with
    the quarter that holds `start`, and excluding `end`.
  - `walkforward.trains_refit(open_time, refit: int) -> np.ndarray[bool]`.
  - `walkforward.model_in_force(open_time, refits: list[int]) -> np.ndarray[int]`: a position in
    `refits`, or −1.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_walkforward.py`:

```python
"""Labels and the walk-forward schedule (spec §2.2, §2.4): a row is daily bar t, decided at
t + 1 day; its label is known at t + 8 days; a refit at R trains on it only if t + 8 days ≤ R − 7
days, so no training label overlaps the 7 days before a refit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.signals.model_lab import walkforward as wf
from research.signals.model_lab.labels import up_label

DAY = 86_400_000
Q3 = 1_782_864_000_000  # 2026-07-01 00:00 UTC


def test_the_label_is_whether_the_close_seven_days_on_is_higher():
    close = pd.Series([10.0, 11, 9, 10, 10, 10, 10, 10, 12, 9, 10])
    # close[7] = 10 vs close[0] = 10 is not higher; close[8] = 12 > 11; close[9] = 9 = 9
    assert up_label(close).tolist()[:4] == [0.0, 1.0, 0.0, 0.0]
    assert up_label(close).iloc[4:].isna().all()  # close[t+7] not known yet


def test_quarter_starts_begin_with_the_quarter_in_force():
    days = wf.quarter_starts("2026-05-15", "2027-01-01")
    assert days == [Q3 - 91 * DAY, Q3, Q3 + 92 * DAY]  # 2026-04-01, 07-01, 10-01


def test_quarter_starts_exclude_the_end():
    assert wf.quarter_starts("2026-07-01", "2026-10-01") == [Q3]


def test_a_refit_trains_on_rows_whose_label_ended_seven_days_before_it():
    t = np.array([Q3 - 15 * DAY, Q3 - 14 * DAY])  # labels known on Q3 - 7 and Q3 - 6 days
    assert wf.trains_refit(t, Q3).tolist() == [True, False]


def test_no_training_label_overlaps_the_seven_days_before_a_refit():  # spec §4.4
    t = Q3 + np.arange(-400, 400) * DAY
    for refit in wf.quarter_starts(Q3 - 300 * DAY, Q3 + 300 * DAY):
        trained = t[wf.trains_refit(t, refit)]
        label_ends = trained + 8 * DAY
        assert (label_ends <= refit - 7 * DAY).all()
        assert trained.max() == refit - 15 * DAY  # and nothing older is lost


def test_a_decision_uses_the_refit_in_force_at_its_close():
    refits = [Q3 - 91 * DAY, Q3]
    t = np.array([Q3 - 93 * DAY, Q3 - 2 * DAY, Q3 - DAY, Q3 + 50 * DAY])
    # bar Q3 - 1 day closes at Q3, when the Q3 refit is in force
    assert wf.model_in_force(t, refits).tolist() == [-1, 0, 1, 1]
```

  Two values come from the calendar. 2026-07-01 00:00 UTC is 1,782,864,000,000 ms. 2026-04-01 is
  91 days earlier (April 30 + May 31 + June 30), and 2026-10-01 is 92 days later.

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_walkforward.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.walkforward'`.

- [ ] **Step 3: Implement** `research/signals/model_lab/labels.py`:

```python
"""Labels for the timing arms (spec 2026-10-02 §2.2).

Rows are daily bars indexed by open_time on a complete daily grid (features.daily_grid). A row's
decision is made when its bar closes, at 00:00 UTC the next day."""

from __future__ import annotations

import pandas as pd

HORIZON_DAYS = 7


def up_label(close: pd.Series) -> pd.Series:
    """1.0 when close[t+7] / close[t] - 1 > 0, else 0.0, and NaN while close[t+7] is unknown.

    `close` must sit on a complete daily grid, so that 7 rows on is 7 days on."""
    ahead = close.shift(-HORIZON_DAYS) / close - 1.0
    return (ahead > 0).astype(float).where(ahead.notna())
```

  and `research/signals/model_lab/walkforward.py`:

```python
"""The quarterly refit schedule, with purged labels and an embargo (spec 2026-10-02 §2.4).

A row is daily bar t, keyed by its open_time. Its decision is made when the bar closes, at t + 1
day, and its 7-day label is known at t + 8 days. A refit at R trains on a row only if that label
window ended at least 7 days before R: the spec's `t + 7d ≤ refit − 7d`, with t the decision
time."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS
from research.siglib.data import to_ms
from research.signals.model_lab.labels import HORIZON_DAYS

EMBARGO_DAYS = 7


def quarter_starts(start, end) -> list[int]:
    """Every quarter's first day from the quarter holding `start` up to `end` (exclusive), as
    epoch ms at 00:00 UTC. The first one is the refit in force at `start`."""
    first = pd.Timestamp(to_ms(start), unit="ms").to_period("Q").start_time
    days = pd.date_range(first, pd.Timestamp(to_ms(end), unit="ms"), freq="QS", inclusive="left")
    return [to_ms(day) for day in days]


def trains_refit(open_time, refit: int) -> np.ndarray:
    """Which rows a refit at `refit` may train on: label window over 7 days before it."""
    return np.asarray(open_time) + (1 + HORIZON_DAYS + EMBARGO_DAYS) * DAY_MS <= refit


def model_in_force(open_time, refits: list[int]) -> np.ndarray:
    """Each row's position in `refits` of the latest refit at or before its decision time
    (t + 1 day), or -1 before the first."""
    return np.searchsorted(np.asarray(refits), np.asarray(open_time) + DAY_MS, side="right") - 1
```

- [ ] **Step 4: Run the tests.**

  Run: `python -m pytest -q tests/research/test_model_lab_walkforward.py`
  Expected: 6 passed.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/labels.py research/signals/model_lab/walkforward.py tests/research/test_model_lab_walkforward.py
git commit -m "feat: the timing label and the quarterly walk-forward schedule

A refit trains only on labels known 7 days before it, so no training label
overlaps the days just before a refit."
```

---

### Task 5: Daily RV and the 21 timing features

**Files:**
- Create: `research/signals/model_lab/features.py`
- Test: `tests/research/test_model_lab_features.py`

**Interfaces:**
- Consumes: `research.config.DAY_MS`.
- Produces:
  - `features.RETURN_DAYS`, `SMA_DAYS`, `ANNUAL_DAYS = 365` and `TIMING_FEATURES`, the 21
    column names in the spec's order.
  - `features.daily_grid(daily: pd.DataFrame) -> pd.DataFrame`: indexed by open_time, one row per
    day.
  - `features.daily_rv(hourly: pd.DataFrame) -> pd.Series`: indexed by day (ms).
  - `features.annualised_vol(mean_daily_rv: pd.Series) -> pd.Series`, which is √(365 · max(x,
    0)).
  - `features.timing_features(bars, rv, other_close) -> pd.DataFrame`, with columns
    `TIMING_FEATURES` and `bars`'s index.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_features.py`:

```python
"""The 21 timing features (spec §2.2, as amended): computed at bar t from bars closed by t, on a
complete daily grid; daily RV sums squared hourly log returns, keeping returns across gaps."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import features as feat

DAY = 86_400_000
HOUR = 3_600_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _bars(n_days, growth=0.001, quote=None):
    """Daily klines with close = e^(growth · i), and taker buys 60% of quote volume."""
    quote = np.ones(n_days) if quote is None else np.asarray(quote, dtype=float)
    return pd.DataFrame({"open_time": BASE + np.arange(n_days) * DAY,
                         "close": np.exp(growth * np.arange(n_days)),
                         "quote_volume": quote, "taker_buy_quote_volume": 0.6 * quote})


def _features(bars, rv=1e-4, other_growth=0.002):
    grid = feat.daily_grid(bars)
    other = pd.Series(np.exp(other_growth * np.arange(len(grid))), index=grid.index)
    return feat.timing_features(grid, pd.Series(rv, index=grid.index), other)


def test_the_feature_list_is_the_spec_table():
    assert len(feat.TIMING_FEATURES) == 21
    assert feat.TIMING_FEATURES[:9] == [f"ret_{n}" for n in (1, 3, 7, 14, 30, 60, 90, 180, 365)]


def test_daily_rv_keeps_a_return_across_missing_hours():
    hourly = pd.DataFrame({
        "open_time": [BASE, BASE + HOUR, BASE + 3 * HOUR, BASE + DAY, BASE + 3 * DAY],
        "close": np.exp([0.0, 0.01, 0.04, 0.02, 0.02]),
    })
    rv = feat.daily_rv(hourly)
    # day 0: 0.01² + 0.03² (the 2-hour return across the missing hour); day 1: 0.02²; day 3: 0
    assert rv.index.tolist() == [BASE, BASE + DAY, BASE + 3 * DAY]  # day 2 has no bar, so no value
    assert rv.tolist() == pytest.approx([1e-3, 4e-4, 0.0])


def test_feature_values_on_a_steady_climb():
    quote = np.r_[np.ones(393), np.full(7, 4.0)]
    row = _features(_bars(400, quote=quote)).iloc[-1]
    for n in (1, 3, 7, 14, 30, 60, 90, 180, 365):
        assert row[f"ret_{n}"] == pytest.approx(0.001 * n)
    assert row["trend_7"] == pytest.approx(1 / np.mean(np.exp(-0.001 * np.arange(7))) - 1)
    assert row[["rv_1", "rv_7", "rv_30"]].tolist() == pytest.approx([math.sqrt(365e-4)] * 3)
    assert row["drawdown_365"] == 0.0  # a new high
    assert row["volume_7_30"] == pytest.approx(4.0 / ((23 + 7 * 4.0) / 30))
    assert row["taker_buy_7"] == pytest.approx(0.6)
    assert row["other_ret_30"] == pytest.approx(0.06)


def test_drawdown_is_from_the_highest_close_of_the_last_365_days():
    bars = _bars(400)
    bars.loc[399, "close"] = 0.8 * bars.loc[398, "close"]
    assert _features(bars).iloc[-1]["drawdown_365"] == pytest.approx(-0.2)


def test_the_first_complete_row_comes_after_365_days():
    X = _features(_bars(400))
    assert X.notna().all(axis=1).idxmax() == BASE + 365 * DAY


def test_a_missing_day_blanks_every_window_that_spans_it():
    bars = _bars(400).drop(index=390)
    X = _features(bars)
    assert X.loc[BASE + 390 * DAY, ["ret_1", "trend_7", "volume_7_30"]].isna().all()
    assert np.isnan(X.loc[BASE + 396 * DAY, "trend_7"])  # its 7-day window spans day 390
    assert not np.isnan(X.loc[BASE + 397 * DAY, "trend_7"])


def test_future_bars_never_change_a_feature():  # spec §4.4 look-ahead
    rng = np.random.default_rng(20261002)
    bars = _bars(500, quote=rng.uniform(1, 2, 500))
    before = _features(bars)
    cut = 450
    later = bars.copy()
    later.loc[cut:, ["close", "quote_volume", "taker_buy_quote_volume"]] *= rng.uniform(
        0.5, 2.0, (500 - cut, 3))
    after = _features(later)
    pd.testing.assert_frame_equal(before.iloc[:cut], after.iloc[:cut])
    assert not before.iloc[cut:].equals(after.iloc[cut:])
```

  The hand values:
  - **The RV test.** Day 0's returns are 0.01 and then 0.03, the second spanning the missing
    hour, so its RV is 0.0001 + 0.0009 = 1e-3. Day 1 gets one return of −0.02 (4e-4), and day 3
    gets 0. Day 2 has no bar, so it gets no value.
  - **The volume ratio on the climb.** The last 30 days hold 23 days at 1 and 7 at 4.
  - **`trend_7` on a series growing 0.1% a day.** The close over its 7-day mean is
    1 / mean(e^(−0.001k), k = 0..6).

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_features.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.features'`.

- [ ] **Step 3: Implement** `research/signals/model_lab/features.py`:

```python
"""The 21 timing features of the BTC and ETH arms (spec 2026-10-02 §2.2, as amended).

Each is computed at daily bar t from bars closed by t's close. Bars sit on a complete daily grid,
so a missing day leaves NaN in every window that spans it, and the arms never train on or decide
from such a row."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS

RETURN_DAYS = (1, 3, 7, 14, 30, 60, 90, 180, 365)
SMA_DAYS = (7, 20, 50, 100, 200)
ANNUAL_DAYS = 365
TIMING_FEATURES = [
    *(f"ret_{n}" for n in RETURN_DAYS),
    *(f"trend_{n}" for n in SMA_DAYS),
    "rv_1", "rv_7", "rv_30",
    "drawdown_365",
    "volume_7_30",
    "taker_buy_7",
    "other_ret_30",
]


def daily_grid(daily: pd.DataFrame) -> pd.DataFrame:
    """One asset's daily klines indexed by open_time, one row per day from its first bar to its
    last; a day without a bar is a row of NaN."""
    bars = daily.set_index("open_time").sort_index()
    return bars.reindex(np.arange(bars.index[0], bars.index[-1] + DAY_MS, DAY_MS))


def daily_rv(hourly: pd.DataFrame) -> pd.Series:
    """Realised variance per day: squared log returns between consecutive hourly closes, summed
    over the day that holds the later bar.

    A return across missing hours stays in, so its square carries their variance and the day's
    sum stays unbiased. A day with no hourly bar has no value."""
    bars = hourly.sort_values("open_time")
    squared = np.log(bars["close"]).diff() ** 2
    day = (bars["open_time"] // DAY_MS) * DAY_MS
    return squared.groupby(day.to_numpy()).sum(min_count=1)


def annualised_vol(mean_daily_rv: pd.Series) -> pd.Series:
    """√(365 · RV): a mean daily variance as annual volatility. A negative value, which only an
    extrapolating forecast can produce, counts as 0."""
    return np.sqrt(ANNUAL_DAYS * mean_daily_rv.clip(lower=0.0))


def timing_features(bars: pd.DataFrame, rv: pd.Series, other_close: pd.Series) -> pd.DataFrame:
    """The 21 features at every row of `bars` (a daily_grid frame). `rv` is daily_rv of the same
    asset and `other_close` the other asset's daily closes, both indexed by day."""
    close = bars["close"]
    log_close = np.log(close)
    rv = rv.reindex(bars.index)
    quote = bars["quote_volume"]
    other = np.log(other_close.reindex(bars.index))
    cols = {f"ret_{n}": log_close - log_close.shift(n) for n in RETURN_DAYS}
    cols |= {f"trend_{n}": close / close.rolling(n).mean() - 1.0 for n in SMA_DAYS}
    cols["rv_1"] = annualised_vol(rv)
    cols["rv_7"] = annualised_vol(rv.rolling(7).mean())
    cols["rv_30"] = annualised_vol(rv.rolling(30).mean())
    cols["drawdown_365"] = close / close.rolling(365).max() - 1.0
    cols["volume_7_30"] = quote.rolling(7).mean() / quote.rolling(30).mean()
    cols["taker_buy_7"] = bars["taker_buy_quote_volume"].rolling(7).sum() / quote.rolling(7).sum()
    cols["other_ret_30"] = other - other.shift(30)
    return pd.DataFrame(cols, index=bars.index)[TIMING_FEATURES]
```

- [ ] **Step 4: Run the tests.**

  Run: `python -m pytest -q tests/research/test_model_lab_features.py`
  Expected: 7 passed.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/features.py tests/research/test_model_lab_features.py
git commit -m "feat: daily realised variance and the timing arms' 21 features

A return across missing hours stays in its day's RV, so outages neither empty a
day nor hide its variance; a missing daily bar blanks every window over it."
```

---

### Task 6: The models: LightGBM's two settings, HAR, and the size scale

**Files:**
- Create: `research/signals/model_lab/models.py`
- Test: `tests/research/test_model_lab_models.py`

**Interfaces:**
- Consumes: `labels.HORIZON_DAYS` (Task 4); `features.annualised_vol` in the tests (Task 5).
- Produces:
  - `models.SETTINGS` (`"S1"`, `"S2"`, the spec's table), `FIXED_PARAMS`, `THRESHOLD = 0.5`,
    `HAR_TERMS` and `SIGMA_STAR_DAYS = 365`.
  - `models.lightgbm_params(setting) -> dict`: everything `lightgbm.train` gets, objective
    included.
  - `models.fit_direction(X, y, setting) -> lightgbm.Booster`; its `.predict(X)` returns p.
  - `models.har_terms(rv) -> pd.DataFrame`, with columns `rv_d, rv_w, rv_m`.
  - `models.har_target(rv) -> pd.Series`.
  - `models.fit_har(terms, target) -> np.ndarray`, the coefficients (b0, b_d, b_w, b_m).
  - `models.har_forecast(coef, terms) -> pd.Series`.
  - `models.size_scale(sigma_hat: pd.Series) -> pd.Series`, which is v.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_models.py`:

```python
"""The timing arms' models (spec §2.2, §2.4, as amended): the two pre-registered LightGBM settings,
deterministic; HAR by OLS; σ̂ annualised by √365; v = min(1, σ*/σ̂) with σ* a 365-day median."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import models
from research.signals.model_lab.features import annualised_vol


def test_the_settings_are_the_spec_table():  # §2.4: the only search, fixed before any run
    common = {"learning_rate": 0.03, "subsample": 0.8, "subsample_freq": 1,
              "colsample_bytree": 0.8, "reg_lambda": 1.0}
    assert models.SETTINGS == {
        "S1": {"num_leaves": 7, "max_depth": 3, "n_estimators": 300, "min_child_samples": 100,
               **common},
        "S2": {"num_leaves": 15, "max_depth": 4, "n_estimators": 600, "min_child_samples": 50,
               **common},
    }
    assert models.FIXED_PARAMS["random_state"] == 20261002
    assert models.FIXED_PARAMS["deterministic"] is True


def _learnable(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 3)), columns=["a", "b", "c"])
    y = (X["a"] + rng.normal(scale=0.5, size=n) > 0).astype(float)
    return X, y


def test_the_classifier_is_deterministic_and_runs_every_round():
    X, y = _learnable()
    first, second = (models.fit_direction(X, y, "S1") for _ in range(2))
    assert np.array_equal(first.predict(X), second.predict(X))
    assert first.num_trees() == 300


def test_the_classifier_learns_a_real_pattern():
    X, y = _learnable()
    p = models.fit_direction(X, y, "S2").predict(X)
    assert ((p > models.THRESHOLD) == y).mean() > 0.8


def test_har_target_is_the_next_seven_days_mean():
    rv = pd.Series(np.arange(20, dtype=float))
    assert models.har_target(rv).iloc[0] == pytest.approx(np.mean(np.arange(1, 8)))
    assert models.har_target(rv).iloc[13:].isna().all()  # day 19 is the last known


def test_har_recovers_known_coefficients():
    rng = np.random.default_rng(1)
    rv = pd.Series(rng.uniform(1e-4, 4e-4, 400))
    terms = models.har_terms(rv)
    target = 1e-5 + 0.3 * terms["rv_d"] + 0.4 * terms["rv_w"] + 0.2 * terms["rv_m"]
    coef = models.fit_har(terms, target)
    assert coef == pytest.approx([1e-5, 0.3, 0.4, 0.2])
    assert models.har_forecast(coef, terms).iloc[-1] == pytest.approx(target.iloc[-1])


def test_sigma_hat_is_annualised_and_never_negative():
    assert annualised_vol(pd.Series([1e-4, -1e-5])).tolist() == pytest.approx(
        [math.sqrt(365e-4), 0.0])


def test_size_scale_cuts_exposure_only_above_the_median():
    sigma = pd.Series(np.r_[np.full(365, 0.5), 1.0, 0.25, 0.0])
    v = models.size_scale(sigma)
    assert v.iloc[:364].isna().all()  # σ* needs 365 days of σ̂
    assert v.iloc[364] == 1.0
    assert v.iloc[365] == pytest.approx(0.5)  # σ̂ twice the median
    assert v.iloc[366:].tolist() == [1.0, 1.0]  # below the median, or 0: never above 1
```

  Each size-scale value checks against a median, which is 0.5 at every one of these rows:
  - When σ̂ is twice the median, v is 0.5.
  - When σ̂ is half the median, v would be 2; it is capped at 1.
  - When σ̂ is 0, v would be infinite; it is capped at 1.

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_models.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.models'`.

- [ ] **Step 3: Implement** `research/signals/model_lab/models.py`:

```python
"""The timing arms' models (spec 2026-10-02 §2.2, §2.4, as amended): a LightGBM classifier for
direction, and the HAR forecast of volatility that sizes the position."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from research.signals.model_lab.labels import HORIZON_DAYS

# The only search (§2.4). The names are LightGBM's scikit-learn aliases, which lightgbm.train
# accepts as they are; n_estimators is the number of boosting rounds.
SETTINGS = {
    "S1": {"num_leaves": 7, "max_depth": 3, "learning_rate": 0.03, "n_estimators": 300,
           "min_child_samples": 100, "subsample": 0.8, "subsample_freq": 1,
           "colsample_bytree": 0.8, "reg_lambda": 1.0},
    "S2": {"num_leaves": 15, "max_depth": 4, "learning_rate": 0.03, "n_estimators": 600,
           "min_child_samples": 50, "subsample": 0.8, "subsample_freq": 1,
           "colsample_bytree": 0.8, "reg_lambda": 1.0},
}
# Fixed for both settings. LightGBM's documentation asks for force_row_wise (or col-wise)
# whenever deterministic is on, and one thread makes the fixed thread count trivially the same
# on every machine.
FIXED_PARAMS = {"random_state": 20261002, "deterministic": True, "force_row_wise": True,
                "num_threads": 1, "verbose": -1}
THRESHOLD = 0.5
HAR_TERMS = ["rv_d", "rv_w", "rv_m"]
SIGMA_STAR_DAYS = 365


def lightgbm_params(setting: str) -> dict:
    """Everything lightgbm.train is given for a setting, as frozen_params.json records it."""
    return {"objective": "binary", **SETTINGS[setting], **FIXED_PARAMS}


def fit_direction(X: pd.DataFrame, y: pd.Series, setting: str) -> lgb.Booster:
    """A binary classifier of the 7-day label under one of the two settings."""
    params = lightgbm_params(setting)
    rounds = params.pop("n_estimators")
    return lgb.train(params, lgb.Dataset(X, label=y), num_boost_round=rounds)


def har_terms(rv: pd.Series) -> pd.DataFrame:
    """The HAR regressors at each day: RV_t, mean(RV[t−6..t]) and mean(RV[t−29..t])."""
    return pd.DataFrame({"rv_d": rv, "rv_w": rv.rolling(7).mean(), "rv_m": rv.rolling(30).mean()})


def har_target(rv: pd.Series) -> pd.Series:
    """What HAR forecasts: mean(RV[t+1..t+7]), the next 7 days' mean daily variance."""
    return rv.rolling(HORIZON_DAYS).mean().shift(-HORIZON_DAYS)


def fit_har(terms: pd.DataFrame, target: pd.Series) -> np.ndarray:
    """OLS coefficients (b0, b_d, b_w, b_m), fitted on the rows where all four values exist."""
    rows = terms.assign(target=target).dropna()
    x = np.column_stack([np.ones(len(rows)), rows[HAR_TERMS].to_numpy()])
    coef, *_ = np.linalg.lstsq(x, rows["target"].to_numpy(), rcond=None)
    return coef


def har_forecast(coef: np.ndarray, terms: pd.DataFrame) -> pd.Series:
    """b0 + b_d·RV_t + b_w·RV_week + b_m·RV_month at each row of `terms`."""
    return coef[0] + terms[HAR_TERMS] @ coef[1:]


def size_scale(sigma_hat: pd.Series) -> pd.Series:
    """v_t = min(1, σ*_t / σ̂_t), where σ* is the median σ̂ over the trailing 365 days.

    A σ̂ of 0 gives v = 1, the limit as the forecast falls. NaN until 365 days of σ̂ exist."""
    sigma_star = sigma_hat.rolling(SIGMA_STAR_DAYS).median()
    return (sigma_star / sigma_hat).clip(upper=1.0)
```

- [ ] **Step 4: Run the tests.**

  Run: `python -m pytest -q tests/research/test_model_lab_models.py`
  Expected: 7 passed.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/models.py tests/research/test_model_lab_models.py
git commit -m "feat: the timing arms' LightGBM settings and HAR volatility model

The two settings are the spec's only search, pinned by a test; fits are
deterministic, and v never exceeds 1, even on a zero or negative forecast."
```

---

### Task 7: The arms: the band, the walk-forward decisions and the book

**Files:**
- Create: `research/signals/model_lab/arms.py`
- Modify: `tests/research/conftest.py` (docstring, two imports, `make_spot_market` and the
  `spot_market` fixture)
- Test: `tests/research/test_model_lab_arms.py`

**Interfaces:**
- Consumes:
  - `features.daily_grid`, `daily_rv`, `timing_features` and `annualised_vol` (Task 5);
  - `models.fit_direction`, `har_terms`, `har_target`, `fit_har`, `har_forecast`, `size_scale`,
    `THRESHOLD` and `SIGMA_STAR_DAYS` (Task 6);
  - `labels.up_label` (Task 4);
  - `walkforward.quarter_starts`, `trains_refit` and `model_in_force` (Task 4);
  - `siglib.run_backtest`, `CostModel` and `to_ms`.
- Produces:
  - `arms.BAND = 0.2`, `HAR_START = "2018-01-01"`, and `TIMING_ARMS = {"btc": ("BTCUSDT",
    "ETHUSDT"), "eth": ("ETHUSDT", "BTCUSDT")}` (asset, other).
  - `arms.rebalance(s, e, band=BAND) -> pd.Series`: the weight held after each decision.
  - `arms.timing_decisions(daily: dict[str, DataFrame], hourly: DataFrame, arm, setting, start,
    end) -> DataFrame`. Its index is bar open_time for the decisions in [start, end), and its
    columns are `p, sigma_hat, v, s, e, w`. It raises ValueError on a decision row missing a
    feature, or when σ* is undefined.
  - `arms.run_book(close, weights, start, end, cost_model=CostModel()) -> BacktestResult`, over
    [start, end).
  - `conftest.make_spot_market(seed, signal=0.0, start="2017-08-17", end="2023-07-01",
    hourly_vol=0.006) -> (daily, hourly)`: dicts keyed `"BTCUSDT"` and `"ETHUSDT"` in the
    warehouse's kline columns, served by the `spot_market` fixture.

- [ ] **Step 1: Add the synthetic market to `tests/research/conftest.py`.** Extend the module
  docstring's fixture sentence to end with:

```python
data.binance.vision and its S3 listing, so no test touches the network; `spot_market` makes
synthetic BTC and ETH spot klines for the model lab's timing arms.
```

  Replace the line `from research import archive_source, config  # noqa: E402  (the skips above
  guard these imports)` with:

```python
import numpy as np  # noqa: E402  (the skips above guard these imports)
import pandas as pd  # noqa: E402

from research import archive_source, config  # noqa: E402
```

  Append:

```python
def make_spot_market(seed: int, signal: float = 0.0, start: str = "2017-08-17",
                     end: str = "2023-07-01", hourly_vol: float = 0.006):
    """(daily, hourly): synthetic BTCUSDT and ETHUSDT spot klines in the warehouse's columns.

    Each asset has a hidden regime f = ±1 that flips on about one day in 20 and shows in its
    taker-buy share (0.5 + 0.04·f). Day d drifts by `signal` · f[d-1], spread evenly over its 24
    hours, so with signal 0 both assets are random walks whatever their flow."""
    rng = np.random.default_rng(seed)
    first = int(pd.Timestamp(start, tz="UTC").value // 1_000_000)
    n_days = (int(pd.Timestamp(end, tz="UTC").value // 1_000_000) - first) // config.DAY_MS
    daily, hourly = {}, {}
    for k, symbol in enumerate(("BTCUSDT", "ETHUSDT")):
        regime = np.where(np.cumsum(rng.random(n_days) < 0.05) % 2 == 0, 1.0, -1.0)
        drift = signal * np.concatenate([[0.0], regime[:-1]])
        hours = rng.normal(np.repeat(drift / 24, 24), hourly_vol)
        close = 100.0 * (k + 1) * np.exp(np.cumsum(hours))
        open_ = np.concatenate([[100.0 * (k + 1)], close[:-1]])
        quote = rng.lognormal(10.0, 0.3, close.size)
        share = 0.5 + 0.04 * np.repeat(regime, 24) + rng.normal(0.0, 0.02, close.size)
        h = pd.DataFrame({
            "open_time": first + np.arange(close.size) * config.HOUR_MS,
            "open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
            "close": close, "volume": quote / close, "quote_volume": quote,
            "taker_buy_volume": share * quote / close, "taker_buy_quote_volume": share * quote,
            "trades": 100,
        })
        g = h.groupby(h["open_time"] // config.DAY_MS * config.DAY_MS)
        daily[symbol] = pd.DataFrame({
            "open_time": g["open_time"].first(), "open": g["open"].first(),
            "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
            "volume": g["volume"].sum(), "quote_volume": g["quote_volume"].sum(),
            "taker_buy_volume": g["taker_buy_volume"].sum(),
            "taker_buy_quote_volume": g["taker_buy_quote_volume"].sum(),
            "trades": g["trades"].sum(),
        }).reset_index(drop=True)
        hourly[symbol] = h
    return daily, hourly


@pytest.fixture
def spot_market():
    """make_spot_market, for the model lab's timing tests."""
    return make_spot_market
```

  Why a hidden regime and not momentum: an earlier draft drifted on the sign of the last 30 days.
  That drift fed on itself and produced years-long one-way trends, which made buy-and-hold an
  erratic yardstick. Here the regime is outside the price and balanced, and only the 7-day
  taker-buy share reveals it.

- [ ] **Step 2: Write the failing tests** in `tests/research/test_model_lab_arms.py`:

```python
"""The timing arms (spec §2.1–2.2, as amended): the 0.2 rebalancing band, next-bar execution
through siglib, and the whole walk-forward pipeline: no look-ahead, a planted signal found, and
nothing found in random walks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.siglib.stats import sharpe, weekly_returns
from research.signals.model_lab import arms
from research.signals.model_lab.features import daily_grid
from research.signals.model_lab.labels import up_label

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC
START, END = "2021-07-01", "2023-07-01"  # the validation decisions


def _rebalanced(s, e, band=arms.BAND):
    idx = BASE + np.arange(len(s)) * DAY
    return arms.rebalance(pd.Series(s, index=idx, dtype=float),
                          pd.Series(e, index=idx, dtype=float), band).tolist()


def test_a_new_signal_moves_at_once_and_a_small_change_waits():
    assert _rebalanced([1, 1, 1, 0, 1], [0.9, 0.75, 0.6, 0.0, 0.5]) == [0.9, 0.9, 0.6, 0.0, 0.5]


def test_a_change_inside_the_band_waits_and_one_beyond_it_moves():
    assert _rebalanced([1, 1, 1], [0.5, 0.69, 0.71]) == [0.5, 0.5, 0.71]


def test_the_band_is_strict():  # a band of 0.25 makes the boundary exact in binary
    assert _rebalanced([1, 1, 1], [0.5, 0.75, 0.875], band=0.25) == [0.5, 0.5, 0.875]


def test_the_book_starts_flat():
    assert _rebalanced([0, 1], [0.0, 0.1]) == [0.0, 0.1]  # the first long is a change of signal


def test_volatility_sizing_alone_moves_only_past_the_band():  # the s ≡ 1 baseline (§3.5)
    assert _rebalanced([1, 1, 1, 1], [1.0, 0.85, 0.79, 1.0]) == [1.0, 1.0, 0.79, 1.0]


def test_a_weight_earns_the_next_day_net_of_costs():
    idx = BASE + np.arange(4) * DAY
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    weights = pd.Series([1.0, 0.0, 0.0, 0.0], index=idx)
    book = arms.run_book(close, weights, BASE + DAY, BASE + 4 * DAY)
    # decided at bar 0, so it earns bar 1 (+10%) less the 10 bp entry; sold on bar 2 at 10 bp
    assert book.returns.tolist() == pytest.approx([0.10 - 0.001, -0.001, 0.0])


def test_buy_and_hold_pays_one_entry():
    idx = BASE + np.arange(4) * DAY
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    book = arms.run_book(close, pd.Series(1.0, index=idx), BASE + DAY, BASE + 4 * DAY)
    assert book.n_trades == 1 and book.trade_costs.sum() == pytest.approx(0.001)


@pytest.fixture
def fast_trees(monkeypatch):
    """Ten rounds instead of hundreds: the pipeline's plumbing, not the model, is under test."""
    small = {name: {**s, "n_estimators": 10} for name, s in arms.models.SETTINGS.items()}
    monkeypatch.setattr(arms.models, "SETTINGS", small)


def _decide(daily, hourly, arm="btc", setting="S1"):
    asset, _ = arms.TIMING_ARMS[arm]
    return arms.timing_decisions(daily, hourly[asset], arm, setting, START, END)


def test_decisions_cover_the_window_from_the_bar_before_it(spot_market, fast_trees):
    daily, hourly = spot_market(1)
    out = _decide(daily, hourly)
    assert out.index[0] == pd.Timestamp("2021-06-30", tz="UTC").value // 1_000_000
    assert out.index[-1] == pd.Timestamp("2023-06-29", tz="UTC").value // 1_000_000
    assert list(out.columns) == ["p", "sigma_hat", "v", "s", "e", "w"]


def _scrambled_from(frames, cut, rng):
    """Copies of the frames with every price and volume from `cut` on multiplied at random."""
    out = {}
    for symbol, bars in frames.items():
        bars = bars.copy()
        future = bars["open_time"] >= cut
        for col in ("close", "quote_volume", "taker_buy_quote_volume"):
            bars.loc[future, col] *= rng.uniform(0.5, 2.0, int(future.sum()))
        out[symbol] = bars
    return out


def test_future_data_never_changes_a_past_decision(spot_market, fast_trees):  # spec §4.4
    daily, hourly = spot_market(2)
    before = _decide(daily, hourly)
    # 3 days after the 2022-07-01 refit: a leaked label would reach past it
    cut = pd.Timestamp("2022-07-04", tz="UTC").value // 1_000_000
    rng = np.random.default_rng(3)
    after = _decide(_scrambled_from(daily, cut, rng), _scrambled_from(hourly, cut, rng))
    pd.testing.assert_frame_equal(before[before.index < cut], after[after.index < cut])
    assert not before[before.index >= cut].equals(after[after.index >= cut])


def test_a_decision_without_every_feature_stops_the_run(spot_market, fast_trees):
    daily, hourly = spot_market(1)
    missing = pd.Timestamp("2022-01-10", tz="UTC").value // 1_000_000
    daily["BTCUSDT"] = daily["BTCUSDT"][daily["BTCUSDT"]["open_time"] != missing]
    with pytest.raises(ValueError, match="2022-01-10 lacks a feature"):
        _decide(daily, hourly)


def test_a_probability_of_exactly_one_half_stays_out(spot_market, monkeypatch):
    # A tree model with no split on a balanced training set predicts exactly 0.5 (§2.2: s = 1
    # only when p > 0.5).
    class CoinFlip:
        def predict(self, X):
            return np.full(len(X), 0.5)

    monkeypatch.setattr(arms.models, "fit_direction", lambda X, y, setting: CoinFlip())
    out = _decide(*spot_market(1))
    assert (out["s"] == 0.0).all() and (out["w"] == 0.0).all()


def _hit_rate_and_sharpes(daily, hourly):
    out = _decide(daily, hourly)
    close = daily_grid(daily["BTCUSDT"])["close"]
    label = up_label(close).reindex(out.index)
    hit = float((out["s"] == label)[label.notna()].mean())
    book = arms.run_book(close, out["w"], START, END)
    hold = arms.run_book(close, pd.Series(1.0, index=close.index), START, END)
    return hit, sharpe(weekly_returns(book.returns)), sharpe(weekly_returns(hold.returns))


def test_a_planted_signal_is_found(spot_market):  # spec §4.4 power, with the real settings
    hit, book, hold = _hit_rate_and_sharpes(*spot_market(3, signal=0.01))
    assert hit > 0.55 and book > hold + 1.0


def test_a_random_walk_yields_nothing(spot_market):  # spec §4.4 null
    hit, book, hold = _hit_rate_and_sharpes(*spot_market(1))
    assert 0.43 < hit < 0.57 and book < hold + 0.5
```

  How the expected values come out:
  - **The book.** It decides 1.0 at bar 0 and earns bar 1's +10%, less the 10 bp entry. The
    weight decided at bar 1 is 0, so bar 2 pays the 10 bp exit and earns nothing.
  - **The look-ahead cut.** It sits 3 days after a refit, so a training label that leaked past
    the refit would reach the scrambled data and change a decision before the cut.
  - **The power and null bounds.** These were measured across 5 seeds (see the power table).
    Seed 3 at 1%/day gives a hit rate of 0.59 and a Sharpe 2.2 above buy-and-hold's. Seed 1 on
    a random walk gives a hit rate of 0.48 and a Sharpe 0.3 below.

- [ ] **Step 3: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_arms.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.arms'`.

- [ ] **Step 4: Implement** `research/signals/model_lab/arms.py`:

```python
"""The BTC and ETH timing arms (spec 2026-10-02 §2.1–2.2, §2.4, as amended).

timing_decisions walks the quarterly refits and turns each day's model outputs into the weight
the arm holds; run_book prices those weights through siglib.run_backtest, the only place P&L is
computed."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS
from research.siglib.backtest import BacktestResult, run_backtest
from research.siglib.costs import CostModel
from research.siglib.data import to_ms
from research.signals.model_lab import features as feat
from research.signals.model_lab import models
from research.signals.model_lab.labels import up_label
from research.signals.model_lab.walkforward import model_in_force, quarter_starts, trains_refit

BAND = 0.2
# HAR refits every quarter from here on, so that σ̂ exists point-in-time for the 365 days σ*
# needs before a decision.
HAR_START = "2018-01-01"
TIMING_ARMS = {"btc": ("BTCUSDT", "ETHUSDT"), "eth": ("ETHUSDT", "BTCUSDT")}  # asset, other


def rebalance(s: pd.Series, e: pd.Series, band: float = BAND) -> pd.Series:
    """The weight held after each decision: e_t when s_t differs from the previous s, otherwise
    e_t only if it is more than `band` from the weight held. The book starts flat."""
    held, last_s, out = 0.0, 0.0, []
    for s_t, e_t in zip(s.to_numpy(), e.to_numpy()):
        if s_t != last_s or abs(e_t - held) > band:
            held = e_t
        last_s = s_t
        out.append(held)
    return pd.Series(out, index=e.index)


def _direction(X, y, t, decide, refits, setting) -> np.ndarray:
    """p_t for the decided rows, each from the classifier refit in force at its decision."""
    p = np.full(len(t), np.nan)
    trainable = X.notna().all(axis=1).to_numpy() & y.notna().to_numpy()
    in_force = model_in_force(t, refits)
    for i, refit in enumerate(refits):
        use = decide & (in_force == i)
        if use.any():
            train = trainable & trains_refit(t, refit)
            p[use] = models.fit_direction(X[train], y[train], setting).predict(X[use])
    return p


def _sigma_hat(rv, t, refits) -> pd.Series:
    """σ̂_t at every row from HAR_START on, each from the HAR refit in force at its decision."""
    terms, target = models.har_terms(rv), models.har_target(rv)
    forecast = np.full(len(t), np.nan)
    in_force = model_in_force(t, refits)
    for i, refit in enumerate(refits):
        use = in_force == i
        train = trains_refit(t, refit)
        forecast[use] = models.har_forecast(models.fit_har(terms[train], target[train]), terms[use])
    return feat.annualised_vol(pd.Series(forecast, index=rv.index))


def timing_decisions(daily: dict[str, pd.DataFrame], hourly: pd.DataFrame, arm: str,
                     setting: str, start, end) -> pd.DataFrame:
    """The arm's decisions in [start, end): one row per daily bar t, decided at t + 1 day, with
    columns p, s, sigma_hat, v, e and w (the weight held from that decision on).

    `daily` holds both assets' daily klines, `hourly` the arm's own hourly klines."""
    asset, other = TIMING_ARMS[arm]
    bars = feat.daily_grid(daily[asset])
    rv = feat.daily_rv(hourly).reindex(bars.index)
    X = feat.timing_features(bars, rv, feat.daily_grid(daily[other])["close"])
    t = bars.index.to_numpy()
    decide = (t + DAY_MS >= to_ms(start)) & (t + DAY_MS < to_ms(end))
    incomplete = ~X[decide].notna().all(axis=1)
    if incomplete.any():
        day = pd.Timestamp(incomplete.idxmax(), unit="ms")
        raise ValueError(f"{arm}: the decision on bar {day:%Y-%m-%d} lacks a feature")
    sigma_hat = _sigma_hat(rv, t, quarter_starts(HAR_START, end))
    out = pd.DataFrame({
        "p": _direction(X, up_label(bars["close"]), t, decide, quarter_starts(start, end), setting),
        "sigma_hat": sigma_hat,
        "v": models.size_scale(sigma_hat),
    }, index=bars.index)[decide]
    if out["v"].isna().any():
        raise ValueError(f"{arm}: σ* needs {models.SIGMA_STAR_DAYS} days of σ̂ before {start}")
    out["s"] = (out["p"] > models.THRESHOLD).astype(float)
    out["e"] = out["s"] * out["v"]
    out["w"] = rebalance(out["s"], out["e"])
    return out


def run_book(close: pd.Series, weights: pd.Series, start, end,
             cost_model: CostModel = CostModel()) -> BacktestResult:
    """The book over [start, end) through siglib.run_backtest: the weight decided at bar t earns
    bar t + 1 (§2.1). `close` and `weights` are indexed by bar open_time."""
    first, end_ms = to_ms(start) - DAY_MS, to_ms(end)
    prices = close[(close.index >= first) & (close.index < end_ms)].to_frame("asset")
    held = weights.reindex(prices.index).fillna(0.0).to_frame("asset")
    return run_backtest(prices, held, cost_model).window(start, end)
```

- [ ] **Step 5: Run the tests, then the suite.**

  Run: `python -m pytest -q tests/research/test_model_lab_arms.py && python -m pytest -q`
  Expected: 13 passed, then all pass (230). The arms file takes about 3 seconds: two of its tests
  run the real S1 setting.

- [ ] **Step 6: Commit.**

```bash
git add research/signals/model_lab/arms.py tests/research/conftest.py tests/research/test_model_lab_arms.py
git commit -m "feat: the BTC and ETH timing arms, walked forward through siglib

Each decision uses only the refits in force at its close; future data never
changes a past decision, a planted 1%/day signal is found, and a random walk
yields nothing."
```

---

### Task 8: The stop rule

**Files:**
- Create: `research/signals/model_lab/gates.py`
- Test: `tests/research/test_model_lab_gates.py`

**Interfaces:**
- Consumes: `siglib.stats.weekly_returns` (summed, Task 2), `sharpe` and `max_drawdown`.
- Produces: `gates.stop_rule(arm: pd.Series, btc: pd.Series) -> dict[str, bool]`, keyed `"G1"`
  and `"G2"`. Both inputs are daily net returns over the same window.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_gates.py`:

```python
"""The stop rule (spec §3.4): on the validation period, G1 needs a strictly higher weekly Sharpe
than BTC's and G2 a daily drawdown no deeper than BTC's."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.signals.model_lab import gates

DAY = 86_400_000
MONDAY = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _daily(values):
    return pd.Series(values, index=MONDAY + np.arange(len(values)) * DAY, dtype=float)


BTC = _daily(np.tile([0.02, -0.01, 0.0, 0.0, 0.01, -0.02, 0.0], 8)[:-1] + 0.001 * np.arange(55))


def test_the_same_book_passes_g2_but_not_g1():
    assert gates.stop_rule(BTC, BTC) == {"G1": False, "G2": True}  # ties: > fails, ≤ holds


def test_a_flat_book_has_no_sharpe_and_fails_g1():
    assert gates.stop_rule(_daily(np.zeros(55)), BTC) == {"G1": False, "G2": True}


def test_a_better_book_passes_both():
    assert gates.stop_rule(BTC + 0.002, BTC) == {"G1": True, "G2": True}


def test_a_deeper_drawdown_fails_g2():
    worse = BTC.copy()
    worse.iloc[3] = -0.30
    assert gates.stop_rule(worse, BTC)["G2"] is False
```

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_gates.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.gates'`.

- [ ] **Step 3: Implement** `research/signals/model_lab/gates.py`:

```python
"""The verdict's gates (spec 2026-10-02 §3.3–3.4). Phase 3 needs only the stop rule.

Every input is a book's daily net returns, indexed by bar open_time like BacktestResult.returns."""

from __future__ import annotations

import pandas as pd

from research.siglib.stats import max_drawdown, sharpe, weekly_returns


def stop_rule(arm: pd.Series, btc: pd.Series) -> dict[str, bool]:
    """G1 and G2 on the validation period (§3.4): a higher Sharpe of weekly returns than BTC's,
    and a daily drawdown no deeper. A book with no Sharpe ratio fails G1."""
    return {"G1": sharpe(weekly_returns(arm)) > sharpe(weekly_returns(btc)),
            "G2": max_drawdown(arm) <= max_drawdown(btc)}
```

- [ ] **Step 4: Run the tests.**

  Run: `python -m pytest -q tests/research/test_model_lab_gates.py`
  Expected: 4 passed.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/gates.py tests/research/test_model_lab_gates.py
git commit -m "feat: the stop rule, G1 and G2 on the validation period

An arm that cannot beat BTC's weekly Sharpe or match its drawdown on train is
recorded as failed and never reaches the unseal."
```

---

### Task 9: The validation study and the freeze

**Files:**
- Create: `research/signals/model_lab/study.py`
- Test: `tests/research/test_model_lab_study.py`

**Interfaces:**
- Consumes: `arms` (Task 7), `gates.stop_rule` (Task 8), `models` (Task 6),
  `features.TIMING_FEATURES`, `ANNUAL_DAYS` and `daily_grid` (Task 5), `labels.HORIZON_DAYS`,
  `walkforward.EMBARGO_DAYS`, `siglib.data.load_klines` and `siglib.stats`.
- Produces:
  - `study.VALIDATION_START = "2021-07-01"`, `VALIDATION_END = "2023-07-01"`, `OUTPUT` (the
    `output/` folder beside the module), `COSTS = CostModel()` and `SPOT`.
  - `study.load_spot(end=VALIDATION_END) -> (daily, hourly)`, which raises RuntimeError on any
    bar at or after `end`.
  - `study.run_trial(daily, hourly, arm, setting) -> BacktestResult`.
  - `study.trial_row(arm, setting, book) -> dict`, with columns `arm, setting, sharpe,
    sharpe_per_week, weeks, max_drawdown, total_return, turnover, trades, trade_cost`.
  - `study.choose(rows) -> "S1" | "S2"`.
  - `study.frozen_params(arm, setting, rows, stop, btc) -> dict`.
  - `study.main()`: the CLI `python -m research.signals.model_lab.study`.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_study.py`:

```python
"""The validation study (spec §2.4, §3.4): four trials logged, the higher validation Sharpe kept
(ties to S1), the stop rule applied, every constant frozen, and nothing read from the sealed
windows."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from research.signals.model_lab import study

SEALED = pd.Timestamp(study.VALIDATION_END, tz="UTC").value // 1_000_000


@pytest.fixture
def fast_trees(monkeypatch):
    small = {name: {**s, "n_estimators": 10} for name, s in study.models.SETTINGS.items()}
    monkeypatch.setattr(study.models, "SETTINGS", small)


@pytest.fixture
def market(warehouse, spot_market, monkeypatch, tmp_path):
    """A synthetic spot warehouse running a year into the sealed windows, and a scratch output."""
    daily, hourly = spot_market(4, end="2024-07-01")
    monkeypatch.setattr(study, "OUTPUT", tmp_path / "output")

    def write(frames):
        for interval, by_symbol in frames.items():
            folder = warehouse / f"archive_spot_klines_{interval}"
            folder.mkdir(parents=True, exist_ok=True)
            for symbol, bars in by_symbol.items():
                bars.to_parquet(folder / f"{symbol}.parquet", index=False)

    write({"1d": daily, "1h": hourly})
    return write, daily, hourly


def test_the_study_logs_four_trials_and_freezes_both_arms(market, fast_trees):
    study.main()
    log = pd.read_csv(study.OUTPUT / "combo_log.csv")
    assert list(zip(log["arm"], log["setting"])) == [("btc", "S1"), ("btc", "S2"),
                                                    ("eth", "S1"), ("eth", "S2")]
    assert log["weeks"].tolist() == [103] * 4  # complete Monday weeks in the validation period
    for arm, asset in (("btc", "BTCUSDT"), ("eth", "ETHUSDT")):
        frozen = json.loads((study.OUTPUT / arm / "frozen_params.json").read_text())
        assert frozen["asset"] == asset
        assert frozen["setting"] == study.choose(log[log["arm"] == arm])
        assert frozen["status"] == ("frozen" if frozen["validation"]["G1"]
                                    and frozen["validation"]["G2"] else "failed_on_validation")
        assert frozen["lightgbm_params"]["random_state"] == 20261002
        assert len(frozen["features"]) == 21


def test_the_study_never_reads_the_sealed_windows(market, fast_trees):  # spec §2.4
    write, daily, hourly = market
    study.main()
    first = (study.OUTPUT / "combo_log.csv").read_text()
    for frames in (daily, hourly):
        for bars in frames.values():
            bars.loc[bars["open_time"] >= SEALED, ["close", "quote_volume"]] *= 3.0
    write({"1d": daily, "1h": hourly})
    study.main()
    assert (study.OUTPUT / "combo_log.csv").read_text() == first


def test_a_sealed_bar_stops_the_study(monkeypatch):
    late = pd.DataFrame({"open_time": [SEALED]})
    monkeypatch.setattr(study, "load_klines", lambda *args, **kwargs: late)
    with pytest.raises(RuntimeError, match="sealed"):
        study.load_spot()


@pytest.mark.parametrize("s1, s2, kept", [
    (0.5, 0.5, "S1"),         # a tie goes to S1
    (0.4, 0.5, "S2"),
    (math.nan, 0.1, "S2"),    # a missing Sharpe ranks below any number
    (math.nan, math.nan, "S1"),
])
def test_the_higher_validation_sharpe_is_kept(s1, s2, kept):
    rows = pd.DataFrame({"setting": ["S1", "S2"], "sharpe": [s1, s2]})
    assert study.choose(rows) == kept
```

  Why 103 weeks: the validation decisions earn returns from Thursday 2021-07-01 to Friday
  2023-06-30. The first complete Monday week starts on 2021-07-05, and the last one starts on
  2023-06-19.

- [ ] **Step 2: Run them to see them fail.**

  Run: `python -m pytest -q tests/research/test_model_lab_study.py`
  Expected: an error collecting the file, `ModuleNotFoundError: No module named
  'research.signals.model_lab.study'`.

- [ ] **Step 3: Implement** `research/signals/model_lab/study.py`:

```python
"""Train-only validation study of the BTC and ETH arms, then their freeze (spec 2026-10-02 §2.4).

    python -m research.signals.model_lab.study

Each arm runs both settings over the validation decisions, 2021-07-01 to 2023-06-30, with its
quarterly refits and baseline costs: four of Experiment 1's six trials. An arm keeps the setting
whose book has the higher Sharpe of weekly net returns; a tie, or a Sharpe ratio neither book has,
goes to S1. The kept setting then meets the stop rule against BTC (§3.4). The run writes the trial
log and each arm's frozen_params.json under output/, and never loads a bar from the sealed
windows."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from research.siglib.backtest import BacktestResult
from research.siglib.costs import CostModel
from research.siglib.data import load_klines, to_ms
from research.siglib.stats import max_drawdown, sharpe, weekly_returns
from research.signals.model_lab import arms, gates, models
from research.signals.model_lab.features import ANNUAL_DAYS, TIMING_FEATURES, daily_grid
from research.signals.model_lab.labels import HORIZON_DAYS
from research.signals.model_lab.walkforward import EMBARGO_DAYS

VALIDATION_START = "2021-07-01"
VALIDATION_END = "2023-07-01"  # where the sealed windows begin
OUTPUT = Path(__file__).parent / "output"
COSTS = CostModel()  # baseline: 10 bp per side
SPOT = tuple(asset for asset, _ in arms.TIMING_ARMS.values())


def load_spot(end=VALIDATION_END) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """(daily, hourly) archive spot klines of both assets: every bar that opened before `end`."""
    daily = {s: load_klines(s, "1d", end=end, source="archive_spot_klines") for s in SPOT}
    hourly = {s: load_klines(s, "1h", end=end, source="archive_spot_klines") for s in SPOT}
    for bars in [*daily.values(), *hourly.values()]:
        if len(bars) and bars["open_time"].max() >= to_ms(end):
            raise RuntimeError("the study loaded a bar from the sealed windows")
    return daily, hourly


def run_trial(daily: dict[str, pd.DataFrame], hourly: dict[str, pd.DataFrame], arm: str,
              setting: str) -> BacktestResult:
    """One arm under one setting over the validation decisions, at baseline costs."""
    asset, _ = arms.TIMING_ARMS[arm]
    decisions = arms.timing_decisions(daily, hourly[asset], arm, setting, VALIDATION_START,
                                      VALIDATION_END)
    return arms.run_book(daily_grid(daily[asset])["close"], decisions["w"], VALIDATION_START,
                         VALIDATION_END, COSTS)


def trial_row(arm: str, setting: str, book: BacktestResult) -> dict:
    """One trial-log row. sharpe_per_week, the Sharpe ratio in weekly units, feeds G6 (§3.3)."""
    weekly = weekly_returns(book.returns)
    return {"arm": arm, "setting": setting, "sharpe": sharpe(weekly),
            "sharpe_per_week": sharpe(weekly, periods_per_year=1), "weeks": len(weekly),
            "max_drawdown": max_drawdown(book.returns), "total_return": book.total_return,
            "turnover": book.turnover, "trades": book.n_trades,
            "trade_cost": float(book.trade_costs.sum())}


def choose(rows: pd.DataFrame) -> str:
    """S2 only if its Sharpe beats S1's; a missing Sharpe ranks below any number."""
    sharpes = rows.set_index("setting")["sharpe"].fillna(-math.inf)
    return "S2" if sharpes["S2"] > sharpes["S1"] else "S1"


def frozen_params(arm: str, setting: str, rows: pd.DataFrame, stop: dict[str, bool],
                  btc: BacktestResult) -> dict:
    """Everything the unseal needs to rerun this arm exactly: the kept setting and every
    constant, plus the validation evidence for the choice."""
    asset, other = arms.TIMING_ARMS[arm]
    by_setting = rows.set_index("setting")
    return {
        "arm": arm, "asset": asset, "other_asset": other,
        "status": "frozen" if all(stop.values()) else "failed_on_validation",
        "setting": setting,
        "lightgbm_params": models.lightgbm_params(setting),
        "versions": {package: version(package) for package in ("lightgbm", "numpy", "pandas")},
        "features": TIMING_FEATURES,
        "constants": {"threshold": models.THRESHOLD, "band": arms.BAND,
                      "horizon_days": HORIZON_DAYS, "embargo_days": EMBARGO_DAYS,
                      "refits": "first day of each calendar quarter", "har_start": arms.HAR_START,
                      "sigma_star_days": models.SIGMA_STAR_DAYS, "annual_days": ANNUAL_DAYS},
        "costs": asdict(COSTS),
        "validation": {
            "start": VALIDATION_START, "end": VALIDATION_END,
            "sharpe": by_setting["sharpe"].to_dict(),
            "max_drawdown": float(by_setting.loc[setting, "max_drawdown"]),
            "btc_sharpe": sharpe(weekly_returns(btc.returns)),
            "btc_max_drawdown": max_drawdown(btc.returns),
            **stop,
        },
    }


def main() -> None:
    daily, hourly = load_spot()
    btc_close = daily_grid(daily["BTCUSDT"])["close"]
    btc = arms.run_book(btc_close, pd.Series(1.0, index=btc_close.index), VALIDATION_START,
                        VALIDATION_END, COSTS)
    rows, books = [], {}
    for arm in arms.TIMING_ARMS:
        for setting in models.SETTINGS:
            books[arm, setting] = run_trial(daily, hourly, arm, setting)
            rows.append(trial_row(arm, setting, books[arm, setting]))
            print(f"{arm} {setting}: weekly Sharpe {rows[-1]['sharpe']:+.3f}, "
                  f"max drawdown {rows[-1]['max_drawdown']:.1%}, {rows[-1]['trades']} trades")
    log = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    log.to_csv(OUTPUT / "combo_log.csv", index=False)
    for arm in arms.TIMING_ARMS:
        mine = log[log["arm"] == arm]
        setting = choose(mine)
        stop = gates.stop_rule(books[arm, setting].returns, btc.returns)
        params = frozen_params(arm, setting, mine, stop, btc)
        path = OUTPUT / arm / "frozen_params.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(params, indent=2) + "\n")
        print(f"{arm}: keeps {setting}; G1 {stop['G1']}, G2 {stop['G2']}: {params['status']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests, then the suite, then the syntax check.**

  Run: `python -m pytest -q tests/research/test_model_lab_study.py && python -m pytest -q && python -m compileall -q research`
  Expected: 7 passed, then all pass (241).

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/study.py tests/research/test_model_lab_study.py
git commit -m "feat: the timing arms' validation study and mechanical freeze

Four trials are logged; each arm keeps its higher validation Sharpe (ties to S1),
meets the stop rule, and freezes every constant; nothing sealed is ever read."
```

---

### Task 10: Run the study on real data, freeze, and record

**Files:**
- Create: `research/signals/model_lab/output/combo_log.csv`
- Create: `research/signals/model_lab/output/btc/frozen_params.json` and
  `research/signals/model_lab/output/eth/frozen_params.json`
- Modify: `CLAUDE.md`, `agents/roadmap.md`

**Interfaces:** none. This task runs Task 9's CLI on the archive and commits what it writes.

- [ ] **Step 1: Check the order.** The first real-data run must come after the spec says what it
  runs.

  Run: `git log --oneline -12 && python -m pytest -q`
  Expected: Task 1's `docs: fix the timing arms' open definitions …` sits below every commit of
  Tasks 2–9, and the suite passes (241). If the spec amendment is missing, stop: the run is not
  pre-registered.

- [ ] **Step 2: Run the study.**

  Run: `python -m research.signals.model_lab.study`
  Expected: four trial lines, `btc S1`, `btc S2`, `eth S1` and `eth S2`, each with a weekly
  Sharpe, a max drawdown and a trade count. Then one line per arm naming the kept setting, G1,
  G2 and the status. It reads only bars before 2023-07-01 and takes under a minute.
  - Nothing here is a choice. The setting and the status follow from the rules, and the numbers
    are recorded as they come out.
  - **If it raises** (a missing feature, or σ* undefined), stop and show the owner. The spec does
    not allow a workaround picked after seeing train data.

- [ ] **Step 3: Commit the trial log by itself.**

```bash
git add research/signals/model_lab/output/combo_log.csv
git commit -m "research: the BTC and ETH arms' four validation trials

Experiment 1's trials 1-4 of 6, logged before the freeze; G6 deflates by all of
them."
```

- [ ] **Step 4: Commit the freeze by itself** (spec §2.4: "committed in its own commit").

```bash
git add research/signals/model_lab/output/btc/frozen_params.json research/signals/model_lab/output/eth/frozen_params.json
git commit -m "research: freeze the BTC and ETH timing arms

Each arm's setting and every constant are fixed before any sealed bar is read;
an arm that failed G1 or G2 on validation is frozen as failed and never unsealed."
```

- [ ] **Step 5: Update `CLAUDE.md`.**
  - In `## Stack`, after the bullet on libraries an experiment adds, add: `LightGBM 4.7.0 is
    pinned for Experiment 1 (requirements-research.txt).`
  - Under `### Commands`, add `python -m research.signals.model_lab.study  # train-only:
    validation trials and the freeze`.
  - After the Signal code subsection, add one sentence: "Experiment 1's frozen parameters live in
    `research/signals/model_lab/output/{arm}/frozen_params.json`. Never edit a frozen file; a
    change is a new experiment."
  - Update both test counts, 195, to the count `python -m pytest -q` prints (241).

- [ ] **Step 6: Update `agents/roadmap.md`.** Tick `**3. BTC and ETH arms**` and append this log
  entry with the real numbers:

```markdown
- 2026-10-DD — phase 3 (BTC and ETH arms) frozen: validation weekly Sharpe BTC S1 x / S2 x, ETH S1 x / S2 x against BTC's x; BTC keeps Sx (status), ETH keeps Sx (status). Weekly returns are summed (owner's ruling). Next: phase 4's plan (the ranker).
```

- [ ] **Step 7: Run the suite and commit.**

```bash
python -m pytest -q && git add CLAUDE.md agents/roadmap.md && git commit -m "docs: record the frozen timing arms

Phase 3 is closed; the ranker's plan comes next, and the arms stay sealed until
the joint unseal."
```

---

## Handed on to phases 4 and 5

- **The trial log is shared.** `study.main()` writes `combo_log.csv` afresh with phase 3's four
  rows. Phase 4 must append its two ranker trials, never rewrite the file. G6's trial variance
  uses all six `sharpe_per_week` values (weekly units, spec §3.3).
- **Reuse, don't copy.**
  - The ranker refits on the first Monday on or after each quarter's first day. It can map
    `walkforward.quarter_starts` forward to Mondays, and `trains_refit` holds for any decision
    grid whose labels run 7 days.
  - `models.lightgbm_params` hard-codes objective `binary`; the ranker's regressor needs it as a
    parameter.
  - `labels` needs the percentile label.
- **Weekly returns are summed everywhere** (owner's ruling). `oos_eval.py` takes Sharpe, alpha and
  the deflated Sharpe from `stats.weekly_returns` as it now stands. Drawdown stays on the
  compounded daily curve.
- **§3.5's baselines for the BTC and ETH arms** come cheaply from this phase:
  - Volatility sizing alone is `rebalance(1, v)`, and direction alone is `rebalance(s, s)`, both
    taken from `timing_decisions`' columns.
  - Buy-and-hold is `run_book` on a constant 1.
  - Only the 200-day SMA filter is new code.
- **The null and power tests with alpha** belong to phase 5, where G3 exists: G3 fails on random
  walks and passes on a planted signal. This phase's versions test hit rates and Sharpe ratios.
- **`oos_eval.py` should check `frozen_params.json`'s `versions`** against what is installed
  before it runs, because a different LightGBM can change a frozen model's predictions.
- **The freeze's status gates the unseal.** An arm with status `failed_on_validation` gets no
  out-of-sample run (§3.4).
