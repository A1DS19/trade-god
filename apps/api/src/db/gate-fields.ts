/*
 * THE ONE required-field list.
 *
 * `rs_gate_completeness` and the editor's blocker list are both generated from this array.
 * Ruled 2026-09-21, because an adversary confirmed the CHECK is INERT on a draft: it is
 * `CASE WHEN product_passed THEN ... ELSE true END` and `product_passed` is only written at
 * commit, so `SELECT CASE WHEN NULL::boolean THEN false ELSE true END` returns `t`. Nothing in
 * the database refuses an incomplete draft. A hand-written blocker list could therefore tell the
 * operator they are ready while the database would refuse them, and a conjunct the list forgot
 * would render as nothing at all under the heading "what blocks the commit".
 *
 * So: one array, two consumers, and `gate-fields.test.ts` asserts the committed .sql still
 * reproduces the string this file generates.
 *
 * Column NAMES are not written here. `gateCompletenessSql` takes a resolver and `schema.ts`
 * passes `(key) => t[key].name`, so the snake_case spelling always comes from the drizzle column
 * itself. The naive version hand-wrote them, and a regex derivation of the same thing produced
 * `liquidity_depth2pct_usd` for `liquidity_depth_2pct_usd` — a key nothing reads.
 */

export type GateSection =
  | 'product'
  | 'liquidity'
  | 'narrative'
  | 'team'
  | 'accrual'
  | 'risk'
  | 'commit'

/**
 * The columns a requirement may read. Structurally a subset of `ReportScoresRow`; the
 * assignability is asserted in `gate-fields.test.ts`, so a renamed or retyped column is a
 * compile error here rather than a silently false blocker.
 */
export interface GateScoresRow {
  overviewSentence: string | null
  productEase: number | null
  productHairFire: number | null
  productExclusivity: number | null
  productPassed: boolean | null
  productEaseRationale: string | null
  productHairFireRationale: string | null
  productExclusivityRationale: string | null
  liquidityTier: 'low' | 'medium' | 'high' | null
  liquidityJustification: string | null
  liquidityDepth2pctUsd: number | null
  liquidityTopPoolTvlUsd: number | null
  liquidityNoDexPool: boolean
  narrativeMaturity: number | null
  narrativeSmartMoney: number | null
  narrativeHairFire: number | null
  narrativeCommunication: number | null
  narrativeLineage: number | null
  narrativeMutation: number | null
  narrativeTotal: number | null
  narrativeMaturityRationale: string | null
  narrativeSmartMoneyRationale: string | null
  narrativeHairFireRationale: string | null
  narrativeCommunicationRationale: string | null
  narrativeLineageRationale: string | null
  narrativeMutationRationale: string | null
  teamWeightedScore: number | null
  accrualAssessed: boolean
  accrualAbsentReason: string | null
  accrualRationale: string | null
  accrualGrossAnnualFlowUsd: number | null
  accrualNetAnnualFlowUsd: number | null
  discoveryMarketCapUsd: number | null
  discoveryPremiumKind: 'MULTIPLE' | 'ISSUANCE_NEGATIVE' | 'PURE_PREMIUM' | null
  riskNotes: string | null
  waivedCitationCount: number | null
}

export type GateColumnKey = keyof GateScoresRow

/** Resolves a camelCase key to the column's real snake_case name. */
export type ColumnName = (key: GateColumnKey) => string

export interface GateRequirement {
  /** The blocker code the editor renders and step 6 will reuse. */
  readonly code: string
  readonly section: GateSection
  /**
   * `operator` — the editor writes it, so its state is known now.
   * `commit` — build-order step 6 writes it, so the editor renders it `unknown`, never a tick.
   */
  readonly writtenBy: 'operator' | 'commit'
  readonly message: string
  /** One conjunct of `rs_gate_completeness`. */
  readonly sql: (name: ColumnName) => string
  readonly satisfied: (row: GateScoresRow) => boolean
}

const q = (name: ColumnName, key: GateColumnKey): string => `"report_scores"."${name(key)}"`

const isProse = (value: unknown): boolean => typeof value === 'string' && value.trim() !== ''

/** Prose that must actually exist — `present()` in schema.ts, `length(btrim(coalesce(...)))`. */
function prose(
  code: string,
  section: GateSection,
  key: GateColumnKey,
  message: string,
): GateRequirement {
  return {
    code,
    section,
    writtenBy: 'operator',
    message,
    sql: (name) => `length(btrim(coalesce(${q(name, key)}, ''))) > 0`,
    satisfied: (row) => isProse(row[key]),
  }
}

/** A value that must be present. */
function value(
  code: string,
  section: GateSection,
  writtenBy: 'operator' | 'commit',
  key: GateColumnKey,
  message: string,
): GateRequirement {
  return {
    code,
    section,
    writtenBy,
    message,
    sql: (name) => `${q(name, key)} IS NOT NULL`,
    satisfied: (row) => row[key] !== null,
  }
}

/**
 * Every conjunct of `rs_gate_completeness`, in DDL order.
 *
 * The accrual CASE is expanded into five independent conjuncts. `CASE WHEN a THEN b AND c ELSE d
 * END` is `(a OR d) AND (NOT a OR b) AND (NOT a OR c)`, which is the same constraint with one
 * blocker code per line instead of one code for five different absences.
 */
export const GATE_REQUIREMENTS: readonly GateRequirement[] = [
  prose('OVERVIEW_SENTENCE', 'product', 'overviewSentence', 'the one-sentence overview is empty'),
  // The three sub-scores are NOT in the hand-written constraint this replaces, and that was a
  // hole: rs_product_total_is_sum reads `product_total = ease + hair_fire + exclusivity`, and
  // with any of them NULL the comparison is NULL, which a CHECK accepts. Verified on 16.13.
  value('PRODUCT_EASE', 'product', 'operator', 'productEase', 'Ease of Use is not scored'),
  value(
    'PRODUCT_HAIR_FIRE',
    'product',
    'operator',
    'productHairFire',
    'Hair-on-Fire (the gate field, 0-10) is not scored',
  ),
  value(
    'PRODUCT_EXCLUSIVITY',
    'product',
    'operator',
    'productExclusivity',
    'Exclusivity Factor is not scored',
  ),
  prose(
    'PRODUCT_EASE_RATIONALE',
    'product',
    'productEaseRationale',
    'Ease of Use has no rationale',
  ),
  prose(
    'PRODUCT_HAIR_FIRE_RATIONALE',
    'product',
    'productHairFireRationale',
    'Hair-on-Fire has no rationale',
  ),
  prose(
    'PRODUCT_EXCLUSIVITY_RATIONALE',
    'product',
    'productExclusivityRationale',
    'Exclusivity Factor has no rationale',
  ),
  value(
    'LIQUIDITY_TIER',
    'liquidity',
    'operator',
    'liquidityTier',
    'no liquidity tier has been assigned',
  ),
  prose(
    'LIQUIDITY_JUSTIFICATION',
    'liquidity',
    'liquidityJustification',
    'the liquidity tier has no justification',
  ),
  value(
    'LIQUIDITY_DEPTH',
    'liquidity',
    'operator',
    'liquidityDepth2pctUsd',
    'the +/-2% depth figure is missing',
  ),
  {
    code: 'LIQUIDITY_TOP_POOL',
    section: 'liquidity',
    writtenBy: 'operator',
    message: 'the largest DEX pool TVL is missing, and "no DEX pool exists" is not ticked',
    sql: (name) =>
      `(${q(name, 'liquidityTopPoolTvlUsd')} IS NOT NULL OR ${q(name, 'liquidityNoDexPool')})`,
    satisfied: (row) => row.liquidityTopPoolTvlUsd !== null || row.liquidityNoDexPool,
  },
  value(
    'NARRATIVE_MATURITY',
    'narrative',
    'operator',
    'narrativeMaturity',
    'Narrative Maturity is not scored',
  ),
  value(
    'NARRATIVE_SMART_MONEY',
    'narrative',
    'operator',
    'narrativeSmartMoney',
    'Smart Money Compatibility is not scored',
  ),
  value(
    'NARRATIVE_HAIR_FIRE',
    'narrative',
    'operator',
    'narrativeHairFire',
    'Hair-on-Fire Innovation (the narrative field, 0-6) is not scored',
  ),
  value(
    'NARRATIVE_COMMUNICATION',
    'narrative',
    'operator',
    'narrativeCommunication',
    'Narrative Communication is not scored',
  ),
  value(
    'NARRATIVE_LINEAGE',
    'narrative',
    'operator',
    'narrativeLineage',
    'Narrative Lineage is not scored',
  ),
  value(
    'NARRATIVE_MUTATION',
    'narrative',
    'operator',
    'narrativeMutation',
    'Narrative Mutation is not scored',
  ),
  value(
    'NARRATIVE_TOTAL',
    'narrative',
    'commit',
    'narrativeTotal',
    'the narrative total is written by the commit route from narrativeTotal()',
  ),
  prose(
    'NARRATIVE_MATURITY_RATIONALE',
    'narrative',
    'narrativeMaturityRationale',
    'Narrative Maturity has no rationale',
  ),
  prose(
    'NARRATIVE_SMART_MONEY_RATIONALE',
    'narrative',
    'narrativeSmartMoneyRationale',
    'Smart Money Compatibility has no rationale',
  ),
  prose(
    'NARRATIVE_HAIR_FIRE_RATIONALE',
    'narrative',
    'narrativeHairFireRationale',
    'Hair-on-Fire Innovation has no rationale',
  ),
  prose(
    'NARRATIVE_COMMUNICATION_RATIONALE',
    'narrative',
    'narrativeCommunicationRationale',
    'Narrative Communication has no rationale',
  ),
  prose(
    'NARRATIVE_LINEAGE_RATIONALE',
    'narrative',
    'narrativeLineageRationale',
    'Narrative Lineage has no rationale',
  ),
  prose(
    'NARRATIVE_MUTATION_RATIONALE',
    'narrative',
    'narrativeMutationRationale',
    'Narrative Mutation has no rationale',
  ),
  value(
    'TEAM_WEIGHTED_SCORE',
    'team',
    'commit',
    'teamWeightedScore',
    'the team weighted score is written by the commit route from teamWeightedScore()',
  ),
  {
    code: 'ACCRUAL_ABSENT_REASON',
    section: 'accrual',
    writtenBy: 'operator',
    message:
      'the four accrual inputs are not all filled, so the report must say why no accrual figure exists',
    sql: (name) =>
      `(${q(name, 'accrualAssessed')} OR length(btrim(coalesce(${q(name, 'accrualAbsentReason')}, ''))) > 0)`,
    satisfied: (row) => row.accrualAssessed || isProse(row.accrualAbsentReason),
  },
  prose(
    'ACCRUAL_RATIONALE',
    'accrual',
    'accrualRationale',
    'the accrual section has no rationale naming the mechanism',
  ),
  {
    code: 'ACCRUAL_GROSS_FLOW',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'gross annual holder flow is written by the commit route from annualHolderFlow()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'accrualGrossAnnualFlowUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.accrualGrossAnnualFlowUsd !== null,
  },
  {
    code: 'ACCRUAL_NET_FLOW',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'net annual holder flow is written by the commit route from annualHolderFlow()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'accrualNetAnnualFlowUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.accrualNetAnnualFlowUsd !== null,
  },
  {
    code: 'DISCOVERY_MARKET_CAP',
    section: 'accrual',
    writtenBy: 'operator',
    message: 'the accrual section is assessed, so it needs a market cap with its provenance',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'discoveryMarketCapUsd')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.discoveryMarketCapUsd !== null,
  },
  {
    code: 'DISCOVERY_PREMIUM_KIND',
    section: 'accrual',
    writtenBy: 'commit',
    message: 'the discovery premium verdict is written by the commit route from discoveryPremium()',
    sql: (name) =>
      `(NOT ${q(name, 'accrualAssessed')} OR ${q(name, 'discoveryPremiumKind')} IS NOT NULL)`,
    satisfied: (row) => !row.accrualAssessed || row.discoveryPremiumKind !== null,
  },
  prose('RISK_NOTES', 'risk', 'riskNotes', 'the risk notes are empty'),
  value(
    'WAIVED_CITATION_COUNT',
    'commit',
    'commit',
    'waivedCitationCount',
    'the waived-citation count is written by the commit route',
  ),
]

/**
 * `rs_gate_completeness`, generated. One line on purpose: the string is compared byte-for-byte
 * against the committed .sql by gate-fields.test.ts, and a newline is one more thing a generator
 * or a formatter can reflow.
 */
export function gateCompletenessSql(name: ColumnName): string {
  const conjuncts = GATE_REQUIREMENTS.map((requirement) => requirement.sql(name)).join(' AND ')
  return `CASE WHEN ${q(name, 'productPassed')} THEN ${conjuncts} ELSE true END`
}
