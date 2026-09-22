import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { getTableColumns } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { evaluateBlockers } from '../reports/blockers.ts'
import { GATE_REQUIREMENTS, type GateScoresRow, gateCompletenessSql } from './gate-fields.ts'
import { type ReportScoresRow, reportScores } from './schema.ts'

/*
 * ONE LIST, TWO CONSUMERS, AND A TEST THAT THEY STILL AGREE.
 *
 * `rs_gate_completeness` is generated from GATE_REQUIREMENTS and so is the blocker list, but the
 * migration is a committed artifact: someone can edit the array and forget `drizzle-kit
 * generate`, and then the editor's list and the database's constraint disagree while both look
 * authored. This is the same technique frozen-surface.test.ts uses on the frozen numbers.
 */

const DRIZZLE = resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle')

const migrations = readdirSync(DRIZZLE)
  .filter((entry) => entry.endsWith('.sql'))
  .sort()
  .map((entry) => readFileSync(resolve(DRIZZLE, entry), 'utf8'))
  .join('\n')

const generated = gateCompletenessSql((key) => reportScores[key].name)

describe('the generated gate constraint', () => {
  it('appears verbatim in the committed migrations', () => {
    expect(
      migrations,
      'GATE_REQUIREMENTS changed and no migration was generated for it. Run\n' +
        '  cd apps/api && pnpm exec drizzle-kit generate --name <what_changed>\n' +
        'and commit the new .sql, its snapshot and the journal entry.',
    ).toContain(generated)
  })

  it('names only real report_scores columns', () => {
    const real = new Set(Object.values(getTableColumns(reportScores)).map((column) => column.name))
    const named = [...generated.matchAll(/"report_scores"\."([a-z0-9_]+)"/g)].map(
      (match) => match[1] as string,
    )
    expect(named.length).toBeGreaterThan(30)
    expect(named.filter((name) => !real.has(name))).toEqual([])
  })

  it('gives every requirement a unique blocker code', () => {
    const codes = GATE_REQUIREMENTS.map((requirement) => requirement.code)
    expect(new Set(codes).size).toBe(codes.length)
  })

  it('requires the three product sub-scores, which the hand-written version did not', () => {
    // `product_total = ease + hair_fire + exclusivity` is NULL when any of them is NULL, and a
    // CHECK accepts NULL. Confirmed on 16.13: the old constraint took (NULL, 5, 5, total 16).
    for (const code of ['PRODUCT_EASE', 'PRODUCT_HAIR_FIRE', 'PRODUCT_EXCLUSIVITY']) {
      expect(GATE_REQUIREMENTS.map((requirement) => requirement.code)).toContain(code)
    }
  })
})

/**
 * The structural pin. `GateScoresRow` is a hand-declared subset of the real row so that
 * `gate-fields.ts` can stay free of a schema import; this is what makes a renamed or retyped
 * column a compile error rather than a blocker that silently reads `undefined !== null`.
 */
const STRUCTURAL_PIN = (row: ReportScoresRow): GateScoresRow => row

describe('the blocker list', () => {
  const empty: GateScoresRow = {
    overviewSentence: null,
    productEase: null,
    productHairFire: null,
    productExclusivity: null,
    productPassed: null,
    productEaseRationale: null,
    productHairFireRationale: null,
    productExclusivityRationale: null,
    liquidityTier: null,
    liquidityJustification: null,
    liquidityDepth2pctUsd: null,
    liquidityTopPoolTvlUsd: null,
    liquidityNoDexPool: false,
    narrativeMaturity: null,
    narrativeSmartMoney: null,
    narrativeHairFire: null,
    narrativeCommunication: null,
    narrativeLineage: null,
    narrativeMutation: null,
    narrativeTotal: null,
    narrativeMaturityRationale: null,
    narrativeSmartMoneyRationale: null,
    narrativeHairFireRationale: null,
    narrativeCommunicationRationale: null,
    narrativeLineageRationale: null,
    narrativeMutationRationale: null,
    teamWeightedScore: null,
    accrualAssessed: false,
    accrualAbsentReason: null,
    accrualRationale: null,
    accrualGrossAnnualFlowUsd: null,
    accrualNetAnnualFlowUsd: null,
    discoveryMarketCapUsd: null,
    discoveryPremiumKind: null,
    riskNotes: null,
    waivedCitationCount: null,
  }

  it('accepts the real row type', () => {
    expect(typeof STRUCTURAL_PIN).toBe('function')
  })

  it('has one row per conjunct', () => {
    expect(evaluateBlockers(empty)).toHaveLength(GATE_REQUIREMENTS.length)
  })

  it('never marks a commit-written column clear', () => {
    const commitRows = evaluateBlockers(empty).filter(
      (blocker) => blocker.state === 'unknown' && blocker.implementedInStep === 6,
    )
    expect(commitRows.map((blocker) => blocker.code)).toEqual([
      'NARRATIVE_TOTAL',
      'TEAM_WEIGHTED_SCORE',
      'ACCRUAL_GROSS_FLOW',
      'ACCRUAL_NET_FLOW',
      'DISCOVERY_PREMIUM_KIND',
      'WAIVED_CITATION_COUNT',
    ])
  })

  it('counts a blank string as missing, not as present', () => {
    const blanks = evaluateBlockers({ ...empty, riskNotes: '   ', overviewSentence: '' })
    const codes = blanks.filter((blocker) => blocker.state === 'blocking').map((b) => b.code)
    expect(codes).toContain('RISK_NOTES')
    expect(codes).toContain('OVERVIEW_SENTENCE')
  })

  it('clears the top-pool row when no DEX pool exists', () => {
    const ticked = evaluateBlockers({ ...empty, liquidityNoDexPool: true })
    const row = ticked.find((blocker) => blocker.code === 'LIQUIDITY_TOP_POOL')
    expect(row?.state).toBe('clear')
  })
})
