import { and, eq, sql } from 'drizzle-orm'
import type { Tx } from '../db/client.ts'
import { reports } from '../db/schema.ts'
import { AlreadyCommittedError, ReportNotFoundError, StaleVersionError } from './errors.ts'

/**
 * Rule 4, in one place: UPDATE ... WHERE id = $1 AND version = $2, 409 on zero rows.
 *
 * This MUST be the first statement of any transaction that mutates a draft — the report, its
 * scores, its team rows or its citations. Two reasons, and both matter:
 *
 *  - it is the staleness check. Zero rows updated means someone else moved the report on
 *    since the editor loaded it. SQL does not treat that as an error, so this function does.
 *  - it is the lock. The UPDATE takes a FOR NO KEY UPDATE row lock on `reports`, which
 *    serialises it against every other writer's CAS. Taking it first means every writer locks
 *    the same row in the same order, so two editors cannot deadlock against each other.
 *
 * It bumps `version` on every successful call, so a client's token is good for exactly one
 * write.
 */
export async function casBumpVersion(
  tx: Tx,
  reportId: string,
  expectedVersion: number,
): Promise<number> {
  const bumped = await tx
    .update(reports)
    .set({ version: sql`${reports.version} + 1` })
    .where(
      and(
        eq(reports.id, reportId),
        eq(reports.version, expectedVersion),
        eq(reports.status, 'draft'),
      ),
    )
    .returning({ version: reports.version })

  const row = bumped[0]
  if (row !== undefined) return row.version

  // Zero rows. Read the row back to say WHY, because the editor's next move differs for each:
  // reload (stale), start a new report (committed), or report a bug (missing).
  const current = await tx
    .select({ version: reports.version, status: reports.status })
    .from(reports)
    .where(eq(reports.id, reportId))
    .limit(1)

  const actual = current[0]
  if (actual === undefined) throw new ReportNotFoundError(reportId)
  if (actual.status === 'committed') throw new AlreadyCommittedError(reportId)
  throw new StaleVersionError(reportId, expectedVersion, actual.version)
}
