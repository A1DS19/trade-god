import { defineConfig } from 'drizzle-kit'

/**
 * `drizzle-kit generate` only — it needs no database connection, so there are no
 * dbCredentials here on purpose.
 *
 * NEVER run `drizzle-kit push`. It diffs schema.ts against the live database and knows
 * nothing about drizzle/0001_immutability_triggers.sql or drizzle/0002_role_grants.sql,
 * which schema.ts does not and cannot re-emit. A push would leave the ledger unguarded and
 * say nothing.
 */
export default defineConfig({
  dialect: 'postgresql',
  schema: './src/db/schema.ts',
  out: './drizzle',
})
