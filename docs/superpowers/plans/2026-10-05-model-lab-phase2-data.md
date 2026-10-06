# Model Lab Phase 2 — Data Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put Binance's public archive into the warehouse, prove that it matches the REST
warehouse, and build what every later phase stands on: listings, the frozen exclusion list, the
point-in-time top-50 universe, and `siglib/stats.py` for the verdict statistics.

**Architecture:** Two new warehouse modules mirror the existing REST pair:
- `research/archive_source.py` handles the S3 listing, checksummed monthly downloads and parsing.
- `research/archive_backfill.py` is the resumable CLI. It stores raw archive data in five new
  warehouse datasets, and `research/archive_reconcile.py` checks that data against the REST
  `klines_1d`.

Under `research/signals/model_lab/`:
- `listings.py` turns the archive's folders into listings: settled folders merged, zero-trade
  days dropped, relisted tickers split.
- `exclusions.py` freezes what never enters the universe.
- `universe.py` ranks listings point-in-time.

`research/siglib/stats.py` holds weekly compounding, Sharpe, drawdown, Newey-West alpha and the
deflated Sharpe ratio. The warehouse stays a faithful mirror of the archive, and every cleaning
rule runs when the data is loaded.

**Tech Stack:** Python 3.14.
- pandas 3.0.3, numpy 2.4.4 and pyarrow 24.0.0, all already pinned.
- From the standard library: `urllib`, `zipfile`, `hashlib`, `xml.etree.ElementTree` and
  `statistics.NormalDist`.
- **No new dependency.** LightGBM arrives with phase 3's plan.

**Spec:** `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`, covering §1 Data, §3.2–3.3
Measurement and Gates, and §4 Code, operations and tests. Task 1 writes the archive probe's
findings (2026-10-05) into §1, §3.2–3.3 and §4; approving this plan approves that text.

## What the archive probe found (2026-10-05)

Each finding comes from downloading and reading real files, not from documentation.

| Finding | Evidence | Handled in |
|---|---|---|
| Futures CSVs before about 2022 have no header row; later ones do | `BTCUSDT-1d-2020-01` vs `BTCUSDT-1d-2026-09` | Task 2 |
| Spot klines switch to **microsecond** timestamps in 2025-01 | `BTCUSDT-1d-2025-01` starts `1735689600000000` | Task 2 |
| Funding files are `calc_time,funding_interval_hours,last_funding_rate`, with ms jitter | `BTCUSDT-fundingRate-2026-08`: `1785542400001` | Task 2 |
| The UM klines listing spans two pages (1,056 folders; S3 serves 1,000 per page) | `IsTruncated=true`, `NextMarker=…/WMTUSDT/` | Task 3 |
| Five perps have Chinese-character tickers (`币安人生USDT` and four more), and none has a premium folder | the listings | Tasks 3–4 |
| 17 settled folders (`TLMUSDTSETTLED`, `AERGOUSDTSETTLEDSETTLED`, `ICPUSDT_SETTLED`, …) exist, for klines only | listings of all three UM datasets | Tasks 3–4, 10 |
| Settled folders mostly duplicate their live folder but hold 18 traded days it lacks, among them BNX's last 11 before its 2023-02 redenomination (120 → 1.6) | row-by-row comparison of all 39 settled files | Task 10 |
| A settled contract **never stops publishing**. All 133 perps Binance lists as `SETTLING` still get a flat, zero-trade bar every day: BLZ has sat at 0.06836 since it stopped trading on 2024-12-23. Under the spec's literal rule ("when a held symbol's data ends") these contracts never delist; they stay eligible as a free, flat asset | `BLZUSDT-1d-2024-12` and `-2026-09`, `fapi` exchangeInfo statuses | Task 10 |
| The 900 archive perps are 524 trading crypto perps, 133 settled ones (as above), 31 older delistings whose data does end, and 212 TradFi contracts | exchangeInfo `status` and `contractType`, plus the listing | Tasks 9–11 |
| A relisted ticker continues in the same file: old contract, then a zero-trade halt at the settlement price, then the new contract at an unrelated price. PUMP: 0.0471, then 26 halted days, then 0.0052. TLM halted for about 9 months; CTK went 1.01 → 0.45, LIT 0.59 → 3.63 | all 17 relistings | Task 10 |
| MINA's old contract traded on 2023-02-06 (in its settled folder only), and the new one opened 2023-02-07: no gap marks the switch | `MINAUSDTSETTLED-1d-2023-02` | Task 10 |
| The last traded close is the price a settled contract then sits at: PUMP 0.0471, BLZ 0.06836 | `PUMPUSDT-1d-2025-06`, `BLZUSDT-1d-2024-12` | Task 10 checks every halt |
| The 219 live symbols in the REST warehouse have **zero** missing days and **zero** zero-trade days | scan of `klines_1d` | Task 10's rule costs live coins nothing |
| The REST warehouse starts a relisted ticker at its relisting (ICP 2022-09-27, PUMP 2025-07-11, LIT 2025-12-24) | `klines_1d` | Task 5 compares shared days only |
| The UM archive starts in **2020-01**, the first month across all 900 perps, while the REST warehouse has BTC from 2019-09-09 | the listing's first months, `klines_1d/BTCUSDT` | Task 5 checks coverage inside the archive's span only |
| 212 TradFi perps, which Binance itself labels `contractType: TRADIFI_PERPETUAL`: 174 equities and ETFs, 15 HK, 8 KR and 2 CN equities, 8 commodities, 4 pre-IPO companies and 1 FX pair. They share the UM archive with the crypto perps from 2025-12 (XAU) on, and trade every day, weekends included | exchangeInfo, first archive months, `TSLAUSDT-1d-2026-09` | Task 9 |
| Monthly files through **2026-09** are already published | `BTCUSDT-1d-2026-09` | the sealed window, which ends 2026-10-01, is fully covered |

## Global Constraints

These are copied from the spec, and every task's requirements include them.

**Data**
- All new data comes from `data.binance.vision` monthly zips, "each checked against the archive's
  published `.CHECKSUM` before it is stored".
- "The fetcher waits at least 0.2 s between requests, skips months already stored, and is
  resumable."
- "The existing REST warehouse, its datasets and the 05:30 cron are not touched."
- Reconciliation: "the closes must match to within 1e-9 relative. A mismatch fails the data step."
- Exclusions are "built from symbol names only, never from outcomes", and "committed and reviewed
  by the owner in the data step, before any model run".

**The universe**
- "Decision time is Monday 00:00 UTC. Decisions use daily bars that closed by then, meaning
  `open_time` ≤ the preceding Sunday 00:00."
- A symbol is eligible when it has "at least 60 daily bars before *d* (`siglib`'s
  `ELIGIBILITY_DAYS`)", has "a close on *d* − 1", and "is not excluded".
- Symbols rank by "the sum over the 30 daily bars ending *d* − 1", and the top 50 form the
  universe. "If fewer than 20 symbols are eligible, the book holds nothing that week."

**Statistics**
- Sharpe: "Mean ÷ standard deviation of weekly returns, × √52. The risk-free rate is 0."
- Max drawdown is "taken on the daily equity curve".
- Alpha: "An OLS regression `r_arm = α + β·r_BTC + ε` on weekly returns, with Newey-West standard
  errors at 4 lags."
- G6 follows "Bailey & López de Prado, 2014", with N = 6 and a sensitivity value at N = 60.

**Tests**
- "The suite makes **no network calls**: archive files … are recorded fixtures."

**Repo rules**
- Backfills run from the dev machine only, never from a hosted IP. Every endpoint is unsigned.
- Commit straight to `main`, with **no AI attribution** and a concise, why-focused message.
- Chain test commands with `&&`. `python -m pytest -q` is green before anything is called done.

## Review Focus

These are the five inputs most likely to bite that no other test pins, each with what a reasonable
person would expect:

1. **A settled or relisted ticker that keeps publishing bars.** All 133 settled perps get a flat,
   zero-trade bar every day, and 17 relisted tickers continue in the old contract's file. Expect a
   settled listing to end at its last traded bar and leave the universe. Expect a relisted ticker
   to become two listings, with no return across the switch and a new listing that waits its 60
   bars. Pinned in Task 10.
2. **Spot klines in microseconds from 2025-01.** Expect milliseconds in the warehouse, so a 2025
   bar lands in 2025 and not in the year 56976. Pinned in Task 2.
3. **Non-ASCII tickers** (`币安人生USDT`). Expect percent-encoded ASCII URLs and a parquet file under
   the ticker's own name. Pinned in Tasks 3 and 4.
4. **A window that opens with a loss.** Expect the starting equity of 1.0 to count as a peak, so a
   first-day loss is a drawdown. (`BacktestResult.max_drawdown` misses it on a `.window()` slice.)
   Pinned in Task 6.
5. **An arm that is an exact multiple of BTC over a window** (constant exposure, no trades). Expect
   α = 0 and t = 0, not floating-point noise that could pass G3 or count as positive in G4. Pinned
   in Task 7.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md` | modify (Task 1) | the probe's findings as spec text |
| `agents/CONTEXT.md` | modify (Task 1) | "Listing" joins the vocabulary |
| `research/binance_source.py` | modify (Task 2) | `kline_row` and `premium_row` become public and shared with the archive parser |
| `research/archive_source.py` | create (Tasks 2–3) | parse, verify, list and fetch; no storage |
| `research/config.py` | modify (Task 4) | five archive datasets and `ARCHIVE_DELAY` |
| `research/archive_backfill.py` | create (Task 4) | resumable CLI over the archive |
| `research/archive_reconcile.py` | create (Task 5) | CLI: REST vs archive closes, plus coverage |
| `research/siglib/data.py` | modify (Tasks 6, 10) | `week_start`; `load_klines(source=…)` |
| `research/siglib/stats.py` | create (Tasks 6–8) | weekly returns, Sharpe, drawdown, NW alpha, DSR |
| `research/signals/model_lab/__init__.py` | create (Task 9) | package marker |
| `research/signals/model_lab/exclusions.py` | create (Task 9) | the frozen exclusion sets |
| `research/signals/model_lab/listings.py` | create (Task 10) | archive folders → listings |
| `research/signals/model_lab/universe.py` | create (Task 11) | point-in-time top 50 per Monday, plus a review report |
| `tests/research/conftest.py` | modify (Task 3) | shared `warehouse` fixture and `FakeArchive` |
| `tests/research/test_archive_source.py` | create (Tasks 2–3) | |
| `tests/research/test_archive_backfill.py` | create (Task 4) | |
| `tests/research/test_archive_reconcile.py` | create (Task 5) | |
| `tests/research/test_siglib_stats.py` | create (Tasks 6–8) | |
| `tests/research/test_siglib_data.py` | modify (Tasks 6, 10) | |
| `tests/research/test_model_lab_exclusions.py` | create (Task 9) | |
| `tests/research/test_model_lab_listings.py` | create (Task 10) | |
| `tests/research/test_model_lab_universe.py` | create (Task 11) | |
| `CLAUDE.md`, `agents/roadmap.md` | modify (Task 12) | datasets, quirks, commands, test count |

**Order.** Do Tasks 1–4 first, then **start the full backfill**, which runs for hours (Task 4,
Step 7). Tasks 6–11 need no real data, so they proceed while it runs. Task 5's real-data run and
Task 12 wait for the backfill to finish.

---

### Task 1: Write the probe's findings into the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-10-02-daily-model-lab-design.md`
- Modify: `agents/CONTEXT.md`

**Interfaces:** none (documentation). Later tasks implement this text; where code and spec
disagree, the spec wins and the code is fixed.

- [ ] **Step 1: Record the amendment in the status lines.** After the line
  `**Amended 2026-10-05** (owner's ruling): phase 1 no longer gates phases 2–6; see Phases.` add
  the following. Use the date on which the owner approved this plan, if that is a later day.

```markdown
**Amended 2026-10-05** (owner's approval of the phase 2 plan): §1.1, §1.2, §3.2, §3.3, §4.1 and
§4.4 take in what the archive probe found: settled folders, zero-trade days, listings, TradFi
exclusions, reconciliation coverage, complete weeks, and noise-level alpha.
```

- [ ] **Step 2: §1.1. Settled folders, reconciliation coverage, TradFi exclusions.**

  First, insert this bullet after the **Symbol list** bullet:

```markdown
- **Settled folders.** The same listing holds 17 folders named `{SYMBOL}SETTLED`,
  `{SYMBOL}SETTLEDSETTLED` or `{SYMBOL}_SETTLED`, for perps Binance settled and later relisted
  under the same name. They exist for klines only and are stored in `archive_um_klines_1d` under
  their own names. Most of their rows duplicate the live folder. The rest are an old contract's
  last days, some of which only these folders hold: BNX's last 11 trading days before its 2023-02
  redenomination are there and nowhere else.
```

  Second, replace the **Reconciliation** bullet with:

```markdown
- **Reconciliation.** On every symbol and day where both the existing warehouse and the archive
  hold a perp daily close, the closes must match to within 1e-9 relative. Every REST daily bar
  between the archive's first and last day for that symbol must also be in the archive, because a
  missing day ends a listing (§1.2). The UM archive starts in 2020-01, so REST's 2019 days fall
  outside that span. A mismatch or a missing day fails the data step.
```

  Third, replace the two **Exclusions** bullets with:

```markdown
- stablecoin and pegged-asset perps;
- index or composite contracts (for example `BTCDOMUSDT`);
- perps on traditional assets: stocks, ETFs, commodities, currencies and pre-IPO company
  valuations. Binance labels them `TRADIFI_PERPETUAL`; 212 of them appeared from 2025-12 on
  (`XAUUSDT`, `NVDAUSDT`, `OPENAIUSDT`).
```

  Fourth, replace the sentence "The list is built from symbol names only, never from outcomes."
  with:

```markdown
The list is built from what each ticker is, never from outcomes: its name, plus Binance's own
`TRADIFI_PERPETUAL` label, since names like `CATUSDT` (Caterpillar) and `WENUSDT` (Wendy's) read
like coins.
```

- [ ] **Step 3: §1.2. Listings and delisting.**

  First, insert this before the paragraph that begins "A symbol is **eligible**":

```markdown
**Listings.** A ticker can outlive its contract, so the universe is built from listings:
- **A zero-trade day is not a trading day.** A settled contract gets a flat bar at its settlement
  price, with no trades, every day until Binance relists the ticker, and otherwise indefinitely.
  On 2026-10-05 all 133 settled perps still had such bars: BLZ had sat at 0.06836 since
  2024-12-23. Their data never ends, so without this rule they would never delist. None of the
  219 live symbols in the REST warehouse has a single zero-trade day.
- **A settled folder's last bar ends a contract.** Its rows, and the live folder's rows before
  that day, belong to the contract that ended there. The live rows from that day on belong to the
  next contract. MINA's old contract traded on 2023-02-06 and the new one opened on 2023-02-07,
  so no gap would have marked the switch.
- **Within a contract, every missing day starts a new listing.**

A relisted ticker is therefore a new listing. Its 60-bar count and its age start again, and no
feature or return crosses from one listing to the next. Without this rule, PUMPUSDT would step
from the old token's 0.0471 to the new token's 0.0052, a −89% day that never happened.

The latest listing keeps the ticker's name, and earlier ones are named `{SYMBOL}@{first day}`.
From here on, "symbol" means a listing.
```

  Second, replace the **Delisting** paragraph with:

```markdown
**Delisting.** A listing ends at its last traded bar, and `siglib.run_backtest` then forces its
weight to zero. That last traded close is Binance's settlement price: PUMP's 0.0471 and BLZ's
0.06836 are the prices they then sat at, and the data step checks every halt. So a crash into
delisting counts in full.
```

- [ ] **Step 4: §3.2 and §3.3. Weeks, Sharpe, alpha noise, and the trial variance.**

  First, replace the **Weekly returns** bullet with:

```markdown
- **Weekly returns.** Daily net returns are compounded from Monday 00:00 to Monday 00:00 UTC, for
  every arm and for the benchmark. Only complete weeks count. A window's leftover days at either
  end enter its daily drawdown, but no weekly statistic.
```

  Second, replace the **Sharpe** bullet with:

```markdown
- **Sharpe.** Mean ÷ sample standard deviation (ddof = 1) of weekly returns, × √52. The
  risk-free rate is 0. An arm whose returns do not vary has no Sharpe ratio, and it fails every
  gate that uses one.
```

  Third, replace the **Alpha** bullet with:

```markdown
- **Alpha.** An OLS regression `r_arm = α + β·r_BTC + ε` on weekly returns, with Newey-West
  standard errors at 4 lags (Bartlett weights, no small-sample correction). An |α| below 1e-12 per
  week is floating-point noise, for example an arm that is an exact multiple of BTC over a window,
  and counts as α = 0 with t = 0.
```

  Fourth, in **How G6 is computed**, replace the "benchmark Sharpe" bullet with:

```markdown
- **The benchmark Sharpe** comes from the sample variance (ddof = 1, the conservative choice) of
  those 6 trials' validation Sharpe ratios, in weekly units.
```

- [ ] **Step 5: §4.1 and §4.4. Layout and tests.**

  First, in the §4.1 layout block, add a line after `research/archive_backfill.py …`:

```
research/archive_reconcile.py         # CLI: REST vs archive daily closes and coverage; exit 1 on any miss
```

  Second, add this line after `├── exclusions.py …`:

```
├── listings.py                       # settled folders, zero-trade days, relistings → listings
```

  Third, append this bullet to §4.4:

```markdown
- **Listings.** A relisted ticker splits at its halt. A settled folder fills only the days its
  live folder lacks. A settled folder's last bar separates two contracts even when no day is
  missing between them.
```

- [ ] **Step 6: Vocabulary.** In `agents/CONTEXT.md`, under "## The data", add this entry after
  **Eligibility**:

```markdown
**Listing** — one contract's tradable life under a ticker: a run of traded daily bars that ends
at a settlement or a missing day.
- A relisted ticker is a new listing. Earlier listings are named `TICKER@YYYY-MM-DD`, after their
  first day.
- Eligibility, age and features are per listing.
- In code: `model_lab.listings.split_listings`.

_Avoid_: "symbol" or "coin" when a listing is meant.
```

  In the **Eligibility** entry, replace the `In code:` line with:
  `- In code: `eligible_mask`, `pit_top30_mask`, `model_lab.universe.build_universe`.`

- [ ] **Step 7: Commit.**

```bash
git add docs/superpowers/specs/2026-10-02-daily-model-lab-design.md agents/CONTEXT.md
git commit -m "docs: write the archive probe's findings into the Experiment 1 spec

Relisted tickers, settled folders and TradFi perps would otherwise leak fake
returns and non-crypto assets into the universe; the text lands before any
model run, as pre-registration requires."
```

---

### Task 2: Archive parsing and checksum verification

**Files:**
- Modify: `research/binance_source.py:34` (rename `_kline_row` → `kline_row`) and
  `research/binance_source.py:82-95` (extract `premium_row`)
- Create: `research/archive_source.py`
- Test: `tests/research/test_archive_source.py`

**Interfaces:**
- Produces:
  - `binance_source.kline_row(k: list) -> dict` with keys `open_time, open, high, low, close,
    volume, close_time, quote_volume, trades, taker_buy_volume, taker_buy_quote_volume`.
  - `binance_source.premium_row(k: list) -> dict` with keys `open_time, open, high, low, close,
    close_time`.
  - `archive_source.verify_checksum(payload: bytes, checksum_text: str) -> None`, which raises
    `ValueError("checksum mismatch …")`.
  - `archive_source.read_csv_rows(payload: bytes) -> list[list[str]]`, without the header row.
  - `archive_source.parse_klines(rows) -> list[dict]` (keys as `kline_row`, times in ms).
  - `archive_source.parse_premium(rows) -> list[dict]` (keys as `premium_row`, times in ms).
  - `archive_source.parse_funding(rows) -> list[dict]` with keys `funding_time,
    funding_interval_hours, funding_rate`.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_archive_source.py`:

```python
"""archive_source turns the public archive's monthly zips into warehouse rows: checksum first,
then parsing that copes with header rows, microsecond spot timestamps and funding jitter.

The CSV lines below are real rows from data.binance.vision (2026-10-05), trimmed."""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from research import archive_source as src

KLINE_HEADER = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,"
                "taker_buy_volume,taker_buy_quote_volume,ignore")
FUTURES_2020 = (  # no header row, as in every futures file before about 2022
    "1577836800000,7189.43,7260.43,7170.15,7197.57,56801.329,1577923199999,409678760.56957,101871,28834.200,208001969.84595,0\n"
    "1577923200000,7197.57,7209.59,6922.00,6962.04,115295.677,1578009599999,815627831.08338,224747,55404.262,391911677.42577,0\n"
)
FUTURES_2026 = KLINE_HEADER + "\n" + (
    "1788220800000,78549.60,79196.00,76368.00,77400.10,151357.832,1788307199999,11776717838.40160,3622828,72544.811,5646145648.39730,0\n"
)
SPOT_2025 = (  # microseconds, as in every spot file from 2025-01
    "1735689600000000,93576.00000000,95151.15000000,92888.00000000,94591.79000000,10373.32613000,"
    "1735775999999999,975444194.13799830,1516556,5347.73648000,502914035.64059070,0\n"
)
FUNDING = (
    "calc_time,funding_interval_hours,last_funding_rate\n"
    "1785542400001,8,0.00004123\n"
    "1785571200002,8,-0.00001500\n"
)
PREMIUM = KLINE_HEADER + "\n" + (
    "1785542400000,-0.00039615,-0.00000792,-0.00140974,-0.00046270,0,1785628799999,0,17280,0,0,0\n"
)


def _zip(text: str, *names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names or ("data.csv",):
            zf.writestr(name, text)
    return buf.getvalue()


def test_futures_klines_without_a_header_row():
    rows = src.parse_klines(src.read_csv_rows(_zip(FUTURES_2020)))
    assert [r["open_time"] for r in rows] == [1577836800000, 1577923200000]
    assert rows[0]["close"] == 7197.57 and rows[0]["trades"] == 101871
    assert rows[0]["taker_buy_quote_volume"] == 208001969.84595


def test_futures_klines_with_a_header_row():
    [row] = src.parse_klines(src.read_csv_rows(_zip(FUTURES_2026)))
    assert row["open_time"] == 1788220800000 and row["quote_volume"] == 11776717838.4016


def test_spot_microsecond_timestamps_become_milliseconds():
    [row] = src.parse_klines(src.read_csv_rows(_zip(SPOT_2025)))
    assert row["open_time"] == 1735689600000  # 2025-01-01 00:00 UTC
    assert row["close_time"] == 1735775999999


def test_funding_keeps_jitter_and_interval():
    rows = src.parse_funding(src.read_csv_rows(_zip(FUNDING)))
    assert rows[0] == {"funding_time": 1785542400001, "funding_interval_hours": 8,
                       "funding_rate": 0.00004123}
    assert rows[1]["funding_rate"] == -0.000015


def test_premium_keeps_ohlc_and_times_only():
    [row] = src.parse_premium(src.read_csv_rows(_zip(PREMIUM)))
    assert row == {"open_time": 1785542400000, "open": -0.00039615, "high": -0.00000792,
                   "low": -0.00140974, "close": -0.0004627, "close_time": 1785628799999}


def test_checksum_must_match():
    payload = _zip(FUTURES_2020)
    published = f"{hashlib.sha256(payload).hexdigest()}  BTCUSDT-1d-2020-01.zip\n"
    src.verify_checksum(payload, published)
    with pytest.raises(ValueError, match="checksum mismatch"):
        src.verify_checksum(payload + b"x", published)


def test_a_zip_must_hold_exactly_one_csv():
    with pytest.raises(ValueError, match="one CSV"):
        src.read_csv_rows(_zip(FUTURES_2020, "a.csv", "b.csv"))
```

- [ ] **Step 2: Run the tests to see them fail.**

Run: `python -m pytest tests/research/test_archive_source.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'research.archive_source'`.

- [ ] **Step 3: Make the REST row builders public** in `research/binance_source.py`. Rename
`_kline_row` to `kline_row`, at its definition (line 34) and its one call in `fetch_klines`. Then
replace the inline dict in `fetch_premium_index` with a named builder placed right after
`kline_row`:

```python
def premium_row(k: list) -> dict:
    """Premium-index klines carry no volume or trade data, so keep OHLC and times only."""
    return {"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "close_time": int(k[6])}
```

  and in `fetch_premium_index`, delete the old comment and dict and end with:

```python
    return [premium_row(k) for k in _drop_unclosed(raw, _now_ms())]
```

- [ ] **Step 4: Create `research/archive_source.py`** with the parsing half:

```python
"""Binance's public archive (data.binance.vision): listing, checksummed downloads, parsing.

Every archive file is a monthly zip holding one CSV, published beside a `.CHECKSUM` in sha256sum
format (`<hex>  <file name>`). Quirks seen in real files on 2026-10-05:
- futures CSVs have a header row from about 2022 on; older ones have none;
- spot klines switch from millisecond to microsecond timestamps in 2025-01;
- funding files are `calc_time,funding_interval_hours,last_funding_rate`, with ms jitter.
Nothing here writes to the warehouse; research.archive_backfill does.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

from research.binance_source import kline_row, premium_row

# Epoch milliseconds reach 1e14 only in the year 5138; epoch microseconds passed it in 1973.
MICROS_FLOOR = 10**14


def verify_checksum(payload: bytes, checksum_text: str) -> None:
    """Raise unless the payload's sha256 is the one the archive published."""
    expected = checksum_text.split()[0]
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch: published {expected}, downloaded {actual}")


def read_csv_rows(payload: bytes) -> list[list[str]]:
    """The zip's single CSV, split into cells, without its header row if it has one."""
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one CSV in the zip, found {names}")
        text = zf.read(names[0]).decode()
    rows = [line.split(",") for line in text.splitlines() if line]
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]
    return rows


def _as_ms(t: int) -> int:
    return t // 1000 if t >= MICROS_FLOOR else t


def _ms_times(row: dict) -> dict:
    return {**row, "open_time": _as_ms(row["open_time"]), "close_time": _as_ms(row["close_time"])}


def parse_klines(rows: list[list[str]]) -> list[dict]:
    return [_ms_times(kline_row(cells)) for cells in rows]


def parse_premium(rows: list[list[str]]) -> list[dict]:
    return [_ms_times(premium_row(cells)) for cells in rows]


def parse_funding(rows: list[list[str]]) -> list[dict]:
    return [
        {"funding_time": _as_ms(int(c[0])), "funding_interval_hours": int(c[1]),
         "funding_rate": float(c[2])}
        for c in rows
    ]
```

- [ ] **Step 5: Run the new tests and the whole suite.**

Run: `python -m pytest tests/research/test_archive_source.py -q && python -m pytest -q`
Expected: 7 new tests pass, and the existing `test_binance_source.py` still passes after the
rename.

- [ ] **Step 6: Commit.**

```bash
git add research/binance_source.py research/archive_source.py tests/research/test_archive_source.py
git commit -m "feat: parse Binance archive files behind a checksum check

Archive CSVs change format mid-history (header rows, microsecond spot
timestamps); parsing them in one place keeps every later phase on milliseconds."
```

---

### Task 3: Archive listing and checksummed monthly fetch

**Files:**
- Modify: `research/archive_source.py` (append)
- Modify: `tests/research/conftest.py` (shared fixtures)
- Test: `tests/research/test_archive_source.py` (append)

**Interfaces:**
- Consumes: Task 2's `verify_checksum`, `read_csv_rows`, `parse_klines`, `parse_premium` and
  `parse_funding`.
- Produces:
  - `ARCHIVE_URL: str`, `LISTING_URL: str` and `SPOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")`.
  - `SOURCES: dict[str, Source]`, keyed by the five dataset names `archive_spot_klines_1d`,
    `archive_spot_klines_1h`, `archive_um_klines_1d`, `archive_um_funding` and
    `archive_um_premium_1d`.
  - `http_get(url: str) -> bytes`.
  - `list_keys(prefix, *, get, delay, delimiter=None) -> list[str]`.
  - `settled_base(name: str) -> str | None`.
  - `list_um_symbols(*, get, delay) -> tuple[list[str], list[str]]`, returning (perps, settled
    folders).
  - `list_month_keys(dataset, symbol, *, get, delay) -> dict[str, str]` (month → zip key).
  - `fetch_month(dataset, key, *, get, delay) -> list[dict]`.
  - Test fixtures `warehouse`, a temporary warehouse directory, and `archive`, a `FakeArchive`
    with `.publish(key, csv_text, *, corrupt=False)`, `.urls` and `.page_size`.

- [ ] **Step 1: Shared test fixtures.** Replace `tests/research/conftest.py` with the following.
  Older test files keep their own `warehouse` fixtures; a local fixture overrides this one.

```python
"""Research tests need the dev-only deps; skip the whole directory without them.

Shared fixtures: `warehouse` points the store at a temp dir; `archive` stands in for
data.binance.vision and its S3 listing, so no test touches the network.
"""

import hashlib
import io
import urllib.error
import urllib.parse
import zipfile

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from research import archive_source, config  # noqa: E402  (the skips above guard these imports)


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class FakeArchive:
    """data.binance.vision in memory: published files plus S3-style paged listings.

    Call it like archive_source.http_get. Every requested URL is kept in `urls`."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.urls: list[str] = []
        self.page_size = 1000

    def publish(self, key: str, csv_text: str, *, corrupt: bool = False) -> None:
        """Publish a monthly zip holding one CSV beside its .CHECKSUM (a wrong one if corrupt)."""
        name = key.rsplit("/", 1)[-1]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(name.removesuffix(".zip") + ".csv", csv_text)
        payload = buf.getvalue()
        digest = hashlib.sha256(b"tampered" if corrupt else payload).hexdigest()
        self.files[key] = payload
        self.files[key + ".CHECKSUM"] = f"{digest}  {name}\n".encode()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url.startswith(archive_source.LISTING_URL):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)
            return self._listing(query["prefix"][0], query["marker"][0], "delimiter" in query)
        key = urllib.parse.unquote(url.removeprefix(archive_source.ARCHIVE_URL))
        if key not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return self.files[key]

    def _listing(self, prefix: str, marker: str, delimited: bool) -> bytes:
        entries = sorted(k for k in self.files if k.startswith(prefix))
        if delimited:
            entries = sorted({prefix + k[len(prefix):].split("/")[0] + "/"
                              for k in entries if "/" in k[len(prefix):]})
        remaining = [e for e in entries if e > marker]
        page, truncated = remaining[: self.page_size], len(remaining) > self.page_size
        tag = ("<CommonPrefixes><Prefix>{}</Prefix></CommonPrefixes>" if delimited
               else "<Contents><Key>{}</Key></Contents>")
        next_marker = f"<NextMarker>{page[-1]}</NextMarker>" if delimited and truncated else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>{next_marker}"
            + "".join(tag.format(e) for e in page)
            + "</ListBucketResult>"
        ).encode()


@pytest.fixture
def archive():
    return FakeArchive()
```

- [ ] **Step 2: Write the failing tests** by appending to `tests/research/test_archive_source.py`:

```python
UM = "data/futures/um/monthly/klines/"


def test_list_keys_follows_every_page(archive):
    archive.page_size = 2
    for month in ("2026-07", "2026-08", "2026-09"):
        archive.publish(f"{UM}BTCUSDT/1d/BTCUSDT-1d-{month}.zip", FUTURES_2026)
    keys = src.list_keys(f"{UM}BTCUSDT/1d/", get=archive, delay=0)
    assert len(keys) == 6  # three zips, three checksums
    assert len(archive.urls) == 3  # pages of two


@pytest.mark.parametrize("name, base", [
    ("TLMUSDTSETTLED", "TLMUSDT"),
    ("AERGOUSDTSETTLEDSETTLED", "AERGOUSDT"),
    ("ICPUSDT_SETTLED", "ICPUSDT"),
    ("BTCUSDT", None),
])
def test_settled_base(name, base):
    assert src.settled_base(name) == base


def test_um_symbols_are_usdt_perps_plus_their_settled_folders(archive):
    archive.page_size = 3  # the delimited listing pages too
    for name in ("BTCUSDT", "BTCUSDT_210326", "ETHBUSD", "TLMUSDT", "TLMUSDTSETTLED",
                 "ICPUSDT", "ICPUSDT_SETTLED", "AERGOUSDT", "AERGOUSDTSETTLEDSETTLED",
                 "GONEUSDTSETTLED", "币安人生USDT"):
        archive.publish(f"{UM}{name}/1d/{name}-1d-2026-09.zip", FUTURES_2026)
    perps, settled = src.list_um_symbols(get=archive, delay=0)
    assert perps == ["AERGOUSDT", "BTCUSDT", "ICPUSDT", "TLMUSDT", "币安人生USDT"]
    assert settled == ["AERGOUSDTSETTLEDSETTLED", "ICPUSDT_SETTLED", "TLMUSDTSETTLED"]


def test_month_keys_cover_every_published_zip(archive):
    folder = "data/futures/um/monthly/fundingRate/BTCUSDT/"
    for month in ("2026-08", "2026-09"):
        archive.publish(f"{folder}BTCUSDT-fundingRate-{month}.zip", FUNDING)
    assert src.list_month_keys("archive_um_funding", "BTCUSDT", get=archive, delay=0) == {
        "2026-08": f"{folder}BTCUSDT-fundingRate-2026-08.zip",
        "2026-09": f"{folder}BTCUSDT-fundingRate-2026-09.zip",
    }


def test_fetch_month_verifies_before_parsing(archive):
    good, bad = (f"{UM}BTCUSDT/1d/BTCUSDT-1d-{m}.zip" for m in ("2026-09", "2026-08"))
    archive.publish(good, FUTURES_2026)
    archive.publish(bad, FUTURES_2026, corrupt=True)
    [row] = src.fetch_month("archive_um_klines_1d", good, get=archive, delay=0)
    assert row["open_time"] == 1788220800000
    with pytest.raises(ValueError, match="checksum mismatch"):
        src.fetch_month("archive_um_klines_1d", bad, get=archive, delay=0)


def test_non_ascii_tickers_are_percent_encoded(archive):
    archive.publish(f"{UM}币安人生USDT/1d/币安人生USDT-1d-2026-09.zip", FUTURES_2026)
    months = src.list_month_keys("archive_um_klines_1d", "币安人生USDT", get=archive, delay=0)
    src.fetch_month("archive_um_klines_1d", months["2026-09"], get=archive, delay=0)
    assert archive.urls and all(url.isascii() for url in archive.urls)
```

- [ ] **Step 3: Run them to see them fail.**

Run: `python -m pytest tests/research/test_archive_source.py -q`
Expected: the six new tests fail with `AttributeError: module 'research.archive_source' has no
attribute 'list_keys'` (or `settled_base`, `LISTING_URL`).

- [ ] **Step 4: Implement the listing and fetching half.** First, add these imports at the top of
  `research/archive_source.py`, merged with the existing ones and sorted:

```python
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
```

  Then append the following at the end of the module:

```python
ARCHIVE_URL = "https://data.binance.vision/"
LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
UM_KLINES_ROOT = "data/futures/um/monthly/klines/"
MONTH_RE = re.compile(r"-(\d{4}-\d{2})\.zip$")
SPOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True)
class Source:
    folder: str  # S3 prefix holding one symbol's monthly files; {symbol} is filled in
    parse: Callable[[list[list[str]]], list[dict]]


SOURCES: dict[str, Source] = {
    "archive_spot_klines_1d": Source("data/spot/monthly/klines/{symbol}/1d/", parse_klines),
    "archive_spot_klines_1h": Source("data/spot/monthly/klines/{symbol}/1h/", parse_klines),
    "archive_um_klines_1d": Source("data/futures/um/monthly/klines/{symbol}/1d/", parse_klines),
    "archive_um_funding": Source("data/futures/um/monthly/fundingRate/{symbol}/", parse_funding),
    "archive_um_premium_1d": Source(
        "data/futures/um/monthly/premiumIndexKlines/{symbol}/1d/", parse_premium),
}


def http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _paced(get, url: str, delay: float) -> bytes:
    """The spec's pacing: wait at least `delay` seconds before every request."""
    if delay > 0:
        time.sleep(delay)
    return get(url)


def list_keys(prefix: str, *, get, delay: float, delimiter: str | None = None) -> list[str]:
    """Every key under `prefix` (or, given a delimiter, every sub-folder), across S3's pages."""
    found: list[str] = []
    marker = ""
    while True:
        query = {"prefix": prefix, "marker": marker}
        if delimiter:
            query["delimiter"] = delimiter
        root = ET.fromstring(_paced(get, f"{LISTING_URL}?{urllib.parse.urlencode(query)}", delay))
        path = "s3:CommonPrefixes/s3:Prefix" if delimiter else "s3:Contents/s3:Key"
        page = [el.text for el in root.iterfind(path, S3_NS)]
        found += page
        if root.findtext("s3:IsTruncated", namespaces=S3_NS) != "true":
            return found
        # S3 names the next marker only for delimited listings; otherwise it is the last key.
        marker = root.findtext("s3:NextMarker", namespaces=S3_NS) or page[-1]


def settled_base(name: str) -> str | None:
    """The ticker a settled folder belongs to (TLMUSDTSETTLED, AERGOUSDTSETTLEDSETTLED and
    ICPUSDT_SETTLED → TLMUSDT, AERGOUSDT and ICPUSDT), or None for an ordinary folder."""
    if "SETTLED" not in name:
        return None
    return name.split("SETTLED")[0].rstrip("_")


def list_um_symbols(*, get, delay: float) -> tuple[list[str], list[str]]:
    """(USDT perps, their settled folders) from the archive's UM klines listing (spec §1.1).

    A perp is a USDT-quoted name without `_`, which marks dated delivery contracts."""
    names = [p[len(UM_KLINES_ROOT):].rstrip("/")
             for p in list_keys(UM_KLINES_ROOT, get=get, delay=delay, delimiter="/")]
    perps = sorted(n for n in names if n.endswith("USDT") and "_" not in n)
    known = set(perps)
    settled = sorted(n for n in names if settled_base(n) in known)
    return perps, settled


def list_month_keys(dataset: str, symbol: str, *, get, delay: float) -> dict[str, str]:
    """month ('YYYY-MM') → zip key, for every monthly zip published for this dataset and symbol."""
    months = {}
    for key in list_keys(SOURCES[dataset].folder.format(symbol=symbol), get=get, delay=delay):
        match = MONTH_RE.search(key)
        if match:
            months[match.group(1)] = key
    return dict(sorted(months.items()))


def fetch_month(dataset: str, key: str, *, get, delay: float) -> list[dict]:
    """Download one monthly zip and its checksum, verify, parse. Nothing unverified is returned.

    Keys are percent-encoded: five tickers are Chinese characters (币安人生USDT …)."""
    checksum = _paced(get, ARCHIVE_URL + urllib.parse.quote(key + ".CHECKSUM"), delay).decode()
    payload = _paced(get, ARCHIVE_URL + urllib.parse.quote(key), delay)
    verify_checksum(payload, checksum)
    return SOURCES[dataset].parse(read_csv_rows(payload))
```

  A zip published without its `.CHECKSUM` is not skipped: `fetch_month` gets a 404 for the
  checksum, and the backfill reports that month as a failure. Every stored month is a verified
  one.

- [ ] **Step 5: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_archive_source.py -q && python -m pytest -q`
Expected: all of `test_archive_source.py` passes (16 tests counting the parametrized cases), and
so does the rest of the suite.

- [ ] **Step 6: Commit.**

```bash
git add research/archive_source.py tests/research/conftest.py tests/research/test_archive_source.py
git commit -m "feat: list and fetch the Binance archive month by month

The UM listing spans two S3 pages and five tickers are Chinese characters,
so paging and percent-encoding are pinned by an in-memory archive fake."
```

---

### Task 4: The archive backfill CLI, then start the real run

**Files:**
- Modify: `research/config.py`
- Create: `research/archive_backfill.py`
- Test: `tests/research/test_archive_backfill.py`

**Interfaces:**
- Consumes: from Task 3, `src.SOURCES`, `src.SPOT_SYMBOLS`, `src.http_get`,
  `src.list_um_symbols`, `src.list_month_keys` and `src.fetch_month`; and the `warehouse` and
  `archive` fixtures.
- Produces:
  - `config.ARCHIVE_DELAY = 0.2`, and the five archive datasets in `config.DATASETS`.
  - `archive_backfill.stored_months(dataset, symbol) -> set[str]`.
  - `archive_backfill.work_list(perps, settled) -> dict[str, list[str]]`.
  - `archive_backfill.run(work, *, get, delay) -> Summary`, where `Summary.new_rows:
    dict[(dataset, symbol), int]` and `Summary.failures: list[(dataset, symbol, month | None)]`.
  - The CLI `python -m research.archive_backfill [--datasets …] [--symbols …] [--dry-run]`.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_archive_backfill.py`:

```python
"""archive_backfill: every published month is fetched once, verified and stored; reruns resume;
a bad month is reported and retried, never stored."""

from __future__ import annotations

import urllib.error
import urllib.parse

from research import archive_backfill as backfill
from research import store

UM = "data/futures/um/monthly/klines/"
AUGUST = "1785542400000,1,1,1,1,1,1785628799999,1,1,1,1,0\n"
SEPTEMBER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
    "taker_buy_quote_volume,ignore\n"
    "1788220800000,78549.60,79196.00,76368.00,77400.10,151357.832,1788307199999,"
    "11776717838.40160,3622828,72544.811,5646145648.39730,0\n"
)
KLINES = {"archive_um_klines_1d": ["BTCUSDT"]}


def _publish(archive, symbol, month, text, corrupt=False):
    archive.publish(f"{UM}{symbol}/1d/{symbol}-1d-{month}.zip", text, corrupt=corrupt)


def test_first_run_stores_every_published_month(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == []
    assert summary.new_rows[("archive_um_klines_1d", "BTCUSDT")] == 2
    stored = store.load("archive_um_klines_1d", "BTCUSDT")
    assert list(stored["open_time"]) == [1785542400000, 1788220800000]


def test_rerun_downloads_only_what_is_missing(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)
    backfill.run(KLINES, get=archive, delay=0)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)  # a month published later
    archive.urls.clear()
    backfill.run(KLINES, get=archive, delay=0)
    downloads = [u for u in archive.urls if u.startswith(backfill.src.ARCHIVE_URL)]
    assert len(downloads) == 2 and all("2026-09" in u for u in downloads)  # zip + checksum


def test_corrupt_month_is_reported_never_stored_and_retried(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST, corrupt=True)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == [("archive_um_klines_1d", "BTCUSDT", "2026-08")]
    assert list(store.load("archive_um_klines_1d", "BTCUSDT")["open_time"]) == [1788220800000]
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)  # republished intact
    assert backfill.run(KLINES, get=archive, delay=0).failures == []
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 2


def test_a_listing_failure_stays_with_its_symbol(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)

    def flaky(url):
        if "BADUSDT" in urllib.parse.unquote(url):
            raise urllib.error.URLError("timed out")
        return archive(url)

    summary = backfill.run({"archive_um_klines_1d": ["BADUSDT", "BTCUSDT"]}, get=flaky, delay=0)
    assert summary.failures == [("archive_um_klines_1d", "BADUSDT", None)]
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 1


def test_work_list_routes_each_dataset():
    work = backfill.work_list(["BTCUSDT", "TLMUSDT"], ["TLMUSDTSETTLED"])
    assert work["archive_spot_klines_1d"] == work["archive_spot_klines_1h"] == ["BTCUSDT", "ETHUSDT"]
    assert work["archive_um_klines_1d"] == ["BTCUSDT", "TLMUSDT", "TLMUSDTSETTLED"]
    assert work["archive_um_funding"] == work["archive_um_premium_1d"] == ["BTCUSDT", "TLMUSDT"]


def test_a_non_ascii_ticker_is_stored_under_its_own_name(warehouse, archive):
    _publish(archive, "币安人生USDT", "2026-09", SEPTEMBER)
    backfill.run({"archive_um_klines_1d": ["币安人生USDT"]}, get=archive, delay=0)
    assert len(store.load("archive_um_klines_1d", "币安人生USDT")) == 1


def test_stored_months_come_from_the_time_column(warehouse):
    rows = [{"funding_time": 1785542400001, "funding_rate": 0.0},   # 2026-08-01
            {"funding_time": 1788220800001, "funding_rate": 0.0}]   # 2026-09-01
    store.upsert("archive_um_funding", "BTCUSDT", rows, "funding_time")
    assert backfill.stored_months("archive_um_funding", "BTCUSDT") == {"2026-08", "2026-09"}
    assert backfill.stored_months("archive_um_funding", "ETHUSDT") == set()
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_archive_backfill.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'research.archive_backfill'`.

- [ ] **Step 3: Register the datasets.** In `research/config.py`, add this under
  `RATE_LIMIT_DELAY`:

```python
ARCHIVE_DELAY = 0.2  # seconds between data.binance.vision requests (spec 2026-10-02 §1.1)
```

  and add these entries at the end of `DATASETS`:

```python
    # Binance public archive (data.binance.vision), monthly files: spec 2026-10-02 §1.1
    "archive_spot_klines_1d": ("open_time", DAY_MS),
    "archive_spot_klines_1h": ("open_time", HOUR_MS),
    "archive_um_klines_1d": ("open_time", DAY_MS),
    "archive_um_funding": ("funding_time", 8 * HOUR_MS),
    "archive_um_premium_1d": ("open_time", DAY_MS),
```

- [ ] **Step 4: Create `research/archive_backfill.py`:**

```python
"""Resumable backfill of Binance's public archive into the warehouse (spec 2026-10-02 §1.1).

    python -m research.archive_backfill                     # every archive dataset and symbol
    python -m research.archive_backfill --datasets archive_um_klines_1d --symbols BNXUSDT,BNXUSDTSETTLED
    python -m research.archive_backfill --dry-run           # list the work, fetch no data

Run from the DEV machine only. Each run re-lists the archive and downloads only months not yet
stored, so an interrupted run resumes where it stopped. The first full run makes about 137,000
requests, about 22,000 monthly files per UM dataset each with a checksum, and takes roughly a day
at the 0.2 s pacing. The REST warehouse, its datasets and the 05:30 cron are untouched: every
archive dataset has its own folder.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import pandas as pd

from research import archive_source as src
from research import config, store


@dataclass
class Summary:
    new_rows: dict = field(default_factory=dict)  # (dataset, symbol) -> int
    failures: list = field(default_factory=list)  # [(dataset, symbol, month or None)]


def stored_months(dataset: str, symbol: str) -> set[str]:
    """Months ('YYYY-MM') with at least one stored row; those are never downloaded again."""
    time_col, _ = config.DATASETS[dataset]
    df = store.load(dataset, symbol)
    if df.empty:
        return set()
    return set(pd.to_datetime(df[time_col], unit="ms", utc=True).dt.strftime("%Y-%m"))


def work_list(perps: list[str], settled: list[str]) -> dict[str, list[str]]:
    """Symbols per dataset: spot is BTC and ETH only, and settled folders exist for klines only."""
    return {
        "archive_spot_klines_1d": list(src.SPOT_SYMBOLS),
        "archive_spot_klines_1h": list(src.SPOT_SYMBOLS),
        "archive_um_klines_1d": perps + settled,
        "archive_um_funding": perps,
        "archive_um_premium_1d": perps,
    }


def _backfill_one(dataset: str, symbol: str, *, get, delay: float, summary: Summary) -> None:
    try:
        months = src.list_month_keys(dataset, symbol, get=get, delay=delay)
    except Exception as e:
        summary.failures.append((dataset, symbol, None))
        print(f"{symbol:<24} {dataset:<24} listing FAILED: {e}", file=sys.stderr)
        return
    time_col, _ = config.DATASETS[dataset]
    have = stored_months(dataset, symbol)
    added = 0
    for month, key in months.items():
        if month in have:
            continue
        try:
            rows = src.fetch_month(dataset, key, get=get, delay=delay)
            added += store.upsert(dataset, symbol, rows, time_col)
        except Exception as e:
            summary.failures.append((dataset, symbol, month))
            print(f"{symbol:<24} {dataset:<24} {month} FAILED: {e}", file=sys.stderr)
    summary.new_rows[(dataset, symbol)] = added
    print(f"{symbol:<24} {dataset:<24} +{added} rows")


def run(work: dict[str, list[str]], *, get, delay: float) -> Summary:
    summary = Summary()
    for dataset, symbols in work.items():
        for symbol in symbols:
            _backfill_one(dataset, symbol, get=get, delay=delay, summary=summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", default=",".join(src.SOURCES),
                        help=f"subset of: {','.join(src.SOURCES)}")
    parser.add_argument("--symbols", help="comma-separated override, applied to every dataset")
    parser.add_argument("--dry-run", action="store_true", help="list the work, fetch no data")
    args = parser.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    unknown = [d for d in datasets if d not in src.SOURCES]
    if unknown:
        parser.error(f"unknown datasets: {unknown}")

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        work = {d: symbols for d in datasets}
    else:
        perps, settled = src.list_um_symbols(get=src.http_get, delay=config.ARCHIVE_DELAY)
        print(f"Archive listing: {len(perps)} USDT perps, {len(settled)} settled folders")
        everything = work_list(perps, settled)
        work = {d: everything[d] for d in datasets}

    if args.dry_run:
        for dataset, symbols in work.items():
            print(f"{dataset:<24} {len(symbols)} symbols")
        return

    summary = run(work, get=src.http_get, delay=config.ARCHIVE_DELAY)
    total = sum(summary.new_rows.values())
    print(f"\nDone: +{total} rows across {len(summary.new_rows)} tasks; "
          f"{len(summary.failures)} failures")
    if summary.failures:
        for dataset, symbol, month in summary.failures:
            print(f"  FAILED {symbol} {dataset} {month or 'listing'}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_archive_backfill.py -q && python -m pytest -q`
Expected: 7 new tests pass, and so does the rest of the suite.

- [ ] **Step 6: Commit.**

```bash
git add research/config.py research/archive_backfill.py tests/research/test_archive_backfill.py
git commit -m "feat: resumable backfill of the Binance public archive

Delisted perps exist only in the archive, and the PIT universe needs them;
months already stored are skipped so a day-long first run can be interrupted."
```

- [ ] **Step 7: Start the full backfill** in the background. Write the log under the gitignored
  warehouse, because `/tmp` is tmpfs on this machine and empties at every reboot.

```bash
python -m research.archive_backfill --dry-run
nohup python -m research.archive_backfill > research/warehouse/archive-backfill.log 2>&1 &
```

  The dry run should print `Archive listing: 900 USDT perps, 17 settled folders`, or slightly more
  if Binance has listed perps since 2026-10-05. Then let the full run go.
  - **How long.** About 137,000 requests: 22,252 monthly kline files over 900 perps, about as many
    each for funding and premium, every file with its checksum, plus listings. On 2026-10-05 each
    request took 0.3–0.8 s to answer, on top of the 0.2 s pacing, so expect roughly a day.
  - **What finishes first.** The datasets run in order (spot, then UM klines, then funding, then
    premium), so `archive_um_klines_1d` is complete about a third of the way in. Task 5's real run
    and Task 11's report need only that dataset.
  - **Checking on it.** Run `tail -3 research/warehouse/archive-backfill.log`.
  - **Failures.** When the run ends with failures, rerun the same command; months already stored
    are skipped. Stop when a run ends with `0 failures`. A month that keeps failing on its checksum
    is a finding for the owner, not something to work around.

---

### Task 5: Reconcile the archive against the REST warehouse

**Files:**
- Create: `research/archive_reconcile.py`
- Test: `tests/research/test_archive_reconcile.py`

**Interfaces:**
- Consumes: `store.load`, `siglib.data.list_symbols` and the `warehouse` fixture.
- Produces: `archive_reconcile.REL_TOL = 1e-9`; `compare(rest, archive) -> (DataFrame,
  list[int])`; `reconcile() -> dict` with keys `symbols`, `days`, `mismatches` (a list of dicts
  with `symbol, open_time, close_rest, close_archive, rel_diff`) and `missing` (a list of
  `(symbol, open_time)`); and the CLI `python -m research.archive_reconcile`, which exits 1 on
  any mismatch or missing day.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_archive_reconcile.py`:

```python
"""Reconciliation (spec §1.1): shared days must agree within 1e-9 relative, and a REST day the
archive lacks fails too, because a missing day would end a live coin's listing."""

from __future__ import annotations

from research import archive_reconcile as rec
from research import store

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _days(dataset, symbol, closes, first=0):
    rows = [{"open_time": BASE + (first + i) * DAY, "close": c} for i, c in enumerate(closes)]
    store.upsert(dataset, symbol, rows, "open_time")


def test_identical_closes_pass(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0, 102.0])
    report = rec.reconcile()
    assert report["symbols"] == 1 and report["days"] == 3
    assert report["mismatches"] == [] and report["missing"] == []


def test_a_planted_mismatch_is_caught(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0001, 102.0])
    [m] = rec.reconcile()["mismatches"]
    assert m["symbol"] == "BTCUSDT" and m["open_time"] == BASE + DAY


def test_float_noise_inside_the_tolerance_passes(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0 * (1 + 1e-12)])
    assert rec.reconcile()["mismatches"] == []


def test_a_rest_day_the_archive_lacks_is_caught(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0])
    _days(rec.ARCHIVE, "BTCUSDT", [102.0], first=2)
    assert rec.reconcile()["missing"] == [("BTCUSDT", BASE + DAY)]


def test_rest_days_after_the_archive_ends_are_not_missing(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0, 103.0])  # REST runs into the current month
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0])  # the archive stops at the last full month
    report = rec.reconcile()
    assert report["missing"] == [] and report["days"] == 2


def test_rest_days_before_the_archive_starts_are_not_missing(warehouse):
    _days(rec.REST, "BTCUSDT", [99.0, 100.0, 101.0])  # REST's BTC starts 2019-09-09
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0], first=1)  # the UM archive starts 2020-01
    report = rec.reconcile()
    assert report["missing"] == [] and report["days"] == 2


def test_symbols_in_only_one_store_are_skipped(warehouse):
    _days(rec.REST, "ETHUSDT", [1.0])
    _days(rec.ARCHIVE, "DEADUSDT", [1.0])
    assert rec.reconcile()["symbols"] == 0
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_archive_reconcile.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'research.archive_reconcile'`.

- [ ] **Step 3: Create `research/archive_reconcile.py`:**

```python
"""Reconcile the archive's perp daily closes with the REST warehouse (spec 2026-10-02 §1.1).

    python -m research.archive_reconcile     # exit 1 on any mismatch or missing day

Where both hold a daily close for a symbol and day, the closes must agree within REL_TOL. Every
REST day inside the archive's span for that symbol must also be in the archive: the listing rule
reads a missing day as the end of a listing, so an archive hole would split a live coin. REST days
outside the span are expected: the UM archive starts in 2020-01, REST's BTC in 2019-09, and REST
runs into the current month.
"""

from __future__ import annotations

import sys

import pandas as pd

from research import store
from research.siglib.data import list_symbols

REL_TOL = 1e-9
REST = "klines_1d"
ARCHIVE = "archive_um_klines_1d"


def compare(rest: pd.DataFrame, archive: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """(rows whose closes disagree beyond REL_TOL, REST open_times the archive lacks)."""
    both = rest[["open_time", "close"]].merge(
        archive[["open_time", "close"]], on="open_time", suffixes=("_rest", "_archive"))
    rel = (both["close_rest"] - both["close_archive"]).abs() / both["close_archive"].abs()
    disagree = both[rel > REL_TOL].assign(rel_diff=rel[rel > REL_TOL])
    inside = rest["open_time"].between(archive["open_time"].min(), archive["open_time"].max())
    missing = sorted(set(rest.loc[inside, "open_time"]) - set(archive["open_time"]))
    return disagree, missing


def reconcile() -> dict:
    report: dict = {"symbols": 0, "days": 0, "mismatches": [], "missing": []}
    for symbol in sorted(set(list_symbols(REST)) & set(list_symbols(ARCHIVE))):
        rest, archive = store.load(REST, symbol), store.load(ARCHIVE, symbol)
        disagree, missing = compare(rest, archive)
        report["symbols"] += 1
        report["days"] += int(rest["open_time"].isin(archive["open_time"]).sum())
        report["mismatches"] += [{"symbol": symbol, **r} for r in disagree.to_dict("records")]
        report["missing"] += [(symbol, t) for t in missing]
    return report


def _day(ms: int) -> str:
    return f"{pd.to_datetime(ms, unit='ms'):%Y-%m-%d}"


def main() -> None:
    report = reconcile()
    print(f"{report['symbols']} symbols, {report['days']} shared days; "
          f"{len(report['mismatches'])} mismatches, "
          f"{len(report['missing'])} REST days missing from the archive")
    for m in report["mismatches"][:40]:
        print(f"  MISMATCH {m['symbol']:<16} {_day(m['open_time'])} "
              f"rest={m['close_rest']} archive={m['close_archive']}")
    for symbol, t in report["missing"][:40]:
        print(f"  MISSING  {symbol:<16} {_day(t)}")
    if report["mismatches"] or report["missing"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_archive_reconcile.py -q && python -m pytest -q`
Expected: 7 new tests pass, and so does the rest of the suite.

- [ ] **Step 5: Commit.**

```bash
git add research/archive_reconcile.py tests/research/test_archive_reconcile.py
git commit -m "feat: reconcile archive daily closes against the REST warehouse

The archive replaces REST history for every experiment; a disagreement or a
hole in it must stop the data step rather than leak into a backtest."
```

- [ ] **Step 6: The real-data run waits for Task 4's backfill.** When the backfill has finished
  with `0 failures`, run `python -m research.archive_reconcile`. Expect `0 mismatches, 0 REST days
  missing from the archive` and exit code 0, with about 219 symbols compared.
  - If there are mismatches, stop. That is a finding for the owner. Do not loosen `REL_TOL`.
  - If REST days are missing from the archive, list them for the owner too. They decide whether
    the listing rule or the data needs a ruling.

---

### Task 6: `siglib/stats.py`, part 1: weeks, Sharpe and drawdown

**Files:**
- Modify: `research/siglib/data.py` (add `week_start`)
- Create: `research/siglib/stats.py`
- Test: `tests/research/test_siglib_stats.py` and `tests/research/test_siglib_data.py`

**Interfaces:**
- Produces:
  - `siglib.data.week_start(t_ms)`, which takes an int or an int ndarray and returns Monday
    00:00 UTC of the week holding `t_ms`.
  - `stats.WEEKS_PER_YEAR = 52`.
  - `stats.weekly_returns(daily: pd.Series) -> pd.Series`, indexed by each week's Monday in ms.
  - `stats.sharpe(returns: pd.Series, periods_per_year: int = 52) -> float`, which is NaN when
    undefined.
  - `stats.max_drawdown(returns: pd.Series) -> float`.

- [ ] **Step 1: Write the failing tests.** First, append to `tests/research/test_siglib_data.py`:

```python
def test_week_start_is_monday_midnight_utc():
    assert data.week_start(BASE) == BASE  # 2024-01-01 was a Monday
    assert data.week_start(BASE + 6 * DAY + 23 * HOUR) == BASE  # Sunday 23:00
    assert data.week_start(BASE + 7 * DAY) == BASE + 7 * DAY
    assert data.week_start(BASE - 1) == BASE - 7 * DAY
    assert list(data.week_start(np.array([BASE + DAY, BASE + 8 * DAY]))) == [BASE, BASE + 7 * DAY]
```

  Then create `tests/research/test_siglib_stats.py`:

```python
"""siglib.stats against hand-computed values (spec §3.2–3.3, §4.4).

Reference values were computed twice, independently, on 2026-10-05: with explicit Python loops,
and with statsmodels 0.15.0 (OLS, cov_type="HAC", maxlags=4, use_correction=False) and scipy
1.18.1 (biased skewness and kurtosis, norm.ppf and norm.cdf). Neither library is a dependency.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from research.config import DAY_MS
from research.siglib import stats

MONDAY = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _daily(first_day: int, returns: list[float]) -> pd.Series:
    return pd.Series(returns, index=[MONDAY + (first_day + i) * DAY_MS for i in range(len(returns))])


def _weekly(returns: list[float]) -> pd.Series:
    return pd.Series(returns, index=[MONDAY + 7 * i * DAY_MS for i in range(len(returns))])


def test_weekly_returns_compound_complete_monday_weeks_only():
    # Saturday 2024-01-06 through Tuesday 2024-01-23: two complete weeks between partial ends.
    returns = [0.01] * 18
    returns[12] = -0.02  # Thursday 2024-01-18, inside the second week
    weekly = stats.weekly_returns(_daily(5, returns))
    assert list(weekly.index) == [MONDAY + 7 * DAY_MS, MONDAY + 14 * DAY_MS]
    assert weekly.iloc[0] == pytest.approx(1.01**7 - 1, rel=1e-12)
    assert weekly.iloc[1] == pytest.approx(1.01**6 * 0.98 - 1, rel=1e-12)


def test_sharpe_is_mean_over_sample_std_times_root_52():
    assert stats.sharpe(pd.Series([0.01, 0.02, -0.01, 0.03])) == pytest.approx(
        5.277986629117474, rel=1e-12)


def test_sharpe_per_period():
    assert stats.sharpe(pd.Series([0.01, 0.02, -0.01, 0.03]), periods_per_year=1) == pytest.approx(
        5.277986629117474 / math.sqrt(52), rel=1e-12)


def test_returns_that_do_not_vary_have_no_sharpe():  # an arm that never trades in a window
    assert math.isnan(stats.sharpe(pd.Series([0.0, 0.0, 0.0])))
    assert math.isnan(stats.sharpe(pd.Series([0.01])))
    assert not stats.sharpe(pd.Series([0.0, 0.0])) > -1.0  # NaN fails every gate comparison


def test_max_drawdown_counts_a_loss_on_the_first_day():
    # equity 1.0 → 0.9 → 0.945 → 0.756 → 0.9828: the trough sits 24.4% under the starting 1.0
    assert stats.max_drawdown(pd.Series([-0.10, 0.05, -0.20, 0.30])) == pytest.approx(0.244, rel=1e-12)


def test_max_drawdown_edges():
    assert stats.max_drawdown(pd.Series([], dtype=float)) == 0.0
    assert stats.max_drawdown(pd.Series([0.01, 0.02])) == 0.0
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_siglib_stats.py tests/research/test_siglib_data.py -q`
Expected: `ModuleNotFoundError: No module named 'research.siglib.stats'`, and
`AttributeError: … 'week_start'` in the data test.

- [ ] **Step 3: Implement.** First, append to `research/siglib/data.py`:

```python
def week_start(t_ms):
    """Monday 00:00 UTC of the week holding t_ms (epoch ms); works elementwise on int arrays.

    Day 0 of the epoch, 1970-01-01, was a Thursday: three days after a Monday."""
    days = t_ms // config.DAY_MS
    return (days - (days + 3) % 7) * config.DAY_MS
```

  Then create `research/siglib/stats.py`:

```python
"""Performance statistics for the model lab's verdicts (spec 2026-10-02 §3.2–3.3).

Conventions, pinned by tests/research/test_siglib_stats.py against hand-computed values:
- returns are simple returns indexed by bar open_time in epoch ms, like BacktestResult.returns;
- a week runs from Monday 00:00 to Monday 00:00 UTC, and only complete weeks count;
- standard deviations are sample (ddof=1); skewness and kurtosis are population moments, with
  kurtosis not in excess form (a normal distribution has 3), as in Bailey & López de Prado (2014).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.siglib.data import week_start

WEEKS_PER_YEAR = 52


def weekly_returns(daily: pd.Series) -> pd.Series:
    """Compound daily returns into Monday-to-Monday weeks, indexed by each week's Monday (ms).

    A week missing any of its seven days is dropped, so a window's leftover days at either end
    never form a partial week."""
    weeks = week_start(daily.index.to_numpy(dtype="int64"))
    grouped = (1.0 + daily).groupby(weeks)
    complete = grouped.size() == 7
    return (grouped.prod() - 1.0)[complete]


def sharpe(returns: pd.Series, periods_per_year: int = WEEKS_PER_YEAR) -> float:
    """Mean over sample standard deviation, × √periods_per_year. NaN when the standard deviation
    is zero or undefined: a NaN Sharpe fails every comparison a gate makes."""
    sd = float(returns.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(returns.mean()) / sd * math.sqrt(periods_per_year)


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall of the compounded equity curve, as a positive fraction.

    The starting equity of 1.0 counts as a peak, so a loss on the first bar is a drawdown."""
    equity = np.concatenate([[1.0], np.cumprod(1.0 + returns.to_numpy(dtype=float))])
    return float((1.0 - equity / np.maximum.accumulate(equity)).max())
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_siglib_stats.py tests/research/test_siglib_data.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/siglib/data.py research/siglib/stats.py tests/research/test_siglib_stats.py tests/research/test_siglib_data.py
git commit -m "feat: weekly returns, Sharpe and drawdown for the Experiment 1 gates

Every gate compares weekly Sharpe and daily drawdown; pinning complete weeks
and the starting-equity peak now keeps the verdict from depending on edges."
```

---

### Task 7: `siglib/stats.py`, part 2: Newey-West alpha

**Files:**
- Modify: `research/siglib/stats.py`
- Test: `tests/research/test_siglib_stats.py` (append)

**Interfaces:**
- Consumes: nothing beyond numpy and pandas.
- Produces:
  - `stats.ALPHA_NOISE = 1e-12`.
  - `stats.AlphaFit`, a frozen dataclass with `alpha, beta, se_alpha, t_alpha: float` and
    `n: int`.
  - `stats.nw_alpha(arm: pd.Series, bench: pd.Series, lags: int = 4) -> AlphaFit`.

- [ ] **Step 1: Write the failing tests** by appending to `tests/research/test_siglib_stats.py`:

```python
BENCH = [0.021, -0.034, 0.015, 0.042, -0.011, 0.008, -0.027, 0.033, 0.012, -0.019, 0.026, -0.004]
ARM = [0.015, -0.012, 0.010, 0.030, -0.002, 0.009, -0.010, 0.020, 0.011, -0.006, 0.018, 0.001]


def test_nw_alpha_matches_the_reference():
    fit = stats.nw_alpha(_weekly(ARM), _weekly(BENCH))
    assert fit.alpha == pytest.approx(0.004256714955921019, rel=1e-9)
    assert fit.beta == pytest.approx(0.5309583956281898, rel=1e-9)
    assert fit.se_alpha == pytest.approx(0.00022645201261195535, rel=1e-9)
    assert fit.t_alpha == pytest.approx(18.797426027805987, rel=1e-9)
    assert fit.n == 12


def test_zero_lags_gives_the_white_standard_error():
    fit = stats.nw_alpha(_weekly(ARM), _weekly(BENCH), lags=0)
    assert fit.se_alpha == pytest.approx(0.0003640714004282908, rel=1e-9)


def test_an_exact_multiple_of_btc_has_zero_alpha():  # constant exposure and no trades
    fit = stats.nw_alpha(_weekly([0.5 * b for b in BENCH]), _weekly(BENCH))
    assert fit.alpha == 0.0 and fit.t_alpha == 0.0
    assert fit.beta == pytest.approx(0.5, rel=1e-12)


def test_weeks_align_on_the_index():
    assert stats.nw_alpha(_weekly(ARM), _weekly(BENCH + [0.05])).n == 12
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_siglib_stats.py -q`
Expected: `AttributeError: module 'research.siglib.stats' has no attribute 'nw_alpha'`.

- [ ] **Step 3: Implement.** In `research/siglib/stats.py`, add
  `from dataclasses import dataclass` to the imports, then append:

```python
# An exact multiple of BTC (constant exposure, no trades) leaves OLS an alpha of about 1e-19
# with a standard error just as small, so its t-statistic is noise that could pass a gate.
ALPHA_NOISE = 1e-12


@dataclass(frozen=True)
class AlphaFit:
    alpha: float
    beta: float
    se_alpha: float
    t_alpha: float
    n: int


def nw_alpha(arm: pd.Series, bench: pd.Series, lags: int = 4) -> AlphaFit:
    """OLS arm = α + β·bench + ε on index-aligned rows, with Newey-West standard errors.

    Bartlett weights 1 - lag/(lags + 1), no small-sample correction: statsmodels' HAC with
    use_correction=False. An |α| under ALPHA_NOISE is reported as α = 0, t = 0."""
    both = pd.concat([arm, bench], axis=1, join="inner").dropna()
    y = both.iloc[:, 0].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(both)), both.iloc[:, 1].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    scores = x * (y - x @ coef)[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        gamma = scores[lag:].T @ scores[:-lag]
        meat += (1.0 - lag / (lags + 1)) * (gamma + gamma.T)
    bread = np.linalg.inv(x.T @ x)
    se = math.sqrt((bread @ meat @ bread)[0, 0])
    alpha = float(coef[0])
    if abs(alpha) < ALPHA_NOISE:
        return AlphaFit(alpha=0.0, beta=float(coef[1]), se_alpha=se, t_alpha=0.0, n=len(both))
    return AlphaFit(alpha=alpha, beta=float(coef[1]), se_alpha=se, t_alpha=alpha / se, n=len(both))
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_siglib_stats.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/siglib/stats.py tests/research/test_siglib_stats.py
git commit -m "feat: Newey-West alpha against BTC for gates G3 and G4

Pinned to statsmodels' HAC to the ninth digit; a noise-level alpha from an arm
that merely scales BTC is reported as zero so it can never pass a gate."
```

---

### Task 8: `siglib/stats.py`, part 3: the deflated Sharpe ratio

**Files:**
- Modify: `research/siglib/stats.py`
- Test: `tests/research/test_siglib_stats.py` (append)

**Interfaces:**
- Consumes: `stats.sharpe` (Task 6).
- Produces:
  - `stats.EULER_GAMMA`.
  - `stats.expected_max_sharpe(n_trials: int, trial_sharpe_variance: float) -> float`.
  - `stats.deflated_sharpe(returns: pd.Series, trial_sharpes: Sequence[float], n_trials:
    int | None = None) -> float`. Sharpe ratios are per period, so in weekly units for weekly
    returns; `n_trials` defaults to `len(trial_sharpes)`.

- [ ] **Step 1: Write the failing tests** by appending to `tests/research/test_siglib_stats.py`:

```python
DSR_WEEKLY = [0.012, -0.020, 0.031, 0.004, -0.008, 0.017, 0.025, -0.013, 0.009, 0.002,
              0.019, -0.027, 0.014, 0.006, -0.003, 0.022, 0.011, -0.016, 0.028, 0.001]
TRIAL_SHARPES = [0.05, 0.12, 0.08, 0.15, 0.02, 0.10]  # sample variance 0.0022266666666666667


def test_expected_max_sharpe_of_six_unskilled_trials():
    assert stats.expected_max_sharpe(6, 0.0022266666666666667) == pytest.approx(
        0.061350483116021814, rel=1e-9)


def test_deflated_sharpe_matches_the_reference():
    # sr = 0.34858705162657744, skew = -0.35176553477902145, kurt = 2.236838711880152, T = 20
    # z = (sr - sr0) * sqrt(T - 1) / sqrt(1 - skew*sr + (kurt - 1)/4 * sr^2) = 1.1623883379537419
    assert stats.deflated_sharpe(_weekly(DSR_WEEKLY), TRIAL_SHARPES) == pytest.approx(
        0.8774611208839094, rel=1e-9)


def test_sixty_trials_deflate_further():  # spec §3.3: the N = 60 value is reported, not gated
    assert stats.deflated_sharpe(_weekly(DSR_WEEKLY), TRIAL_SHARPES, n_trials=60) == pytest.approx(
        0.8321758103627532, rel=1e-9)


def test_returns_that_do_not_vary_have_no_deflated_sharpe():
    assert math.isnan(stats.deflated_sharpe(_weekly([0.0] * 20), TRIAL_SHARPES))
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_siglib_stats.py -q`
Expected: `AttributeError: module 'research.siglib.stats' has no attribute 'expected_max_sharpe'`.

- [ ] **Step 3: Implement.** In `research/siglib/stats.py`, add
  `from collections.abc import Sequence` and `from statistics import NormalDist` to the imports,
  then append:

```python
EULER_GAMMA = 0.5772156649015329


def expected_max_sharpe(n_trials: int, trial_sharpe_variance: float) -> float:
    """The Sharpe ratio the best of n_trials skill-less trials is expected to reach, given the
    variance of their Sharpe ratios (Bailey & López de Prado 2014, the benchmark SR0)."""
    nd = NormalDist()
    return math.sqrt(trial_sharpe_variance) * (
        (1 - EULER_GAMMA) * nd.inv_cdf(1 - 1 / n_trials)
        + EULER_GAMMA * nd.inv_cdf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe(returns: pd.Series, trial_sharpes: Sequence[float],
                    n_trials: int | None = None) -> float:
    """Probability that the true Sharpe ratio of `returns` beats the best skill-less trial.

    Sharpe ratios are per period, not annualised. The trials' variance is the sample variance
    (ddof=1), the conservative choice. n_trials defaults to len(trial_sharpes); the spec's
    sensitivity value passes 60. NaN when `returns` has no Sharpe ratio."""
    sr = sharpe(returns, periods_per_year=1)
    if math.isnan(sr):
        return float("nan")
    x = returns.to_numpy(dtype=float)
    dev = x - x.mean()
    m2 = float(np.mean(dev**2))
    skew = float(np.mean(dev**3)) / m2**1.5
    kurt = float(np.mean(dev**4)) / m2**2
    sr0 = expected_max_sharpe(n_trials if n_trials is not None else len(trial_sharpes),
                              float(np.var(trial_sharpes, ddof=1)))
    z = (sr - sr0) * math.sqrt(len(x) - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
    return NormalDist().cdf(z)
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_siglib_stats.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/siglib/stats.py tests/research/test_siglib_stats.py
git commit -m "feat: deflated Sharpe ratio for gate G6

Six trials are counted on train; G6 must discount the best of them for luck,
with the trial variance taken conservatively and the N = 60 sensitivity alongside."
```

---

### Task 9: The exclusion list, for the owner's review

**Files:**
- Create: `research/signals/model_lab/__init__.py` (empty)
- Create: `research/signals/model_lab/exclusions.py`
- Test: `tests/research/test_model_lab_exclusions.py`

**Interfaces:**
- Produces: `exclusions.STABLECOINS`, `PEGGED`, `INDEXES`, `TRADFI` and `EXCLUDED`, all
  `frozenset[str]` of tickers.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_exclusions.py`:

```python
"""The exclusion list (spec §1.1) is a frozen set of tickers reviewed by the owner. These tests
pin its shape and its reviewed size: any edit to the list has to change them, in plain sight."""

from __future__ import annotations

from research.signals.model_lab import exclusions as ex


def test_the_categories_are_disjoint_and_make_up_the_whole():
    groups = [ex.STABLECOINS, ex.PEGGED, ex.INDEXES, ex.TRADFI]
    assert sum(len(g) for g in groups) == len(ex.EXCLUDED)
    assert frozenset().union(*groups) == ex.EXCLUDED


def test_every_entry_is_a_usdt_perp_ticker():
    assert all(t.endswith("USDT") and "_" not in t for t in ex.EXCLUDED)


def test_the_reviewed_sizes():  # a change here is a change the owner reviews again
    assert (len(ex.STABLECOINS), len(ex.PEGGED), len(ex.INDEXES), len(ex.TRADFI)) == (1, 2, 6, 212)
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_model_lab_exclusions.py -q`
Expected: `ModuleNotFoundError: No module named 'research.signals.model_lab'`.

- [ ] **Step 3: Create the package and the list.** First, create an empty
  `research/signals/model_lab/__init__.py`. Then create
  `research/signals/model_lab/exclusions.py`:

```python
"""Perps the ranker never holds (spec 2026-10-02 §1.1), decided by what each ticker is.

Frozen before any model run and reviewed by the owner. It was drafted on 2026-10-05 from the
archive's 900 USDT perps. TRADFI is every contract Binance's exchangeInfo labels
TRADIFI_PERPETUAL; the other sets come from the tickers' names. No price, volume or return
informed any entry. A ticker excluded here is excluded in every listing it has. TradFi contracts
listed after 2026-10-05 have no bars inside Experiment 1's windows, so the list is complete for
this experiment; the paper phase amends it.

Kept on purpose, for the owner to confirm:
- USTCUSDT, a stablecoin that lost its peg in 2022 and now trades like any token;
- FRAXUSDT, STABLEUSDT, STBLUSDT and USUALUSDT, tokens of stablecoin projects rather than
  stablecoins;
- PUMPBTCUSDT, a governance token that is not pegged to BTC.
"""

STABLECOINS = frozenset({"USDCUSDT"})

# Tokens backed by gold: they track a commodity, not crypto.
PEGGED = frozenset({"PAXGUSDT", "XAUTUSDT"})

# Composite contracts. Binance's exchangeInfo marks the first three INDEX; the rest are delisted.
INDEXES = frozenset({
    "ALLUSDT", "BTCDOMUSDT", "DEFIUSDT",
    "BLUEBIRDUSDT", "DOTECOUSDT", "FOOTBALLUSDT",
})

# Binance's TRADIFI_PERPETUAL contracts in the archive, grouped by its underlyingType.
TRADFI = frozenset({
    # CN_EQUITY (2)
    "CXMTUSDT", "UNITREEUSDT",
    # COMMODITY (8)
    "BZUSDT", "CLUSDT", "COPPERUSDT", "NATGASUSDT", "XAGUSDT", "XAUUSDT", "XPDUSDT", "XPTUSDT",
    # EQUITY (174), stocks and ETFs
    "AAOIUSDT", "AAPLUSDT", "ACNUSDT", "ADBEUSDT", "AGPUUSDT", "ALABUSDT", "AMATUSDT",
    "AMCUSDT", "AMDUSDT", "AMZNUSDT", "ANETUSDT", "APLDUSDT", "APPUSDT", "ARMUSDT", "ASMLUSDT",
    "ASTSUSDT", "AVGOUSDT", "AXTIUSDT", "BABAUSDT", "BBXUSDT", "BEUSDT", "BITOUSDT", "BMNRUSDT",
    "BNCUSDT", "BOTUSDT", "BRKBUSDT", "BSPUSDT", "BWETUSDT", "BXUSDT", "CATUSDT", "CBRSUSDT",
    "CIENUSDT", "COHRUSDT", "COINUSDT", "COSTUSDT", "CRCLUSDT", "CRDOUSDT", "CRMLUSDT",
    "CRMUSDT", "CRWDUSDT", "CRWVUSDT", "CSCOUSDT", "CVNAUSDT", "CYPHUSDT", "DDOGUSDT",
    "DELLUSDT", "DISUSDT", "DJTUSDT", "DKNGUSDT", "DRAMUSDT", "EBAYUSDT", "EWJUSDT", "EWTUSDT",
    "EWYUSDT", "EWZUSDT", "FLEXUSDT", "FLNCUSDT", "FWDIUSDT", "GDXUSDT", "GEVUSDT", "GLWUSDT",
    "GMEUSDT", "GOOGLUSDT", "GPROUSDT", "GSUSDT", "GTLBUSDT", "HDUSDT", "HIMSUSDT", "HOODUSDT",
    "HPEUSDT", "HUTUSDT", "IBMUSDT", "INTCUSDT", "INTWUSDT", "IONQUSDT", "IRENUSDT", "IWMUSDT",
    "JPMUSDT", "KLACUSDT", "KORUUSDT", "KOUSDT", "KSTRUSDT", "LITEUSDT", "LLYUSDT", "LRCXUSDT",
    "LYTEUSDT", "MARAUSDT", "MDBUSDT", "METAUSDT", "MPUSDT", "MRKUSDT", "MRNAUSDT", "MRVLUSDT",
    "MSFTUSDT", "MSTRUSDT", "MUUSDT", "MUUUSDT", "MVLLUSDT", "NBISUSDT", "NETUSDT", "NFLXUSDT",
    "NKEUSDT", "NOKUSDT", "NOWUSDT", "NVDAUSDT", "NVDLUSDT", "NVOUSDT", "OKLOUSDT", "ONDSUSDT",
    "ORCLUSDT", "PANWUSDT", "PATHUSDT", "PAYPUSDT", "PDDUSDT", "PENGUSDT", "PLTRUSDT",
    "PYPLUSDT", "QCOMUSDT", "QNTXUSDT", "QQQUSDT", "RAMUSDT", "RDDTUSDT", "RIVNUSDT",
    "RKLBUSDT", "RUMUSDT", "SECZUSDT", "SHAZUSDT", "SHOPUSDT", "SKDDUSDT", "SKHYUSDT",
    "SKUUUSDT", "SMCIUSDT", "SMHUSDT", "SNDKUSDT", "SNOWUSDT", "SNXXUSDT", "SOFIUSDT",
    "SONYUSDT", "SOXLUSDT", "SOXSUSDT", "SPCXUSDT", "SPYUSDT", "SQQQUSDT", "STRCUSDT",
    "STXXUSDT", "TBTUSDT", "TEAMUSDT", "TEMUSDT", "TERUSDT", "TMFUSDT", "TQQQUSDT", "TSLAUSDT",
    "TSLLUSDT", "TSMUSDT", "TTWOUSDT", "TWSTUSDT", "TXNUSDT", "TZAUSDT", "UBERUSDT", "UNHUSDT",
    "URNMUSDT", "USARUSDT", "UVXYUSDT", "VRTUSDT", "VSTUSDT", "VUSDT", "WDCUSDT", "WENUSDT",
    "WMTUSDT", "XBIUSDT", "XLEUSDT", "XOMUSDT", "ZMUSDT", "ZSUSDT",
    # FX (1)
    "USDBRLUSDT",
    # HK_EQUITY (15)
    "BYDUSDT", "CSOPSAMSUNG2LUSDT", "CSOPSKHYNIX2LUSDT", "GIGADEVUSDT", "HK0625USDT",
    "HK0700USDT", "HK0992USDT", "HK1810USDT", "KUAISHOUUSDT", "MEITUANUSDT", "MINIMAXUSDT",
    "POPMARTUSDT", "TENCENTUSDT", "ZHIPUUSDT", "ZHONGJIUSDT",
    # KR_EQUITY (8)
    "HANMIUSDT", "HYUNDAIUSDT", "KODEX200USDT", "LGELECTRONICSUSDT", "NAVERUSDT",
    "SAMSUNGEMUSDT", "SAMSUNGUSDT", "SKHYNIXUSDT",
    # PREMARKET (4), pre-IPO company valuations
    "ANTHROPICUSDT", "MOONSHOTUSDT", "OPENAIUSDT", "OURAUSDT",
})

EXCLUDED = STABLECOINS | PEGGED | INDEXES | TRADFI
```

  Several short TradFi tickers look like crypto tokens: `CATUSDT`, `WENUSDT`, `BOTUSDT`, `NETUSDT`,
  `RAMUSDT`, `VUSDT`. Binance labels every one of them `EQUITY`, and none appears in the archive
  before 2026. `CAT` is Caterpillar, `WEN` Wendy's, `NET` Cloudflare and `V` Visa, not the coins.
  The list follows Binance's label, not a guess at the name.

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_model_lab_exclusions.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/__init__.py research/signals/model_lab/exclusions.py tests/research/test_model_lab_exclusions.py
git commit -m "feat: freeze the ranker's exclusion list for the owner's review

212 TradFi contracts share the UM archive with crypto perps; excluding them,
stablecoins, gold tokens and indexes by what they are, before any model run,
keeps the experiment about crypto."
```

  The owner's review of this list is Task 12, Step 5. It is also part of reviewing this plan.

---

### Task 10: Listings

**Files:**
- Modify: `research/siglib/data.py:79-84` (`load_klines` gains `source`)
- Create: `research/signals/model_lab/listings.py`
- Test: `tests/research/test_model_lab_listings.py` and `tests/research/test_siglib_data.py`

**Interfaces:**
- Consumes: `archive_source.settled_base` (Task 3) and `config.DAY_MS`.
- Produces:
  - `siglib.data.load_klines(symbols="all", interval="1h", start=None, end=None,
    source="klines")`, where `source` is `"klines"` (REST), `"archive_um_klines"` or
    `"archive_spot_klines"`.
  - `listings.contract_numbers(daily) -> np.ndarray`.
  - `listings.split_listings(daily) -> pd.DataFrame`, with the input's columns plus `ticker`.
    `symbol` becomes the listing's name.
  - `listings.settlement_mismatches(daily) -> pd.DataFrame` with columns `symbol, open_time,
    close, halt_close`.

- [ ] **Step 1: Write the failing tests.** First, append to `tests/research/test_siglib_data.py`:

```python
def test_load_klines_reads_the_archive_datasets(tmp_warehouse):
    times = [BASE, BASE + DAY]
    _write(tmp_warehouse, "archive_um_klines_1d", "BNXUSDTSETTLED", _klines(times, [1.0, 2.0]))
    df = data.load_klines("all", "1d", source="archive_um_klines")
    assert df["symbol"].tolist() == ["BNXUSDTSETTLED", "BNXUSDTSETTLED"]
```

  Then create `tests/research/test_model_lab_listings.py`:

```python
"""Listings (spec §1.2, as amended): settled folders fill only missing days, zero-trade days
are dropped, and a ticker splits wherever a contract ends or a day is missing.

Every fixture mirrors a real archive case from 2026-10-05, named in its test."""

from __future__ import annotations

import pandas as pd

from research.signals.model_lab import listings

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _bars(symbol, first_day, n, close=1.0, trades=10):
    return [{"symbol": symbol, "open_time": BASE + (first_day + i) * DAY, "close": close,
             "trades": trades, "quote_volume": 100.0} for i in range(n)]


def _split(*groups):
    return listings.split_listings(pd.DataFrame([row for g in groups for row in g]))


def _days(out, name):
    return sorted((out.loc[out["symbol"] == name, "open_time"] - BASE) // DAY)


def test_a_relisting_after_a_zero_trade_halt_is_a_new_listing():  # PUMP, 2025
    out = _split(_bars("PUMPUSDT", 0, 10, close=0.0471),
                 _bars("PUMPUSDT", 10, 26, close=0.0471, trades=0),
                 _bars("PUMPUSDT", 36, 5, close=0.0052))
    assert sorted(out["symbol"].unique()) == ["PUMPUSDT", "PUMPUSDT@2024-01-01"]
    assert _days(out, "PUMPUSDT@2024-01-01") == list(range(10))
    assert _days(out, "PUMPUSDT") == list(range(36, 41))
    assert (out["ticker"] == "PUMPUSDT").all()


def test_a_settled_folder_fills_only_the_days_its_live_folder_lacks():  # BNX, 2022-23
    live_old = [r for r in _bars("BNXUSDT", 0, 10, close=120.0) if r["open_time"] != BASE + 4 * DAY]
    folder = (_bars("BNXUSDTSETTLED", 0, 10, close=999.0)  # duplicates the live days...
              + _bars("BNXUSDTSETTLED", 10, 3, close=119.9, trades=0))  # ...then halt and settle
    out = _split(live_old, folder, _bars("BNXUSDT", 12, 9, close=1.6))
    old = out[out["symbol"] == "BNXUSDT@2024-01-01"]
    assert _days(out, "BNXUSDT@2024-01-01") == list(range(10))
    assert old.loc[old["open_time"] == BASE + 4 * DAY, "close"].item() == 999.0  # the gap, filled
    assert set(old.loc[old["open_time"] != BASE + 4 * DAY, "close"]) == {120.0}  # live wins
    assert _days(out, "BNXUSDT") == list(range(12, 21))


def test_a_settled_folders_last_bar_separates_contracts_without_a_gap():  # MINA, 2023-02
    out = _split(_bars("MINAUSDT", 0, 9, close=0.80),
                 _bars("MINAUSDTSETTLED", 9, 1, close=0.78),  # old contract's last traded day
                 _bars("MINAUSDTSETTLED", 10, 1, close=0.78, trades=0),  # its settlement bar
                 _bars("MINAUSDT", 10, 11, close=0.86))  # the new contract, the very next day
    assert _days(out, "MINAUSDT@2024-01-01") == list(range(10))
    assert _days(out, "MINAUSDT") == list(range(10, 21))


def test_two_settled_folders_make_three_contracts():  # AERGO, 2025 and 2026
    out = _split(_bars("AERGOUSDT", 0, 5),
                 _bars("AERGOUSDTSETTLED", 8, 1, trades=0),
                 _bars("AERGOUSDT", 8, 8),
                 _bars("AERGOUSDTSETTLEDSETTLED", 20, 1))
    assert _days(out, "AERGOUSDT@2024-01-01") == list(range(5))
    assert _days(out, "AERGOUSDT@2024-01-09") == list(range(8, 16))
    assert _days(out, "AERGOUSDT") == [20]  # the old contract's last day, after a gap


def test_a_settled_contract_ends_at_its_last_traded_bar():  # BLZ: flat at 0.06836 since 2024-12
    out = _split(_bars("BLZUSDT", 0, 10, close=0.07), _bars("BLZUSDT", 10, 90, close=0.06836, trades=0))
    assert out["symbol"].unique().tolist() == ["BLZUSDT"]
    assert _days(out, "BLZUSDT") == list(range(10))


def test_a_continuous_ticker_is_one_listing_under_its_own_name():
    out = _split(_bars("BTCUSDT", 0, 30))
    assert out["symbol"].unique().tolist() == ["BTCUSDT"] and len(out) == 30


def test_a_missing_day_without_a_settled_folder_still_splits():  # conservative for data holes
    out = _split(_bars("XUSDT", 0, 5), _bars("XUSDT", 6, 5))
    assert sorted(out["symbol"].unique()) == ["XUSDT", "XUSDT@2024-01-01"]


def test_a_ticker_that_only_ever_halted_has_no_listing():
    assert _split(_bars("DEADUSDT", 0, 5, trades=0)).empty


def test_the_last_traded_close_is_the_halt_price():  # spec §1.2 delisting
    daily = pd.DataFrame(_bars("PUMPUSDT", 0, 3, close=0.0471) + _bars("PUMPUSDT", 3, 2, close=0.0471, trades=0))
    assert listings.settlement_mismatches(daily).empty
    planted = pd.DataFrame(_bars("XUSDT", 0, 3, close=2.0) + _bars("XUSDT", 3, 2, close=1.5, trades=0))
    [row] = listings.settlement_mismatches(planted).itertuples()
    assert row.close == 2.0 and row.halt_close == 1.5
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_model_lab_listings.py tests/research/test_siglib_data.py -q`
Expected: `ModuleNotFoundError: No module named 'research.signals.model_lab.listings'`, and a
`TypeError` about the unexpected keyword `source` in the data test.

- [ ] **Step 3: Implement.** First, in `research/siglib/data.py`, replace `load_klines` with:

```python
def load_klines(symbols="all", interval: str = "1h", start=None, end=None,
                source: str = "klines") -> pd.DataFrame:
    """Long klines frame: [symbol, open_time, open, high, low, close, volume, quote_volume, …].

    source: "klines" (the REST warehouse), "archive_um_klines" or "archive_spot_klines"."""
    dataset = f"{source}_{interval}"
    if dataset not in config.DATASETS:
        raise ValueError(f"unknown dataset {dataset!r}")
    return _load_dataset(dataset, symbols, "open_time", KLINE_COLS, start, end)
```

  Then create `research/signals/model_lab/listings.py`:

```python
"""Listings: one contract's tradable life under a ticker (spec 2026-10-02 §1.2, as amended).

The archive keeps one folder per ticker, and a ticker can outlive its contract. On 2026-10-05:
- a settled contract got a flat, zero-trade bar at its settlement price every day until its
  ticker was relisted, and otherwise indefinitely: all 133 settled perps still did (BLZ had sat
  at 0.06836 since 2024-12-23), so without dropping those bars they would never delist;
- a relisted ticker continued the same file at an unrelated price: PUMPUSDT went from the old
  token's 0.0471 to the new token's 0.0052;
- 17 settled folders held old contracts' last days, some of which the live folder lacks: BNX's
  last 11 trading days before its 2023-02 redenomination exist only in BNXUSDTSETTLED.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.archive_source import settled_base
from research.config import DAY_MS


def contract_numbers(daily: pd.DataFrame) -> np.ndarray:
    """Each row's contract within its ticker, counting from 0.

    A settled folder's last bar ends a contract: the folder's rows belong to it, and the live
    folder's rows from that day on belong to the next one."""
    contract = np.zeros(len(daily), dtype=int)
    symbol = daily["symbol"].to_numpy()
    open_time = daily["open_time"].to_numpy()
    folders = daily[daily["symbol"] != daily["ticker"]]
    ends = folders.groupby("symbol")["open_time"].max()
    for ticker, folder_ends in ends.groupby(ends.index.map(settled_base)):
        bounds = np.sort(folder_ends.to_numpy())
        live = symbol == ticker
        contract[live] = np.searchsorted(bounds, open_time[live], side="right")
        for folder, end in folder_ends.items():
            contract[symbol == folder] = np.searchsorted(bounds, end, side="left")
    return contract


def split_listings(daily: pd.DataFrame) -> pd.DataFrame:
    """Archive daily klines (live and settled folders, long format) → listings.

    Keeps traded bars only, one row per listing and day. `symbol` becomes the listing's name and
    the raw ticker moves to `ticker`. The latest listing of a ticker keeps the ticker's name;
    earlier ones are TICKER@YYYY-MM-DD, after their first day."""
    df = daily.assign(ticker=daily["symbol"].map(lambda s: settled_base(s) or s))
    df = df.assign(contract=contract_numbers(df), from_folder=df["symbol"] != df["ticker"])
    df = df[df["trades"] > 0]
    df = (df.sort_values(["ticker", "contract", "open_time", "from_folder"])
            .drop_duplicates(["ticker", "contract", "open_time"], keep="first"))  # live wins
    step = df.groupby(["ticker", "contract"])["open_time"].diff()
    listing = (step != DAY_MS).cumsum()  # NaN marks each contract's first bar
    first = df.groupby(listing)["open_time"].transform("min")
    newest = first == first.groupby(df["ticker"]).transform("max")
    dated = df["ticker"] + "@" + pd.to_datetime(first, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    return (df.assign(symbol=df["ticker"].where(newest, dated))
              .drop(columns=["contract", "from_folder"])
              .reset_index(drop=True))


def settlement_mismatches(daily: pd.DataFrame, rel_tol: float = 1e-9) -> pd.DataFrame:
    """Folders whose last traded close before a halt differs from the halt price.

    The spec's delisting rule assumes the two are equal: the last traded close is the settlement
    price. An empty result confirms it for every halt in the data."""
    df = daily.sort_values(["symbol", "open_time"])
    following = df.groupby("symbol")[["trades", "close"]].shift(-1)
    halts = (df["trades"] > 0) & (following["trades"] == 0)
    rel = (df["close"] - following["close"]).abs() / following["close"].abs()
    hits = df.loc[halts & (rel > rel_tol), ["symbol", "open_time", "close"]]
    return hits.assign(halt_close=following.loc[hits.index, "close"]).reset_index(drop=True)
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_model_lab_listings.py tests/research/test_siglib_data.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/siglib/data.py research/signals/model_lab/listings.py tests/research/test_model_lab_listings.py tests/research/test_siglib_data.py
git commit -m "feat: split the archive into listings at settlements and gaps

A relisted ticker continues the same archive file at an unrelated price;
without listings, PUMP alone would book a -89% day that never happened."
```

---

### Task 11: The point-in-time universe

**Files:**
- Create: `research/signals/model_lab/universe.py`
- Test: `tests/research/test_model_lab_universe.py`

**Interfaces:**
- Consumes: `siglib.data.week_start`, `to_ms`, `load_klines(source=…)` and `ELIGIBILITY_DAYS`;
  `exclusions.EXCLUDED` (Task 9); and `listings.split_listings` and `settlement_mismatches`
  (Task 10).
- Produces:
  - `universe.TOP_N = 50`, `MIN_BREADTH = 20` and `VOLUME_WINDOW_DAYS = 30`.
  - `universe.mondays(start, end) -> list[int]`.
  - `universe.build_universe(listings: pd.DataFrame, dates: list[int], excluded:
    frozenset[str] = EXCLUDED) -> pd.DataFrame`, with columns `decision_time, rank, symbol,
    ticker, quote_volume_30d`.
  - The report CLI `python -m research.signals.model_lab.universe`.

- [ ] **Step 1: Write the failing tests** in `tests/research/test_model_lab_universe.py`:

```python
"""The PIT universe (spec §1.2): 60 bars before d, a bar on d - 1, not excluded; ranked by the
30 days of quote volume ending d - 1; top 50; nothing when fewer than 20 are eligible."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import universe

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC, a Monday


def _listing(symbol, first_day, n_days, volume=1.0, ticker=None):
    return pd.DataFrame({"symbol": symbol, "ticker": ticker or symbol, "quote_volume": volume,
                         "open_time": [BASE + (first_day + i) * DAY for i in range(n_days)]})


def _at(day, *frames, excluded=frozenset()):
    return universe.build_universe(pd.concat(frames, ignore_index=True), [BASE + day * DAY],
                                   excluded=excluded)


@pytest.fixture
def one_is_enough(monkeypatch):
    monkeypatch.setattr(universe, "MIN_BREADTH", 1)


def test_mondays_are_utc_midnights_inside_the_range():
    assert universe.mondays("2024-01-03", "2024-01-30") == [BASE + d * DAY for d in (7, 14, 21, 28)]
    assert universe.mondays(BASE, BASE + 7 * DAY) == [BASE]


def test_a_listing_enters_with_its_60th_bar(one_is_enough):
    x = _listing("XUSDT", 0, 200)
    assert _at(59, x).empty  # 59 bars before d
    assert _at(60, x)["symbol"].tolist() == ["XUSDT"]


def test_a_listing_leaves_when_its_data_ends(one_is_enough):
    x = _listing("XUSDT", 0, 100)  # last bar on day 99
    assert _at(100, x)["symbol"].tolist() == ["XUSDT"]
    assert _at(101, x).empty  # no bar on d - 1


def test_the_top_n_by_30_day_volume_with_ties_broken_by_name(one_is_enough, monkeypatch):
    monkeypatch.setattr(universe, "TOP_N", 2)
    out = _at(100, _listing("CUSDT", 0, 100, 5.0), _listing("BUSDT", 0, 100, 9.0),
              _listing("AUSDT", 0, 100, 5.0), _listing("DUSDT", 0, 100, 1.0))
    assert out["symbol"].tolist() == ["BUSDT", "AUSDT"] and out["rank"].tolist() == [1, 2]
    assert out["quote_volume_30d"].tolist() == [270.0, 150.0]


def test_volume_outside_the_30_days_does_not_count(one_is_enough, monkeypatch):
    monkeypatch.setattr(universe, "TOP_N", 1)
    early_whale = pd.concat([_listing("WUSDT", 0, 69, 1e9), _listing("WUSDT", 69, 31, 1.0)])
    out = _at(100, early_whale, _listing("SUSDT", 0, 100, 2.0))
    assert out["symbol"].tolist() == ["SUSDT"]


def test_fewer_than_20_eligible_means_no_universe():
    nineteen = [_listing(f"S{i:02d}USDT", 0, 100) for i in range(19)]
    assert _at(100, *nineteen).empty
    assert len(_at(100, *nineteen, _listing("S19USDT", 0, 100))) == 20


def test_excluded_tickers_never_enter(one_is_enough):
    out = _at(100, _listing("USDCUSDT", 0, 100, 1e9), _listing("XUSDT", 0, 100),
              excluded=frozenset({"USDCUSDT"}))
    assert out["symbol"].tolist() == ["XUSDT"]


def test_an_excluded_ticker_stays_out_in_every_listing(one_is_enough):
    old = _listing("PAXGUSDT@2024-01-01", 0, 100, ticker="PAXGUSDT")
    assert _at(100, old, excluded=frozenset({"PAXGUSDT"})).empty


def test_future_bars_never_change_past_membership():  # spec §4.4 look-ahead
    rng = np.random.default_rng(20261002)
    frames = [_listing(f"S{i:02d}USDT", int(rng.integers(0, 60)), 300, float(rng.uniform(1, 100)))
              for i in range(40)]
    dates = [BASE + d * DAY for d in range(70, 300, 7)]
    before = universe.build_universe(pd.concat(frames, ignore_index=True), dates, excluded=frozenset())
    cutoff = BASE + 180 * DAY
    perturbed = []
    for f in frames:
        f = f.copy()
        future = f["open_time"] >= cutoff
        f.loc[future, "quote_volume"] = rng.uniform(1, 1e6, int(future.sum()))
        perturbed.append(f[~future | (rng.random(len(f)) > 0.3)])  # some future bars vanish too
    perturbed.append(_listing("NEWUSDT", 175, 100, 1e9))  # a newcomer, eligible only after cutoff
    after = universe.build_universe(pd.concat(perturbed, ignore_index=True), dates, excluded=frozenset())
    pd.testing.assert_frame_equal(before[before["decision_time"] <= cutoff].reset_index(drop=True),
                                  after[after["decision_time"] <= cutoff].reset_index(drop=True))
```

  Two values in these tests come from arithmetic. In the top-N test, the 30-day sums are 9 × 30
  = 270 and 5 × 30 = 150. In the volume-window test, WUSDT's last 31 bars have volume 1, so its
  sum over days 70–99 is 30, against SUSDT's 60; its huge early days sit outside the window.

- [ ] **Step 2: Run them to see them fail.**

Run: `python -m pytest tests/research/test_model_lab_universe.py -q`
Expected: `ModuleNotFoundError: No module named 'research.signals.model_lab.universe'`.

- [ ] **Step 3: Create `research/signals/model_lab/universe.py`:**

```python
"""Point-in-time top-50 universe for the ranker (spec 2026-10-02 §1.2, as amended).

Decision dates are Mondays 00:00 UTC, and a decision on date d sees only bars that closed by d
(open_time < d). A listing (see listings.py) is eligible on d when all of these hold:
- it has at least ELIGIBILITY_DAYS (60) daily bars before d;
- it has a bar on d - 1 day;
- its ticker is not in exclusions.EXCLUDED.

Eligible listings rank by quote volume summed over [d - 30 days, d - 1 day], with ties broken by
name, and the top TOP_N form the week's universe. A week with fewer than MIN_BREADTH eligible
listings has no universe, so the book holds nothing that week.

    python -m research.signals.model_lab.universe     # summary over the archive, for review
"""

from __future__ import annotations

import pandas as pd

from research.config import DAY_MS
from research.siglib.data import ELIGIBILITY_DAYS, load_klines, to_ms, week_start
from research.signals.model_lab.exclusions import EXCLUDED
from research.signals.model_lab.listings import settlement_mismatches, split_listings

TOP_N = 50
MIN_BREADTH = 20
VOLUME_WINDOW_DAYS = 30
WEEK_MS = 7 * DAY_MS


def mondays(start, end) -> list[int]:
    """Decision dates: every Monday 00:00 UTC in [start, end), as epoch ms."""
    start_ms, end_ms = to_ms(start), to_ms(end)
    first = int(week_start(start_ms))
    if first < start_ms:
        first += WEEK_MS
    return list(range(first, end_ms, WEEK_MS))


def build_universe(listings: pd.DataFrame, dates: list[int],
                   excluded: frozenset[str] = EXCLUDED) -> pd.DataFrame:
    """Long frame [decision_time, rank, symbol, ticker, quote_volume_30d], one row per member."""
    tickers = listings.groupby("symbol")["ticker"].first()
    volume = listings.pivot(index="open_time", columns="symbol", values="quote_volume").sort_index()
    volume = volume.reindex(range(int(volume.index[0]), int(volume.index[-1]) + DAY_MS, DAY_MS))
    bars = volume.notna().cumsum()  # bars with open_time <= each row
    window = volume.rolling(VOLUME_WINDOW_DAYS, min_periods=1).sum()
    allowed = ~tickers.reindex(volume.columns).isin(excluded)
    members = []
    for d in dates:
        prev = d - DAY_MS
        if prev not in volume.index:
            continue
        eligible = (bars.loc[prev] >= ELIGIBILITY_DAYS) & volume.loc[prev].notna() & allowed
        if eligible.sum() < MIN_BREADTH:
            continue
        ranked = (window.loc[prev][eligible].rename("quote_volume_30d").rename_axis("symbol")
                  .reset_index()
                  .sort_values(["quote_volume_30d", "symbol"], ascending=[False, True])
                  .head(TOP_N))
        members.append(ranked.assign(decision_time=d, rank=range(1, len(ranked) + 1)))
    columns = ["decision_time", "rank", "symbol", "ticker", "quote_volume_30d"]
    if not members:
        return pd.DataFrame(columns=columns)
    out = pd.concat(members, ignore_index=True)
    return out.assign(ticker=out["symbol"].map(tickers))[columns]


def main() -> None:
    daily = load_klines("all", "1d", source="archive_um_klines")
    listed = split_listings(daily)
    per_ticker = listed.groupby("ticker")["symbol"].nunique()
    print(f"{daily['symbol'].nunique()} archive folders -> {listed['symbol'].nunique()} listings "
          f"over {len(per_ticker)} tickers; {int((per_ticker > 1).sum())} tickers have more than one")
    mismatched = settlement_mismatches(daily)
    print(f"settlement check: {len(mismatched)} halts where the last traded close is not the halt price")
    for row in mismatched.head(20).itertuples():
        print(f"  {row.symbol:<24} last close {row.close} vs halt price {row.halt_close}")

    end = int(listed["open_time"].max()) + DAY_MS
    members = build_universe(listed, mondays(int(listed["open_time"].min()), end))
    last_bar = listed.groupby("symbol")["open_time"].max()
    members = members.assign(
        year=pd.to_datetime(members["decision_time"], unit="ms", utc=True).dt.year,
        ended_early=members["symbol"].map(last_bar) < end - WEEK_MS,
    )
    per_listing = members.drop_duplicates(["year", "symbol"])
    summary = pd.DataFrame({
        "weeks": members.groupby("year")["decision_time"].nunique(),
        "listings": per_listing.groupby("year").size(),
        "of_which_ended_before_the_data": per_listing.groupby("year")["ended_early"].sum(),
    })
    print(f"\n{members['decision_time'].nunique()} weeks with a universe; per year, the listings "
          f"that were members and how many of them later delisted, settled or were relisted:")
    print(summary.to_string())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and the suite.**

Run: `python -m pytest tests/research/test_model_lab_universe.py -q && python -m pytest -q`
Expected: everything passes.

- [ ] **Step 5: Commit.**

```bash
git add research/signals/model_lab/universe.py tests/research/test_model_lab_universe.py
git commit -m "feat: point-in-time top-50 universe of listings for the ranker

Ranking only what was observable each Monday, delisted contracts included, is
the survivorship fix Phase C lacked; a look-ahead test pins it."
```

---

### Task 12: Close the data step on real data

**Files:**
- Modify: `CLAUDE.md`
- Modify: `agents/roadmap.md`

**Interfaces:** none. This task runs the CLIs on real data and records the results.

- [ ] **Step 1: Confirm that the backfill finished** (Task 4, Step 7):
  `tail -3 research/warehouse/archive-backfill.log` ends with `0 failures`.
- [ ] **Step 2: Reconcile.** `python -m research.archive_reconcile` exits 0, as in Task 5, Step 6.
- [ ] **Step 3: Gap report.** Run `python -m research.check`. Expect gaps in
  `archive_um_klines_1d` for the relisted tickers, which are the halts the listings rule handles.
  Phase 3 needs BTC and ETH spot bars without holes, so list any gap in `archive_spot_klines_1d`
  or `archive_spot_klines_1h` for the owner. Copy the report's summary line into the roadmap log
  entry in Step 7.
- [ ] **Step 4: The universe report.** Run `python -m research.signals.model_lab.universe`.
  Expect:
  - about 917 archive folders, a little over 900 listings, and 17 or more tickers with more than
    one listing;
  - a settlement check showing how many halts break the spec's assumption. Any non-zero count
    goes to the owner;
  - a yearly table from 2020 (the UM archive starts in 2020-01, and the first universe needs 60
    bars and 20 eligible listings) to 2026, where `of_which_ended_before_the_data` is non-zero in
    every year up to 2025. That is the survivorship fix showing itself: 164 crypto perps were
    delisted or settled.
- [ ] **Step 5: The owner's review.** Show the owner `research/signals/model_lab/exclusions.py`
  and the outputs of Steps 2–4. This is the review the spec requires "in the data step, before any
  model run". Phase 3 does not start until the owner has said yes, and any change the owner asks
  for lands in its own commit first.
- [ ] **Step 6: Update `CLAUDE.md`.**
  - Under `### Datasets`, add a bullet: "`archive_spot_klines_1d/1h` (BTC and ETH since
    2017-08), and `archive_um_klines_1d`, `archive_um_funding` and `archive_um_premium_1d` for
    every USDT perp in Binance's public archive, live or delisted, including 17 settled folders.
    These are monthly files, so they end at the last complete month. Refresh them with
    `python -m research.archive_backfill`; the daily cron does not touch them."
  - Under `### Commands`, add the commands `python -m research.archive_backfill`,
    `python -m research.archive_reconcile` and `python -m research.signals.model_lab.universe`.
  - Under `### Known data quirks`, add five bullets: settled folders and relisted tickers (point
    to `listings.py`); the microsecond spot timestamps from 2025-01; header rows only from about
    2022; the five Chinese-character tickers; and the TradFi perps, which are excluded.
  - Update both mentions of "111 tests" to the new count printed by `python -m pytest -q`.
- [ ] **Step 7: Update `agents/roadmap.md`.** Tick `**2. Data.**` and append this log entry, with
  the real numbers:

```markdown
- 2026-10-DD — phase 2 (data) complete: archive backfilled (N rows), reconciled against REST (S symbols, D shared days, 0 mismatches), L listings over T tickers, exclusions reviewed by the owner. Next: phase 3's plan (BTC and ETH arms).
```

- [ ] **Step 8: Run the suite and commit.**

```bash
python -m pytest -q && git add CLAUDE.md agents/roadmap.md && git commit -m "docs: close Experiment 1's data step

The archive, its reconciliation, listings and the universe are in place and
reviewed; phase 3 can now make its choices on train."
```

---

## Handed on to phases 3 and 4

- **Funding and premium are not split into listings here.** Phase 4 assigns each `archive_um_funding`
  and `archive_um_premium_1d` row to the listing whose first-to-last days contain it.
  `split_listings` gives every listing's first and last `open_time`.
- **`siglib.data.KLINE_COLS` has no `taker_buy_quote_volume`.** The taker-buy features in phases
  3 and 4 add it there, with a test.
- **`archive_spot_klines_1h` may have hourly gaps from early exchange outages.** `research.check`
  reports them. Phase 3 decides how daily RV treats a day with missing hours, and writes that
  down before its first real-data run.
- **The universe has no rows for weeks with fewer than 20 eligible listings.** Phase 4's training
  set inherits that: those weeks have no rows.
