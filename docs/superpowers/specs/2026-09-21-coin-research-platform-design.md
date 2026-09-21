# Coin Research Platform — Design (Phase A)

**Date:** 2026-09-21
**Status:** Approved by user (approach B "Instrument", Phase A coins-first, Electron/TS stack, local-only)

## Context

trade-god's quantitative era is over. The pre-registered OOS run
(`research/signals/intraday/output/2b/oos_results.csv`) measured the surviving strategy at
**−15.2% return, profit factor 0.986, Sharpe −0.29 across 2,791 trades** at baseline costs
(−25.2% under stress). Training-set profit factor was 1.021. Five of six intraday families were
rejected outright; the survivor was negative out-of-sample. The 66-day paper run that looked
positive was ~1.8 months drawn from a distribution with ~6% monthly volatility, evaluated at three
sequential check-ins — and its entire gain sat in ~10 of 312 trades. The AWS account closure that
destroyed the paper telemetry is the occasion for this pivot, not its cause.

What survives and has value: the `research/` parquet warehouse (6M+ rows, point-in-time), and the
discipline that produced an honest rejection — pre-registration, sealed OOS, cost stress.

This project points that discipline at a different method: the CoinPicks fundamental research
framework. The framework's own materials are in `~/Downloads/Altcoin-Trading-System-STANDARD-2026-08-07/`
(`Research/framework/00`–`06`, `doctrine/research/`), transcribed from the Skool classroom.

**The gap this fills.** The framework's "AI tool" is a prompt you paste into Claude Code with PDFs
attached. It asks the model to extract weights, validate that Quality is 0–1 ("if a value is >1 it
was typed on a 0–10 scale by mistake → divide it by 10"), check that exactly five windows exist,
range-check `|Signal| ≤ 10`, then compute weighted averages. That is arithmetic and schema
validation delegated to a language model, with a human trusting output they cannot verify. It also
demands every claim carry a Ctrl+F-able source quote — which an LLM will fabricate fluently, a risk
the framework acknowledges with its "No AI-only reports" rule but does not enforce.

This tool makes the deterministic parts deterministic and the verification mechanical.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Approach | B — "Instrument": deterministic core, LLM demoted to draftsman, verification enforced in code |
| Phase A scope | Coin research pipeline only, full depth (chain layer + ledger included) |
| Shell | Electron + electron-vite, following the proven `klickbrain/desktop` template |
| UI | React + Tailwind v4 + shadcn, Biome, pnpm |
| Storage | `better-sqlite3`, single local file |
| Chain reads | `viem` (Multicall3 built in) — Ethereum, Base, Arbitrum |
| Drafting | `Drafter` interface: Claude Code CLI (subscription) primary, API key fallback |
| Deployment | Local only. No host, no auth, no Docker, no Postgres |
| Forward returns | Existing Python `research/` warehouse, run offline, writes into the SQLite file |

**Rejected:** Tauri (klickbrain's `docs/PROJECT.md:551` planned Tauri, then shipped Electron at
v0.8.3 — decision validated by execution). Python backend (Electron removes the premise; viem beats
web3.py + multicall.py for chain reads, and packaging Python into Electron buys nothing here).
Hosted web app (cannot use the Claude Code subscription — drafting would revert to API billing).
Watcher/alerting service (out of scope; deliberately not scaffolded for).

## Normative formulas (frozen)

**The formulas below are the rules, taken verbatim from the CoinPicks lessons. They are
authoritative and frozen.** The implementation reproduces them exactly. Weights, ranges, gates, and
thresholds are not tunable, not "improvable", and not to be adjusted because an alternative looks
better calibrated. If a formula appears wrong, that is raised with the user as a finding — it is
never silently changed in code.

This rule exists because the entire point of this tool is to *test* the framework honestly. A
modified formula tests a different framework, and the ledger's answer would be about something
nobody uses.

### Phase A — per-coin

| Quantity | Formula | Source lesson |
|---|---|---|
| Product gate | `ease(0–10) + hairfire(0–10) + exclusivity(0–10)`; **≥16 pass, 0–15 drop** | `md=fb82f6eb039d4e76bad5fda7171d17ef` |
| Narrative total | `maturity(0–7) + smart_money(0–6) + hairfire(0–6) + communication(0–5) + lineage(0–4) + mutation(0–3)` = **/31** | `md=00651b71cac24c7380957b4f7f7016e5` |
| Individual team score | `H(0–5) + M(0–3) + L(0–2)` = **/10** | `md=0e32e8d435954e15988a4880aa42b9dc` |
| Team weighted score | `(founder × 5 + Σ others) ÷ (5 + count(others))` | same |
| Gross annual holder flow | `segment_revenue_usd × capture_share × accrual_pct` | `00-how-we-think.md` §1 |
| Net annual holder flow | `gross − annual_issuance_usd` | same |
| Discovery premium | `market_cap ÷ net_annual_flow` | `00-how-we-think.md` §5 |
| Liquidity tier | **No formula.** ±2% depth + largest pool TVL → human assigns Low/Med/High | `md=d46fdc6a21a14a8399d2afb4491eebe3` |

Team worked example, used as a test fixture: founder 8, others 7/5/6 →
`(8×5 + 7+5+6) ÷ (5+3) = 58 ÷ 8 = 7.25`.

Multiplication rule (`00-how-we-think.md` §1): *"These steps multiply. One zero anywhere zeroes the
product."* Implementations return the offending multiplicand, not a bare zero.

### Phase B — pillar / market direction (recorded now, built later)

```
Signal = ( (P − 50) ÷ 50 ) × Quality × Impact
```

| Input | Range | Rule |
|---|---|---|
| `P` | 0–100 | Probability this pillar is **good for crypto by that window** — *not* "this event definitely happens by then." >50 bull, <50 bear, 50 coin-flip. |
| `Quality` | 0.5–1.0 | Strength of evidence. *"Quality changes how hard you lean — never which way."* Floor of 0.5 means worst evidence halves a signal, never flips it. |
| `Impact` | 1–10 | Market-moving power of the subject, set at subject selection. |

Output range is ±10. Windows are **exactly five and locked**: 1 month, 3 months, 6 months, 1 year,
3 years. Pillar weights are "% of my thesis" and sum to 100% across pillars; the per-window market
call is the weight-weighted aggregate of pillar signals.

Worked example, used as a test fixture (CLARITY Act, 6-month window): `P=62, Quality=0.85,
Impact=9` → `(62−50) ÷ 50 = 0.24` → `0.24 × 0.85 × 9 = +1.8` → **Bull**.

Validation rules the framework's own prompt asks a language model to remember, and which this
implementation enforces as schema constraints instead:

- `Quality` must be 0–1. A value >1 was typed on a 0–10 scale — reject it; do not silently divide.
- `Impact` must be 0–10.
- Exactly the five locked windows must be present; reject off-grid windows (2-year, 5-year).
- `|Signal|` ≤ 10 — anything larger is impossible under the formula and indicates bad input.
- Use the committed value, never the AI draft, whenever both exist.

Source: `md=399abaebc4b54f769d4e26dde6b92bd5` (Build Your Pillar Reports) and
`md=814a7190f2b941f1ad2946da0b9a5a5e` (Combining Pillar Reports Into a Working Theory). All lesson
URLs are under `https://www.skool.com/coinpicksgenesis/classroom/eed2ad74?`.

## 1. What Phase A produces

One deliverable per researched coin: a **committed, immutable, point-in-time report** carrying

- a Product gate result (pass/fail),
- a Liquidity tier grounded in on-chain reserves,
- a Narrative score `/31`,
- a Team weighted score `/10`,
- a value-accrual computation with the contract address that makes it true (or the finding that
  none exists),
- every non-trivial claim backed by a citation whose quote has been **mechanically confirmed to
  appear at that URL**.

And, accumulating across reports: a ledger that will eventually answer whether any of these scores
predict anything.

## 2. The method, as implemented

Faithful to `Research/framework/`. Ranges are enforced, not clamped.

### 2.1 Product gate (`02-product-exclusivity.md`)

| Input | Range |
|---|---|
| Ease of Use | 0–10 |
| Hair-on-Fire | 0–10 |
| Exclusivity Factor | 0–10 |

`total = ease + hairfire + exclusivity`; **`total >= 16` passes, 0–15 drops the project.**
A failed gate ends the report — later sections stay locked.

Note: Hair-on-Fire is scored 0–10 here but **0–6 in the final report, inside the Narrative
section**. Two distinct fields; the report field is not derived from the gate field.

### 2.2 Liquidity (`03-liquidity-analysis.md`)

Tier is `Low | Medium | High`, assigned by the human from two measured inputs: **±2% depth across
CEXs** (CoinGecko markets) and **largest DEX pool TVL** (measured on-chain, §5). The framework is
explicit that there is no formula — "make your best guess between low, medium, or high risk."
The tool measures; the human tiers.

### 2.3 Narrative (`04-narrative-scoring.md`) — `/31`

| Sub-score | Max |
|---|---|
| Narrative Maturity | 7 |
| Smart Money Compatibility | 6 |
| Hair-on-Fire Innovation | 6 |
| Narrative Communication | 5 |
| Narrative Lineage | 4 |
| Narrative Mutation | 3 |

Every sub-score requires a 1–2 sentence rationale **and** at least one verified citation.

### 2.4 Team (`05-team-credibility.md`) — `/10`

Per person: `H (0–5) + M (0–3) + L (0–2) = /10`. Then:

```
weighted = (founder_score * 5 + sum(other_scores)) / (5 + count(others))
```

Constraints enforced by the tool: exactly one founder; 3–5 people total; each person's summary is
**one sentence about prior experience, never the current project**; each carries at least one
financial metric from a prior role.

### 2.5 Value accrual (`00-how-we-think.md`)

```
gross_annual_flow = segment_revenue_usd * capture_share * accrual_pct
net_annual_flow   = gross_annual_flow - annual_issuance_usd
```

The framework states "these steps multiply — one zero anywhere zeroes the product." The
implementation therefore **reports which multiplicand was zero** rather than returning a bare 0.

`discovery_premium = market_cap / net_annual_flow`, returning a distinct `PURE_PREMIUM` verdict
when `net_annual_flow <= 0` — the framework's "100% premium, pure narrative, tradable but never
ownable."

## 3. Architecture

```
trade-god/
├── desktop/                     # NEW — the application
│   ├── electron.vite.config.ts
│   ├── src/
│   │   ├── main/                # Node: db, chain reads, vendor fetches, drafter, verifier
│   │   ├── preload/             # typed IPC surface
│   │   └── renderer/            # React + Tailwind + shadcn
│   └── package.json
├── research/                    # EXISTING — Python warehouse, offline, unchanged in Phase A
│   └── forward_returns.py       # NEW — joins commits to warehouse returns, writes to SQLite
├── legacy/                      # app/intraday/ archived here alongside the retired bots
└── docs/superpowers/specs/
```

Single package, no monorepo: there is one consumer of the core logic.

Everything that touches the network or the disk lives in `main/`. The renderer is pure UI over a
typed IPC surface — no `fetch` from the renderer, no keys in the renderer.

## 4. Data model (SQLite)

Append-only where it matters. A committed report is never edited; a change creates a new version.

| Table | Key columns |
|---|---|
| `coins` | `id`, `symbol`, `name`, `coingecko_id`, `chain`, `contract_address`, `address_sources` (JSON, ≥2 required), `created_at` |
| `reports` | `id`, `coin_id`, `version`, `status` (`draft`\|`committed`), `created_at`, `committed_at` |
| `report_scores` | one row per report; every score column paired with `*_draft` + `*_draft_reason` |
| `report_team` | `report_id`, `position`, `name`, `role`, `is_founder`, `h`, `m`, `l`, `summary` |
| `citations` | `id`, `report_id`, `field`, `url`, `quote`, `status`, `verified_at`, `http_status`, `matched_offset`, `waiver_reason` |
| `chain_facts` | `id`, `coin_id`, `report_id?`, `kind`, `chain`, `block_number`, `fetched_at`, `payload` (JSON) |
| `forward_returns` | `report_id`, `horizon_days`, `return_pct`, `computed_at` |

`citations.status ∈ {unverified, verified, near_miss, failed, unverifiable_js, waived}`.

Every `chain_facts` row carries `block_number` and `fetched_at` — the framework's §8 rule that every
number is either verified (say where) or a guess (say so).

## 5. Chain layer (`main/chain/`, viem)

| Module | Produces |
|---|---|
| `pools.ts` | Pool census: enumerate pools, read reserves on-chain via Multicall3, compute per-pool price, **drop pools whose price deviates more than 5% from the TVL-weighted median** (the framework's poison-pair trap; threshold configurable), sum surviving depth, compute price impact for a stated position size in and out |
| `safety.ts` | Source verified?, proxy + upgrade admin, mint authority, owner / pause / blacklist selectors, deployer address, contract age |
| `issuance.ts` | Circulating vs total from chain, vesting contract balances, upcoming cliffs |
| `holders.ts` | Top-N holders, share held by top 10, exchange vs non-exchange, deployer still holding |
| `accrual.ts` | **Locate the contract that moves value to holders** (fee switch, burn address, revenue distributor, buyback wallet) and measure realised flow over the trailing 90 days |

`accrual.ts` is the highest-signal module. The framework's sharpest test — *"if this project's
business doubled tomorrow, one more dollar is forced to the token holder because ______"* — has an
on-chain answer or it has none. When no such contract is found, that is recorded as a **finding**,
not an absence of data.

Liquidity figures are re-pulled live at decision time and never read from a stored value: the
framework's error log records stored liquidity rotting 12× in two weeks.

## 6. Vendor adapters (`main/sources/`)

CoinGecko (markets, ±2% depth, categories), GeckoTerminal (pool discovery), DeFiLlama (TVL, fees,
revenue, raises), Artemis (protocol revenue, P/S, DAU).

Every adapter returns `{ value, provenance }` where provenance carries `source`, `url`,
`fetched_at`, and a `verified | vendor_claim` label. Vendor numbers are never silently promoted to
verified facts. Responses cache to SQLite with a per-endpoint TTL.

**Team credibility has no usable API and stays manual** — the tool stores and verifies the
citations, it does not source them.

## 7. Citation verifier (`main/verify/`) — the gate

1. Fetch the URL (real UA, timeout, same-host redirects followed).
2. Normalize both sides: unicode quotes, non-breaking spaces, soft hyphens, collapsed whitespace.
3. Assert the normalized quote is a substring of the normalized document.
4. On miss, compute the closest-matching span and return `near_miss` with it, so the human
   adjudicates rather than guesses.

PDFs are text-extracted. JS-rendered pages that yield no text return `unverifiable_js` — an honest
"cannot check," never a false negative.

**A report cannot reach `committed` while any citation is `unverified`, `near_miss`, `failed`, or
`unverifiable_js`.** The only escape is an explicit `waived` status with a recorded
`waiver_reason` — an absolute gate with no escape hatch gets routed around; a logged waiver stays
auditable.

Verification re-runs at commit time, not only at entry.

## 8. Drafting boundary (`main/drafter/`)

```ts
interface Drafter {
  draft(section: SectionRequest): Promise<{ value: number | string; reason: string }>
}
```

Two implementations:

- `ClaudeCliDrafter` — invokes the local Claude Code CLI in headless mode. Uses the subscription;
  no API billing. Default.
- `ApiKeyDrafter` — direct Messages API call, `claude-opus-5`, for when the CLI is unavailable.
  (`klickbrain/desktop/src/main/ai.ts:80` is a working reference implementation of this shape.)

**The LLM writes only to `*_draft` and `*_draft_reason` columns. It can never write a committed
value.** This is the framework's "an empty My Decision box means the work isn't done," enforced by
schema instead of by discipline. The UI renders the draft greyed beside a required empty input.

Volume is ~10–15 calls per report — irrelevant against subscription limits.

## 9. UI (`renderer/`)

| View | Purpose |
|---|---|
| Coin list | Reports, status, grades, last verified |
| Report editor | Product gate → Liquidity → Narrative → Team → Accrual → Commit |
| Chain panel | Pool census table, safety flags, holder concentration, accrual contracts found |
| Ledger | Committed reports against forward returns; per-sub-score correlation once N is adequate |

The editor is the product. Each scored field shows the draft and its one-line reason beside an
empty input, with live per-citation verification state. **The Commit button is disabled and names
exactly what blocks it** — empty decisions, unverified citations, out-of-range values.

React is warranted here specifically: per-field async verification state, draft-vs-committed
duality, and a gate that must recompute on every change.

## 10. The ledger

Every commit snapshots the full report immutably with its timestamp. `research/forward_returns.py`
runs offline against the existing parquet warehouse and writes `forward_returns` rows at fixed
horizons.

This is the reason the project lives in this repo rather than a new one. The framework has never
been tested: nobody knows whether a 26.5/31 coin outperforms a 15/31 coin, or whether Smart Money
Compatibility predicts anything. With enough committed reports, that becomes a measurable question —
and the answer may be no, which is a result worth having.

**Standing caution, recorded deliberately:** this repo's history is four systems that produced a
confident number which turned out to be worthless. The scores this tool computes are unvalidated
until the ledger says otherwise. The UI must present them as judgments with evidence attached, never
as a verdict.

## 11. Testing

Following the repo's money-paths-first philosophy, here meaning **scoring and gating paths first**:

- Scoring core: exhaustive unit tests plus property tests asserting every range boundary rejects.
- Team weighting: the framework's worked example (`8,7,5,6 → 7.25`) as a fixture.
- Accrual: zero-multiplicand detection, `PURE_PREMIUM` verdict.
- Citation verifier: fixtures for exact match, whitespace variants, unicode quotes, PDF, JS-only
  page, 404, redirect, `near_miss`.
- Pool census: a recorded poison-pair fixture asserting the outlier pool is dropped.
- Commit gate: every blocking condition individually asserted.

## 12. Out of scope for Phase A

Pillar / market-direction / thesis pipeline (Phase B — the `Signal = ((P − 50) ÷ 50) × Quality ×
Impact` machinery over five locked windows). Solana. Any execution or order path. Wallet clustering
or entity resolution. Alerting, cron, or any deployed service. Nansen, Arkham, Token Terminal.

## 13. Open items

| Item | State |
|---|---|
| Claude Code CLI subscription auth from a spawned process | **Unverified.** Confirm before building `ClaudeCliDrafter`; `ApiKeyDrafter` is the fallback either way, so it does not block the spec. |
| Paid vendor tiers | Start on free tiers (CoinGecko demo, GeckoTerminal, DeFiLlama, Artemis). Upgrade only when a rate limit actually bites. |
| Forward-return horizons | Defaulting to **30 / 90 / 180 / 365 days** from commit date. Change before the first commit lands — retrofitting horizons onto existing commits is fine, but comparing across changed horizons is not. |
