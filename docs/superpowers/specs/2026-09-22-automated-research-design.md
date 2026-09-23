# CoinPicks — Automated Research: Design

**Status:** draft for the owner's review, 2026-09-22. Revision 2 — rewritten after a five-lens
adversarial review (142 findings, 140 confirmed; the resolutions are folded in below).

**Supersedes, in `2026-09-21-coin-research-platform-design.md`:**

- the human-scoring premise (§1) and §8's guarantee that "the human types every score" — for
  **automated** reports only; human reports keep them;
- the EvidenceFinder's role (§8) — replaced by the researcher (§4.3) and the containment rules of §5;
- §12's exclusion of "Alerting, cron, or any deployed service" — replaced by §8 (a local systemd user
  service, still loopback only);
- §6's source list — DeFiLlama raises and Artemis are dropped (both paid-only);
- §13's "Paid vendor tiers" row, which named Artemis among the free tiers — replaced by §4.2;
- the Hono/Node stack rows, and §9's "No component library" and `hc<AppType>` — replaced by §9 and §10;
- the frozen table's **Liquidity tier** row ("human assigns") — for automated reports, a versioned rule
  assigns (§4.7, ruled 2026-09-22); human reports keep the row as written.

**Unchanged and binding:** every *formula* in "Normative formulas (frozen)"; the five schema rules
(§4.3); the three-role privilege split; the immutability triggers; Drizzle as the only DDL author; the
four boundaries (§3.3) — including boundary 3, "one process touches the network and the database",
which is why the pipeline runs inside the API (§8); the ledger (§10) for reports, with its frozen
30/90/180/365 horizons; the citation verifier's rules (§7) for human citations.

The rulings behind this document are in `agents/decisions.md` (2026-09-22). The feasibility evidence is
summarised in Appendix B.

---

## 1. What it produces

Each morning the system refreshes every coin's numbers, re-researches the coins that are due, commits
an immutable report per researched coin, and publishes one **signal** per coin:

| Signal | Meaning |
|---|---|
| **Buy candidate** | very likely passes the frozen product gate and ranks in the top N (§4.8) |
| **Exit warning** | a coin flagged in the last 90 days now fails the gate, or its liquidity, premium or listing has worsened — each confirmed over time (§4.8) |
| **Needs review** | the system cannot signal honestly; the owner looks |
| **Hold** | none of the above |

The owner trades by hand. **Automatic trading is out of scope** until the signals have a validated
forward track record. Until then the Signals screen says, on every visit, that the signals are
**unvalidated** and how many days of track record exist (old §10's caution: scores are judgments with
evidence attached, not verdicts).

Validation is forward-only: web pages cannot be replayed for past dates, so a backtest would be
look-ahead. A 20-coin **pilot** runs first (§15 Q11) and doubles as the researcher bench (§4.3).

## 2. What does not change

- **The frozen formulas** are evaluated exactly as today, at exactly one moment: inside the commit
  transaction. `SCORING_VERSION` does not move.
- **Out-of-range values are rejected, never clamped;** sub-scores are whole numbers.
- **Human reports** work as today: the editor saves draft sub-scores, rationales and figures to
  `report_scores` section by section, and the commit transaction computes the derived columns. Human
  citations follow old §7 unchanged (no Jev involvement).
- **Automated reports** differ only in who supplies the draft values: the pipeline writes them from the
  rubric (§4.5), the live numbers (§4.2) and code-assembled prose (§4.6), then calls the same commit.

## 3. The automated report's lifecycle

1. **Research starts** for a due coin: the pipeline creates a **draft** `reports` row
   (`origin = automated`) for that coin and run. The dossier's claims attach to it as `citations` rows.
2. **Verification and scoring** write `citations` updates and `jev_answers` rows against the draft.
3. **Commit** (§4.6) if every required value can be produced. The draft becomes an immutable committed
   report.
4. **Not commitable** (a key unscored, prose not assemblable, team incomplete, a vendor down): the draft
   is **kept, never deleted**, with its reason (`unscored:<key>`, `prose:<column>`, `team`, `vendor:<name>`).
   It is counted on the Runs screen so the population missing from the ledger stays visible, and the
   coin's signal reads `needs review` until a later run commits.
5. **Gate fails:** the report still commits — decisions 2026-09-21: a ledger of passes alone is
   survivorship bias — with the product section and the columns a failed gate requires, and the
   downstream sections empty. Narrative, team and accrual answers stay in `jev_answers` and never reach
   `report_scores` or `report_team`.

## 4. The pipeline

```
universe ─▶ numbers ─▶ research ─▶ verification ─▶ scoring ─▶ commit ─▶ signal
 (§4.1)     (§4.2)      (§4.3)       (§4.4)         (§4.5)     (§4.6)    (§4.8)
```

Numbers come from data APIs or are parsed by code out of a verified quote — never generated by a model.
Judgments come from Jev over verified evidence only. Arithmetic lives in code.

### 4.1 Universe and coin identity

- **Universe** = the latest warehouse snapshot (the day's top 100 USDT perpetuals by 24h quote volume,
  written by the 05:30 cron) **∪ every flagged coin** (a buy candidate within the last 90 days) that is
  still listed. A flagged coin that falls out of the top 100 keeps being watched; one that is delisted or
  settling fires an exit warning (§4.8).
- **Mapping** a Binance symbol to a CoinGecko id starts from CoinGecko's Binance Futures ticker list and
  must pass all of:
  1. the multiplier is read from the symbol prefix (`1000`, `1000000`, `1M`), and CoinGecko's price
     times that multiplier is within 2% of Binance's index price;
  2. `market_cap > 0`;
  3. `platforms` has a real entry — `{"": ""}`, which CoinGecko returns for native L1s *and* for fake
     index ids, counts as empty — or the id is on the committed native-L1 allowlist;
  4. the category list does not include "Multiplier Denominated Tokens".
- A committed **override table** (`apps/api/src/research/mapping-overrides.ts`) pins ids a human
  confirmed (`mapping_status = override`); overrides count as mapped. A symbol that fails and has no
  override is not researched; its signal is `needs review`, reason `mapping`. On the June–July warehouse
  set (136 symbols), 3 of CoinGecko's own ids were wrong and 1 was a fake index id.
- **Identity for the `coins` row:** `chain` is CoinGecko's asset platform for the coin's primary
  contract (or the native chain for an allowlisted L1); `contract_address` is that contract. The
  existing rule of ≥2 address sources holds: the second source is the project's own site or docs page
  containing the address, found by the verifier's matcher, or the chain explorer's token page — CoinGecko
  and GeckoTerminal are one company and count once. Unconfirmed → `needs review`, reason `address`.
- The commit's identity snapshot (the `coinpicks_assert_commitable` trigger) also freezes
  `binance_symbol` and `coingecko_id`, since an override can change them later.

### 4.2 Numbers

Adapters live in `apps/api/src/sources/`. Each figure carries `{ source, url, fetchedAt, label }`,
`label = vendor_claim` (vendor numbers are never promoted to verified).

**Daily live pull** (every coin in the universe, before research):

| Figure | Source |
|---|---|
| Price, market cap, links, platforms, description | CoinGecko `/coins/{id}` |
| ±2% depth, up and down | CoinGecko `/coins/{id}/tickers?depth=true&exchange_ids=<allowlist>`; drop tickers with `is_anomaly` or `is_stale`, and DEX tickers (base is a contract address) |
| Largest DEX pool | GeckoTerminal `/networks/{net}/tokens/multi/{≤30 addresses}?include=top_pools` (keyless); the pool is **dropped** if its implied token price is more than 5% from CoinGecko's price — framework/00 §6: poison pairs advertise absurd liquidity at a fake price |

**At research time only** (roughly 180 coin-researches a month at the chosen cadence):

| Figure | Source |
|---|---|
| Implied circulating supply, a year of history | CoinGecko `/coins/{id}/market_chart?days=365` (`market_cap ÷ price`) |
| Fees / revenue (context only, never a formula input — §4.5) | DeFiLlama `api.llama.fi`, joined by `gecko_id` through a confirmed override |

- **Budget:** 2 CoinGecko calls per coin per day ≈ 6.1k credits/month, plus ≈ 200 for research-time
  calls and new mappings — under the Demo key's 10k. GeckoTerminal stays keyless (its calls would spend
  the same Demo credits).
- `market_snapshots` holds one row per coin per **UTC day**. A re-run on the same day replaces that day's
  row (a partial pull is not left standing); rows from past days are immutable.
- The screens that show CoinGecko or GeckoTerminal data carry their required attribution ("Powered by
  CoinGecko", a GeckoTerminal link).
- **CoinGecko's terms** discourage storing their data and require deletion if access ends; the schema
  requires stored depth and market-cap figures on every committed report. §15 Q6.

### 4.3 Research

The researcher writes a **dossier**: for each claim key (Appendix A), zero or more claims
`{ key, claim, url, quote }`, and for the team, 3–5 proposed people with a role label and whether they
are the founder.

**Bounds** (in `RESEARCH_VERSION`): at most 8 claims per key; `claim` ≤ 300 characters; `quote` ≤ 600
characters; a claim's `url` must be one the researcher **actually retrieved** in that session (a search
result or a fetched page, recorded from the tool results) — any other URL is rejected before the
verifier sees it. The role label is a closed set taken from framework/05: Founder, Head of Product, Head
of Marketing, Executive, Advisor.

**Bench on the pilot** — two arms, same prompt, same model, differing only in the search source:

- **Arm A:** Claude with the server-side `web_search` and `web_fetch` tools (exact type strings pinned
  at bench start; `_20260318` variants exist at the time of writing).
- **Arm B:** the same Claude model with one client tool, `search`, backed by Perplexity's Search API
  ($5 per 1,000 requests); page text reaches the model only through our own fetcher.
- **Winner:** the higher usable-claim coverage (share of scored keys with ≥1 usable claim, §4.4), unless
  it costs more than twice the other arm per coin; a tie goes to the cheaper arm. The winner, its prompt,
  output schema, model id and tool versions are pinned in `RESEARCH_VERSION`.
- The model is the owner's call (§15 Q9): the fact-check lists `claude-opus-5` as legacy and
  `claude-opus-5-5` as current and cheaper ($4 / $20 per MTok against $5 / $25).

**Guards:**

- Output is parsed through a zod schema before anything is stored. The research seam is lifted from the
  sibling repo (profe); it does not exist here yet.
- Whether the dossier can come back as structured output while web-search citations are on is
  undocumented; one live call at bench start decides between single-pass and two-pass (search turn, then
  an extraction turn without citations).
- **Spend:** a per-run ceiling and a monthly ceiling (`COINPICKS_RESEARCH_BUDGET_RUN_USD`,
  `…_MONTH_USD`; defaults set in the Phase 2 plan). Cost is computed from the API's usage fields and a
  price table pinned in `RESEARCH_VERSION`. At either ceiling the run stops starting coins; coins already
  started finish.
- **Anthropic errors:** 429 `rate_limit_error` → wait `retry-after`, at most 3 tries; 429
  `enforced_spend_limit_reached`, or 400 for the self-set spend limit → research stops for the month and
  the Runs screen says so; other 5xx → the coin fails for this run and stays due.

### 4.4 Verification

For each claim, in order:

1. **Fetch** the URL. Only `http(s)`, only public addresses, checked **at connection time** — the
   resolved IP is validated and the connection pinned to it, so DNS rebinding cannot swap in a private
   address — and re-checked on **every redirect hop** (at most 3). Timeout 20 s, body ≤ 5 MB, content
   types HTML, PDF or plain text only. A fetch that fails for infrastructure reasons (timeout, 5xx, bot
   wall, refused address) sets status `unreachable` — an infrastructure result, never a finding against
   the claim.
2. **Match**, with old §7's normalization (unicode quotes, NBSP, soft hyphens, whitespace). A trailing
   `…` or `...` is stripped. An **inner** ellipsis splits the quote into fragments; at most 3 fragments,
   each ≥ 25 characters, all present **in order within 600 characters** of each other. No match →
   `failed`. The matcher is code; no model is involved.
3. **Window:** the matched block (paragraph, list item or table row) plus up to 1,500 characters on each
   side.
4. **Support:** one Jev Choice over the window and the claim — *supports*, *contradicts* or *says nothing*
   (TypeSafe's citation-check pattern).
5. **Independence**, in code:
   - **first-party** — the project's registrable domains (CoinGecko `links`: homepage, docs, blog) and its
     official accounts on shared platforms, matched by URL prefix (`x.com/<handle>`, `github.com/<org>`,
     `<handle>.medium.com`, `t.me/<name>`, `mirror.xyz/<name>`, …);
   - **independent** — a registrable domain that is neither the project's nor a shared user-content
     platform;
   - **unknown** — a shared-platform URL not matched to the project. It never counts as independent.

A claim is **usable evidence** when its quote was found (`status = verified`) **and** Jev chose
*supports* with confidence ≥ the support floor (0.6, in `RESEARCH_VERSION`). Nothing is deleted: every
claim keeps its status, support verdict and probabilities, so "did the researcher help?" stays
answerable.

Each checked row stores what was actually seen: the final URL after redirects, the page's SHA-256, the
fetch time, the match offset and the window text.

### 4.5 Scoring (Jev)

- **One Jev request per scoring key** (per person for the team), all sent in parallel. A request's state
  is that key's usable claims with their windows — a Jev request has one state that every question in it
  reads, so a per-key request is how each key sees only its own evidence.
- `RUBRIC_VERSION` (new, frozen) holds per key the ordered levels and the value each level becomes
  (Appendix A). Every Score's instruction is "choose the highest level whose description the evidence
  supports".
- **Product:** a Score over the lesson's bands; the sub-score is **the chosen band's lowest value**
  (ruled 2026-09-22). The chosen band is the one with the highest probability; **an exact tie goes to the
  lower band**, the same conservative rule. The expected score is stored, never turned into a number.
- **Narrative:** a Score with one level per integer (Appendix A.2); ties go to the lower level.
- **Team:**
  - The founder is the proposed person with a usable claim under `teamFounder` (a claim about *this*
    project is allowed for this key only). Zero or several founders → not commitable, reason `team`.
  - H, M and L are Scores over framework/05's rungs, fed only by usable claims about **prior** experience
    (framework/05's critical rule).
  - A proposed person with no usable prior-experience claim is **dropped** — absence of evidence is not
    a rung of 0. Fewer than 3 people left → not commitable, reason `team`.
- **Accrual** (the frozen chain, framework/00 §1):
  - *Segment revenue* is a dollar figure parsed by code from a usable claim under `accrualSegmentRevenue`
    whose quote names the segment and contains exactly one dollar amount. DeFiLlama's protocol
    fees/revenue measure something else — revenue already routed through the system — and are shown as
    context only.
  - *Capture share* and *token accrual* are Scores over Appendix A.4's buckets; each becomes its bucket's
    lowest fraction.
  - *Annual issuance* = `max(0, S_now − S_365d) × P_now`, from implied supply (`S = market_cap ÷ price`)
    at research time. A net decrease (burns) gives 0 and is noted in the risk notes. Less than 365 days
    of history → unassessed.
  - Any input missing → accrual unassessed, with a generated absent-reason naming what is missing.
- **A key with no usable claim is not scored.** If a product key is unscored, the gate cannot run and
  the report is not commitable, reason `unscored:<key>`. On a passing gate, an unscored narrative key
  blocks the commit the same way (the completeness CHECK requires all six).
- Every answer is stored in `jev_answers`: the exact state sent, the question text, the levels,
  probabilities, confidence, the chosen level, the value it produced, and the raw response. The client
  always sends `model: "jev-1.13.0"` and asserts the response's model matches; the SDK's default alias
  is never used. Answers are re-parsed through a zod schema (probabilities sum to about 1, keys match the
  levels) before storage — the SDK validates nothing.

Jev is not documented as deterministic, and the vendor's own repeat runs show the top label changing on
close calls. §4.8 is built around that.

### 4.6 Commit

The pipeline calls the same commit transaction the editor uses. It writes the draft's values, then the
frozen formulas compute the derived columns; `reports.status` flips to `committed` and the versions are
recorded (§6).

**What a passing gate requires, and where each value comes from** (the `rs_gate_completeness` conjuncts,
plus the provenance and tier CHECKs):

| Column(s) | Source for an automated report |
|---|---|
| product, narrative sub-scores | §4.5 |
| three product and six narrative rationales | code template: the chosen level's text from Appendix A, then the ids of the usable claims behind it |
| `overview_sentence` | the first sentence of CoinGecko's description (vendor text, not model text), with its URL; §15 Q7 |
| liquidity figures and their provenance | the day's live pull (§4.2), `label = vendor_claim`, `measured_at` = fetch time |
| `liquidity_tier`, its timestamp | §4.7; the timestamp is the commit time |
| `liquidity_justification` | code template: L, its depth and pool parts, the day's tercile bounds, `TIER_RULE_VERSION` |
| accrual inputs, `accrual_rationale` or absent reason | §4.5; the rationale names the bucket texts and claim ids |
| market cap and its provenance | the live pull |
| `risk_notes` | code template: the tier's risk reading, keys backed only by first-party or unknown sources, contradicted claims, the share of claims that were usable, a net-burn note, the premium verdict |
| `waived_citation_count` | 0 — automated reports never waive |
| `report_team` rows | §4.5; `summary` is the **verbatim** usable quote (with URL) of the person's highest-support prior-experience claim, never the model's claim text; `roles` is the closed-set label |

The templates are part of `RUBRIC_VERSION`. A column that cannot be produced makes the report not
commitable, reason `prose:<column>`.

Citations: model rows carry `origin = model`, `finder_provider` and `finder_model`; the commit sets
`selected_at` on every usable claim, so old §7's rule — no unverified *selected* citation at commit —
holds unchanged.

### 4.7 Liquidity tier (rule v1)

The tier names **liquidity**: Low = least liquid. The screens show it with lesson 03's reading — "Low
Liquidity = High Volatility" — so Low is the high-risk tier.

- `L = Σ over allowlisted exchanges of (depth up + depth down) ÷ 2 + largest valid pool TVL` from the
  **live pull at the moment of decision** — framework/00 §6: "Never trust a stored liquidity figure;
  re-pull it live at decision time." Stored snapshots are history, never an input to a tier.
- Tier by the day's universe terciles of L (cut points at the 1/3 and 2/3 quantiles, upper bound
  inclusive): the bottom third Low, the middle Medium, the top High.
- No DEX pool: lesson 03's fallback — "If a coin has no DEX pool, assign tier based only on ±2% depth
  across CEXs." How native L1s (no contract, so no pool lookup) are handled is §15 Q8.
- Noise is handled in §4.8 (persistence), not by averaging stored figures.
- The lesson's benchmark — the pre-pump liquidity of recent top performers — has no free historical
  source. Universe terciles are the proxy; building the lesson's benchmark from our own snapshots is v2.

### 4.8 Signals (rule v1)

**When:** once a day, after the research step, for every coin in the universe. Each coin's signal reads
its **latest committed automated report** and the day's live pull. No committed report, or one older
than 35 days → `needs review`, reason `stale`.

**P(gate):** the three product answers are independent distributions over bands. `P(gate)` is the
total probability of the band combinations whose lowest values sum to ≥ 16. This is the robust quantity:
per-key confidence depends on each key's number of levels, and a floor on each key separately does not
limit how likely the sum is to be wrong.

**Precedence:** exit warning, then needs review, then buy candidate, then hold. A coin gets exactly one.

- **Exit warning** — only for a flagged coin (a buy candidate at any time in the last 90 days), when any
  of these holds:
  - `P(gate) ≤ 0.3` in its two most recent committed reports;
  - its tier fell to a less liquid tier on 3 consecutive daily pulls **and** L is at least 25% below its
    value on the day it was first flagged;
  - its premium verdict left `MULTIPLE` (for `ISSUANCE_NEGATIVE` or `PURE_PREMIUM`) in its two most
    recent reports;
  - its perpetual is delisted or settling.

  An exit warning fires once per flag episode (from the first buy-candidate signal to the exit, or to 90
  days without one), with its reasons stored.
- **Needs review:** mapping or address unconfirmed; the latest research was not commitable (§3, with its
  reason); report stale; `0.3 < P(gate) < 0.7`; or a coin that would otherwise be a buy candidate has any
  narrative or team answer whose chosen level holds less than 0.5 of the probability.
- **Buy candidate:** `P(gate) ≥ 0.7`, and every product sub-score has at least one **independent** usable
  claim. The candidates are the top **5** by narrative total, then team weighted score, then `P(gate)`,
  then symbol.
- **Hold:** everything else.

Buy candidacy is decided by one run. Its protection against Jev noise is the `P(gate) ≥ 0.7` bar, not
persistence; exit warnings require persistence.

### 4.9 The owner's role

- **Signals** is the morning read. **Review queue** lists each coin whose latest signal is
  `needs review`, with the reason, the uncertain answer's distribution and its claims. The owner marks it
  reviewed, with a note, in `review_notes` (mutable, separate from the immutable signals). A reviewed
  coin leaves the queue until its reason changes.
- A committed automated report is never edited. A correction is a **human report** through the editor —
  the comparison track in the ledger.

## 5. Containment — what replaces the EvidenceFinder guarantees

Old §8 promised the model's reasoning had nowhere to persist and that no model-reachable path wrote
`report_scores`. Automated reports change the second promise by design, so it is restated precisely:

- **No free text written by a model reaches a committed column.** The researcher's `claim` text is
  stored for audit in `citations.claim` and shown on screen, never copied into `report_scores` or
  `report_team`.
- The only model-chosen values that are committed are **Jev level choices** (mapped to values by the
  frozen rubric) and **the team role label** (a closed set).
- Every committed number comes from an API or is parsed by code out of a verified quote.
- A test asserts all three: it scans every write path into `report_scores` and `report_team` for its
  source.

## 6. Versioned surfaces — what makes two ledger rows comparable

| Constant | Lives in | Holds | Bumps when |
|---|---|---|---|
| `SCORING_VERSION` (existing) | `scoring/ranges.ts` | frozen formulas, ranges, weights, thresholds | a frozen formula changes (not in this design) |
| `RUBRIC_VERSION` (new, frozen) | `scoring/rubric.ts` — pure data plus the level→value function, no app imports | Appendix A levels, values and prose templates | any level, value or template changes |
| `RESEARCH_VERSION` (new) | `research/version.ts` | researcher prompt, schema, model, tool type strings, claim bounds, retrieved-URL rule; verifier normalization, fragment rule, window, support floor, independence rules; Jev model id and question texts; accrual parsing and issuance rules; the cost price table | any of those changes |
| `TIER_RULE_VERSION` (new) | `research/version.ts` | §4.7's rule and the exchange allowlist | the rule or allowlist changes |
| `SIGNAL_RULE_VERSION` (new) | `research/version.ts` | §4.8's thresholds, N, windows and precedence | any of those changes |

- A frozen-surface test fails if a rubric level, value or template changes without a version bump.
- An automated report records all five. A human report records `SCORING_VERSION` only, and leaves the
  others null.
- **The ledger compares rows only within one origin and one combination of versions.**

## 7. Data model changes

Drizzle only; migrations committed in order; `drizzle-kit push` never. Every new closed set is a
pgEnum (schema rule 1); pgEnums stay append-only.

**Enums:** `citation_status` gains `unreachable`; new `citation_support` (`supports`, `contradicts`,
`unrelated`), `mapping_status` (`verified`, `override`, `failed`), `report_origin` (`automated`,
`human`), `run_kind` (`daily`, `numbers`, `research`, `signals`), `run_status` (`running`, `finished`,
`failed`, `abandoned`), `signal_kind` (`buy_candidate`, `exit_warning`, `needs_review`, `hold`),
`team_role` (the §4.3 closed set).

**Existing tables grow**

- `coins`: `binance_symbol`, `mapping_status`, `mapping_checked_at`. The existing nullable
  `coingecko_id` becomes the mapping target (populated, unique when not null).
- `reports`: `origin`, `run_id`, `rubric_version`, `research_version`, `tier_rule_version`,
  `signal_rule_version` (null on human reports), `uncommitted_reason`; the identity snapshot gains
  `coin_binance_symbol`, `coin_coingecko_id`.
- `citations`: `claim`, `scoring_key`, `first_party` (`first_party` | `independent` | `unknown`, pgEnum),
  `support`, `support_confidence`, `support_probabilities` (jsonb), `final_url`, `page_sha256`,
  `match_offset`, `window_text`. The existing reset trigger also resets the support fields when `claim`,
  `url` or `quote` changes.
- `report_team`: `role_label` (`team_role`).

**New tables**

- `research_runs` — kind, status, started/finished, universe snapshot id, the versions in force, counts,
  cost, failure summary. Rows are updated while running; a `finished`, `failed` or `abandoned` row is
  immutable.
- `market_snapshots` — unique on (coin, UTC day): the figures of §4.2, each with its source URL and
  fetch time, and the pools considered (jsonb). Same-day rows are replaceable; a trigger refuses UPDATE
  or DELETE of a past day.
- `jev_answers` — report, scoring key (plus person for team), state (jsonb), question text, levels,
  probabilities, confidence, chosen level, value, model id, raw response. Owned by its report: the child
  immutability trigger applies.
- `coin_signals` — run, coin, report, kind, rank, `p_gate`, reasons (jsonb), `signal_rule_version`,
  issued-on date. Append-only through a generic `coinpicks_append_only()` trigger (the child trigger
  cannot be reused — every signal points at an already-committed report). Named `coin_signals` because
  "Signal" already names Phase B's pillar formula; `agents/CONTEXT.md` gains both entries.
- `review_notes` — coin, signal, reviewed-at, note, reason at review time. Mutable; the owner's
  annotations.
- `signal_returns` — (signal, horizon) key; entry price is the signal day's daily close from the
  warehouse; outcome columns written by Python. Horizons are the frozen 30/90/180/365. `forward_returns`
  stays as it is, for reports.

**Grants** (a new migration; grants die with their tables): `coinpicks_app` gets the DML each table
needs (INSERT/SELECT on the append-only tables, UPDATE where rows are replaceable). `research` gets
SELECT on `coin_signals`, `market_snapshots` and `jev_answers`, and INSERT/UPDATE on the outcome columns
of `signal_returns`. `TRUNCATE` is refused on every new table.

## 8. Runs and operations

- **One process.** The pipeline lives in `apps/api/src/research/` and runs **inside the API process**
  (boundary 3). Nothing else touches the network or the database. `POST /runs` starts a run — the UI's
  "Research now" and the scheduler both use it.
- **The API runs as a systemd user service** (`coinpicks-api.service`: `bun --env-file=… src/server.ts`,
  restart on failure, lingering enabled), so the schedule works without a terminal open. Its boot path is
  unchanged: migrate as owner, assert the guards, close that pool, serve as `coinpicks_app`.
- **Schedule:** the warehouse cron at 05:30 (installed); at 06:00 a cron entry calls
  `curl --fail -X POST http://127.0.0.1:8789/runs -d '{"kind":"daily"}'`. A daily run is numbers → research
  → signals.
- **Run lock:** a Postgres advisory lock taken with `pg_try_advisory_lock` on a dedicated connection held
  for the whole run. It releases itself if the process dies, so a crash cannot leave a stuck flag. At
  boot, any `running` row without the lock becomes `abandoned`.
- **What is due for research:** never researched → due now; flagged, or last `P(gate) ≥ 0.3` → 7 days
  after the last research; otherwise 30 days. Each run researches at most 25 due coins (setting), oldest
  first, within the spend ceilings. The pilot restricts the universe to its list.
- **A vendor down mid-run:** numbers → that coin's snapshot row is marked partial and its tier is not
  recomputed that day; researcher → the coin stays due; Jev → nothing is committed that run; the coin's
  signal uses its previous report if that is 35 days old or less. Every failure is written to the run
  row.
- **Logs** go to `~/.local/state/coinpicks/`; `/tmp` is tmpfs here and empties at boot (the installed
  warehouse cron moves there too). The Runs screen is the primary alarm: a missing or failed daily run
  shows at the top of Signals.

## 9. Stack (ruled 2026-09-22: Elysia on Bun)

**Workspace:** Bun 1.4.2 as runtime and package manager (bun workspaces). The catalog keeps TypeScript
5.9.3 pinned. **Both apps' tests move to `bun test`**, and the Vitest pin is retired (the decisions entry
that set it is marked). The API suite passes 123 of 124 under `bun test` as is. The one failure is an
assertion that uses `.resolves` on a drizzle thenable, which Bun rejects; the fix is to `await` the value
first. Vitest on the Bun runtime breaks `import { z } from 'zod'` (oven-sh/bun#39866). CI moves to
`oven-sh/setup-bun`.

**API (`apps/api`):**

- **Elysia 1.4.30 and `@elysia/eden` 1.4.10, pinned exactly.** 2.0 is in beta with breaking changes; the
  pin is recorded like the TypeScript pin.
- The app stays **one chained expression** (as today, so `typeof app` keeps its route types), with the
  **error handler registered first**. Elysia applies a hook only to routes registered after it, so the
  default handler — which returns raw SQL and parameters in a 500 — never serves a route. A test throws a
  `DrizzleQueryError` and asserts the body is `{ code: 'INTERNAL' }` with no SQL.
- `listen({ hostname: '127.0.0.1', port, reusePort: false })`. Bun otherwise binds every interface, and
  Elysia's default port reuse lets a second process share the port silently.
- **Keep `pg` 8.23.0 with `drizzle-orm/node-postgres`** (verified unchanged on Bun, including the
  migrator, the role split and the triggers). The refusal mapping (SQLSTATE on `.cause`; CP001 → 409;
  23514/23505 → 422) ports unchanged.
- **Wire schemas stay strings.** Eden types a request body with the schema's *output* type (open upstream
  bugs, still in the 2.0 beta), so each route's body schema declares the raw strings, and the handler
  runs the transforming zod parse — the frozen validators inside it — and maps a failure to the same
  named 422. The 422 message reads `error.valueError` (array paths intact) rather than `error.all`.
- Runs **uncompiled**: `bun build --compile` breaks the boot migrator's path.

**Web (`apps/web`):**

- TanStack Start 1.168.57 on Bun, Eden from a **type-only** import with `parseDate: false`. Eden turns a
  network failure into a synthetic `{ status: 503 }` and throws on a cut JSON body. The editor's
  landed-write handling is re-derived for Eden's `{ data, error, status }` shape, and its failure-path
  walks are repeated.
- The production server is a `Bun.serve({ hostname: '127.0.0.1', port, reusePort: false, fetch })`
  around the Start build's handler. It replaces `scripts/serve.ts`, and Hono leaves the repo.
- `importProtection` and both bundle guards stay.

**Keys and live calls:**

- The four keys (`ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `TYPESAFE_API_KEY`, `COINGECKO_DEMO_API_KEY`)
  live in `~/.config/coinpicks/keys.env`. Only the API service loads it, through `--env-file`. The repo's
  `.env` keeps the DSNs and ports only — Bun auto-loads a working directory's `.env` into every command,
  tests included. It still holds trading-era keys that should be revoked (§15 Q12).
- Every vendor client refuses to construct unless `COINPICKS_LIVE_CALLS=1`, which only the service unit
  sets. The test suite never sets it, so a test cannot reach a paid endpoint by accident.
- `bundle.test.ts` gains needles for the documented key prefixes (`sk-ant-`, `pplx-`, `CG-`). When a
  keys file is present it also scans both bundles for the literal key values.
- **Pre-existing defect, fixed in Phase 0:** the client-size ceiling was measured with
  `NODE_ENV=development`, which `~/.claude/settings.json` injects into every Claude session. CI builds
  in production mode, where the ceiling cannot catch the leak it was written for. The web test pins
  `NODE_ENV=production` for its build, and both numbers are re-measured and recorded in the comment.

## 10. Screens (Spectral)

- **Stack:** shadcn, Base UI "base-nova" style, Tailwind v4 oklch tokens, dark only, lucide icons.
- **Type:** Unbounded for display, with `tabular-nums` on numeric columns (its default digits are
  proportional), over Hanken Grotesk (whose digits are already equal-width).
- **Tokens:** ground `#0D0F24`, surfaces `#13163A` / `#181B48`, hairline `#262A5C`, ink `#ECEBFF`,
  muted-foreground `#A3A5D6`, primary `#9D8CFF`; signal colours buy `#5BE8C4`, exit `#FF7196`, review
  `#FFC45E`. **Text on a filled primary or signal colour is the ground colour, never the ink** (ink on
  primary measures 2.35:1).
- **Setup, as measured on a scratch copy:**
  - `shadcn init -b base -p nova`;
  - import aliases through `package.json#imports` with extension-less targets, so generated imports keep
    their extensions;
  - `shadcn eject`, so the CLI is not a runtime dependency;
  - exact re-pins after every `shadcn add`, then `biome check --write`, with remaining findings fixed per
    component;
  - the dark variant `(&:where(.dark, .dark *))`;
  - init's Geist font removed;
  - the editor's 106 hard-coded light classes moved to tokens.

| Screen | Content |
|---|---|
| Signals | today's signals: signal, `P(gate)`, gate, narrative, team, tier (with its risk reading), premium, the least-certain answer's belief strip. The unvalidated banner and track-record days sit on top, and a failed or missing daily run is flagged first. |
| Review queue | needs-review coins: reason, distribution, claims with first-party / independent / unknown marks, and the review note |
| Coin | report and signal history, and the dossier with each claim's verification (final URL, window, verdict) |
| Runs | runs, versions, cost against the ceilings, failures, not-commitable drafts and their reasons |
| Ledger | returns by signal kind within one version combination (Phase 5) |
| Editor | today's editor, restyled, for human reports |

The **belief strip** is Jev's probability across a key's levels, with the chosen level lit. It is the one
bold element; everything else stays quiet, and colour only ever means a signal state.

## 11. Testing

- **Money paths first**, each against real Postgres where a table is involved:
  - the rubric (every Appendix A level, band → lowest value, tie → lower);
  - `P(gate)`;
  - the matcher (fragments, ellipses, normalization);
  - independence;
  - the tier rule;
  - the signal rule and its precedence;
  - issuance and segment-revenue parsing;
  - prose assembly;
  - the commit transaction for passing, failing and not-commitable reports;
  - the containment test (§5).
- **No live calls:** Jev, researcher and vendor responses are recorded fixtures, re-parsed through the
  production zod schemas; the `COINPICKS_LIVE_CALLS` guard makes a live call impossible from the suite.
- **Guards:** the frozen-surface test extends to `RUBRIC_VERSION`; the bundle needles extend to keys; the
  boundary test is unchanged.
- **Walks:** the editor's failure-path walks are repeated after the Eden port, typing rather than
  pasting.

## 12. Accepted limits

- Ease of Use is judged from docs and reviews, never hands-on.
- Marketing pages can steer Jev (its documentation says so). Usable evidence and the independent-claim
  requirement mitigate this; they do not cure it.
- The universe is the top 100 by perp volume; lesson 01's targets mostly sit below it.
- Tiers are relative to the day's universe, not lesson 03's pre-pump benchmark (v1).
- Issuance is an implied-supply proxy, not unlock data; net burns count as zero issuance.
- The band rule caps the product total at 23, and a product scored Ease 0–3 ("mostly vaporware") still
  passes when both other scores are 8–10 — the frozen gate is a sum (Appendix A.1).

## 13. Build order — one plan per phase

| Phase | Delivers | Keys | Exit |
|---|---|---|---|
| **0 · Stack** | Bun workspace; Elysia API (all 13 routes, one chain, error handler first); Eden client; `bun test` for both apps; shadcn Spectral; the NODE_ENV and key-needle guard fixes; the loopback web server | none | every existing test green, same behaviour, editor walks repeated |
| **1 · Numbers** | CoinGecko and GeckoTerminal adapters; mapping, overrides, address confirmation; `market_snapshots`; `research_runs` and the run lock; `POST /runs` (numbers only) | CoinGecko Demo | 7 consecutive daily snapshots for the universe |
| **2 · Research + verification** | researcher (both bench arms), retrieved-URL rule, fetcher with the SSRF rules, matcher, **Jev client** and the support check, independence, citations extension, spend ceilings | Anthropic, Perplexity, TypeSafe | pilot dossiers verified; bench decided and pinned |
| **3 · Scoring + commit** | `RUBRIC_VERSION` (after Appendix A is approved), `jev_answers`, `P(gate)`, prose assembly, the automated commit, the not-commitable path | same | every pilot coin committed or kept with a reason |
| **4 · Signals + screens** | tier rule, signal rule, `coin_signals`, `review_notes`; Signals, Review queue, Coin, Runs | same | the morning read works on the pilot |
| **5 · Schedule + ledger** | systemd service, the 06:00 cron call, logs; `signal_returns` in Python; pilot → 100 | same | first 30-day read |

TypeSafe's site mentions a waitlist while its console shows billing; access is confirmed before Phase 2.

## 14. Risks

| Risk | Handling |
|---|---|
| Jev answers change between runs | `P(gate)` bars; persistence for exits; the full state and raw answer stored |
| A wrong CoinGecko id | the four checks, overrides, address confirmation; unmapped → needs review |
| Depth noise, fake pools | the allowlist, anomaly and stale drops, the 5% pool-price check, persistence for tier exits |
| Hostile pages | SSRF rules at connection time and on every redirect; the retrieved-URL rule; claim bounds; independence |
| Runaway spend | per-run and monthly ceilings; distinct handling of spend-limit errors |
| A silent failure | runs recorded; the Signals screen flags a missing daily run; logs outside tmpfs |
| A vendor or model retired | versions pinned and recorded; a change is a version bump, never silent |
| Elysia 2.0 | exact pin now; a separate, planned migration later |

## 15. Open questions for the owner

1. **Approve Appendix A** — the narrative levels (drafted), the Smart Money rewrite, the accrual buckets,
   the H/M/L mapping and the prose templates of §4.6. Phase 3 waits for this.
2. **Narrative Maturity's direction.** The draft reads *higher = further along*. If the framework means
   a sweet spot (early but validated scores highest), the scale is re-ordered first.
3. **Hair-on-Fire Innovation (0–6)** reuses lesson 02's band wording on seven levels; confirm, or supply
   0–6 wording.
4. **Signal defaults:** `P(gate)` bars 0.7 and 0.3; the 0.5 chosen-level floor for candidates; top N =
   5; the 90-day flag window; 2-report and 3-day persistence; the 25% liquidity drop; the 35-day
   staleness.
5. **Tier rule v1:** universe terciles of live L.
6. **CoinGecko's storage terms:** accept for personal, non-redistributed use (recommended), or plan a
   licensed source later. Storing derived tiers only is not an option: the schema requires the figures.
7. **`overview_sentence` source:** CoinGecko's description (recommended; vendor text), or a new
   verified-quote key.
8. **Native L1s** (no contract, no pool lookup): measure the canonical wrapped token's pools on its own
   chain (WETH, WSOL, WBNB …) through the override table (recommended), or treat them as depth-only.
   Depth-only needs `liquidity_no_dex_pool`, which would be false.
9. **Researcher model:** `claude-opus-5-5` (current, cheaper) or `claude-opus-5`.
10. **Evidence required per key** (the question deferred to step 6): every scored key needs ≥1 usable
    claim, and a buy candidate needs ≥1 independent usable claim per product key. Human reports keep old
    §7.
11. **Pilot coins:** 20 coins chosen from the universe — recommended ranks 31–50 by volume, liquid but
    not the majors that lesson 01 is not looking for.
12. **The repo `.env`** still holds the trading era's Binance, Telegram and Claude keys; revoke them at
    the source.

---

## Appendix A — `RUBRIC_VERSION` v1 draft

Lines in quotation marks are verbatim from the named lesson and held to the file by a test.
Lines without quotation marks are **editor-authored drafts awaiting approval**. Every Score's
instruction is "choose the highest level whose description the evidence supports"; a probability tie
goes to the lower level.

### A.1 Product (framework/02) — Score over bands; value = the band's lowest number

| Key | Levels (low → high) | Values |
|---|---|---|
| Ease of Use | "(0–3) Does not do what it claims. Complex, broken, or mostly vaporware." · "(4–6) Works, but clunky or not as smooth as claimed." · "(7–10) Does what it claims. Genuinely easy, reliable, and effective in practice." | 0 · 4 · 7 |
| Hair-on-Fire (gate) | "(0–1) Gimmicky or irrelevant" · "(2–4) Interesting, but not exciting" · "(5–7) Clearly valuable or innovative — sparks curiosity" · "(8–10) Undeniable "hair-on-fire" urgency — feels necessary and immediate" | 0 · 2 · 5 · 8 |
| Exclusivity Factor | "(0–1) No exclusivity; generic, easily copied" · "(2–4) Some differentiation, but not rare or defensible" · "(5–7) Clear unique edge (first-to-market or notable feature), but somewhat deniable" · "(8–10) Rare, NOT duplicatable advantage (e.g., Coinbase-level solo integration, legal win like XRP, or official blockchain fork approval) that competitors cannot replicate" | 0 · 2 · 5 · 8 |

Consequences worth knowing before approving:

- The product total can reach at most 23.
- Of the 48 band combinations, 10 pass the 16+ gate:
  - Ease 7–10 with the other two at (2–4, 8–10), (8–10, 2–4), (5–7, 5–7), (5–7, 8–10), (8–10, 5–7) or
    (8–10, 8–10);
  - Ease 4–6 with (5–7, 8–10), (8–10, 5–7) or (8–10, 8–10);
  - Ease 0–3 with (8–10, 8–10).
- That last combination means a product scored "mostly vaporware" still passes when Hair-on-Fire and
  Exclusivity are both 8–10. The frozen gate is a sum, and this design does not change it.

### A.2 Narrative (framework/04) — Score, one level per integer

**Narrative Maturity (0–7)** — framework/04: "How far along is the narrative in the market cycle?"
*(direction: §15 Q2)*

| Value | Level |
|---|---|
| 0 | No recognizable narrative: the market does not yet group this project with any story. |
| 1 | The story exists only in the project's own materials; no outside discussion. |
| 2 | Niche: a few independent writers or communities discuss the narrative. |
| 3 | Emerging: several projects pitch the same narrative, and sector coverage mentions it. |
| 4 | Recognized: major crypto media and data sites track the narrative as a category. |
| 5 | Established: the category holds several large projects and dedicated funds or indices. |
| 6 | Leading: the narrative is one of the cycle's main themes inside crypto. |
| 7 | Fully mature: recognized inside and outside crypto; a settled part of the market. |

**Smart Money Compatibility (0–6)** — framework/04: "Would serious capital flow into this structure?"
Each level includes the one below it.

| Value | Level |
|---|---|
| 0 | No: the structure shuts serious capital out — an anonymous team, no legal entity, no custody or exchange access. |
| 1 | Serious capital could hold it only around major obstacles: unclear legal status, thin venues. |
| 2 | Holdable in principle, with no sign of interest from funds or institutions. |
| 3 | Credible capital is in: known crypto funds or angels are invested. |
| 4 | Top-tier crypto funds are invested. |
| 5 | An institutional path exists: regulated custody or a compliant venue listing, live or announced. |
| 6 | Serious capital is flowing in at scale through institutional channels. |

**Hair-on-Fire Innovation (0–6)** — framework/04: "Does this product innovate or solve a mass problem in
a way that users and/or the entire industry urgently feels they must adopt right now?" *(§15 Q3)*

| Value | Level |
|---|---|
| 0 | "Gimmicky or irrelevant" (framework/02) |
| 1 | Solves a minor problem that few people have. |
| 2 | "Interesting, but not exciting" (framework/02) |
| 3 | A real problem, with some evidence of demand. |
| 4 | "Clearly valuable or innovative — sparks curiosity" (framework/02) |
| 5 | Urgent for a large group of users; adoption is accelerating. |
| 6 | "Undeniable "hair-on-fire" urgency — feels necessary and immediate" (framework/02) |

**Narrative Communication (0–5)** — framework/04: "How well is the story being told?"

| Value | Level |
|---|---|
| 0 | No coherent story: after the project's own materials you still cannot say what it does. |
| 1 | The story exists but is confused, jargon-heavy, or contradicts itself across channels. |
| 2 | Understandable with effort; the message is inconsistent or rarely repeated. |
| 3 | Clear: a newcomer can say what it does in one sentence after the landing page. |
| 4 | Clear and consistent across site, docs and social, and others repeat it accurately. |
| 5 | Exceptional: a crisp line the market repeats unprompted; the story spreads without the team. |

**Narrative Lineage (0–4)** — framework/04: "Is this clearly connected to a previously proven 100x trend?"

| Value | Level |
|---|---|
| 0 | No connection to any previously proven 100x trend. |
| 1 | A loose thematic resemblance only. |
| 2 | The same sector as a proven 100x trend, without a direct link. |
| 3 | A direct successor or extension of a proven 100x trend, and it says so credibly. |
| 4 | Widely recognized as the next chapter of a proven 100x trend. |

**Narrative Mutation (0–3)** — framework/04: "Has this narrative evolved into a real-world trend?"

| Value | Level |
|---|---|
| 0 | No: purely crypto-native, with no use outside crypto. |
| 1 | Early signs of use or attention outside crypto. |
| 2 | Measurable real-world adoption: users, partners or revenue outside crypto. |
| 3 | Yes: an established real-world trend in its own right. |

### A.3 Team (framework/05) — Score per person over the rungs; value = the rung's number

| Rung | Levels (low → high) | Values |
|---|---|---|
| H | "0 – No founding or executive leadership" · "2 – Founded a crypto project with unclear or early traction" · "4 – Leadership in a global institution (e.g. SEC, CFTC, IMF, BIS, G7/G20)" **or** "4 – Executive at a major crypto company (e.g. Coinbase, Binance, Kraken)" (one level) · "5 – Founded and scaled a successful crypto company with real traction" | 0 · 2 · 4 · 5 |
| M | "0 – No real-world business experience" · "1 – Business exists, but traction is unclear" · "2 – Non-executive role at a top company (e.g. PM at Coinbase, engineer at Amazon)" · "3 – Founded a real-world business with profit, growth, or acquisition" | 0 · 1 · 2 · 3 |
| L | "0 – No experience, credentials, or evidence of contribution" · "1 – Has exposure (e.g. influencer or public face) but lacks real roles or skills" · "2 – Holds strong credentials (MBA, PhD, CFA, etc.)" | 0 · 1 · 2 |

### A.4 Accrual (framework/00) — buckets; value = the bucket's lowest fraction

**Capture share** — framework/00: "what fraction of that segment plausibly routes through THIS system?
Be brutal."

| Value | Level |
|---|---|
| 0 | Essentially none of the segment routes through this system. |
| 0.01 | A sliver: roughly 1–5% of the segment. |
| 0.05 | A meaningful niche: roughly 5–20%. |
| 0.20 | A major share: roughly 20–50%. |
| 0.50 | Dominant: half of the segment or more. |

**Token accrual** — framework/00: "of the revenue that routes through the system, what percentage is
forced through the token?"

| Value | Level |
|---|---|
| 0 | Nothing forces revenue to holders — including a treasury that may buy back, which framework/00 calls "a promise, not a mechanism". |
| 0.01 | A contractual mechanism forces under 10% of revenue to holders. |
| 0.10 | A contractual mechanism forces 10–50% of revenue to holders. |
| 0.50 | A contractual mechanism forces half of revenue or more to holders. |

### A.5 Prose templates (part of `RUBRIC_VERSION`)

- **Rationale** (product, narrative, accrual): `<chosen level text> — evidence: #<citation id>, …`
- **Liquidity justification:**
  `L = $<L> (±2% depth $<d> across <n> venues + largest pool $<p> on <network>); universe terciles $<t1> / $<t2> on <date>; tier rule <TIER_RULE_VERSION>.`
- **Risk notes:** one line per item that applies:
  - the tier's risk reading;
  - keys resting only on first-party or unknown sources;
  - contradicted claims;
  - the usable share of claims;
  - a net burn;
  - the premium verdict.
- **Team summary:** the verbatim usable quote and its URL.
- **Overview:** the first sentence of CoinGecko's description and its URL (§15 Q7).

---

## Appendix B — Feasibility facts (2026-09-22)

Measured in scratch copies; the research did not modify the repo. Versions are from `npm view` on the day.

- **Stack:**
  - bun 1.4.2; elysia 1.4.30 (2.0.0-beta.16 breaks the API); @elysia/eden 1.4.10; drizzle-orm 0.45.3;
    drizzle-kit 0.31.11; pg 8.23.0; @tanstack/react-start 1.168.57; @tanstack/react-router 1.170.38;
    vite 8.3.0; zod 4.6.5.
  - Elysia validates zod 4 through Standard Schema and runs superRefine. `onError` can return a custom
    422, in production mode too.
  - Eden's browser runtime is 12.1 KB and carries no server code.
  - The API suite passes 124/124 with Vitest on Node and 123/124 under `bun test`.
- **Data:**
  - CoinGecko `/coins/{id}/tickers?depth=true` returns `cost_to_move_up_usd` and
    `cost_to_move_down_usd`. The ticker `trust_score` is always null; `is_anomaly`, `is_stale` and
    `bid_ask_spread_percentage` are usable.
  - No plan sorts GeckoTerminal pools by reserve. The keyless `tokens/multi` endpoint takes ≤30
    addresses and returns each token's top pool.
  - DeFiLlama fees and revenue are free. Emissions, unlocks and raises return HTTP 402; its API tier
    costs $300/month.
  - Artemis has no free API.
- **Researcher:**
  - Anthropic web search costs $10 per 1,000 searches. `cited_text` is at most 150 characters and
    sometimes ends in "...". Web fetch has no per-call fee.
  - Perplexity's Search API costs $5 per 1,000 requests, each up to 5 queries. Its Sonar API ends
    2026-09-27.
  - No provider guarantees a verbatim quote.
- **Jev:**
  - `POST https://api.typesafe.ai/v1/systemone` with a Bearer key.
  - Score takes 2–10 levels; Choice takes up to 255 options.
  - Model `jev-1.13.0`; $0.042 per 1M input tokens, output free; 1,200 requests/min.
  - Context is 64k tokens, of which 32k is for the state plus the longest question.
  - `@typesafe-ai/sdk` 0.6.0 validates no responses and retries on timeout, so set an explicit timeout
    and pin the version.
  - Confidence is `clamp((n·p_max − 1)/(n − 1))`, which depends on the number of levels.
- **UI:**
  - shadcn 4.21.0 (base-nova), @base-ui/react 1.8.0, @fontsource-variable/unbounded and
    @fontsource-variable/hanken-grotesk 5.3.0.
  - All 62 components pass this repo's strict tsconfig and `boundary.test.ts`.
