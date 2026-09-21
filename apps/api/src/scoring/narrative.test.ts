import { describe, expect, it } from 'vitest'
import { NARRATIVE_TOTAL_MAX, narrativeTotal } from './narrative'
import { ScoreRangeError } from './ranges'

const FULL = { maturity: 7, smartMoney: 6, hairFire: 6, communication: 5, lineage: 4, mutation: 3 }

describe('narrativeTotal', () => {
  it('maxes at 31', () => {
    expect(narrativeTotal(FULL)).toBe(31)
    expect(NARRATIVE_TOTAL_MAX).toBe(31)
  })

  it('reproduces the framework ARB worked example: 3+6+6+4.5+4+3 = 26.5', () => {
    expect(
      narrativeTotal({
        maturity: 3,
        smartMoney: 6,
        hairFire: 6,
        communication: 4.5,
        lineage: 4,
        mutation: 3,
      }),
    ).toBe(26.5)
  })

  it('rejects a sub-score above its own maximum', () => {
    expect(() => narrativeTotal({ ...FULL, mutation: 4 })).toThrow(ScoreRangeError)
    expect(() => narrativeTotal({ ...FULL, lineage: 5 })).toThrow(ScoreRangeError)
  })

  it('names the offending sub-score', () => {
    try {
      narrativeTotal({ ...FULL, mutation: 4 })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect((e as ScoreRangeError).field).toBe('mutation')
    }
  })
})
