/**
 * Where the DB tests connect. Overridable for CI, which runs Postgres as a service rather
 * than as the compose container.
 */
export const TEST_OWNER_URL =
  process.env.TEST_DATABASE_URL_OWNER ??
  'postgresql://coinpicks_owner:coinpicks_owner@localhost:5433/coinpicks_test'

export const TEST_APP_URL =
  process.env.TEST_DATABASE_URL ??
  'postgresql://coinpicks_app:coinpicks_app@localhost:5433/coinpicks_test'

export const TEST_RESEARCH_URL =
  process.env.TEST_RESEARCH_DATABASE_URL ??
  'postgresql://research:research@localhost:5433/coinpicks_test'

export interface DriverError {
  /** The SQLSTATE: '23514' for a CHECK, '23505' for a unique index, '42501' for a
   *  privilege refusal, 'CP001' for one of ours. */
  code: string
  message: string
  /** The constraint that refused it, when Postgres names one. */
  constraint: string | undefined
}

/**
 * Asserts a statement was refused, and returns the DRIVER's error rather than the wrapper's.
 *
 * `await expect(p).rejects.toThrow(/permission denied/)` looks right and never matches.
 * drizzle 0.45.3 wraps every driver error in DrizzleQueryError at seven call sites in
 * pg-core/session.js; confirmed live that the wrapper's own `code` is undefined and its
 * message is `Failed query: update report_scores set ...`, while the real message, the
 * SQLSTATE and the constraint name sit on `.cause`. A test matching the wrapper's message
 * would pass for the wrong reason or fail for no reason, so walk the chain.
 *
 * The same walk is what the commit route needs in production, and Task 7 lifts it into
 * reports/errors.ts as `sqlstateOf`.
 */
export async function refusal(promise: Promise<unknown>): Promise<DriverError> {
  try {
    await promise
  } catch (error) {
    let cursor: unknown = error
    for (let depth = 0; cursor != null && depth < 10; depth += 1) {
      const node = cursor as {
        code?: unknown
        message?: unknown
        constraint?: unknown
        cause?: unknown
      }
      if (typeof node.code === 'string' && /^[0-9A-Z]{5}$/.test(node.code)) {
        return {
          code: node.code,
          message: String(node.message),
          constraint: typeof node.constraint === 'string' ? node.constraint : undefined,
        }
      }
      cursor = node.cause
    }
    throw new Error(`no SQLSTATE anywhere in the error chain: ${String(error)}`)
  }
  throw new Error('expected the statement to be refused, but it succeeded')
}
