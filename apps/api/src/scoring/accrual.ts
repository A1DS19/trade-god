import { assertNonNegative, assertRange, ScoreRangeError } from './ranges'

export interface AccrualInput {
  segmentRevenueUsd: number
  /** A fraction in [0, 1], never a percentage. See the domain note below. */
  captureShare: number
  /** A fraction in [0, 1] despite the name, never a percentage. See the domain note below. */
  accrualPct: number
  annualIssuanceUsd: number
}

export interface AccrualResult {
  grossAnnualFlowUsd: number
  netAnnualFlowUsd: number
  /**
   * The framework: "These steps multiply. One zero anywhere zeroes the product."
   * A bare 0 hides which step failed, so name it.
   */
  zeroFactor: 'segmentRevenueUsd' | 'captureShare' | 'accrualPct' | null
}

/**
 * The formula is frozen: revenue x capture x accrual - issuance.
 *
 * The DOMAIN is enforced here, which the framework text leaves implicit and inconsistent:
 * `00-how-we-think.md` calls capture share a "fraction" and token accrual a "percentage"
 * in consecutive sentences, but the multiplication only produces dollars if both are
 * fractions. A 50 typed where 0.5 belongs is a silent 100x error inside a report that is
 * immutable once committed, so it is rejected rather than quietly divided.
 *
 * NOTE ON PROVENANCE: the framework's own AI prompt says to DIVIDE a mis-scaled Quality value
 * by 10. Rejecting instead is this repo's deliberate departure (spec: "reject it; do not silently
 * divide"), not something the lessons prescribe. Recorded here so the next reader does not cite
 * the framework for a rule the framework does not contain.
 */
export function annualHolderFlow(input: AccrualInput): AccrualResult {
  assertNonNegative('segmentRevenueUsd', input.segmentRevenueUsd)
  assertRange('captureShare', input.captureShare, 0, 1)
  assertRange('accrualPct', input.accrualPct, 0, 1)
  assertNonNegative('annualIssuanceUsd', input.annualIssuanceUsd)

  const factors = ['segmentRevenueUsd', 'captureShare', 'accrualPct'] as const
  const zeroFactor = factors.find((f) => input[f] === 0) ?? null

  const grossAnnualFlowUsd = input.segmentRevenueUsd * input.captureShare * input.accrualPct

  return {
    grossAnnualFlowUsd,
    netAnnualFlowUsd: grossAnnualFlowUsd - input.annualIssuanceUsd,
    zeroFactor,
  }
}

export type PremiumResult = { kind: 'MULTIPLE'; multiple: number } | { kind: 'PURE_PREMIUM' }

/**
 * The framework: a token with zero forced flow at any price is "100% premium,
 * pure narrative, tradable but never ownable."
 */
export function discoveryPremium(marketCapUsd: number, netAnnualFlowUsd: number): PremiumResult {
  assertNonNegative('marketCapUsd', marketCapUsd)
  if (!Number.isFinite(netAnnualFlowUsd)) {
    throw new ScoreRangeError(
      'netAnnualFlowUsd',
      netAnnualFlowUsd,
      Number.NEGATIVE_INFINITY,
      Number.POSITIVE_INFINITY,
    )
  }
  if (netAnnualFlowUsd <= 0) return { kind: 'PURE_PREMIUM' }
  return { kind: 'MULTIPLE', multiple: marketCapUsd / netAnnualFlowUsd }
}
