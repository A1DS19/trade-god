import { describe, expect, it } from 'vitest'
import { NARRATIVE_TOTAL_MAX, narrativeTotal } from './narrative.ts'
import { ScoreRangeError } from './ranges.ts'

const FULL = { maturity: 7, smartMoney: 6, hairFire: 6, communication: 5, lineage: 4, mutation: 3 }

describe('narrativeTotal', () => {
  it('maxes at 31', () => {
    expect(narrativeTotal(FULL)).toBe(31)
    expect(NARRATIVE_TOTAL_MAX).toBe(31)
  })

  it('sums a mixed set exactly: 3+6+6+5+4+3 = 27', () => {
    expect(
      narrativeTotal({
        maturity: 3,
        smartMoney: 6,
        hairFire: 6,
        communication: 5,
        lineage: 4,
        mutation: 3,
      }),
    ).toBe(27)
  })

  // Ruled 2026-09-21: sub-scores are whole numbers. The decimal example this repo used to cite
  // (ARB, Communication 4.5/5) appears in no lesson — grep framework/ for ARB, 26.5 or 4.5.
  it('rejects a fractional sub-score', () => {
    expect(() => narrativeTotal({ ...FULL, communication: 4.5 })).toThrow(ScoreRangeError)
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
