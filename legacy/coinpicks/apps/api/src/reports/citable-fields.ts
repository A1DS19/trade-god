import { reportScores } from '../db/schema.ts'

/*
 * The `citations.field` vocabulary, READ OFF THE DRIZZLE COLUMNS.
 *
 * The naive version derived it in the browser with
 * `field.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase())`. That yields
 * `liquidity_depth2pct_usd` for a column actually named `liquidity_depth_2pct_usd` — digits get
 * no separator — so depth citations filed and re-read consistently by the UI would be counted as
 * zero by a commit gate querying real column names. `citations.field` is plain text with no FK
 * and no enum, so nothing else would have caught it.
 *
 * `reportScores.productEase.name` is the column's own spelling. A rename moves both sides at
 * once; a deletion is a compile error here.
 */
export const CITABLE_FIELDS = {
  productEase: reportScores.productEase.name,
  productHairFire: reportScores.productHairFire.name,
  productExclusivity: reportScores.productExclusivity.name,
  liquidityDepth2pctUsd: reportScores.liquidityDepth2pctUsd.name,
  liquidityTopPoolTvlUsd: reportScores.liquidityTopPoolTvlUsd.name,
  narrativeMaturity: reportScores.narrativeMaturity.name,
  narrativeSmartMoney: reportScores.narrativeSmartMoney.name,
  narrativeHairFire: reportScores.narrativeHairFire.name,
  narrativeCommunication: reportScores.narrativeCommunication.name,
  narrativeLineage: reportScores.narrativeLineage.name,
  narrativeMutation: reportScores.narrativeMutation.name,
  accrualSegmentRevenueUsd: reportScores.accrualSegmentRevenueUsd.name,
  accrualCaptureShare: reportScores.accrualCaptureShare.name,
  accrualPct: reportScores.accrualPct.name,
  accrualAnnualIssuanceUsd: reportScores.accrualAnnualIssuanceUsd.name,
  discoveryMarketCapUsd: reportScores.discoveryMarketCapUsd.name,
} as const

/** A team citation is `'team:' || report_team.id` — the uuid, never the position. It reaches
 *  the browser in `bounds.teamFieldPrefix`; apps/web never writes the literal, which is the
 *  same rule that closed the `liquidity_depth2pct_usd` finding one column over. */
export const TEAM_FIELD_PREFIX = 'team:'

const SCORE_FIELDS: ReadonlySet<string> = new Set(Object.values(CITABLE_FIELDS))

/** The uuid a `team:<uuid>` field names, or null when this is not a team field. */
export function teamMemberIdOf(field: string): string | null {
  if (!field.startsWith(TEAM_FIELD_PREFIX)) return null
  return field.slice(TEAM_FIELD_PREFIX.length)
}

/** True for a `report_scores` column in the vocabulary. */
export function isScoreField(field: string): boolean {
  return SCORE_FIELDS.has(field)
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/**
 * True for a field name this editor is allowed to write.
 *
 * A `team:<uuid>` field passes the SPELLING check here and is then checked for EXISTENCE inside
 * the citation transaction. Both halves are needed: an id that is not a uuid at all would reach
 * Postgres as `22P02 invalid input syntax for type uuid` — a 500 on a typo — and an id that is a
 * uuid but names nobody would attach evidence to a person the report does not have.
 */
export function isCitableField(field: string): boolean {
  if (isScoreField(field)) return true
  const memberId = teamMemberIdOf(field)
  return memberId !== null && UUID.test(memberId)
}
