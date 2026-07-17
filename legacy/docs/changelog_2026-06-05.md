# Changelog — 2026-06-05 (swing agent overhaul)

A single day's work, in dependency order: fix the broken stops → fix the universe →
build a test net → fix the strategy hole the data exposed → instrument it. 18 commits
(`d440ac1`…`37a7b68`), tests **12 → 85**.

---

## 1. Exchange-side SL/TP was 100% broken (−4120) — fixed

**`d440ac1` fix(swing): place SL/TP via Algo endpoint**

Every live position since 2026-05-23 was placing its stop-loss/take-profit and getting
rejected with Binance error `-4120` — i.e. **trading with no exchange-side stop**, protected
only by the hourly client-side net. Root cause: Binance migrated USDT-M conditional orders
to the **Algo service on 2025-12-09**; `STOP_MARKET`/`TAKE_PROFIT_MARKET` on `POST /fapi/v1/order`
now reject. The 2026-04-02 "fix" (`reduceOnly`) never worked — a 37-day HOLD dry spell hid it
until the first trade fired.

**Fix:** route to `POST /fapi/v1/algoOrder` (`algoType=CONDITIONAL`, `triggerPrice`,
`closePosition="true"`, `workingType=MARK_PRICE`) via the same internal helper
`futures_create_order` uses (python-binance 1.0.19 has no wrapper). Confirmed live: logs now
show `SL placed` / `TP placed`, no `-4120`.

## 2. Coin universe — walk-forward validated

**`c47d487` → `00b7288` → `2ca6e7a`**

Requested additions (FET/ZEC/HYPE), then a coin-level **walk-forward** (train 2024-06→2025-06
vs OOS test 2025-06→2026-06) on a top-100 re-screen. Findings:
- **Breadth fails:** v2 on all 100 coins = 9.47%/yr. The edge is curation; alpha is in mid-caps
  (~rank 40–100), **not** the top 50 (mega-caps mostly lost).
- **Top 2-yr-PnL names were overfit:** VET (+15.48 train → **−1.08 OOS**), JASMY/INJ/TIA/WLD all
  negative out-of-sample. Walk-forward caught them.
- **Robust new adds:** ENS, TON (positive both windows). FET retained.
- **ZEC/HYPE** are net-negative OOS → dropped. **HYPE later re-added by explicit request**
  (`2ca6e7a`) despite failing WF — flagged the weakest coin in the book.

Final universe (13): `DOGE, 1000SHIB, RUNE, RENDER, 1000FLOKI, TURBO, IP, BSV, IOTA, FET, ENS, TON, HYPE`.

## 3. Test suite & structure overhaul (scope B) — 12 → 71 tests

**`5cd2966` `dcf0a96` `401a56e` `c99c4cf` `b66f2bb` `e912881` `60d1141` `3123d48`**

Built a proper test net before any strategy refactor. New layout under `tests/`
(`swing/ bot/ backtest/ property/ integration/` + a shared `conftest.py`), `pyproject.toml`
pytest config, `hypothesis` added. Coverage, money-paths first:
- SL/TP sizing, position sizing, realized-PnL, expected-move filter; the **client-side safety net**
  (extracted `_safety_net_label` so the only stop protection is testable).
- **Property invariants** (size bounds/monotonic, PnL mirror/sign).
- **Indicator golden tests** vs analytically-known values, both bot + swing modules.
- **Live↔backtest parity** (`test_live_backtest_parity.py`) — feeds `agent.decide()` and
  `decide_v2()` identical snapshots and fails if they diverge (the drift class that caused the
  old conf=0.85-vs-0.80 bug). This is the safety net for the eventual scope-C unification.
- **Opt-in testnet** algoOrder round-trip (`-m testnet`).
- Tidy-up: roadmap doc → `docs/`, dead `migrate.sql` removed, gitignored `cache/`+`outputs/`.

See `docs/testing.md` (living guide) and `docs/testing_plan.md` (the slices).
**Deferred to scope C:** DCA buy/sell gates are inline in `trader.run()` (untestable without
extraction); live & backtest duplicate strategy logic — the parity test guards it.

## 4. Hard RSI entry gate — the strategy hole the data exposed

**`bf7123a` feat + `29cd1f4` docs**

Live trades 67/68/69 (this day): three correlated memecoin shorts opened in **one cycle** at
RSI 16–21, all stopped out, **−$4.14**. Root cause: `MIN_RSI_SHORT=42` was a *soft* penalty, so
the bot shorted deeply-oversold coins right before the bounce — entering the zone its own exit
rule (`SHORT_EXIT_RSI_FLOOR=32`) would immediately close.

**Fix:** hard gate — block short if RSI < `SHORT_ENTRY_RSI_FLOOR` (32), long if RSI >
`LONG_ENTRY_RSI_CEIL` (68), pinned to the exit thresholds. In both `agent.decide()` and
`decide_v2()` (parity-tested). Validated by a threshold sweep (g30=g32 plateau, +$5.35/lower-DD
in train; backtest *understates* the benefit because it neutralizes the OI/funding/L-S signals
that caused the live losses) and a **4-lens adversarial workflow** (unanimous GO@32, conf 0.8).
On the live tape the gate flips trades 63–69 from **−$0.60 → +$3.66** (keeps the +14% winner 66,
removes the cluster). Confirmed live: the same oversold complex that lost $4.14 at 19:06 was
**all blocked** at 23:09.

**Honest caveat (flagged, not hidden):** it's a momentum-continuation filter — in a waterfall
crash it can forgo continuation shorts; the backtest can't validate it; live evidence is n≈1.
Future A/B: 35/65 vs 32/68.

## 5. Shadow tracker — measure whether the gate helps or hurts

**`62a6d01` feat + `c1164f4` docs + `bcf4028` (would-be conf in log)**

Closes the regime-risk loop. When the gate blocks a setup that *would* have cleared confidence
(`would_be_conf ≥ 0.80`), `app/swing/shadow.py` records a counterfactual trade and logs its
would-be PnL forward each cycle:
- `SHADOW-CLOSE … +X%` = the gate **forwent a winner** (over-blocking)
- `SHADOW-CLOSE … −X%` = the gate **avoided a loser** (working)

**Observe-only** — output goes only to `log.info()`, can never touch a position (verified by a
2-lens adversarial workflow, GO conf 0.96). The block log also now shows `[would-be conf 0.62]`
so you can see how near each block was to trading even when no shadow opens. Usage:
`docker compose logs swing | grep SHADOW-CLOSE` and sum the percentages.

## 6. Alert on SL placement failure — never run blind again

**`37a7b68`**

`_place_sl_tp` now sends a **Telegram alert** (not just a silent `log.warning`) if the
exchange-side stop fails to place. This is the exact silent failure that ran undetected for
weeks (the original −4120). Turns "weeks blind" into "within the hour."

---

## Open follow-ups (not done — want more live data first)

- **A/B gate 35/65 vs 32/68** — the adversarial review's dissent: 35 gives entries buffer above
  the exit, but data was too thin to prove it. Revisit once the shadow tracker accumulates.
- **Soft-exit-loss-guard** (`SOFT_EXIT_MAX_LOSS_PCT`): the logs showed it *delayed* the RSI<32
  exits on 67/68/69, turning −1% into −4–5%. Worth revisiting (the gate makes it moot for the
  deep-oversold case).
- **Scope C:** unify live (`agent.py`) and backtest (`backtest_replay/strategy.py`) into one
  strategy core, and extract the DCA buy/sell gates — both guarded by existing parity tests.
- **Later, once trades accumulate:** MFE/MAE per trade (SL/TP tuning), exit-reason/confidence
  PnL attribution, funding paid per trade, correlation/concentration filter.

## Operational notes

- **Infra (host):** enable NTP (kills the `-1021` clock-drift cycle crashes), harden DNS
  (Telegram + Binance both saw intermittent resolution failures), disable **withdrawals** on the
  futures API key (it's trade-only).
- The bot restarted several times this day; in-memory diagnostics (shadow tracker) reset on
  restart — the log lines are the durable record.
