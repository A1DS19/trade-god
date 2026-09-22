import { assertNonNegative, assertRange, ScoreRangeError } from './ranges.ts'

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

export type PremiumResult =
  | { kind: 'MULTIPLE'; multiple: number }
  /** Nothing is forced to holders at all: gross flow is zero. The lesson's "never ownable". */
  | { kind: 'PURE_PREMIUM' }
  /** A real mechanism exists and issuance eats it. Distinct from having no mechanism. */
  | { kind: 'ISSUANCE_NEGATIVE'; grossAnnualFlowUsd: number; netAnnualFlowUsd: number }

/**
 * The frozen formula is unchanged: market cap / net annual flow.
 *
 * What the verdict TAXONOMY distinguishes, and an earlier version did not: the lesson reserves
 * "100% premium, pure narrative, tradable but never ownable" for a token with ZERO forced flow
 * (00-how-we-think.md §5). A token that earns $10M and issues $50M — the lesson's own flagship
 * example in §1 — has a real mechanism that insiders are eating, which is a different finding
 * from having no mechanism at all. It takes the whole AccrualResult rather than a bare net figure
 * precisely so it cannot be called without the gross that tells the two apart.
 */
export function discoveryPremium(marketCapUsd: number, flow: AccrualResult): PremiumResult {
  assertNonNegative('marketCapUsd', marketCapUsd)
  for (const field of ['grossAnnualFlowUsd', 'netAnnualFlowUsd'] as const) {
    if (!Number.isFinite(flow[field])) {
      throw new ScoreRangeError(
        field,
        flow[field],
        Number.NEGATIVE_INFINITY,
        Number.POSITIVE_INFINITY,
      )
    }
  }

  if (flow.netAnnualFlowUsd > 0) {
    return { kind: 'MULTIPLE', multiple: marketCapUsd / flow.netAnnualFlowUsd }
  }
  if (flow.grossAnnualFlowUsd > 0) {
    return {
      kind: 'ISSUANCE_NEGATIVE',
      grossAnnualFlowUsd: flow.grossAnnualFlowUsd,
      netAnnualFlowUsd: flow.netAnnualFlowUsd,
    }
  }
  return { kind: 'PURE_PREMIUM' }
}
