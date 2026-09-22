import { GATE_REQUIREMENTS, type GateScoresRow, type GateSection } from '../db/gate-fields.ts'

export type BlockerState = 'clear' | 'blocking' | 'unknown'

export interface Blocker {
  code: string
  section: GateSection
  state: BlockerState
  message: string
  /** The build-order step that will write this column, when `state` is `'unknown'`. */
  implementedInStep: number | null
}

/**
 * The blocker list, straight off GATE_REQUIREMENTS — the same array that generates
 * `rs_gate_completeness`. Nothing is hand-listed here, so a conjunct cannot be forgotten in one
 * place and remembered in the other.
 *
 * A requirement written by the commit route is `unknown`, NEVER `clear`. A green tick for a
 * check nobody has written is this repo's standing failure mode.
 */
export function evaluateBlockers(scores: GateScoresRow): Blocker[] {
  return GATE_REQUIREMENTS.map((requirement) => {
    const state: BlockerState =
      requirement.writtenBy === 'commit'
        ? 'unknown'
        : requirement.satisfied(scores)
          ? 'clear'
          : 'blocking'
    return {
      code: requirement.code,
      section: requirement.section,
      message: requirement.message,
      state,
      implementedInStep: requirement.writtenBy === 'commit' ? 6 : null,
    }
  })
}
