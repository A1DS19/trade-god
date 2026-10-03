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
 * Below this fraction of gross flow, a positive `net` is float64 debris from
 * `gross - issuance` rather than money reaching holders.
 *
 * Swept: across 960 combinations of round operator inputs where issuance equals gross to the
 * cent — the framework's flagship "earns as much as it prints" case — 120 leave a non-zero
 * residue. $100m revenue x 0.07 capture x 0.01 accrual less $70,000 issuance gives
 * gross = 70000.00000000001 and net = 1.455e-11, which the unguarded branch published as
 * kind='MULTIPLE' at a payback multiple of 3.4e21, immutably.
 *
 * Keyed on gross alone, and that is deliberate: AccrualResult does not carry issuance, and
 * when |net| is genuinely near zero then gross is approximately issuance anyway, so gross is
 * the right scale. When issuance dwarfs gross, net is approximately -issuance — nowhere near
 * zero — and this never fires.
 *
 * The FROZEN formula (market_cap / net_annual_flow) is untouched. This is the verdict
 * taxonomy around it, which is this implementation's own and which the 2026-09-21
 * PURE_PREMIUM ruling already amended once. Ruled again 2026-09-21. The database reproduces
 * the same branch in report_scores' rs_premium_kind_matches_flows.
 */
export const NET_FLOW_NOISE_FLOOR_RATIO = 1e-9

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

  const isNoise =
    Math.abs(flow.netAnnualFlowUsd) < flow.grossAnnualFlowUsd * NET_FLOW_NOISE_FLOOR_RATIO

  if (flow.netAnnualFlowUsd > 0 && !isNoise) {
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
