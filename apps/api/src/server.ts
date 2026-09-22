import { createServer } from 'node:http'
import { sql } from 'drizzle-orm'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { MIGRATIONS_FOLDER, openDb, requireEnv } from './db/client.ts'
import {
  assertGuardsInstalled,
  assertJournalFullyApplied,
  assertNotSuperuser,
} from './db/integrity.ts'

// 8789, not 8787. The sibling project's API container (my-teacher-api-1) holds 8787 permanently
// on this machine, and a server that fails with EADDRINUSE while something ELSE answers /health
// on the same port is how a boot check gets recorded as green without ever having run. Verified:
// curl against 8787 returned {"ok":true,"db":true,"inflight":0} — a different application's
// health shape entirely. Overridable, because the collision is local to this machine.
const PORT = Number(process.env.PORT ?? 8789)

/*
 * Boot, in the order decision A requires and no other.
 *
 * The owner pool exists for the length of the migration and is closed before the app pool is
 * opened. It is not kept around "just in case": a session that owns the tables can DROP
 * TRIGGER in one statement, and if it is not open, nothing a request can reach is able to.
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

/*
 * node:http, not Hono. The HTTP framework and the RPC surface arrive with the editor in
 * build-order step 4; this plan's dependency surface is the database, and /health is the
 * only route that exists before there is anything to edit.
 */
const server = createServer((request, response) => {
  if (request.url !== '/health') {
    response.writeHead(404, { 'content-type': 'application/json' }).end('{"error":"not found"}')
    return
  }
  // SELECT 1 on the APP pool, and the migration count from the boot check. The app role has
  // no USAGE on the `drizzle` schema and must not be given any: /health is not worth widening
  // the request pool's reach by one schema.
  app.db
    .execute(sql`SELECT 1`)
    .then(() => {
      response
        .writeHead(200, { 'content-type': 'application/json' })
        .end(JSON.stringify({ ok: true, migrations: appliedMigrations }))
    })
    .catch((error: unknown) => {
      response
        .writeHead(503, { 'content-type': 'application/json' })
        .end(JSON.stringify({ ok: false, error: String(error) }))
    })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`coinpicks api on http://127.0.0.1:${PORT}, pool user coinpicks_app`)
})
