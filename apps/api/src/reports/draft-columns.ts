import type { ReportScoresRow } from '../db/schema.ts'

/*
 * Which of `report_scores`' 62 columns the EDITOR may write.
 *
 * `draft-columns.test.ts` reads the real column list off the drizzle table and asserts these four
 * arrays partition it exactly, so a column added to schema.ts with no home fails the suite. A
 * column nobody classified is a column nobody decided about, and the write path would have
 * defaulted it into "the editor can set this".
 */

/** The operator types these, through the six section routes. */
export const DRAFT_COLUMNS = [
  'overviewSentence',
  'productEase',
  'productHairFire',
  'productExclusivity',
  'productEaseRationale',
  'productHairFireRationale',
  'productExclusivityRationale',
  'liquidityTier',
  'liquidityTierAssignedAt',
  'liquidityJustification',
  'liquidityDepth2pctUsd',
  'liquidityDepthSource',
  'liquidityDepthUrl',
  'liquidityDepthLabel',
  'liquidityDepthMeasuredAt',
  'liquidityTopPoolTvlUsd',
  'liquidityTopPoolSource',
  'liquidityTopPoolUrl',
  'liquidityTopPoolLabel',
  'liquidityTopPoolMeasuredAt',
  'liquidityNoDexPool',
  'narrativeMaturity',
  'narrativeSmartMoney',
  'narrativeHairFire',
  'narrativeCommunication',
  'narrativeLineage',
  'narrativeMutation',
  'narrativeMaturityRationale',
  'narrativeSmartMoneyRationale',
  'narrativeHairFireRationale',
  'narrativeCommunicationRationale',
  'narrativeLineageRationale',
  'narrativeMutationRationale',
  'accrualSegmentRevenueUsd',
  'accrualCaptureShare',
  'accrualPct',
  'accrualAnnualIssuanceUsd',
  'accrualAbsentReason',
  'accrualRationale',
  'accrualFinding',
  'discoveryMarketCapUsd',
  'discoveryMarketCapSource',
  'discoveryMarketCapUrl',
  'discoveryMarketCapLabel',
  'discoveryMarketCapMeasuredAt',
  'riskNotes',
] as const

/** Written only inside the commit transaction (build-order step 6), from the frozen functions. */
export const DERIVED_COLUMNS = [
  'scoringVersion',
  'productTotal',
  'productPassed',
  'narrativeTotal',
  'teamWeightedScore',
  'accrualGrossAnnualFlowUsd',
  'accrualNetAnnualFlowUsd',
  'accrualZeroFactor',
  'discoveryPremiumKind',
  'discoveryPremiumMultiple',
  'waivedCitationCount',
] as const

/** The viem chain layer's columns. */
export const PHASE_A2_COLUMNS = [
  'liquiditySurvivingPools',
  'accrualContractAddress',
  'accrualMeasuredTrailing90dUsd',
] as const

/** The primary key, and the one GENERATED ALWAYS column — Postgres refuses a write with 428C9. */
export const UNWRITABLE_COLUMNS = ['reportId', 'accrualAssessed'] as const

export type DraftColumn = (typeof DRAFT_COLUMNS)[number]

/** What a section route is allowed to hand `saveSection`. Derived columns are not in the type. */
export type ScoresPatch = Partial<Pick<ReportScoresRow, DraftColumn>>
