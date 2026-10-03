# Where we left off
_2026-10-02_

## This session

The owner asked whether CoinPicks was really the best way to invest, proposed high-frequency
trading with a trained model instead, and asked for a ruling on keeping or deleting the repo.

**Outcome:** keep the repo, retire CoinPicks, no seconds-scale trading. The repo is now a
**model lab**.

- **Research.**
  - Three tracks: HFT feasibility; ML, LLM and RL evidence; low-frequency strategies.
  - Numbers computed from this warehouse.
  - Synthesised in `docs/superpowers/specs/2026-10-02-trading-model-research-findings.md`
    (`93314a8`).
- **The decisive numbers** (all BTC, at VIP-0 fees):

  | Measure | Value |
  |---|---|
  | Taker round trip | 10 bp |
  | Average 5-minute move | 9.1 bp |
  | Maker fee | 2 bp |
  | Whole bid-ask spread | 0.012 bp, about 1/170 of the maker fee |

  Rebates need about $40–110M a day of volume.
- **Archive.** CoinPicks went to `legacy/coinpicks/` (`3387d37`). The decision is the top entry in
  `agents/decisions.md`.
  - CLAUDE.md, README, the roadmap and `agents/CONTEXT.md` were rewritten for the lab
    (`ea52245`).
  - The CoinPicks vocabulary is now at `legacy/coinpicks/CONTEXT.md`.
- **Experiment 1 is pre-registered** in `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`
  (`c045b56`).
  - **Arms:** three race against holding spot BTC — BTC timing, ETH timing, and a weekly
    cross-sectional ranker over a point-in-time top 50 that includes delisted perps.
  - **Gates:** six of them (G1–G6). The arms are unsealed once, together, and six trials are
    counted.
  - **TypeSafe:** Jev is tested forward-only, as a news veto on a "hold BTC" paper book.

### The owner's rulings this session

| Topic | Ruling |
|---|---|
| Goal | Build a trading model; "no edge found" is acceptable |
| Capital | Under $1,000 |
| "High frequency" meant | Seconds or less, then ruled out by the evidence |
| Win rule | Risk-adjusted plus alpha against spot BTC |
| Out-of-sample test | Historical walk-forward first, then 26 weeks of live paper trading before any money |
| Arms | BTC, ETH and the ranker (top 50) |
| TypeSafe | Start recording now |

### What got caught by running things rather than reading them

- **Binance's public archive has every perp, delisted ones included.**
  - It holds 900 USDT perps against the 219 survivors in the warehouse, with daily candles,
    funding and premium history.
  - Phase C's survivorship gap is therefore fixable for free.
  - Its tick-level `bookTicker` ends around March 2024.
- **The 200-day trend filter's −64% drawdown in 2021 is real.**
  - It rode the May crash down to its moving average, then whipsawed 19 times.
- **The local pre-push hook was compiling paths that no longer exist** (`app`, `api_main.py`,
  `intraday_main.py`), so its syntax check checked nothing.
  - It now compiles `research`.
  - The hook is untracked, so the fix lives only on this machine.

## State

- **Git:** branch `main`, pushed through `85da876`. Four newer commits are local:
  `3387d37`, `93314a8`, `ea52245`, `c045b56`.
- **Tests:** pytest, 111 passing.
- **Postgres:** the `coinpicks-db` container is stopped, and its volume `coinpicks_data` is kept.
- **Deletions blocked by permissions:** these untracked folders are gitignored, regenerable and
  harmless. Remove them by hand if wanted:
  - the root `node_modules/`;
  - `legacy/coinpicks/apps/*/node_modules`;
  - `legacy/coinpicks/apps/web/dist`.
- **Cron:** the 05:30 warehouse backfill is unchanged.

## Next session

1. **The owner reviews the spec.** Any change is made before any real-data run.
2. **`writing-plans` for phase 1: the TypeSafe recorder and its two paper books.**
   - It needs `TYPESAFE_API_KEY` and confirmed access (the site mentioned a waitlist while the
     console showed billing).
   - Freeze the feed list and the three question texts in the recorder's first commit.
3. **Then phase 2:** archive datasets, reconciliation, the exclusion list for the owner to review,
   the point-in-time universe, and `siglib/stats.py`.

## Open items

- **Revoke trading-era keys.** `.env` still holds the Binance keys, Telegram token and Claude API
  key from the trading era. Revoke them at the source.
- **Dead docker volumes:** `trade-god_postgres_data`, `trade-god_klines_cache`,
  `trade-god_swing_data`.
- **Stale datasets.** The warehouse's 5m and 15m datasets stop at 2026-07-15, because they are
  excluded from the daily refresh. Experiment 1 does not need them.
- **Stale key file.** `LightsailDefaultKey-ap-southeast-1.pem` sits untracked in the repo root,
  but its account is closed.
