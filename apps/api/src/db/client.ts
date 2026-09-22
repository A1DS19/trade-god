import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { drizzle, type NodePgDatabase } from 'drizzle-orm/node-postgres'
import { Pool } from 'pg'
import * as schema from './schema.ts'

export type Db = NodePgDatabase<typeof schema>

/** The transaction handle drizzle hands the callback. Named once so nothing re-derives it. */
export type Tx = Parameters<Parameters<Db['transaction']>[0]>[0]

export interface DbHandle {
  db: Db
  pool: Pool
  close: () => Promise<void>
}

/** apps/api/drizzle — the committed .sql files plus meta/_journal.json. */
export const MIGRATIONS_FOLDER = resolve(dirname(fileURLToPath(import.meta.url)), '../../drizzle')

/**
 * One pool, one drizzle handle, one way to close them. `max` is small by default because the
 * compose service runs with max_connections=30 and this is a single-user ledger.
 */
export function openDb(connectionString: string, max = 10): DbHandle {
  const pool = new Pool({ connectionString, max })
  const db = drizzle(pool, { schema })
  return { db, pool, close: () => pool.end() }
}

export function requireEnv(name: string): string {
  const value = process.env[name]
  if (value === undefined || value.trim() === '') {
    throw new Error(
      `${name} is not set. Copy .env.example to .env and run \`docker compose up -d db\`. ` +
        'A ledger with no database is not a degraded mode worth having.',
    )
  }
  return value
}
