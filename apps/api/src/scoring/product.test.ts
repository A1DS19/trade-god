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
