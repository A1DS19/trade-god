import { describe, expect, it } from 'vitest'
import { annualHolderFlow, discoveryPremium } from './accrual'
import { ScoreRangeError } from './ranges'

describe('annualHolderFlow', () => {
  it('multiplies the chain then subtracts issuance', () => {
    const r = annualHolderFlow({
      segmentRevenueUsd: 1_000_000_000,
      captureShare: 0.02,
      accrualPct: 0.5,
      annualIssuanceUsd: 4_000_000,
    })
    expect(r.grossAnnualFlowUsd).toBe(10_000_000)
    expect(r.netAnnualFlowUsd).toBe(6_000_000)
    expect(r.zeroFactor).toBeNull()
  })

  it("reports the framework's losing case: earns 10M, issues 50M", () => {
    const r = annualHolderFlow({
      segmentRevenueUsd: 100_000_000,
      captureShare: 1,
      accrualPct: 0.1,
      annualIssuanceUsd: 50_000_000,
    })
    expect(r.netAnnualFlowUsd).toBe(-40_000_000)
  })

  it('names which multiplicand was zero rather than returning a bare 0', () => {
    expect(
      annualHolderFlow({
        segmentRevenueUsd: 1_000_000,
        captureShare: 0.1,
        accrualPct: 0,
        annualIssuanceUsd: 0,
      }).zeroFactor,
    ).toBe('accrualPct')

    expect(
      annualHolderFlow({
        segmentRevenueUsd: 0,
        captureShare: 0.1,
        accrualPct: 0.1,
        annualIssuanceUsd: 0,
      }).zeroFactor,
    ).toBe('segmentRevenueUsd')
  })

  // The framework says "capture share, what FRACTION" but "token accrual %, what PERCENTAGE"
  // (framework/00-how-we-think.md:20-22). The arithmetic only works if both are fractions —
  // 50 instead of 0.5 is a silent 100x error in an immutable committed report. So the domain
  // is enforced, mirroring the framework's own rule for Quality: a value typed on the wrong
  // scale is REJECTED, never quietly divided.
  it('rejects a fraction typed on a 0-100 scale rather than silently multiplying by 100', () => {
    const base = { segmentRevenueUsd: 1_000_000, annualIssuanceUsd: 0 }
    expect(() => annualHolderFlow({ ...base, captureShare: 2, accrualPct: 0.5 })).toThrow(
      ScoreRangeError,
    )
    expect(() => annualHolderFlow({ ...base, captureShare: 0.02, accrualPct: 50 })).toThrow(
      ScoreRangeError,
    )
  })

  it('names which fraction was out of domain', () => {
    try {
      annualHolderFlow({
        segmentRevenueUsd: 1_000_000,
        captureShare: 0.02,
        accrualPct: 50,
        annualIssuanceUsd: 0,
      })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect((e as ScoreRangeError).field).toBe('accrualPct')
      expect((e as ScoreRangeError).value).toBe(50)
    }
  })

  it('rejects negative dollar inputs', () => {
    const ok = { captureShare: 0.1, accrualPct: 0.1 }
    expect(() => annualHolderFlow({ ...ok, segmentRevenueUsd: -1, annualIssuanceUsd: 0 })).toThrow(
      ScoreRangeError,
    )
    expect(() => annualHolderFlow({ ...ok, segmentRevenueUsd: 1, annualIssuanceUsd: -1 })).toThrow(
      ScoreRangeError,
    )
  })
})

describe('discoveryPremium', () => {
  it('returns the multiple when net flow is positive', () => {
    const r = discoveryPremium(50_000_000, 10_000_000)
    expect(r).toEqual({ kind: 'MULTIPLE', multiple: 5 })
  })

  it('returns PURE_PREMIUM when nothing is forced to holders', () => {
    expect(discoveryPremium(50_000_000, 0).kind).toBe('PURE_PREMIUM')
    expect(discoveryPremium(50_000_000, -1).kind).toBe('PURE_PREMIUM')
  })
})

describe('discoveryPremium — malformed input', () => {
  it('rejects a missing market cap instead of returning a premium of 0', () => {
    expect(() => discoveryPremium(null as unknown as number, 10_000_000)).toThrow(ScoreRangeError)
    expect(() => discoveryPremium(Number.NaN, 10_000_000)).toThrow(ScoreRangeError)
  })

  it('rejects a non-finite net flow rather than guessing a verdict', () => {
    expect(() => discoveryPremium(50_000_000, Number.NaN)).toThrow(ScoreRangeError)
    expect(() => discoveryPremium(50_000_000, null as unknown as number)).toThrow(ScoreRangeError)
  })
})
