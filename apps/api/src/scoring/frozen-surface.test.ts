import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './product.ts'
import { SCORING_VERSION } from './ranges.ts'

/**
 * Rule 3's mechanism, not just its intention.
 *
 * The ledger groups by scoring_version, so two framework revisions silently sharing one
 * label corrupts a comparison rather than a row — which is worse, because it survives every
 * integrity check in the schema and cannot be repaired afterwards: committed rows are
 * immutable by construction.
 *
 * This is a table of frozen VALUES rather than a hash of scoring/, on purpose. A hash would
 * fail on a comment reflow and split the ledger for nothing.
 */
const FROZEN_SURFACE = {
  productGateThreshold: 16,
  productSubScoreMax: 10,
  narrativeMaturityMax: 7,
  narrativeSmartMoneyMax: 6,
  narrativeHairFireMax: 6,
  narrativeCommunicationMax: 5,
  narrativeLineageMax: 4,
  narrativeMutationMax: 3,
  narrativeTotalMax: 31,
  teamHMax: 5,
  teamMMax: 3,
  teamLMax: 2,
  teamFounderWeight: 5,
  teamMinPeople: 3,
  teamMaxPeople: 5,
  forwardReturnHorizons: [30, 90, 180, 365],
} as const

describe('the frozen surface', () => {
  it('has not moved since SCORING_VERSION was last set', () => {
    // If this fails, a frozen number changed. Bump SCORING_VERSION in the SAME commit, or
    // revert the number. Do not update this literal on its own.
    expect({
      productGateThreshold: PRODUCT_GATE_THRESHOLD,
      narrativeMaturityMax: NARRATIVE_MAX.maturity,
      narrativeSmartMoneyMax: NARRATIVE_MAX.smartMoney,
      narrativeHairFireMax: NARRATIVE_MAX.hairFire,
      narrativeCommunicationMax: NARRATIVE_MAX.communication,
      narrativeLineageMax: NARRATIVE_MAX.lineage,
      narrativeMutationMax: NARRATIVE_MAX.mutation,
      narrativeTotalMax: NARRATIVE_TOTAL_MAX,
    }).toEqual({
      productGateThreshold: FROZEN_SURFACE.productGateThreshold,
      narrativeMaturityMax: FROZEN_SURFACE.narrativeMaturityMax,
      narrativeSmartMoneyMax: FROZEN_SURFACE.narrativeSmartMoneyMax,
      narrativeHairFireMax: FROZEN_SURFACE.narrativeHairFireMax,
      narrativeCommunicationMax: FROZEN_SURFACE.narrativeCommunicationMax,
      narrativeLineageMax: FROZEN_SURFACE.narrativeLineageMax,
      narrativeMutationMax: FROZEN_SURFACE.narrativeMutationMax,
      narrativeTotalMax: FROZEN_SURFACE.narrativeTotalMax,
    })
  })

  it('names a version the ledger can group by', () => {
    expect(SCORING_VERSION).toBe('coinpicks-2026-09-21')
  })
})

describe('the DDL reproduces the same numbers', () => {
  const ddl = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle/0000_init.sql'),
    'utf8',
  )

  const NARRATIVE_COLUMNS: Record<keyof typeof NARRATIVE_MAX, string> = {
    maturity: 'narrative_maturity',
    smartMoney: 'narrative_smart_money',
    hairFire: 'narrative_hair_fire',
    communication: 'narrative_communication',
    lineage: 'narrative_lineage',
    mutation: 'narrative_mutation',
  }

  it('bounds every narrative sub-score at its frozen maximum', () => {
    for (const key of Object.keys(NARRATIVE_MAX) as (keyof typeof NARRATIVE_MAX)[]) {
      const expected = `"report_scores"."${NARRATIVE_COLUMNS[key]}" BETWEEN 0 AND ${NARRATIVE_MAX[key]}`
      expect(ddl, `missing CHECK: ${expected}`).toContain(expected)
    }
  })

  it('bounds every product sub-score at 0..10 and gates at the frozen threshold', () => {
    for (const column of ['product_ease', 'product_hair_fire', 'product_exclusivity']) {
      expect(ddl).toContain(
        `"report_scores"."${column}" BETWEEN 0 AND ${FROZEN_SURFACE.productSubScoreMax}`,
      )
    }
    expect(ddl).toContain(
      `"report_scores"."product_passed" = ("report_scores"."product_total" >= ${PRODUCT_GATE_THRESHOLD})`,
    )
  })

  it('bounds the three team rungs at H 0..5, M 0..3, L 0..2', () => {
    expect(ddl).toContain(`"report_team"."h" BETWEEN 0 AND ${FROZEN_SURFACE.teamHMax}`)
    expect(ddl).toContain(`"report_team"."m" BETWEEN 0 AND ${FROZEN_SURFACE.teamMMax}`)
    expect(ddl).toContain(`"report_team"."l" BETWEEN 0 AND ${FROZEN_SURFACE.teamLMax}`)
  })

  it('freezes the four forward-return horizons', () => {
    expect(ddl).toContain(
      `"forward_returns"."horizon_days" IN (${FROZEN_SURFACE.forwardReturnHorizons.join(', ')})`,
    )
  })
})
