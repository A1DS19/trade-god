import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  commitReportRow,
  createDraftReport,
  refusal,
  scoreAsDropped,
  TEST_APP_URL,
  TEST_RESEARCH_URL,
} from './testing.ts'

const app = openDb(TEST_APP_URL, 4)
const research = openDb(TEST_RESEARCH_URL, 2)
afterAll(async () => {
  await app.close()
  await research.close()
})

/** A committed report with one priced 30-day horizon, so research has something to read. */
async function pricedReport() {
  const { reportId } = await createDraftReport(app.db)
  await scoreAsDropped(app.db, reportId)
  await commitReportRow(app.db, reportId)
  await app.db.execute(sql`
    INSERT INTO forward_returns
      (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
    VALUES (${reportId}, 30, 2.0, 2.25, 'research/warehouse klines_1d', now())`)
  return reportId
}

describe('the request pool is bound by the guard it cannot reach', () => {
  it('is refused every write against a report it committed itself', async () => {
    const reportId = await pricedReport()
    const e = await refusal(
      app.db.execute(sql`UPDATE report_scores SET narrative_total = 31
                          WHERE report_id = ${reportId}`),
    )
    expect(e.code).toBe('CP001')
    expect(e.message).toMatch(/is committed; UPDATE on report_scores is refused/)
  })

  it('cannot drop a trigger, disable one, or drop a constraint', async () => {
    for (const statement of [
      sql`DROP TRIGGER citations_immutable ON citations`,
      sql`ALTER TABLE citations DISABLE TRIGGER citations_immutable`,
      sql`ALTER TABLE citations DROP CONSTRAINT ct_quote_not_blank`,
      sql`DROP FUNCTION coinpicks_report_child_immutable() CASCADE`,
      sql`DROP TABLE citations`,
    ]) {
      const e = await refusal(app.db.execute(statement))
      expect(e.code).toBe('42501')
      expect(e.message).toMatch(/must be owner of/)
    }
  })

  it('cannot create a table, so it cannot replace one either', async () => {
    const e = await refusal(app.db.execute(sql`CREATE TABLE cp_smuggled (x int)`))
    expect(e.code).toBe('42501')
    expect(e.message).toMatch(/permission denied for schema public/)
  })
})

describe('the research role reads the ledger and writes only its outcome', () => {
  it('reads the five report tables', async () => {
    const reportId = await pricedReport()
    const r = await research.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.n).toBe(1)
  })

  it('cannot write any report table', async () => {
    const reportId = await pricedReport()
    for (const statement of [
      sql`UPDATE report_scores SET product_total = 31 WHERE report_id = ${reportId}`,
      sql`UPDATE reports SET status = 'draft' WHERE id = ${reportId}`,
      sql`INSERT INTO citations (report_id, field, url, quote, origin)
          VALUES (${reportId}, 'f', 'https://example.test/q', 'q', 'human')`,
      sql`DELETE FROM coins`,
      sql`SELECT * FROM chain_facts`,
    ]) {
      const e = await refusal(research.db.execute(statement))
      expect(e.code).toBe('42501')
      expect(e.message).toMatch(/permission denied for table/)
    }
  })

  it('recomputes a horizon in place, the documented ON CONFLICT DO UPDATE way', async () => {
    const reportId = await pricedReport()
    await research.db.execute(sql`
      INSERT INTO forward_returns
        (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
      VALUES (${reportId}, 30, 2.0, 3.0, 'research/warehouse klines_1d', now())
      ON CONFLICT (report_id, horizon_days) DO UPDATE
        SET price_at_commit_usd  = excluded.price_at_commit_usd,
            price_at_horizon_usd = excluded.price_at_horizon_usd,
            price_source         = excluded.price_source,
            priced_at            = excluded.priced_at,
            computed_at          = now()`)
    const r = await research.db.execute<{ return_fraction: number }>(
      sql`SELECT return_fraction FROM forward_returns WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.return_fraction).toBeCloseTo(0.5, 12)
  })

  it('cannot move an observation into a different horizon or onto a different report', async () => {
    const reportId = await pricedReport()
    for (const statement of [
      sql`UPDATE forward_returns SET horizon_days = 365 WHERE report_id = ${reportId}`,
      sql`UPDATE forward_returns SET report_id = gen_random_uuid() WHERE report_id = ${reportId}`,
      sql`DELETE FROM forward_returns WHERE report_id = ${reportId}`,
    ]) {
      const e = await refusal(research.db.execute(statement))
      expect(e.code).toBe('42501')
    }
  })

  it('cannot write the derived fraction at all', async () => {
    const reportId = await pricedReport()
    const e = await refusal(
      research.db.execute(
        sql`UPDATE forward_returns SET return_fraction = 99 WHERE report_id = ${reportId}`,
      ),
    )
    expect(e.message).toMatch(/can only be updated to DEFAULT/)
  })
})
