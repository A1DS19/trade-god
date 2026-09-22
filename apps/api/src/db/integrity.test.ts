import { sql } from 'drizzle-orm'
import { afterAll, describe, expect, it } from 'vitest'
import { openDb } from './client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './integrity.ts'
import { TEST_APP_URL, TEST_OWNER_URL } from './testing.ts'

const app = openDb(TEST_APP_URL, 2)
const owner = openDb(TEST_OWNER_URL, 2)
afterAll(async () => {
  await app.close()
  await owner.close()
})

describe('the boot checks', () => {
  it('passes against a correctly migrated database', async () => {
    await expect(assertGuardsInstalled(owner.db)).resolves.toBeUndefined()
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(3)
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

  it('refuses to serve when a committed migration was never applied', async () => {
    await owner.db.execute(sql`
      DELETE FROM drizzle.__drizzle_migrations
       WHERE created_at = (SELECT max(created_at) FROM drizzle.__drizzle_migrations)`)
    try {
      await expect(assertJournalFullyApplied(owner.db)).rejects.toThrow(
        /3 migrations are committed but 2 are applied/,
      )
    } finally {
      await owner.db.execute(sql`
        INSERT INTO drizzle.__drizzle_migrations (hash, created_at)
        VALUES ('restored-by-integrity-test', (SELECT max(created_at) + 1
                                                 FROM drizzle.__drizzle_migrations))`)
    }
    await expect(assertJournalFullyApplied(owner.db)).resolves.toBe(3)
  })
})
