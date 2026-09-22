import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import type { Db } from './client.ts'

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

export interface DraftReport {
  coinId: string
  reportId: string
}

/**
 * A fresh coin and a fresh draft report, with ids nobody else in the suite will use — the
 * test database is shared and vitest runs files in parallel.
 */
export async function createDraftReport(db: Db): Promise<DraftReport> {
  const coinId = randomUUID()
  const reportId = randomUUID()
  await db.execute(sql`
    INSERT INTO coins (id, symbol, name, chain, contract_address, address_sources)
    VALUES (${coinId}, 'TST', 'Test Coin', 'ethereum', ${`0x${coinId.replace(/-/g, '')}`},
            '["https://a.example","https://b.example"]'::jsonb)`)
  await db.execute(sql`INSERT INTO reports (id, coin_id) VALUES (${reportId}, ${coinId})`)
  // Task 4 deletes the next statement: the reports_seed_scores trigger does it instead.
  await db.execute(sql`INSERT INTO report_scores (report_id) VALUES (${reportId})`)
  return { coinId, reportId }
}

/**
 * The least a report can carry and still be commitable: a product gate that FAILED.
 * A dropped project still commits — a ledger holding only passes is survivorship bias in
 * the exact dataset built to test the framework — and rs_gate_completeness requires the
 * downstream sections only when the gate passed.
 */
export async function scoreAsDropped(db: Db, reportId: string): Promise<void> {
  await db.execute(sql`
    UPDATE report_scores
       SET scoring_version = 'test', product_ease = 5, product_hair_fire = 5,
           product_exclusivity = 5, product_total = 15, product_passed = false
     WHERE report_id = ${reportId}`)
}

/** The status flip, in rule 4's compare-and-swap form. */
export async function commitReportRow(db: Db, reportId: string): Promise<void> {
  await db.execute(sql`
    UPDATE reports SET status = 'committed', committed_at = now(), version = version + 1
     WHERE id = ${reportId} AND status = 'draft'`)
}
