import { assertIntegerRange } from './ranges.ts'

/** Framework: 16+ moves on, 0–15 drops the project. Frozen. */
export const PRODUCT_GATE_THRESHOLD = 16

export interface ProductGateInput {
  ease: number
  hairFire: number
  exclusivity: number
}

export interface ProductGateResult {
  total: number
  passed: boolean
}

export function productGate(input: ProductGateInput): ProductGateResult {
  assertIntegerRange('ease', input.ease, 0, 10)
  assertIntegerRange('hairFire', input.hairFire, 0, 10)
  assertIntegerRange('exclusivity', input.exclusivity, 0, 10)

  const total = input.ease + input.hairFire + input.exclusivity
  return { total, passed: total >= PRODUCT_GATE_THRESHOLD }
}
