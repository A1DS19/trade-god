import { sql } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import { TEST_APP_URL, TEST_OWNER_URL, TEST_RESEARCH_URL, refusal } from './testing.ts'

/**
 * Decision A, asserted rather than assumed: the request pool must not be able to turn the
 * immutability triggers off. `SET session_replication_role = replica` is the statement an
 * attacker used to flip a committed report back to draft and then delete it, and only a
 * superuser may issue it.
 */
describe('the two-role split', () => {
  it('connects as coinpicks_owner, which owns the tables', async () => {
    const h = openDb(TEST_OWNER_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'coinpicks_owner', sup: false })
    await h.close()
  })

  it('connects as coinpicks_app, which is not a superuser and cannot enter replica mode', async () => {
    const h = openDb(TEST_APP_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'coinpicks_app', sup: false })

    const e = await refusal(h.db.execute(sql`SET session_replication_role = replica`))
    expect(e.code).toBe('42501')
    expect(e.message).toBe('permission denied to set parameter "session_replication_role"')
    await h.close()
  })

  it('connects as research, which is not a superuser either', async () => {
    const h = openDb(TEST_RESEARCH_URL, 1)
    const r = await h.db.execute<{ who: string; sup: boolean }>(
      sql`SELECT current_user AS who, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS sup`,
    )
    expect(r.rows[0]).toEqual({ who: 'research', sup: false })
    await h.close()
  })
})
