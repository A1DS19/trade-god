export class ScoreRangeError extends Error {
  readonly field: string
  readonly value: number
  readonly min: number
  readonly max: number

  constructor(field: string, value: number, min: number, max: number) {
    super(`${field} must be between ${min} and ${max}, got ${value}`)
    this.name = 'ScoreRangeError'
    this.field = field
    this.value = value
    this.min = min
    this.max = max
  }
}

/** Rejects out-of-range values. Never clamps — a clamped score is a silently wrong report. */
export function assertRange(field: string, value: number, min: number, max: number): void {
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new ScoreRangeError(field, value, min, max)
  }
}

/**
 * Every rubric sub-score is a whole number.
 *
 * The lessons state their scales as integer-contiguous bands — Ease of Use is (0–3) (4–6) (7–10),
 * and the gate partitions outcomes into "16+" and "0–15", a partition that covers only integers:
 * 15.5 belongs to neither band as written. Allowing decimals also made the arithmetic lie, because
 * three one-decimal sub-scores summing to exactly 16.0 can add in binary to 15.999999999999998 and
 * fail a gate the lesson says to pass — 404 such triples exist, and the error runs one way only.
 *
 * Ruled 2026-09-21. Sub-score INPUTS are integers; derived values (the team weighted score, which
 * is a mean) are not.
 */
export function assertIntegerRange(field: string, value: number, min: number, max: number): void {
  assertRange(field, value, min, max)
  if (!Number.isInteger(value)) {
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
