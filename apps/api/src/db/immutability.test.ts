import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  commitReportRow,
  createDraftReport,
  refusal,
  scoreAsDropped,
  TEST_OWNER_URL,
} from './testing.ts'

// The OWNER connection. Two reasons, and the second is the interesting one: coinpicks_app has
// no table privileges until Task 5, and coinpicks_app will never hold TRUNCATE anyway — so
// the *_no_truncate triggers exist precisely to stop the role that CAN truncate, which is
// this one. Testing them from the app role would assert `permission denied` and prove nothing
// about the trigger.
const h = openDb(TEST_OWNER_URL, 4)
afterAll(() => h.close())

/** A coin, a report, a citation, a founder — then scored and committed. */
async function committedReport() {
  const { coinId, reportId } = await createDraftReport(h.db)
  const citationId = randomUUID()
  await h.db.execute(sql`
    INSERT INTO citations (id, report_id, field, url, quote, origin)
    VALUES (${citationId}, ${reportId}, 'narrative_maturity', 'https://example.test/a',
            'a quote', 'human')`)
  await h.db.execute(sql`
    INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
    VALUES (${reportId}, 1, 'Alice Chen', ARRAY['Founder'], true, 5, 3, 0,
            'Ran a $40M book at a prior firm.')`)
  await scoreAsDropped(h.db, reportId)
  await commitReportRow(h.db, reportId)
  return { coinId, reportId, citationId }
}

describe('the scores row is seeded with the report', () => {
  it('exists without anyone inserting it', async () => {
    const { reportId } = await createDraftReport(h.db)
    const r = await h.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(1)
  })
})

describe('a report cannot be committed unscored', () => {
  it('refuses the flip when report_scores is empty', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(commitReportRow(h.db, reportId))
    expect(e.code).toBe('CP002')
    expect(e.message).toMatch(/report_scores row is missing or unscored/)
  })

  it('refuses a born-committed INSERT, which nothing could ever fill', async () => {
    const { coinId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO reports (coin_id, status, committed_at, coin_symbol, coin_chain)
        VALUES (${coinId}, 'committed', now(), 'TST', 'ethereum')`),
    )
    expect(e.code).toBe('CP002')
  })

  it('snapshots the coin identity at commit, so re-pointing the coin cannot re-point it', async () => {
    const { coinId, reportId } = await committedReport()
    await h.db.execute(sql`
      UPDATE coins SET symbol = 'SCAM', name = 'Other Token', contract_address = '0xdeadbeef'
       WHERE id = ${coinId}`)
    const r = await h.db.execute<{ coin_symbol: string; coin_chain: string }>(
      sql`SELECT coin_symbol, coin_chain FROM reports WHERE id = ${reportId}`,
    )
    expect(r.rows[0]).toEqual({ coin_symbol: 'TST', coin_chain: 'ethereum' })
  })
})

describe('a committed report is refused every write', () => {
  it('refuses UPDATE and DELETE on the report itself', async () => {
    const { reportId } = await committedReport()
    const u = await refusal(
      h.db.execute(sql`UPDATE reports SET version = 99 WHERE id = ${reportId}`),
    )
    expect(u.code).toBe('CP001')
    expect(u.message).toMatch(/is committed; UPDATE on reports is refused/)
    const d = await refusal(h.db.execute(sql`DELETE FROM reports WHERE id = ${reportId}`))
    expect(d.code).toBe('CP001')
  })

  it('refuses INSERT, UPDATE and DELETE on every child table', async () => {
    const { reportId, citationId } = await committedReport()
    for (const statement of [
      sql`UPDATE report_scores SET narrative_total = 31 WHERE report_id = ${reportId}`,
      sql`DELETE FROM report_scores WHERE report_id = ${reportId}`,
      sql`INSERT INTO citations (report_id, field, url, quote, origin)
          VALUES (${reportId}, 'narrative_lineage', 'https://example.test/late', 'late', 'human')`,
      sql`UPDATE citations SET quote = 'TAMPERED' WHERE id = ${citationId}`,
      sql`DELETE FROM citations WHERE id = ${citationId}`,
      sql`UPDATE report_team SET h = 0 WHERE report_id = ${reportId}`,
      sql`DELETE FROM report_team WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(h.db.execute(statement))
      expect(e.code).toBe('CP001')
    }
  })

  it('refuses re-parenting its children onto a draft — the attack that gutted it', async () => {
    const { reportId } = await committedReport()
    const draft = await createDraftReport(h.db)
    for (const statement of [
      sql`UPDATE report_scores SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
      sql`UPDATE report_team SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
      sql`UPDATE citations SET report_id = ${draft.reportId} WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(h.db.execute(statement))
      expect(e.code).toBe('CP001')
      expect(e.message).toMatch(/report_id is immutable/)
    }
    const left = await h.db.execute<{ scores: number; team: number; cits: number }>(sql`
      SELECT (SELECT count(*)::int FROM report_scores WHERE report_id = ${reportId}) AS scores,
             (SELECT count(*)::int FROM report_team   WHERE report_id = ${reportId}) AS team,
             (SELECT count(*)::int FROM citations     WHERE report_id = ${reportId}) AS cits`)
    expect(left.rows[0]).toEqual({ scores: 1, team: 1, cits: 1 })
  })

  it('refuses re-parenting between two DRAFTS as well', async () => {
    const a = await createDraftReport(h.db)
    const b = await createDraftReport(h.db)
    const citationId = randomUUID()
    await h.db.execute(sql`
      INSERT INTO citations (id, report_id, field, url, quote, origin)
      VALUES (${citationId}, ${a.reportId}, 'narrative_maturity', 'https://example.test/a',
              'a quote', 'human')`)
    const e = await refusal(
      h.db.execute(sql`UPDATE citations SET report_id = ${b.reportId} WHERE id = ${citationId}`),
    )
    expect(e.code).toBe('CP001')
  })
})

describe('a draft is still fully editable', () => {
  it('can be discarded even though it has children', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO citations (report_id, field, url, quote, origin)
      VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'a quote', 'human')`)
    await h.db.execute(sql`DELETE FROM reports WHERE id = ${reportId}`)
    const r = await h.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM citations WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(0)
  })

  it('resets a citation that has been repointed at a different claim', async () => {
    const { reportId } = await createDraftReport(h.db)
    const citationId = randomUUID()
    await h.db.execute(sql`
      INSERT INTO citations (id, report_id, field, url, quote, origin, status, waiver_reason,
                             verified_at, http_status)
      VALUES (${citationId}, ${reportId}, 'narrative_maturity', 'https://example.test/a',
              'the old quote', 'human', 'waived', 'page is JS-rendered', now(), 200)`)
    await h.db.execute(sql`
      UPDATE citations SET quote = 'a different claim entirely' WHERE id = ${citationId}`)
    const r = await h.db.execute<{
      status: string
      waiver_reason: string | null
      verified_at: Date | null
      http_status: number | null
    }>(sql`SELECT status, waiver_reason, verified_at, http_status FROM citations
            WHERE id = ${citationId}`)
    expect(r.rows[0]).toEqual({
      status: 'unverified',
      waiver_reason: null,
      verified_at: null,
      http_status: null,
    })
  })
})

describe('TRUNCATE is refused on every ledger table', () => {
  it.each(['reports', 'report_scores', 'report_team', 'citations', 'forward_returns'])(
    'refuses TRUNCATE %s',
    async (table) => {
      // CASCADE deliberately. A bare `TRUNCATE reports` never reaches our trigger — Postgres
      // refuses it at the foreign-key stage with 0A000 (`cannot truncate a table referenced
      // in a foreign key constraint`), so asserting CP001 there would be asserting that an FK
      // exists, not that the ledger is guarded. CASCADE is the statement that gets past the
      // FK, and it is the one that has to be refused by us.
      const e = await refusal(h.db.execute(sql.raw(`TRUNCATE ${table} CASCADE`)))
      expect(e.code).toBe('CP001')
      expect(e.message).toMatch(/append-only ledger/)
    },
  )
})

describe('the guards survive replica mode', () => {
  it('has all twelve triggers at ENABLE ALWAYS', async () => {
    const r = await h.db.execute<{ tgname: string; tgenabled: string }>(sql`
      SELECT t.tgname, t.tgenabled
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE NOT t.tgisinternal AND n.nspname = 'public'
       ORDER BY t.tgname`)
    expect(r.rows.map((x) => x.tgname)).toEqual([
      'citations_immutable',
      'citations_no_truncate',
      'citations_reset_verification',
      'forward_returns_no_truncate',
      'report_scores_immutable',
      'report_scores_no_truncate',
      'report_team_immutable',
      'report_team_no_truncate',
      'reports_assert_commitable',
      'reports_immutable',
      'reports_no_truncate',
      'reports_seed_scores',
    ])
    expect(r.rows.every((x) => x.tgenabled === 'A')).toBe(true)
  })
})
