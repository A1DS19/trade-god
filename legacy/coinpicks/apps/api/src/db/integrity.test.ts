import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { MIGRATIONS_FOLDER, openDb } from './client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './integrity.ts'
import { TEST_APP_URL, TEST_OWNER_URL } from './testing.ts'

/** Read from the journal rather than written down: every new migration would otherwise edit
 *  two assertions in this file, and a number nobody updates is a test that gets deleted. */
const JOURNALLED = (
  JSON.parse(readFileSync(resolve(MIGRATIONS_FOLDER, 'meta/_journal.json'), 'utf8')) as {
    entries: unknown[]
  }
).entries.length

const app = openDb(TEST_APP_URL, 2)
const owner = openDb(TEST_OWNER_URL, 2)
afterAll(async () => {
  await app.close()
  await owner.close()
})

describe('the boot checks', () => {
  it('passes against a correctly migrated database', async () => {
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
    await expect(assertNotSuperuser(app.db)).resolves.toBeUndefined()
  })

  it('refuses to serve when a trigger has been disabled', async () => {
    await owner.db.execute(sql`ALTER TABLE citations DISABLE TRIGGER citations_immutable`)
    try {
      await expect(assertGuardsInstalled(owner.db)).rejects.toThrow(
        /citations_immutable is 'D', not ENABLE ALWAYS/,
      )
    } finally {
      await owner.db.execute(sql`ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_immutable`)
    }
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
  })

  it('refuses to serve when a guard function has been gutted', async () => {
    await owner.db.execute(sql`
      CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
      LANGUAGE plpgsql AS $fn$ BEGIN RETURN NULL; END $fn$`)
    try {
      await expect(assertGuardsInstalled(owner.db)).rejects.toThrow(
        /coinpicks_refuse_truncate\(\) no longer raises CP001/,
      )
    } finally {
      await owner.db.execute(sql`
        CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
          RAISE EXCEPTION 'TRUNCATE on % is refused: this table is an append-only ledger',
            TG_TABLE_NAME USING ERRCODE = 'CP001';
        END $fn$`)
    }
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
  })

  /** The newest applied row, lifted out so the `finally` can put back exactly what it found.
   *  Restoring an invented hash at `max(created_at) + 1` leaves the database one migration
   *  short with a total that still adds up, and drizzle then re-applies the real file at the
   *  next boot because its `when` is newer than the fake row's. */
  async function newestAppliedRow(): Promise<{ hash: string; created_at: string }> {
    const found = await owner.db.execute<{ hash: string; created_at: string }>(sql`
      SELECT hash, created_at FROM drizzle.__drizzle_migrations
       ORDER BY created_at DESC LIMIT 1`)
    const row = found.rows[0]
    if (row === undefined) throw new Error('no applied migrations to remove')
    return row
  }

  it('refuses to serve when a committed migration was never applied', async () => {
    const victim = await newestAppliedRow()
    await owner.db.execute(
      sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = ${victim.created_at}`,
    )
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        `${String(JOURNALLED)} migrations are committed but ${String(JOURNALLED - 1)} are applied`,
      )
    } finally {
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES (${victim.hash}, ${victim.created_at})`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
  })

  it('refuses to serve when the count is right but the set is wrong', async () => {
    const victim = await newestAppliedRow()
    await owner.db.execute(
      sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = ${victim.created_at}`,
    )
    await owner.db.execute(sql`
      INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
      VALUES ('a row that only makes the count add up', 1)`)
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        /the migration count matches, but 1 committed migration\(s\) are not applied/,
      )
    } finally {
      await owner.db.execute(sql`DELETE FROM drizzle.__drizzle_migrations WHERE created_at = 1`)
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES (${victim.hash}, ${victim.created_at})`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(JOURNALLED)
  })
})
