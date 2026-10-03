import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { createApp } from '../app.ts'
import { openDb } from '../db/client.ts'
import { createDraftReport, TEST_APP_URL } from '../db/testing.ts'

/*
 * The editor's money path, against a real PostgreSQL.
 *
 * Every case here is a defect that was reproduced live before the route existed, so each test is
 * named after what it stops rather than after the route it calls.
 */

const handle = openDb(TEST_APP_URL, 4)
// 0, and deliberately not a count: the number only reaches `/health`, and no case in this file
// calls it. A literal nothing asserts is a number nobody updates — the shape Task 1 removed from
// integrity.test.ts.
const app = createApp(handle.db, 0)

afterAll(() => handle.close())

async function send(path: string, method: string, body: unknown): Promise<Response> {
  return app.request(path, {
    method,
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  })
}

interface Refusal {
  code: string
  message: string
  actualVersion?: number
}

const blankProduct = {
  overviewSentence: null,
  productEase: null,
  productHairFire: null,
  productExclusivity: null,
  productEaseRationale: null,
  productHairFireRationale: null,
  productExclusivityRationale: null,
}

const blankLiquidity = {
  depth: null,
  topPool: null,
  liquidityNoDexPool: false,
  liquidityTier: null,
  liquidityJustification: null,
}

async function readEase(reportId: string): Promise<number | null> {
  const rows = await handle.db.execute<{ product_ease: number | null }>(
    sql`SELECT product_ease FROM report_scores WHERE report_id = ${reportId}`,
  )
  return rows.rows[0]?.product_ease ?? null
}

describe('a typo in a numeric box', () => {
  it('is refused by name and leaves the saved value alone', async () => {
    const { reportId } = await createDraftReport(handle.db)

    const saved = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '7',
    })
    expect(saved.status).toBe(200)
    expect(await readEase(reportId)).toBe(7)

    // Number('seven') is NaN, JSON.stringify(NaN) is null, and null means "clear this field".
    // The string arrives intact instead, so the API can refuse it.
    for (const typed of ['seven', '1,000', '7%', '1e999', '7.5', '-1', '']) {
      const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
        ...blankProduct,
        version: 2,
        productEase: typed,
      })
      expect(refused.status, `"${typed}" was accepted`).toBe(422)
    }
    expect(await readEase(reportId), 'a refused save cleared the column').toBe(7)
  })

  it('rejects 7.5 through the frozen assertIntegerRange, before Postgres can round it', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '7.5',
    })
    expect(refused.status).toBe(422)
    // Postgres stores 7.5 into an integer column as 8 and BETWEEN 0 AND 10 then passes on the
    // rounded value. Verified on 16.13. The CHECK cannot defend the integer ruling alone.
    expect(await readEase(reportId)).toBeNull()
  })

  it('rejects an out-of-range score with the frozen message', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/product`, 'PATCH', {
      ...blankProduct,
      version: 1,
      productEase: '11',
    })
    expect(refused.status).toBe(422)
    expect(JSON.stringify(await refused.json())).toContain('ease must be between 0 and 10, got 11')
  })
})

describe('a measured figure', () => {
  it('cannot be stored as a zero the operator never measured', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      depth: {
        value: '',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        measuredAt: '2026-09-21T10:00:00+02:00',
      },
    })
    expect(refused.status).toBe(422)
    const rows = await handle.db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM report_scores
           WHERE report_id = ${reportId} AND liquidity_depth_2pct_usd IS NOT NULL`,
    )
    expect(rows.rows[0]?.n).toBe(0)
  })

  it('cannot be dated in the future, which would lock the tier forever', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      depth: {
        value: '1000000',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        measuredAt: '2099-01-01T00:00:00+00:00',
      },
    })
    expect(refused.status).toBe(422)
  })

  it('cannot predate the genesis block, where a year typo would read back a century off', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      depth: {
        value: '1000000',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        // '0026' for '2026': a valid ISO string that JavaScript's Date reads back as 1926.
        measuredAt: '0026-09-21T10:00:00+00:00',
      },
    })
    expect(refused.status).toBe(422)
    expect(((await refused.json()) as Refusal).message).toContain('cannot predate 2009-01-03')
  })

  it('says in words that "no DEX pool" contradicts a pool figure', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      liquidityNoDexPool: true,
      topPool: {
        value: '500000',
        source: 'DefiLlama',
        url: 'https://defillama.com/',
        label: 'verified',
        measuredAt: '2026-09-20T09:00:00+00:00',
      },
    })
    expect(refused.status).toBe(422)
    const refusal = (await refused.json()) as Refusal
    expect(refusal.code).toBe('CONSTRAINT_REFUSED')
    expect(refusal.message).toContain('"No DEX pool exists" is ticked')
  })

  it('saves with its tier, and the tier is never older than its inputs', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const saved = await send(`/reports/${reportId}/liquidity`, 'PATCH', {
      ...blankLiquidity,
      version: 1,
      liquidityTier: 'medium',
      liquidityJustification: 'thin but real',
      depth: {
        value: '1000000',
        source: 'CoinGecko',
        url: 'https://coingecko.com/',
        label: 'vendor_claim',
        measuredAt: '2026-09-20T09:00:00+00:00',
      },
    })
    expect(saved.status).toBe(200)
    const rows = await handle.db.execute<{ ok: boolean }>(
      sql`SELECT liquidity_tier_assigned_at >= liquidity_depth_measured_at AS ok
            FROM report_scores WHERE report_id = ${reportId}`,
    )
    expect(rows.rows[0]?.ok).toBe(true)
  })
})

describe('the compare-and-swap token', () => {
  it('is spent by one write, and the second is refused with the real version', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const first = await send(`/reports/${reportId}/risk`, 'PATCH', {
      version: 1,
      riskNotes: 'first',
    })
    expect(first.status).toBe(200)

    const stale = await send(`/reports/${reportId}/risk`, 'PATCH', {
      version: 1,
      riskNotes: 'second',
    })
    expect(stale.status).toBe(409)
    const refusal = (await stale.json()) as Refusal
    expect(refusal.code).toBe('STALE_VERSION')
    expect(refusal.actualVersion).toBe(2)
  })
})

describe('team citations', () => {
  it('refuse to attach to a person the database does not have', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/citations`, 'POST', {
      version: 1,
      field: 'team:11111111-2222-4333-8444-555555555555',
      url: 'https://example.com/bio',
      quote: 'grew revenue to $40m',
    })
    expect(refused.status).toBe(422)
    const refusal = (await refused.json()) as Refusal
    expect(refusal.code).toBe('UNKNOWN_TEAM_MEMBER')
  })

  it('survive a reorder and disappear with the person they named', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const person = (name: string, isFounder: boolean) => ({
      id: null,
      name,
      roles: ['Founder'],
      isFounder,
      h: '4',
      m: '2',
      l: '1',
      summary: `${name} ran a $10m book`,
    })

    const created = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 1,
      members: [person('Ada', true), person('Bo', false), person('Cy', false)],
    })
    expect(created.status).toBe(200)
    const team = (await created.json()) as { version: number; team: { id: string }[] }
    const ada = team.team[0] as { id: string }
    const cy = team.team[2] as { id: string }

    const cited = await send(`/reports/${reportId}/citations`, 'POST', {
      version: team.version,
      field: `team:${cy.id}`,
      url: 'https://example.com/cy',
      quote: 'grew revenue to $40m',
    })
    expect(cited.status).toBe(200)
    const afterCitation = (await cited.json()) as { version: number }

    // A reorder that moves the founder: row-by-row updates trip rt_report_position_uniq and
    // rt_one_founder_per_report halfway through. The whole-set replace cannot.
    const reordered = await send(`/reports/${reportId}/team`, 'PUT', {
      version: afterCitation.version,
      members: [
        { ...person('Bo', false), id: team.team[1]?.id ?? null },
        { ...person('Cy', false), id: cy.id },
        { ...person('Ada', true), id: ada.id },
      ],
    })
    expect(reordered.status).toBe(200)
    expect((await reordered.json()) as { citationsRemoved: number }).toMatchObject({
      citationsRemoved: 0,
    })

    const dropped = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 4,
      members: [{ ...person('Ada', true), id: ada.id }],
    })
    expect(dropped.status).toBe(200)
    expect((await dropped.json()) as { citationsRemoved: number }).toMatchObject({
      citationsRemoved: 1,
    })
  })

  it('names the faulty person counting from 1, as the editor numbers its rows', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const person = (name: string, h: string) => ({
      id: null,
      name,
      roles: ['x'],
      isFounder: name === 'A',
      h,
      m: '1',
      l: '1',
      summary: 's',
    })
    const refused = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 1,
      members: [person('A', '1'), person('B', '1'), person('C', '')],
    })
    expect(refused.status).toBe(422)
    const refusal = (await refused.json()) as Refusal & { issues: { path: string }[] }
    expect(refusal.message.startsWith('members.#3.h: ')).toBe(true)
    expect(refusal.issues[0]?.path, 'the machine-readable path stays zero-based').toBe(
      'members.2.h',
    )
  })

  it('refuses two founders by name rather than by constraint', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const refused = await send(`/reports/${reportId}/team`, 'PUT', {
      version: 1,
      members: [
        {
          id: null,
          name: 'A',
          roles: ['x'],
          isFounder: true,
          h: '1',
          m: '1',
          l: '1',
          summary: 's',
        },
        {
          id: null,
          name: 'B',
          roles: ['x'],
          isFounder: true,
          h: '1',
          m: '1',
          l: '1',
          summary: 's',
        },
      ],
    })
    expect(refused.status).toBe(422)
    expect((await refused.json()) as Refusal).toMatchObject({ code: 'TWO_FOUNDERS' })
  })
})

describe('the report payload', () => {
  it('carries a blocker per conjunct and never calls a commit-written column clear', async () => {
    const { reportId } = await createDraftReport(handle.db)
    const response = await app.request(`/reports/${reportId}`)
    expect(response.status).toBe(200)
    const payload = (await response.json()) as {
      blockers: { code: string; state: string }[]
      bounds: { productSubScoreMax: number; citableFields: Record<string, string> }
      scores: { productEase: number | null }
    }
    expect(payload.scores.productEase).toBeNull()
    expect(payload.bounds.productSubScoreMax).toBe(10)
    expect(payload.bounds.citableFields.liquidityDepth2pctUsd).toBe('liquidity_depth_2pct_usd')
    expect(payload.blockers.some((blocker) => blocker.state === 'unknown')).toBe(true)
    expect(
      payload.blockers.filter((blocker) => blocker.code === 'WAIVED_CITATION_COUNT')[0]?.state,
    ).toBe('unknown')
  })

  it('answers a missing report with 404, not with an undefined scores row', async () => {
    const response = await app.request('/reports/11111111-2222-4333-8444-555555555555')
    expect(response.status).toBe(404)
  })
})
