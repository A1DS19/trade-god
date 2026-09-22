import { assertIntegerRange } from './ranges.ts'

/**
 * Frozen sub-score maxima. Note hairFire is 0–6 HERE (inside Narrative) but
 * 0–10 in the Product gate — two distinct fields, neither derived from the other.
 */
export const NARRATIVE_MAX = {
  maturity: 7,
  smartMoney: 6,
  hairFire: 6,
  communication: 5,
  lineage: 4,
  mutation: 3,
} as const

export const NARRATIVE_TOTAL_MAX = 31

export type NarrativeInput = Record<keyof typeof NARRATIVE_MAX, number>

export function narrativeTotal(input: NarrativeInput): number {
  let total = 0
  for (const field of Object.keys(NARRATIVE_MAX) as (keyof typeof NARRATIVE_MAX)[]) {
    assertIntegerRange(field, input[field], 0, NARRATIVE_MAX[field])
    total += input[field]
  }
  return total
}
