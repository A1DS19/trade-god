import { randomUUID } from 'node:crypto'
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import { createDraftReport, refusal, TEST_OWNER_URL } from './testing.ts'

// The OWNER connection, not the app role. coinpicks_app holds no table privileges until the
// grant migration lands in Task 5, and the CHECK constraints under test here are the
// database's, not the privilege system's. Task 5 switches to the app role and proves that the
// triggers bind it too.
const h = openDb(TEST_OWNER_URL, 4)
afterAll(() => h.close())

describe('the day-one draft path', () => {
  it('stores a coin, a report and an all-NULL scores row', async () => {
    const { reportId } = await createDraftReport(h.db)
    const r = await h.db.execute<{ status: string; version: number; accrual_assessed: boolean }>(
      sql`SELECT r.status, r.version, s.accrual_assessed
            FROM reports r JOIN report_scores s ON s.report_id = r.id
           WHERE r.id = ${reportId}`,
    )
    expect(r.rows[0]).toEqual({ status: 'draft', version: 1, accrual_assessed: false })
  })

  it('stores a citation and a team member against the draft', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO citations (report_id, field, url, quote, origin)
      VALUES (${reportId}, 'narrative_maturity', 'https://example.test/a', 'a quote', 'human')`)
    await h.db.execute(sql`
      INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
      VALUES (${reportId}, 1, '  Alice   Chen ', ARRAY['Founder','Head of Product'],
              true, 5, 3, 0, 'Ran a $40M book at a prior firm.')`)
    const r = await h.db.execute<{ name_key: string }>(
      sql`SELECT name_key FROM report_team WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.name_key).toBe('alice chen')
  })
})

describe('the domains Postgres enforces, not TypeScript', () => {
  it('refuses a sub-score above its own maximum', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(
        sql`UPDATE report_scores SET narrative_mutation = 4 WHERE report_id = ${reportId}`,
      ),
    )
    expect(e.constraint).toBe('rs_narrative_mutation_range')
  })

  it('refuses a fraction typed on a 0-100 scale', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`UPDATE report_scores SET accrual_pct = 50 WHERE report_id = ${reportId}`),
    )
    expect(e.constraint).toBe('rs_accrual_pct_unit')
  })

  it("refuses NaN, which Postgres sorts ABOVE every real value so '>= 0' alone lets it through", async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`UPDATE report_scores SET accrual_segment_revenue_usd = 'NaN'::float8
                        WHERE report_id = ${reportId}`),
    )
    expect(e.constraint).toBe('rs_segment_revenue_nonneg')
  })

  it('refuses the same person entered twice under a whitespace and case variant', async () => {
    const { reportId } = await createDraftReport(h.db)
    const insert = (position: number, name: string, isFounder: boolean) =>
      h.db.execute(sql`
        INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
        VALUES (${reportId}, ${position}, ${name}, ARRAY['Founder'], ${isFounder},
                3, 1, 0, 'Prior role, with a number in it.')`)
    await insert(1, 'Alice Chen', true)
    const e = await refusal(insert(2, '  alice   CHEN ', false))
    expect(e.constraint).toBe('rt_report_name_key_uniq')
  })

  it('refuses two founders on one report', async () => {
    const { reportId } = await createDraftReport(h.db)
    const insert = (position: number, name: string) =>
      h.db.execute(sql`
        INSERT INTO report_team (report_id, position, name, roles, is_founder, h, m, l, summary)
        VALUES (${reportId}, ${position}, ${name}, ARRAY['Founder'], true,
                3, 1, 0, 'Prior role, with a number in it.')`)
    await insert(1, 'Alice Chen')
    const e = await refusal(insert(2, 'Bob Diaz'))
    expect(e.constraint).toBe('rt_one_founder_per_report')
  })

  it('refuses an off-grid forward-return horizon', async () => {
    const { reportId } = await createDraftReport(h.db)
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO forward_returns
          (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
        VALUES (${reportId}, 60, 2.0, 2.25, 'research/warehouse klines_1d', now())`),
    )
    expect(e.constraint).toBe('fr_horizon_frozen')
  })

  it('computes return_fraction from the two prices rather than storing a typed number', async () => {
    const { reportId } = await createDraftReport(h.db)
    await h.db.execute(sql`
      INSERT INTO forward_returns
        (report_id, horizon_days, price_at_commit_usd, price_at_horizon_usd, price_source, priced_at)
      VALUES (${reportId}, 30, 2.0, 2.25, 'research/warehouse klines_1d', now())`)
    const r = await h.db.execute<{ return_fraction: number }>(
      sql`SELECT return_fraction FROM forward_returns WHERE report_id = ${reportId}`,
    )
    expect(r.rows[0]?.return_fraction).toBeCloseTo(0.125, 12)
  })

  it('refuses a second coin row for the same (chain, contract address)', async () => {
    const address = `0x${randomUUID().replace(/-/g, '')}`
    const insert = () =>
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, contract_address, address_sources)
        VALUES ('TST', 'Test Coin', 'ethereum', ${address},
                '["https://a.example","https://b.example"]'::jsonb)`)
    await insert()
    const e = await refusal(insert())
    expect(e.constraint).toBe('coins_chain_address_uniq')
  })

  it('requires two address sources once there is an address to have sourced', async () => {
    const e = await refusal(
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, contract_address, address_sources)
        VALUES ('TST', 'Test Coin', 'ethereum', ${`0x${randomUUID().replace(/-/g, '')}`},
                '["https://only-one.example"]'::jsonb)`),
    )
    expect(e.constraint).toBe('coins_address_sources_min_2')
  })

  it('does not require them for a native asset, which has no address', async () => {
    await expect(
      h.db.execute(sql`
        INSERT INTO coins (symbol, name, chain, address_sources)
        VALUES ('ETH', 'Ether', 'ethereum', '[]'::jsonb)`),
    ).resolves.toBeDefined()
  })
})
