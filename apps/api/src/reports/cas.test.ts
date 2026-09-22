import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from '../db/client.ts'
import { commitReportRow, createDraftReport, scoreAsDropped, TEST_APP_URL } from '../db/testing.ts'
import { casBumpVersion } from './cas.ts'
import {
  AlreadyCommittedError,
  ReportNotFoundError,
  StaleVersionError,
  sqlstateOf,
} from './errors.ts'

const h = openDb(TEST_APP_URL, 4)
afterAll(() => h.close())

describe('casBumpVersion', () => {
  it('bumps the version and returns the new one', async () => {
    const { reportId } = await createDraftReport(h.db)
    const v = await h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))
    expect(v).toBe(2)
  })

  it('refuses a token that has already been spent', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))
    await expect(h.db.transaction((tx) => casBumpVersion(tx, reportId, 1))).rejects.toBeInstanceOf(
      StaleVersionError,
    )
  })

  it('says "already committed" rather than "stale", because the editor must do something different', async () => {
    const { reportId } = await createDraftReport(h.db)
    await scoreAsDropped(h.db, reportId)
    await commitReportRow(h.db, reportId)
    await expect(h.db.transaction((tx) => casBumpVersion(tx, reportId, 2))).rejects.toBeInstanceOf(
      AlreadyCommittedError,
    )
  })

  it('says "not found" for an id that never existed', async () => {
    await expect(
      h.db.transaction((tx) => casBumpVersion(tx, '00000000-0000-0000-0000-000000000000', 1)),
    ).rejects.toBeInstanceOf(ReportNotFoundError)
  })

  /**
   * Two tabs, one draft, the same token. The second must block on the first's row lock and
   * then match zero rows — not overwrite it. Verified live: T2's UPDATE stays pending while
   * T1 is open, returns rowCount 0 once T1 commits, and the final version is 2, so exactly
   * one write landed.
   */
  it('lets exactly one of two concurrent writers through', async () => {
    const { reportId } = await createDraftReport(h.db)
    const a = await h.pool.connect()
    const b = await h.pool.connect()
    try {
      const CAS = `update reports set version = version + 1
                     where id = $1 and version = $2 and status = 'draft'
                   returning version`
      await a.query('begin')
      await b.query('begin')

      const first = await a.query(CAS, [reportId, 1])
      expect(first.rowCount).toBe(1)

      const second = b.query(CAS, [reportId, 1])
      let settled = false
      void second.then(() => {
        settled = true
      })
      await new Promise((r) => setTimeout(r, 250))
      expect(settled).toBe(false) // still blocked on A's row lock

      await a.query('commit')
      expect((await second).rowCount).toBe(0) // the editor gets a 409
      await b.query('commit')
    } finally {
      a.release()
      b.release()
    }

    const final = await h.db.execute<{ version: number }>(
      sql`SELECT version FROM reports WHERE id = ${reportId}`,
    )
    expect(final.rows[0]?.version).toBe(2)
  })
})

describe('sqlstateOf', () => {
  it('finds the SQLSTATE that drizzle buried under DrizzleQueryError', async () => {
    const { reportId } = await createDraftReport(h.db)
    await scoreAsDropped(h.db, reportId)
    await commitReportRow(h.db, reportId)
    try {
      await h.db.execute(sql`
        INSERT INTO citations (report_id, field, url, quote, origin)
        VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'q', 'human')`)
      expect.unreachable('the trigger should have refused this')
    } catch (error) {
      expect((error as { code?: unknown }).code).toBeUndefined() // the wrapper carries none
      expect(sqlstateOf(error)).toBe('CP001')
    }
  })

  it('returns undefined for an error that is not a database error', () => {
    expect(sqlstateOf(new Error('nope'))).toBeUndefined()
    expect(sqlstateOf(undefined)).toBeUndefined()
  })
})
