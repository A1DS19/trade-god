/**
 * Commit-path errors. Each maps to exactly one HTTP status, so the route's catch is a closed
 * set. No parameter properties anywhere in here: Node 26 strips types and would refuse the
 * file (see Global Constraints).
 */

/** Raised by the immutability triggers: this row belongs to a committed report. */
export const SQLSTATE_REPORT_COMMITTED = 'CP001'

/** Raised by coinpicks_assert_commitable(): the report has not been scored. */
export const SQLSTATE_REPORT_UNSCORED = 'CP002'

/** Raised by the child trigger when the parent report row is missing. */
export const SQLSTATE_REPORT_MISSING = 'CP404'

/**
 * The SQLSTATE of a database error, wherever drizzle has buried it.
 *
 * `(error as {code?: string}).code === 'CP001'` looks right and is dead code: drizzle 0.45.3
 * wraps every driver error in DrizzleQueryError, which sets no `code` of its own and puts
 * the pg error on `.cause`. Confirmed live — the wrapper's `code` is undefined, its message
 * is `Failed query: insert into citations (...) values (...)`, and `cause.code` is 'CP001'.
 * Every handler written against the naive shape would never fire and a lost race would reach
 * the operator as a 500 carrying the raw statement.
 */
export function sqlstateOf(error: unknown): string | undefined {
  let cursor: unknown = error
  for (let depth = 0; cursor != null && depth < 10; depth += 1) {
    const node = cursor as { code?: unknown; cause?: unknown }
    if (typeof node.code === 'string' && /^[0-9A-Z]{5}$/.test(node.code)) return node.code
    cursor = node.cause
  }
  return undefined
}

export function isReportCommittedError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_COMMITTED
}

export function isReportUnscoredError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_UNSCORED
}

export function isReportMissingError(error: unknown): boolean {
  return sqlstateOf(error) === SQLSTATE_REPORT_MISSING
}

export class ReportNotFoundError extends Error {
  readonly httpStatus = 404
  readonly reportId: string

  constructor(reportId: string) {
    super(`report ${reportId} does not exist`)
    this.name = 'ReportNotFoundError'
    this.reportId = reportId
  }
}

/**
 * The client's compare-and-swap token did not match. The editor must reload and re-apply; it
 * must never retry with the same token.
 */
export class StaleVersionError extends Error {
  readonly httpStatus = 409
  readonly reportId: string
  readonly expectedVersion: number
  readonly actualVersion: number

  constructor(reportId: string, expectedVersion: number, actualVersion: number) {
    super(
      `report ${reportId} moved on: client holds version ${expectedVersion}, ` +
        `database has ${actualVersion}`,
    )
    this.name = 'StaleVersionError'
    this.reportId = reportId
    this.expectedVersion = expectedVersion
    this.actualVersion = actualVersion
  }
}

/** Distinct from stale on purpose: the editor's answer is "start a new report", not
 *  "reload". Re-researching a coin creates a new reports row. */
export class AlreadyCommittedError extends Error {
  readonly httpStatus = 409
  readonly reportId: string

  constructor(reportId: string) {
    super(`report ${reportId} is already committed and is immutable`)
    this.name = 'AlreadyCommittedError'
    this.reportId = reportId
  }
}

/**
 * A citation whose `team:<uuid>` field names a member this report does not have. `citations.field`
 * is text with no foreign key, so this is the only place the reference can be checked before the
 * commit gate counts it as evidence.
 */
export class UnknownTeamMemberError extends Error {
  readonly httpStatus = 422
  readonly field: string

  constructor(field: string) {
    super(`no team member on this report matches ${field}. Save the team first.`)
    this.name = 'UnknownTeamMemberError'
    this.field = field
  }
}
