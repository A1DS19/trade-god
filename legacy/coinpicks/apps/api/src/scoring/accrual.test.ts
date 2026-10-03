import { describe, expect, it } from 'vitest'
import { annualHolderFlow, discoveryPremium } from './accrual.ts'
import { ScoreRangeError } from './ranges.ts'

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
  const flow = (grossAnnualFlowUsd: number, netAnnualFlowUsd: number) => ({
    grossAnnualFlowUsd,
    netAnnualFlowUsd,
    zeroFactor: null,
  })

  it('returns the multiple when net flow is positive', () => {
    expect(discoveryPremium(50_000_000, flow(14_000_000, 10_000_000))).toEqual({
      kind: 'MULTIPLE',
      multiple: 5,
    })
  })

  it('returns PURE_PREMIUM only when nothing is forced to holders at all', () => {
    expect(discoveryPremium(50_000_000, flow(0, 0)).kind).toBe('PURE_PREMIUM')
    expect(discoveryPremium(50_000_000, flow(0, -1)).kind).toBe('PURE_PREMIUM')
  })

  // The lesson reserves "never ownable" for ZERO forced flow. A token earning $10M while issuing
  // $50M — its own flagship example — has a real mechanism that insiders are eating, and calling
  // that the same thing as a governance token with no mechanism loses the finding.
  it('distinguishes a mechanism eaten by issuance from no mechanism at all', () => {
    const r = discoveryPremium(50_000_000, flow(10_000_000, -40_000_000))
    expect(r.kind).toBe('ISSUANCE_NEGATIVE')
    expect(r).toMatchObject({ grossAnnualFlowUsd: 10_000_000, netAnnualFlowUsd: -40_000_000 })
  })

  // Swept, not hypothesised: 120 of 960 combinations of round operator inputs where issuance
  // equals gross to the cent leave a non-zero float residue instead of 0. Without a floor
  // this exact row commits as MULTIPLE with a payback multiple of 3.4e21.
  it('does not call float64 debris a positive holder flow', () => {
    const breakEven = annualHolderFlow({
      segmentRevenueUsd: 100_000_000,
      captureShare: 0.07,
      accrualPct: 0.01,
      annualIssuanceUsd: 70_000,
    })
    expect(breakEven.grossAnnualFlowUsd).toBe(70_000.00000000001)
    expect(breakEven.netAnnualFlowUsd).toBe(1.4551915228366852e-11)

    const verdict = discoveryPremium(50_000_000_000, breakEven)
    expect(verdict.kind).toBe('ISSUANCE_NEGATIVE')
    expect(verdict).toMatchObject({
      grossAnnualFlowUsd: 70_000.00000000001,
      netAnnualFlowUsd: 1.4551915228366852e-11,
    })
  })

  it('still reports a thin but real flow, far above the floor', () => {
    // The floor is a ratio, not an absolute: a genuine $1m net against $1m gross is nowhere
    // near it, and neither is a thin but real margin.
    expect(discoveryPremium(50_000_000, flow(14_000_000, 10_000_000)).kind).toBe('MULTIPLE')
    expect(discoveryPremium(1_000_000, flow(1_000_000, 1)).kind).toBe('MULTIPLE')
  })
})

describe('discoveryPremium — malformed input', () => {
  const ok = { grossAnnualFlowUsd: 14_000_000, netAnnualFlowUsd: 10_000_000, zeroFactor: null }

  it('rejects a missing market cap instead of returning a premium of 0', () => {
    expect(() => discoveryPremium(null as unknown as number, ok)).toThrow(ScoreRangeError)
    expect(() => discoveryPremium(Number.NaN, ok)).toThrow(ScoreRangeError)
  })

  it('rejects a non-finite flow rather than guessing a verdict', () => {
    expect(() => discoveryPremium(50_000_000, { ...ok, netAnnualFlowUsd: Number.NaN })).toThrow(
      ScoreRangeError,
    )
    expect(() =>
      discoveryPremium(50_000_000, { ...ok, grossAnnualFlowUsd: null as unknown as number }),
    ).toThrow(ScoreRangeError)
  })
})
