import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  PRODUCT_SUB_SCORE_MAX,
  TEAM_MAX_PEOPLE,
  TEAM_MIN_PEOPLE,
  TEAM_RUNG_MAX,
} from '../reports/bounds.ts'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './product.ts'
import { SCORING_VERSION } from './ranges.ts'
import { teamWeightedScore } from './team.ts'

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

/*
 * `reports/bounds.ts` restates four numbers that product.ts and team.ts hold as inline literals.
 * Exporting them from the frozen modules would edit two frozen files to avoid a copy; pinning
 * them here costs nothing and pins them to the DDL and to the functions' own behaviour instead.
 *
 * It also gives teamFounderWeight / teamMinPeople / teamMaxPeople something to compare against.
 * Before this block they sat in the FROZEN_SURFACE table above, compared with nothing at all —
 * a literal in a test table that nothing asserts is the failure this project keeps finding.
 */
describe('the write path reproduces the bounds the frozen code holds inline', () => {
  const ddl = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle/0000_init.sql'),
    'utf8',
  )

  it('matches the frozen surface table', () => {
    expect({
      productSubScoreMax: PRODUCT_SUB_SCORE_MAX,
      teamHMax: TEAM_RUNG_MAX.h,
      teamMMax: TEAM_RUNG_MAX.m,
      teamLMax: TEAM_RUNG_MAX.l,
      teamMinPeople: TEAM_MIN_PEOPLE,
      teamMaxPeople: TEAM_MAX_PEOPLE,
    }).toEqual({
      productSubScoreMax: FROZEN_SURFACE.productSubScoreMax,
      teamHMax: FROZEN_SURFACE.teamHMax,
      teamMMax: FROZEN_SURFACE.teamMMax,
      teamLMax: FROZEN_SURFACE.teamLMax,
      teamMinPeople: FROZEN_SURFACE.teamMinPeople,
      teamMaxPeople: FROZEN_SURFACE.teamMaxPeople,
    })
  })

  it('matches the DDL', () => {
    for (const column of ['product_ease', 'product_hair_fire', 'product_exclusivity']) {
      expect(ddl).toContain(`"report_scores"."${column}" BETWEEN 0 AND ${PRODUCT_SUB_SCORE_MAX}`)
    }
    expect(ddl).toContain(`"report_team"."h" BETWEEN 0 AND ${TEAM_RUNG_MAX.h}`)
    expect(ddl).toContain(`"report_team"."m" BETWEEN 0 AND ${TEAM_RUNG_MAX.m}`)
    expect(ddl).toContain(`"report_team"."l" BETWEEN 0 AND ${TEAM_RUNG_MAX.l}`)
  })

  it("matches teamWeightedScore()'s own refusals", () => {
    const person = (isFounder: boolean) => ({ name: 'x', isFounder, h: 1, m: 1, l: 1 })
    const below = Array.from({ length: TEAM_MIN_PEOPLE - 1 }, () => person(false))
    const above = Array.from({ length: TEAM_MAX_PEOPLE + 1 }, () => person(false))
    expect(() => teamWeightedScore(below)).toThrow(
      `team must have ${TEAM_MIN_PEOPLE} to ${TEAM_MAX_PEOPLE} people, got ${below.length}`,
    )
    expect(() => teamWeightedScore(above)).toThrow(
      `team must have ${TEAM_MIN_PEOPLE} to ${TEAM_MAX_PEOPLE} people, got ${above.length}`,
    )
  })

  it('weights the founder by teamFounderWeight, measured against the function', () => {
    // Everyone but the founder scores zero, so the result is (founder x W) / (W + others) and
    // nothing else -- which pins team.ts's inline `* 5` AND the table's literal at once.
    // `expect(FROZEN_SURFACE.teamFounderWeight).toBe(5)` would be a literal compared to a
    // literal: it cannot fail however team.ts is edited, which is the failure this whole block
    // exists to stop. The framework's 7.25 worked example is already pinned, verbatim, by
    // scoring/team.test.ts.
    const weight = FROZEN_SURFACE.teamFounderWeight
    const founderScore = TEAM_RUNG_MAX.h + TEAM_RUNG_MAX.m + TEAM_RUNG_MAX.l
    const others = TEAM_MIN_PEOPLE - 1
    const team = [
      {
        name: 'founder',
        isFounder: true,
        h: TEAM_RUNG_MAX.h,
        m: TEAM_RUNG_MAX.m,
        l: TEAM_RUNG_MAX.l,
      },
      ...Array.from({ length: others }, (_, index) => ({
        name: `other-${String(index)}`,
        isFounder: false,
        h: 0,
        m: 0,
        l: 0,
      })),
    ]
    expect(teamWeightedScore(team)).toBeCloseTo((founderScore * weight) / (weight + others), 10)
  })
})
