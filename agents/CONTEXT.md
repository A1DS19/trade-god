# CONTEXT — canonical vocabulary

Terms used across this project. Use these words; avoid the listed synonyms.

## The report lifecycle

**Report** — one point-in-time analysis of one coin. Mutable while its `status` is `draft`,
immutable forever once `status` is `committed`. A changed conclusion means a new report, never an
edit. _Avoid_: "analysis", "writeup".

**Draft** — a report's pre-commit state: the one window in which a human may still type, change, or
delete anything in it. It carries no LLM-proposed values — the `*_draft` score columns of the
Electron-era design were deleted. _Avoid_: "work in progress", "unsaved".

**Committed** — a report that passed the commit gate. Its rows are frozen in the database by a
`BEFORE UPDATE OR DELETE` trigger, not merely by application code. _Avoid_: "finalized", "saved",
"published".

**Commit gate** — `POST /reports/:id/commit`. One transaction: re-check every precondition (no
empty decisions, no unselected or unverified citations, no out-of-range values), evaluate the
frozen formulas, write `report_scores` with its `scoring_version`, flip `status` to `committed`.
It is the only place a score is computed.

**Scoring version** — the constant in `scoring/ranges.ts` stamped onto every `report_scores` row at
commit. Without it the ledger silently compares rows scored under two different frameworks, which
is its one fatal failure mode.

## Evidence

**Citation** — a `{url, quote}` pair attached to a specific scored field, carrying a verification
status (`unverified`, `verified`, `near_miss`, `failed`, `unverifiable_js`, `waived`) and an origin
(`human` or `model`). A citation is *verified* only when the quote was mechanically found at that
URL. _Avoid_: "source", "reference" — those name the URL alone.

**Candidate** — a citation row with `selected_at IS NULL`: evidence proposed but not yet chosen by
the human. The commit gate counts only selected rows. Unselected candidates are kept, which is what
makes "did the EvidenceFinder actually help?" answerable later.

**EvidenceFinder** — the LLM's only role in this system: given a claim, propose candidate
`{url, quote, why}` triples. It never proposes a number and the `why` has no column to persist in.
Every candidate passes through the deterministic verifier before a human ever sees it.
_Avoid_: "drafter", "assistant", "AI analyst".

**Provider seam** — the single module that puts every model behind one OpenAI-compatible client:
a provider table, strict `json_schema`, answers re-parsed through the caller's own zod schema, a
90s timeout, and an `origin: "model" | "fixture"` tag so a keyless run can never be mistaken for a
real model answer.

**Waiver** — an explicit, reasoned override letting one unverifiable citation through the gate. The
reason is stored; there is no silent bypass.

## The framework

**Frozen formula** — a pure function under `apps/api/src/scoring/`, implemented exactly as the
CoinPicks framework publishes it and never tuned. One copy exists, and the API package's `exports`
map prevents the web app from importing a second evaluation path.

**Product gate** — `ease + hairFire + exclusivity >= 16`. A failure closes the report.

**Narrative score** — the /31 total across six sub-scores. Sub-scores may be **fractional** (the
framework's own worked example scores Communication 4.5/5) — never round or constrain them to
integers.

**Team weighted score** — `(founder × 5 + Σ others) ÷ (5 + N_others)`, out of 10.

**Accrual flow** — annual dollars *forced* to token holders by a mechanism. Governance, exposure,
and alignment are not mechanisms. _Avoid_: "yield", "revenue" — those are the protocol's, not the
holder's.

**Pure premium** — a token with no positive net accrual flow at any price. Tradable, never ownable.

**Pool census** — enumerating every pool for a token, reading reserves on-chain, and discarding
those whose price deviates more than 5% from the TVL-weighted median.

**Poison pair** — a pool advertising large liquidity at a fake price. The thing a census removes.

## The point of all of it

**Ledger** — the accumulated committed reports joined to forward returns at frozen horizons
(30/90/180/365 days). The thing that will eventually say whether any of these scores predict
anything. The answer may be no; that is still a result.

**Pillar** *(Phase B, not built)* — one claim about the market, backed by its own report.

**Signal** *(Phase B, not built)* — `((P − 50) ÷ 50) × Quality × Impact`, range ±10.
