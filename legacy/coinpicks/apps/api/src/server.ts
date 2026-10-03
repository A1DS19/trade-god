import { serve } from '@hono/node-server'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { createApp } from './app.ts'
import { MIGRATIONS_FOLDER, openDb, requireEnv } from './db/client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './db/integrity.ts'

// 8789. Overridable through PORT, because a port collision is local to a machine: the editor's
// vite dev server proxies /api here, and a server that fails with EADDRINUSE while something
// ELSE answers on the same port is how a boot check gets recorded as green without ever having
// run. /health carries `scoringVersion` so the answer can be attributed to THIS application.
const PORT = Number(process.env.PORT ?? 8789)

/*
 * Boot, in the order decision A requires and no other.
 *
 * The owner pool exists for the length of the migration and is closed before the app pool is
 * opened. It is not kept around "just in case": a session that owns the tables can DROP TRIGGER
 * in one statement, and if it is not open, nothing a request can reach is able to.
 */
const owner = openDb(requireEnv('DATABASE_URL_OWNER'), 1)
let appliedMigrations = 0
try {
  await migrate(owner.db, { migrationsFolder: MIGRATIONS_FOLDER })
  appliedMigrations = await assertJournalFullyApplied(owner.db)
  await assertGuardsInstalled(owner.db)
} finally {
  await owner.close()
}

const app = openDb(requireEnv('DATABASE_URL'))
await assertNotSuperuser(app.db)

serve(
  { fetch: createApp(app.db, appliedMigrations).fetch, hostname: '127.0.0.1', port: PORT },
  () => {
    console.log(`coinpicks api on http://127.0.0.1:${PORT}, pool user coinpicks_app`)
  },
)
