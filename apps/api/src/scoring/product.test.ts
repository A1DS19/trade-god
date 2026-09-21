import { describe, expect, it } from 'vitest'
import { PRODUCT_GATE_THRESHOLD, productGate } from './product'
import { ScoreRangeError } from './ranges'

describe('productGate', () => {
  it('sums the three sub-scores', () => {
    expect(productGate({ ease: 7, hairFire: 6, exclusivity: 5 }).total).toBe(18)
  })

  it('passes at exactly 16 — the framework boundary', () => {
    expect(productGate({ ease: 6, hairFire: 5, exclusivity: 5 }).passed).toBe(true)
  })

  it('fails at 15', () => {
    expect(productGate({ ease: 5, hairFire: 5, exclusivity: 5 }).passed).toBe(false)
  })

  it('exposes the threshold as 16', () => {
    expect(PRODUCT_GATE_THRESHOLD).toBe(16)
  })

  it('rejects out-of-range input rather than clamping', () => {
    expect(() => productGate({ ease: 11, hairFire: 5, exclusivity: 5 })).toThrow(ScoreRangeError)
    expect(() => productGate({ ease: -1, hairFire: 5, exclusivity: 5 })).toThrow(ScoreRangeError)
  })

  // Ruled 2026-09-21: the lesson's bands are integer-contiguous, and three one-decimal
  // sub-scores summing to exactly 16.0 could add in binary to 15.999999999999998 and fail a
  // gate the lesson says to pass — 404 such triples exist, all failing one way.
  it('rejects a fractional sub-score', () => {
    expect(() => productGate({ ease: 8.2, hairFire: 7.6, exclusivity: 0.2 })).toThrow(
      ScoreRangeError,
    )
  })

  it('names the offending field in the error', () => {
    try {
      productGate({ ease: 5, hairFire: 99, exclusivity: 5 })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect((e as ScoreRangeError).field).toBe('hairFire')
      expect((e as ScoreRangeError).value).toBe(99)
    }
  })
})
