export class ScoreRangeError extends Error {
  constructor(
    readonly field: string,
    readonly value: number,
    readonly min: number,
    readonly max: number,
  ) {
    super(`${field} must be between ${min} and ${max}, got ${value}`)
    this.name = 'ScoreRangeError'
  }
}

/** Rejects out-of-range values. Never clamps — a clamped score is a silently wrong report. */
export function assertRange(field: string, value: number, min: number, max: number): void {
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new ScoreRangeError(field, value, min, max)
  }
}

/**
 * Rejects negative or non-finite dollar amounts. Separate from assertRange because
 * a dollar figure has a floor but no meaningful ceiling.
 */
export function assertNonNegative(field: string, value: number): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new ScoreRangeError(field, value, 0, Number.POSITIVE_INFINITY)
  }
}
