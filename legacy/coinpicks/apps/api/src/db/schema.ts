import { type SQLWrapper, sql } from 'drizzle-orm'
import {
  bigint,
  boolean,
  check,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from 'drizzle-orm/pg-core'
import { gateCompletenessSql } from './gate-fields.ts'

/*
 * CoinPicks schema. Drizzle is the ONLY DDL author. Seven tables, no user_id anywhere:
 * loopback, one user, no auth.
 *
 * WHY double precision AND NOT numeric, for every money / fraction / derived figure: the
 * frozen core computes in IEEE-754 float64. annualHolderFlow({segmentRevenueUsd: 1,
 * captureShare: 0.1, accrualPct: 0.2}) returns 0.020000000000000004. Verified on 16.13:
 * float8 reproduces that exactly, numeric computes 0.02 — so rs_gross_flow_is_product below
 * would REJECT a row the authoritative TypeScript produced. Schema rule 5 mandates
 * timestamptz and jsonb; it is silent on the numeric type, and rescore parity decides it.
 *
 * WHY the explicit Infinity bounds: Postgres does not use IEEE comparison semantics.
 * 'NaN'::float8 > 1 is TRUE and 'NaN'::float8 >= 0 is TRUE, so `>= 0` alone does NOT
 * reproduce assertNonNegative(). `x BETWEEN 0 AND 1` does exclude NaN, because NaN sorts
 * above every real value.
 */

/** Number.isFinite(), in SQL: NaN and both infinities fail it. */
const finite = (c: SQLWrapper) => sql`${c} > '-Infinity'::float8 AND ${c} < 'Infinity'::float8`

/** assertNonNegative(): finite and >= 0. */
const nonNegativeFinite = (c: SQLWrapper) => sql`${c} >= 0 AND ${c} < 'Infinity'::float8`

/** A fraction in [0, 1] — the 2026-09-21 ruling on captureShare and accrualPct. */
const unitFraction = (c: SQLWrapper) => sql`${c} BETWEEN 0 AND 1`

/** Rejects '' and '   ' wherever the spec requires prose to actually exist. */
const nonBlank = (c: SQLWrapper) => sql`length(btrim(${c})) > 0`

// ---------------------------------------------------------------------------
// Enums. Schema rule 1: pgEnum, never text().$type<>().
// pgEnums are APPEND-ONLY from the first commit. Each of these is a closed set taken from a
// frozen formula or from the spec, so that cost is already paid.
// ---------------------------------------------------------------------------

export const reportStatus = pgEnum('report_status', ['draft', 'committed'])

export const citationStatus = pgEnum('citation_status', [
  'unverified',
  'verified',
  'near_miss',
  'failed',
  'unverifiable_js',
  'waived',
])

export const citationOrigin = pgEnum('citation_origin', ['human', 'model'])

/** Section 2.2: Low | Medium | High, assigned by the human; there is no formula. One
 *  canonical casing, and the UI maps the framework's Low/Medium/High onto it. */
export const liquidityTier = pgEnum('liquidity_tier', ['low', 'medium', 'high'])

/** Section 6: every vendor figure is labelled. A vendor number is never silently promoted
 *  to a verified fact. */
export const provenanceLabel = pgEnum('provenance_label', ['verified', 'vendor_claim'])

/*
 * accrual.ts `AccrualResult.zeroFactor`, camelCase VERBATIM. An earlier revision used
 * snake_case labels and a mapping in the commit route; the mapping was never written, and
 * compiling the commit path against it produced
 *   TS2322: Type '"accrualPct" | "segmentRevenueUsd" | "captureShare" | null' is not
 *   assignable to type '"segment_revenue_usd" | ...'
 * while the database rejected the camelCase label outright. No mapping means no mapping to
 * get wrong, and tsc now checks the assignment for free.
 */
export const accrualZeroFactor = pgEnum('accrual_zero_factor', [
  'segmentRevenueUsd',
  'captureShare',
  'accrualPct',
])

/** accrual.ts `PremiumResult['kind']`, verbatim including case. */
export const discoveryPremiumKind = pgEnum('discovery_premium_kind', [
  'MULTIPLE',
  'ISSUANCE_NEGATIVE',
  'PURE_PREMIUM',
])

/** The five chain modules of spec section 5 (Phase A.2). */
export const chainFactKind = pgEnum('chain_fact_kind', [
  'pool_census',
  'safety',
  'issuance',
  'holders',
  'accrual',
])

// ---------------------------------------------------------------------------
// coins
// ---------------------------------------------------------------------------

export const coins = pgTable(
  'coins',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    symbol: text('symbol').notNull(),
    name: text('name').notNull(),
    /** Nullable: not every researched coin is listed on CoinGecko. */
    coingeckoId: text('coingecko_id'),
    /** text, not an enum: coins are researched before the A.2 chain layer exists, and
     *  adding a chain should not be a migration. */
    chain: text('chain').notNull(),
    /** Nullable: a native asset has no contract. */
    contractAddress: text('contract_address'),
    addressSources: jsonb('address_sources').$type<string[]>().notNull().default([]),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    check('coins_symbol_not_blank', nonBlank(t.symbol)),
    check('coins_name_not_blank', nonBlank(t.name)),
    check('coins_chain_not_blank', nonBlank(t.chain)),
    /*
     * CASE, not AND. jsonb_array_length() RAISES on a non-array and Postgres does not
     * guarantee AND short-circuits — written right-to-left the AND form fails with
     * "cannot get array length of a non-array", a raw function error rather than a
     * constraint violation. CASE never evaluates the untaken arm. The >= 2 rule is about
     * verifying an ADDRESS, so a native asset with none is exempt.
     */
    check(
      'coins_address_sources_min_2',
      sql`CASE
            WHEN jsonb_typeof(${t.addressSources}) <> 'array' THEN false
            WHEN ${t.contractAddress} IS NULL THEN true
            ELSE jsonb_array_length(${t.addressSources}) >= 2
          END`,
    ),
    /** One coin row per (chain, address), or the ledger splits one coin's history in two.
     *  Partial: a native asset carries NULL and Postgres treats NULLs as distinct. */
    uniqueIndex('coins_chain_address_uniq')
      .on(t.chain, sql`lower(${t.contractAddress})`)
      .where(sql`${t.contractAddress} IS NOT NULL`),
    index('coins_symbol_idx').on(t.symbol),
  ],
)

// ---------------------------------------------------------------------------
// reports
// ---------------------------------------------------------------------------

export const reports = pgTable(
  'reports',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    coinId: uuid('coin_id')
      .notNull()
      .references(() => coins.id, { onDelete: 'restrict' }),
    /*
     * Rule 4: the COMPARE-AND-SWAP token, not a revision number. Every draft mutation is
     * UPDATE ... WHERE id = $1 AND version = $2, 409 on zero rows.
     *
     * There is deliberately NO unique constraint on (coin_id, version). The discarded SQLite
     * plan declared UNIQUE (coin_id, version) under the older reading where `version`
     * numbered a coin's reports. Rule 4 overturned that: re-researching a coin creates a NEW
     * reports row, and each report independently walks 1, 2, 3..., so the constraint would
     * make the second report's first save collide with the first report's first save — as a
     * unique-violation inside the commit transaction, after the verifier has already written
     * its results. Reports are distinguished by id; their order is created_at / committed_at.
     */
    version: integer('version').notNull().default(1),
    status: reportStatus('status').notNull().default('draft'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    committedAt: timestamp('committed_at', { withTimezone: true }),
    /*
     * THE COIN IDENTITY SNAPSHOT, written by coinpicks_assert_commitable() at the moment of
     * commit and frozen by reports_immutable thereafter.
     *
     * `coins` has no immutability guard and cannot have a useful one: a token legitimately
     * migrates contract, and the old reports should keep naming the contract they were
     * actually researched against rather than blocking the migration. Without this snapshot,
     * `UPDATE coins SET symbol='SCAM', contract_address='0xdeadbeef'` — CONFIRMED to succeed
     * live — silently re-points every committed report on that coin, and every forward
     * return ever computed from the (chain, contract_address) join, while the committed
     * report's own bytes stay unchanged so nothing looks wrong.
     *
     * contract_address is nullable here for the same reason it is on coins: a native asset
     * has none. symbol and chain are the pair the CHECK keys off.
     */
    coinSymbol: text('coin_symbol'),
    coinChain: text('coin_chain'),
    coinContractAddress: text('coin_contract_address'),
  },
  (t) => [
    check('reports_version_positive', sql`${t.version} >= 1`),
    /** Section 10: every commit snapshots the report immutably WITH ITS TIMESTAMP. A
     *  committed row without one has no ledger date to join on. */
    check(
      'reports_committed_at_iff_committed',
      sql`(${t.status} = 'committed') = (${t.committedAt} IS NOT NULL)`,
    ),
    check(
      'reports_identity_snapshot_iff_committed',
      sql`(${t.status} = 'committed')
          = (${t.coinSymbol} IS NOT NULL AND ${t.coinChain} IS NOT NULL)`,
    ),
    index('reports_coin_id_idx').on(t.coinId),
    /** The ledger reads committed rows in commit order. */
    index('reports_committed_idx').on(t.committedAt).where(sql`${t.status} = 'committed'`),
  ],
)

// ---------------------------------------------------------------------------
// report_scores — one row per report, created by the reports_seed_scores trigger
//
// EVERY column here except report_id is nullable, and accrual_assessed is generated. This
// table holds the DRAFT: a half-finished report has to survive a browser reload. The
// containment guarantee of spec 8.1 is unchanged and restated exactly: the frozen formulas
// are evaluated in exactly one place, and no LLM-reachable code path writes this table.
// `product_passed IS NOT NULL` is the sentinel meaning "the frozen gate ran".
// ---------------------------------------------------------------------------

export const reportScores = pgTable(
  'report_scores',
  {
    reportId: uuid('report_id')
      .primaryKey()
      .references(() => reports.id, { onDelete: 'cascade' }),

    /** Rule 3. Written by the commit route from SCORING_VERSION in scoring/ranges.ts.
     *  Nullable at column level and NOT NULL by trigger at the moment of commit, which is
     *  what "conditionally NOT NULL" has to mean in SQL. */
    scoringVersion: text('scoring_version'),

    overviewSentence: text('overview_sentence'),
    riskNotes: text('risk_notes'),

    // -- Product gate: productGate() / ProductGateResult ----------------------
    productEase: integer('product_ease'),
    productHairFire: integer('product_hair_fire'),
    productExclusivity: integer('product_exclusivity'),
    productTotal: integer('product_total'),
    productPassed: boolean('product_passed'),
    productEaseRationale: text('product_ease_rationale'),
    productHairFireRationale: text('product_hair_fire_rationale'),
    productExclusivityRationale: text('product_exclusivity_rationale'),

    // -- Liquidity: no formula, the human tiers. Every measured figure carries the
    //    section 6 provenance quartet, and the tier carries its own timestamp so a tier
    //    cannot be justified by numbers that postdate and contradict it.
    liquidityTier: liquidityTier('liquidity_tier'),
    liquidityTierAssignedAt: timestamp('liquidity_tier_assigned_at', { withTimezone: true }),
    liquidityJustification: text('liquidity_justification'),
    liquidityDepth2pctUsd: doublePrecision('liquidity_depth_2pct_usd'),
    liquidityDepthSource: text('liquidity_depth_source'),
    liquidityDepthUrl: text('liquidity_depth_url'),
    liquidityDepthLabel: provenanceLabel('liquidity_depth_label'),
    liquidityDepthMeasuredAt: timestamp('liquidity_depth_measured_at', { withTimezone: true }),
    liquidityTopPoolTvlUsd: doublePrecision('liquidity_top_pool_tvl_usd'),
    liquidityTopPoolSource: text('liquidity_top_pool_source'),
    liquidityTopPoolUrl: text('liquidity_top_pool_url'),
    liquidityTopPoolLabel: provenanceLabel('liquidity_top_pool_label'),
    liquidityTopPoolMeasuredAt: timestamp('liquidity_top_pool_measured_at', {
      withTimezone: true,
    }),
    /** framework/03 needs "no pool" distinguishable from "not measured" — the tier rule
     *  depends on the difference. */
    liquidityNoDexPool: boolean('liquidity_no_dex_pool').notNull().default(false),
    /** Pools left after the 5%-deviation poison-pair drop (section 5) — Phase A.2. */
    liquiditySurvivingPools: integer('liquidity_surviving_pools'),

    // -- Narrative: narrativeTotal() over NARRATIVE_MAX -----------------------
    narrativeMaturity: integer('narrative_maturity'),
    narrativeSmartMoney: integer('narrative_smart_money'),
    /** 0-6 HERE. product_hair_fire is 0-10. Two distinct fields, neither derived from the
     *  other (section 2.1). */
    narrativeHairFire: integer('narrative_hair_fire'),
    narrativeCommunication: integer('narrative_communication'),
    narrativeLineage: integer('narrative_lineage'),
    narrativeMutation: integer('narrative_mutation'),
    narrativeTotal: integer('narrative_total'),
    /** Section 2.3 requires a 1-2 sentence rationale per sub-score. Without a column the
     *  commit gate cannot enforce it at all. These are NOT the deleted *_draft_reason
     *  columns: they hold the HUMAN's "My Decision" prose. */
    narrativeMaturityRationale: text('narrative_maturity_rationale'),
    narrativeSmartMoneyRationale: text('narrative_smart_money_rationale'),
    narrativeHairFireRationale: text('narrative_hair_fire_rationale'),
    narrativeCommunicationRationale: text('narrative_communication_rationale'),
    narrativeLineageRationale: text('narrative_lineage_rationale'),
    narrativeMutationRationale: text('narrative_mutation_rationale'),

    // -- Team: teamWeightedScore(). A MEAN, so explicitly not an integer. Per-person
    //    H/M/L live in report_team; memberScore() is h+m+l and is NOT stored, because a
    //    stored sum is a second place to drift.
    teamWeightedScore: doublePrecision('team_weighted_score'),

    // -- Value accrual: AccrualInput -----------------------------------------
    accrualSegmentRevenueUsd: doublePrecision('accrual_segment_revenue_usd'),
    accrualCaptureShare: doublePrecision('accrual_capture_share'),
    /** A fraction in [0, 1] DESPITE THE NAME, which tracks the frozen table's `accrual_pct`
     *  deliberately (ruled 2026-09-21). */
    accrualPct: doublePrecision('accrual_pct'),
    accrualAnnualIssuanceUsd: doublePrecision('accrual_annual_issuance_usd'),
    /*
     * GENERATED, not a flag the editor sets. An unfilled accrual section must not be
     * indistinguishable from a measured zero: with all four inputs NULL, the shortest
     * expression that satisfies the compiler in the gate is `?? 0`, zero is in range, and
     * discoveryPremium() then returns PURE_PREMIUM — the framework's harshest verdict,
     * narrowed by the 2026-09-21 ruling to mean ZERO FORCED FLOW — about a coin nobody
     * assessed, immutably. Deriving the flag from the inputs makes absence and zero
     * different states that no code path can conflate, and rs_premium_needs_assessment
     * below forbids a verdict without an assessment.
     */
    accrualAssessed: boolean('accrual_assessed')
      .notNull()
      .generatedAlwaysAs(
        sql`accrual_segment_revenue_usd IS NOT NULL
            AND accrual_capture_share IS NOT NULL
            AND accrual_pct IS NOT NULL
            AND accrual_annual_issuance_usd IS NOT NULL`,
      ),
    /** Section 1 allows accrual to be absent — "or the finding that none exists" — so the
     *  completeness CHECK cannot simply require the inputs. It requires this instead. */
    accrualAbsentReason: text('accrual_absent_reason'),
    accrualRationale: text('accrual_rationale'),

    // -- Value accrual: AccrualResult ----------------------------------------
    accrualGrossAnnualFlowUsd: doublePrecision('accrual_gross_annual_flow_usd'),
    accrualNetAnnualFlowUsd: doublePrecision('accrual_net_annual_flow_usd'),
    /** "One zero anywhere zeroes the product" — WHICH one. NULL = no zero factor. */
    accrualZeroFactor: accrualZeroFactor('accrual_zero_factor'),
    /** Section 1: "the contract address that makes it true (or the finding that none
     *  exists)". chain/accrual.ts — Phase A.2. */
    accrualContractAddress: text('accrual_contract_address'),
    accrualFinding: text('accrual_finding'),
    /** Named `trailing_90d` and never annualised: a trailing-90-day dollar figure sitting
     *  beside two annual dollar figures, all suffixed `_usd`, is a 4x unit error waiting
     *  for the first ledger query that treats them as comparable. Phase A.2. */
    accrualMeasuredTrailing90dUsd: doublePrecision('accrual_measured_trailing_90d_usd'),

    // -- Discovery premium: discoveryPremium() -------------------------------
    /** The `marketCapUsd` argument, with the same provenance quartet the liquidity figures
     *  carry. It is the single most volatile input in the report — it moves 20% in a week —
     *  and the ledger joins a premium multiple against forward returns, so it has to be
     *  possible to say what price the multiple was struck at. */
    discoveryMarketCapUsd: doublePrecision('discovery_market_cap_usd'),
    discoveryMarketCapSource: text('discovery_market_cap_source'),
    discoveryMarketCapUrl: text('discovery_market_cap_url'),
    discoveryMarketCapLabel: provenanceLabel('discovery_market_cap_label'),
    discoveryMarketCapMeasuredAt: timestamp('discovery_market_cap_measured_at', {
      withTimezone: true,
    }),
    /*
     * PremiumResult is a three-way discriminated union. It lands as a discriminant column
     * plus exactly ONE payload column — the MULTIPLE arm's `multiple`. ISSUANCE_NEGATIVE's
     * payload (gross, net) is already stored above and PURE_PREMIUM has none, so the union
     * costs two columns rather than four.
     */
    discoveryPremiumKind: discoveryPremiumKind('discovery_premium_kind'),
    discoveryPremiumMultiple: doublePrecision('discovery_premium_multiple'),

    /** How much of this report's evidence was waived, so a ledger query can stratify
     *  committed reports by it. That number is a finding about the framework, not
     *  bookkeeping. Written at commit. */
    waivedCitationCount: integer('waived_citation_count'),
  },
  (t) => [
    // -- Ranges: assertIntegerRange() reproduced. Rejected, never clamped. -----
    // These bounds also live in scoring/{ranges,product,narrative}.ts. Task 9 pins the two
    // copies together with a test that reads the generated .sql.
    check('rs_product_ease_range', sql`${t.productEase} BETWEEN 0 AND 10`),
    check('rs_product_hair_fire_range', sql`${t.productHairFire} BETWEEN 0 AND 10`),
    check('rs_product_exclusivity_range', sql`${t.productExclusivity} BETWEEN 0 AND 10`),
    check('rs_narrative_maturity_range', sql`${t.narrativeMaturity} BETWEEN 0 AND 7`),
    check('rs_narrative_smart_money_range', sql`${t.narrativeSmartMoney} BETWEEN 0 AND 6`),
    check('rs_narrative_hair_fire_range', sql`${t.narrativeHairFire} BETWEEN 0 AND 6`),
    check('rs_narrative_communication_range', sql`${t.narrativeCommunication} BETWEEN 0 AND 5`),
    check('rs_narrative_lineage_range', sql`${t.narrativeLineage} BETWEEN 0 AND 4`),
    check('rs_narrative_mutation_range', sql`${t.narrativeMutation} BETWEEN 0 AND 3`),
    check('rs_team_weighted_range', sql`${t.teamWeightedScore} BETWEEN 0 AND 10`),
    check('rs_segment_revenue_nonneg', nonNegativeFinite(t.accrualSegmentRevenueUsd)),
    check('rs_capture_share_unit', unitFraction(t.accrualCaptureShare)),
    check('rs_accrual_pct_unit', unitFraction(t.accrualPct)),
    check('rs_annual_issuance_nonneg', nonNegativeFinite(t.accrualAnnualIssuanceUsd)),
    check('rs_gross_flow_nonneg', nonNegativeFinite(t.accrualGrossAnnualFlowUsd)),
    check('rs_net_flow_finite', finite(t.accrualNetAnnualFlowUsd)),
    check('rs_market_cap_nonneg', nonNegativeFinite(t.discoveryMarketCapUsd)),
    check('rs_premium_multiple_nonneg', nonNegativeFinite(t.discoveryPremiumMultiple)),
    check('rs_measured_90d_nonneg', nonNegativeFinite(t.accrualMeasuredTrailing90dUsd)),
    check('rs_depth_2pct_nonneg', nonNegativeFinite(t.liquidityDepth2pctUsd)),
    check('rs_top_pool_tvl_nonneg', nonNegativeFinite(t.liquidityTopPoolTvlUsd)),
    check('rs_surviving_pools_nonneg', sql`${t.liquiditySurvivingPools} >= 0`),
    check('rs_waived_count_nonneg', sql`${t.waivedCitationCount} >= 0`),
    check('rs_scoring_version_not_blank', nonBlank(t.scoringVersion)),

    /** Rule 3, as a database fact: a scored row names its framework version and a draft
     *  does not. This is what makes `scoring_version` conditionally NOT NULL. */
    check(
      'rs_scored_row_names_its_version',
      sql`(${t.productPassed} IS NULL) = (${t.scoringVersion} IS NULL)`,
    ),

    /*
     * Arithmetic identities, each gated on the scored sentinel.
     *
     * The gate is not decoration. Without it, an operator who types a 0 into
     * accrual_segment_revenue_usd on a half-finished draft trips
     * rs_zero_factor_matches_inputs — a derived column the commit route has not written
     * yet — and cannot save. Reproduced on the naive version. From the moment
     * product_passed is set, every identity below is enforced for the life of the row.
     */
    check(
      'rs_product_total_is_sum',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.productTotal} = ${t.productEase} + ${t.productHairFire} + ${t.productExclusivity}
          END`,
    ),
    check(
      'rs_product_passed_matches_threshold',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.productPassed} = (${t.productTotal} >= 16)
          END`,
    ),
    check(
      'rs_narrative_total_is_sum',
      sql`CASE WHEN ${t.productPassed} IS NULL OR ${t.narrativeTotal} IS NULL THEN true ELSE
            ${t.narrativeTotal} = ${t.narrativeMaturity} + ${t.narrativeSmartMoney}
              + ${t.narrativeHairFire} + ${t.narrativeCommunication}
              + ${t.narrativeLineage} + ${t.narrativeMutation}
          END`,
    ),
    check(
      'rs_gross_flow_is_product',
      sql`CASE WHEN ${t.accrualGrossAnnualFlowUsd} IS NULL THEN true ELSE
            ${t.accrualGrossAnnualFlowUsd}
              = ${t.accrualSegmentRevenueUsd} * ${t.accrualCaptureShare} * ${t.accrualPct}
          END`,
    ),
    check(
      'rs_net_flow_is_gross_minus_issuance',
      sql`CASE WHEN ${t.accrualNetAnnualFlowUsd} IS NULL THEN true ELSE
            ${t.accrualNetAnnualFlowUsd}
              = ${t.accrualGrossAnnualFlowUsd} - ${t.accrualAnnualIssuanceUsd}
          END`,
    ),
    /** `factors.find(f => input[f] === 0) ?? null` — same first-match precedence, in SQL,
     *  so the stored label cannot disagree with the inputs beside it. */
    check(
      'rs_zero_factor_matches_inputs',
      sql`CASE WHEN ${t.productPassed} IS NULL THEN true ELSE
            ${t.accrualZeroFactor} IS NOT DISTINCT FROM (
              CASE
                WHEN ${t.accrualSegmentRevenueUsd} = 0 THEN 'segmentRevenueUsd'
                WHEN ${t.accrualCaptureShare} = 0 THEN 'captureShare'
                WHEN ${t.accrualPct} = 0 THEN 'accrualPct'
                ELSE NULL
              END)::accrual_zero_factor
          END`,
    ),
    /*
     * discoveryPremium()'s branch order, in SQL — INCLUDING the noise floor that Task 8
     * adds to the TypeScript. `net > 0` alone is not the MULTIPLE condition: with segment
     * revenue $100,000,000, capture 0.07, accrual 0.01 and issuance $70,000 — a token
     * forcing exactly as much to holders as it prints — float64 leaves
     * gross = 70000.00000000001 and net = 1.455e-11, and the naive branch commits
     * kind='MULTIPLE' with a payback multiple of 3.4e21. Verified live on 16.13, both that
     * the residue occurs and that this CHECK refuses the verdict.
     *
     * PURE_PREMIUM requires gross = 0 — the 2026-09-21 ruling that it was over-applied.
     */
    check(
      'rs_premium_kind_matches_flows',
      sql`${t.discoveryPremiumKind} IS NOT DISTINCT FROM (
            CASE
              WHEN ${t.accrualNetAnnualFlowUsd} IS NULL THEN NULL
              WHEN ${t.accrualNetAnnualFlowUsd} > 0
                   AND ${t.accrualNetAnnualFlowUsd} >= ${t.accrualGrossAnnualFlowUsd} * 1e-9
                THEN 'MULTIPLE'
              WHEN ${t.accrualGrossAnnualFlowUsd} > 0 THEN 'ISSUANCE_NEGATIVE'
              ELSE 'PURE_PREMIUM'
            END)::discovery_premium_kind`,
    ),
    /** Only the MULTIPLE arm carries a multiple, so a stale non-NULL multiple cannot sit
     *  beside a PURE_PREMIUM verdict — permanently, since the row is immutable the moment
     *  it is wrong. */
    check(
      'rs_premium_multiple_iff_multiple',
      sql`(${t.discoveryPremiumKind} = 'MULTIPLE') = (${t.discoveryPremiumMultiple} IS NOT NULL)`,
    ),
    /** The frozen formula itself: market_cap / net_annual_flow. An identity rather than a
     *  bound, so no invented ceiling can reject a row the frozen core produced. CASE, not
     *  a bare comparison: float8 division by zero RAISES in Postgres and a CHECK is not
     *  guaranteed to short-circuit. */
    check(
      'rs_premium_multiple_is_quotient',
      sql`CASE WHEN ${t.discoveryPremiumMultiple} IS NULL THEN true ELSE
            ${t.discoveryPremiumMultiple}
              = ${t.discoveryMarketCapUsd} / ${t.accrualNetAnnualFlowUsd}
          END`,
    ),
    check(
      'rs_premium_needs_assessment',
      sql`${t.accrualAssessed} OR ${t.discoveryPremiumKind} IS NULL`,
    ),

    // -- Provenance: a figure and the story of where it came from arrive together ------
    check(
      'rs_depth_provenance_complete',
      sql`(${t.liquidityDepth2pctUsd} IS NOT NULL) = (
            ${t.liquidityDepthSource} IS NOT NULL AND ${t.liquidityDepthUrl} IS NOT NULL
            AND ${t.liquidityDepthLabel} IS NOT NULL
            AND ${t.liquidityDepthMeasuredAt} IS NOT NULL)`,
    ),
    check(
      'rs_top_pool_provenance_complete',
      sql`(${t.liquidityTopPoolTvlUsd} IS NOT NULL) = (
            ${t.liquidityTopPoolSource} IS NOT NULL AND ${t.liquidityTopPoolUrl} IS NOT NULL
            AND ${t.liquidityTopPoolLabel} IS NOT NULL
            AND ${t.liquidityTopPoolMeasuredAt} IS NOT NULL)`,
    ),
    check(
      'rs_market_cap_provenance_complete',
      sql`(${t.discoveryMarketCapUsd} IS NOT NULL) = (
            ${t.discoveryMarketCapSource} IS NOT NULL AND ${t.discoveryMarketCapUrl} IS NOT NULL
            AND ${t.discoveryMarketCapLabel} IS NOT NULL
            AND ${t.discoveryMarketCapMeasuredAt} IS NOT NULL)`,
    ),
    /** "No DEX pool" and "TVL not measured" stay different states. */
    check(
      'rs_no_dex_pool_excludes_tvl',
      sql`NOT (${t.liquidityNoDexPool} AND ${t.liquidityTopPoolTvlUsd} IS NOT NULL)`,
    ),
    check(
      'rs_tier_assigned_at_iff_tier',
      sql`(${t.liquidityTier} IS NULL) = (${t.liquidityTierAssignedAt} IS NULL)`,
    ),
    /** The tier is a human judgment about two measurements. It may not predate them: an
     *  operator who assigns 'high', then re-pulls depth that has halved, must not commit a
     *  tier contradicted by the numbers printed beside it. */
    check(
      'rs_tier_not_older_than_its_inputs',
      sql`(${t.liquidityTierAssignedAt} IS NULL
           OR ${t.liquidityDepthMeasuredAt} IS NULL
           OR ${t.liquidityTierAssignedAt} >= ${t.liquidityDepthMeasuredAt})
          AND (${t.liquidityTierAssignedAt} IS NULL
           OR ${t.liquidityTopPoolMeasuredAt} IS NULL
           OR ${t.liquidityTierAssignedAt} >= ${t.liquidityTopPoolMeasuredAt})`,
    ),

    /*
     * Section 2.1: "A failed gate ends the report — later sections stay locked." So every
     * downstream column is nullable at column level and required only when the gate PASSED.
     * A dropped project still commits: that decision is a ledger row, and the ledger needs
     * the 0-15 population to have anything to compare a pass against.
     *
     * Note what this buys and what it does not: it records the rejected population and its
     * product totals. It does NOT cure survivorship bias for the narrative or team scores,
     * because those only exist on a report whose product gate passed.
     */
    check('rs_gate_completeness', sql.raw(gateCompletenessSql((key) => t[key].name))),
  ],
)

// ---------------------------------------------------------------------------
// report_team
// ---------------------------------------------------------------------------

export const reportTeam = pgTable(
  'report_team',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /** Presentation order only — framework/06 mandates Founder, Head of Product, Head of
     *  Marketing, standouts, advisors. It is NOT an identity: inserting a newly-found
     *  co-founder at position 1 renumbers everyone. Citations key on `id`, never on this
     *  (see the citations.field note below). teamWeightedScore() is order-independent. */
    position: integer('position').notNull(),
    name: text('name').notNull(),
    /*
     * The person's identity within the report. framework/05 lets one person hold two roles,
     * and entering them twice weights that person 5+1 inside a frozen formula: a team of
     * three people listed as four rows passes both of teamWeightedScore()'s guards and
     * returns (Alice x 5 + Alice + Bob) / 7 instead of the honest "team must have 3 to 5
     * people, got 2". Whitespace and case variants slip past a naive name constraint, so
     * the key is normalised before it is uniquified.
     *
     * '[[:space:]]+', never '\s+': a drizzle sql template eats a single backslash and
     * silently emits 's+', which normalises the letter s. The POSIX class has no escape to
     * get wrong.
     */
    nameKey: text('name_key')
      .notNull()
      .generatedAlwaysAs(sql`lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')))`),
    /** An array, so one person holding two roles is one row. */
    roles: text('roles').array().notNull(),
    isFounder: boolean('is_founder').notNull(),
    h: integer('h').notNull(),
    m: integer('m').notNull(),
    l: integer('l').notNull(),
    /** Section 2.4: one sentence about PRIOR experience, carrying a financial metric.
     *  Neither half is machine-checkable; only non-emptiness is. */
    summary: text('summary').notNull(),
  },
  (t) => [
    check('rt_h_range', sql`${t.h} BETWEEN 0 AND 5`),
    check('rt_m_range', sql`${t.m} BETWEEN 0 AND 3`),
    check('rt_l_range', sql`${t.l} BETWEEN 0 AND 2`),
    check('rt_position_positive', sql`${t.position} >= 1`),
    check('rt_name_not_blank', nonBlank(t.name)),
    check('rt_roles_not_empty', sql`array_length(${t.roles}, 1) >= 1`),
    check('rt_summary_not_blank', nonBlank(t.summary)),
    uniqueIndex('rt_report_position_uniq').on(t.reportId, t.position),
    uniqueIndex('rt_report_name_key_uniq').on(t.reportId, t.nameKey),
    /** AT MOST one founder, as a database fact. "Exactly one" and "3-5 people" are
     *  cardinality ACROSS rows: teamWeightedScore() throws on both inside the commit
     *  transaction, and the rule-2 trigger then freezes the set. A row-level CHECK cannot
     *  see siblings. */
    uniqueIndex('rt_one_founder_per_report').on(t.reportId).where(sql`${t.isFounder}`),
    index('rt_report_id_idx').on(t.reportId),
  ],
)

// ---------------------------------------------------------------------------
// citations
// ---------------------------------------------------------------------------

export const citations = pgTable(
  'citations',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /*
     * The report field this citation backs, e.g. 'narrative_maturity'. Left as text: team
     * rows and accrual inputs are citable too, and a pgEnum here would need a migration for
     * every newly citable field. The vocabulary is owned by the commit gate.
     *
     * A team citation is 'team:' || report_team.id — the row's uuid, NEVER its position.
     * Position is reorderable, so keying on it silently reattaches every team citation to
     * the person's neighbour the moment a co-founder is inserted at position 1.
     */
    field: text('field').notNull(),
    url: text('url').notNull(),
    quote: text('quote').notNull(),
    status: citationStatus('status').notNull().default('unverified'),
    /*
     * What the VERIFIER last said, recorded even when the human has waived. Without it,
     * 'waived over a JS-rendered page that could not be checked' and 'waived over a quote
     * the fetch proved is not on the page' are indistinguishable at the commit gate — and
     * section 7's waiver plainly exists for the first. The commit gate refuses a waiver
     * whose last_outcome is 'failed'.
     */
    lastOutcome: citationStatus('last_outcome'),
    /** Section 8.2. NO DEFAULT on purpose: a model row must not inherit 'human' by
     *  omission, which is the one mislabel that would corrupt the selection-rate question
     *  this column exists to answer. */
    origin: citationOrigin('origin').notNull(),
    finderProvider: text('finder_provider'),
    finderModel: text('finder_model'),
    /** Section 8.2: NULL = an unselected candidate — offered, verified, not taken. The
     *  commit gate counts only selected rows, as both a blocker and a credential. */
    selectedAt: timestamp('selected_at', { withTimezone: true }),
    verifiedAt: timestamp('verified_at', { withTimezone: true }),
    httpStatus: integer('http_status'),
    matchedOffset: integer('matched_offset'),
    /** Section 7: the only escape from the gate, and it has to be recorded. */
    waiverReason: text('waiver_reason'),
    /** Not in section 4.2. Section 8.2 wants selection rate by provider answerable later;
     *  without an offered-at time a candidate has no age to measure. */
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    check('ct_field_not_blank', nonBlank(t.field)),
    check('ct_url_not_blank', nonBlank(t.url)),
    check('ct_quote_not_blank', nonBlank(t.quote)),
    check('ct_http_status_range', sql`${t.httpStatus} BETWEEN 100 AND 599`),
    check('ct_matched_offset_nonneg', sql`${t.matchedOffset} >= 0`),
    /** Section 7: "an explicit waived status with a RECORDED waiver_reason". */
    check(
      'ct_waiver_reason_iff_waived',
      sql`(${t.status} = 'waived') = (${t.waiverReason} IS NOT NULL AND length(btrim(${t.waiverReason})) > 0)`,
    ),
    /** Section 8.2: finder provenance belongs to model candidates and only to them. */
    check(
      'ct_finder_fields_iff_model',
      sql`(${t.origin} = 'model') = (${t.finderProvider} IS NOT NULL AND ${t.finderModel} IS NOT NULL)`,
    ),
    /** 'unverified' means the verifier has not run; every other state means it has.
     *  `OR status = 'waived'` is not sloppiness: a human waiving a permanently dead or
     *  paywalled URL never got a successful fetch, and the strict biconditional would force
     *  the waive route to fabricate a verified_at to satisfy a constraint. */
    check(
      'ct_verified_at_iff_resolved',
      sql`(${t.status} = 'unverified') = (${t.verifiedAt} IS NULL) OR ${t.status} = 'waived'`,
    ),
    /** last_outcome is what the machine found. 'waived' is a human decision and is never a
     *  fetch result, so it cannot appear here. */
    check('ct_last_outcome_not_waived', sql`${t.lastOutcome} <> 'waived'`),
    index('ct_report_id_idx').on(t.reportId),
    /** The commit gate's query: this report's SELECTED citations and their statuses. */
    index('ct_report_selected_idx')
      .on(t.reportId, t.status)
      .where(sql`${t.selectedAt} IS NOT NULL`),
    /** Section 8.2: "did the evidence finder actually help?" */
    index('ct_finder_idx').on(t.finderProvider, t.finderModel).where(sql`${t.origin} = 'model'`),
  ],
)

// ---------------------------------------------------------------------------
// chain_facts — Phase A.2
//
// Deliberately NOT covered by the immutability triggers, and that is an open item rather
// than a conclusion: rule 2 names four tables, chain_facts is A.2, and rows with a NULL
// report_id would be freely mutable while their siblings were frozen. Recorded in
// agents/decisions.md so the next reader does not "complete" the trigger set by accident.
// ---------------------------------------------------------------------------

export const chainFacts = pgTable(
  'chain_facts',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    coinId: uuid('coin_id')
      .notNull()
      .references(() => coins.id, { onDelete: 'restrict' }),
    /** Section 4.2 writes it `report_id?`: a fact can be pulled for a coin before any report
     *  exists. */
    reportId: uuid('report_id').references(() => reports.id, { onDelete: 'cascade' }),
    kind: chainFactKind('kind').notNull(),
    chain: text('chain').notNull(),
    /** EVERY row carries block_number and fetched_at — the framework's "verified (say where)
     *  or a guess (say so)". bigint because a block height is not a 32-bit quantity in
     *  principle; mode 'number' is exact to 2^53. */
    blockNumber: bigint('block_number', { mode: 'number' }).notNull(),
    fetchedAt: timestamp('fetched_at', { withTimezone: true }).notNull(),
    /** Rule 5: jsonb. Its shape varies by `kind`, so only the container is constrained. */
    payload: jsonb('payload').notNull(),
  },
  (t) => [
    check('cf_block_number_nonneg', sql`${t.blockNumber} >= 0`),
    check('cf_chain_not_blank', nonBlank(t.chain)),
    check('cf_payload_is_object', sql`jsonb_typeof(${t.payload}) = 'object'`),
    index('cf_coin_kind_idx').on(t.coinId, t.kind),
    index('cf_report_id_idx').on(t.reportId),
  ],
)

// ---------------------------------------------------------------------------
// forward_returns — the only table the Python `research` role may write
// ---------------------------------------------------------------------------

export const forwardReturns = pgTable(
  'forward_returns',
  {
    reportId: uuid('report_id')
      .notNull()
      .references(() => reports.id, { onDelete: 'cascade' }),
    /** Section 13: FROZEN at 30/90/180/365 days from commit date. "Retrofitting horizons
     *  onto existing commits is fine; comparing across changed horizons is not" — which is
     *  the failure this CHECK exists to make impossible. */
    horizonDays: integer('horizon_days').notNull(),
    /*
     * The two prices and where they came from. The earlier design stored only the quotient,
     * in a column called `return_pct` that held a fraction, guarded by CHECK (>= -1): that
     * catches a percentage-scaled LOSS (-12.5 fails) and passes every percentage-scaled
     * GAIN (+12.5 stores clean), so the guard worked on half the distribution and
     * research/forward_returns.py — which does not exist yet — had even odds of failing
     * silently into an unrecoverable mixed-unit ledger column.
     *
     * Storing the prices fixes the unit by construction and satisfies section 8's rule that
     * every number is verified (say where) or a guess (say so), which a bare quotient could
     * not.
     */
    priceAtCommitUsd: doublePrecision('price_at_commit_usd').notNull(),
    priceAtHorizonUsd: doublePrecision('price_at_horizon_usd').notNull(),
    priceSource: text('price_source').notNull(),
    pricedAt: timestamp('priced_at', { withTimezone: true }).notNull(),
    /** GENERATED: it cannot disagree with the prices it came from, and the research role
     *  cannot write it at all ("column can only be updated to DEFAULT"). A FRACTION —
     *  0.125 is +12.5% — and the name now says so. */
    returnFraction: doublePrecision('return_fraction')
      .notNull()
      .generatedAlwaysAs(sql`(price_at_horizon_usd / price_at_commit_usd) - 1`),
    computedAt: timestamp('computed_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.reportId, t.horizonDays] }),
    check('fr_horizon_frozen', sql`${t.horizonDays} IN (30, 90, 180, 365)`),
    /** Strictly positive: it is the divisor. */
    check(
      'fr_commit_price_positive',
      sql`${t.priceAtCommitUsd} > 0 AND ${t.priceAtCommitUsd} < 'Infinity'::float8`,
    ),
    check('fr_horizon_price_nonneg', nonNegativeFinite(t.priceAtHorizonUsd)),
    check('fr_price_source_not_blank', nonBlank(t.priceSource)),
  ],
)

// ---------------------------------------------------------------------------
// Row types. The commit path, the gate and the routes all import from here, so a renamed
// column is a compile error rather than a runtime surprise.
// ---------------------------------------------------------------------------

export type CoinRow = typeof coins.$inferSelect
export type ReportRow = typeof reports.$inferSelect
export type ReportScoresRow = typeof reportScores.$inferSelect
export type ReportTeamRow = typeof reportTeam.$inferSelect
export type CitationRow = typeof citations.$inferSelect
export type ChainFactRow = typeof chainFacts.$inferSelect
export type ForwardReturnRow = typeof forwardReturns.$inferSelect

export type NewCoin = typeof coins.$inferInsert
export type NewReport = typeof reports.$inferInsert
export type NewReportTeam = typeof reportTeam.$inferInsert
export type NewCitation = typeof citations.$inferInsert
export type NewChainFact = typeof chainFacts.$inferInsert
export type NewForwardReturn = typeof forwardReturns.$inferInsert
