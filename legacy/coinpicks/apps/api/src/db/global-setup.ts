import { sql } from 'drizzle-orm'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { MIGRATIONS_FOLDER, openDb } from './client.ts'
import { TEST_OWNER_URL } from './testing.ts'

/**
 * Rebuilds `coinpicks_test` from apps/api/drizzle, once per `pnpm test`.
 *
 * DROP SCHEMA rather than TRUNCATE on purpose. `*_no_truncate` refuses TRUNCATE and
 * `*_immutable` refuses DELETE on a committed report's rows, so the usual between-tests
 * reset is impossible by construction — which is the point of the design, so the harness is
 * built around it rather than against it. coinpicks_owner owns coinpicks_test, and the owner
 * of a database is a member of pg_database_owner, which owns schema public.
 */
export async function setup(): Promise<void> {
  const owner = openDb(TEST_OWNER_URL, 1)
  try {
    await owner.db.execute(sql`DROP SCHEMA IF EXISTS drizzle CASCADE`)
    await owner.db.execute(sql`DROP SCHEMA IF EXISTS public CASCADE`)
    await owner.db.execute(sql`CREATE SCHEMA public`)
    await migrate(owner.db, { migrationsFolder: MIGRATIONS_FOLDER })
  } catch (error) {
    throw new Error(
      'could not rebuild coinpicks_test. Run:\n' +
        '  docker compose up -d db\n' +
        '  pnpm --filter @coinpicks/api run db:bootstrap\n' +
        `cause: ${(error as Error).message}`,
      { cause: error },
    )
  } finally {
    await owner.close()
  }
}
