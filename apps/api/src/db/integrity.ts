import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { sql } from 'drizzle-orm'
import { type Db, MIGRATIONS_FOLDER } from './client.ts'

/**
 * Every trigger the ledger's immutability depends on. `tgenabled` must be 'A' — ENABLE
 * ALWAYS. An 'O' (the default, ORIGIN) is silenced by `SET session_replication_role =
 * replica`, which was confirmed live to flip a committed report back to draft and delete it.
 */
export const REQUIRED_TRIGGERS = [
  'citations_immutable',
  'citations_no_truncate',
  'citations_reset_verification',
  'forward_returns_no_truncate',
  'report_scores_immutable',
  'report_scores_no_truncate',
  'report_team_immutable',
  'report_team_no_truncate',
  'reports_assert_commitable',
  'reports_immutable',
  'reports_no_truncate',
  'reports_seed_scores',
] as const

/**
 * The three functions that raise CP001. Checked for the string rather than for a hash of the
 * body: a hash would have to be re-pinned every time a comment is reflowed, and a literal
 * that cries wolf gets deleted. A body that no longer contains 'CP001' is a gutted guard,
 * which is the failure worth being loud about.
 */
export const GUARD_FUNCTIONS = [
  'coinpicks_report_child_immutable',
  'coinpicks_refuse_truncate',
  'coinpicks_reports_immutable',
] as const

/** Runs between the migrator and the port. Ten lines, one millisecond, and it turns a
 *  dropped trigger from silent into a refusal to start. */
export async function assertGuardsInstalled(db: Db): Promise<void> {
  const problems: string[] = []

  const triggers = await db.execute<{ tgname: string; tgenabled: string }>(sql`
    SELECT t.tgname, t.tgenabled
      FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE NOT t.tgisinternal AND n.nspname = 'public'`)
  const state = new Map(triggers.rows.map((row) => [row.tgname, row.tgenabled]))
  for (const name of REQUIRED_TRIGGERS) {
    const enabled = state.get(name)
    if (enabled === undefined) problems.push(`trigger ${name} is missing`)
    else if (enabled !== 'A') problems.push(`trigger ${name} is '${enabled}', not ENABLE ALWAYS`)
  }

  // LIKE 'coinpicks%' without an underscore wildcard: escaping a backslash through a drizzle
  // sql template is exactly the trap that turned '\s+' into 's+' in an earlier draft.
  const functions = await db.execute<{ proname: string; prosrc: string }>(sql`
    SELECT p.proname, p.prosrc
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname LIKE 'coinpicks%'`)
  const bodies = new Map(functions.rows.map((row) => [row.proname, row.prosrc]))
  for (const name of GUARD_FUNCTIONS) {
    const body = bodies.get(name)
    if (body === undefined) problems.push(`function ${name}() is missing`)
    else if (!body.includes('CP001')) problems.push(`function ${name}() no longer raises CP001`)
  }

  if (problems.length > 0) {
    throw new Error(
      `the immutability guards are not intact, refusing to serve:\n  ${problems.join('\n  ')}`,
    )
  }
}

/**
 * Drizzle's migrator selects the single most recent applied row and applies a file only when
 * its journal timestamp is newer. The `hash` column is inserted and never compared, so an
 * already-applied file can be edited silently; worse, a file whose `when` is OLDER than the
 * newest applied row is skipped permanently and the migrator exits 0. For a project whose
 * product is an immutable ledger, a migration that silently did not run is worth shouting
 * about.
 */
export async function assertJournalFullyApplied(db: Db): Promise<number> {
  const journal = JSON.parse(
    readFileSync(resolve(MIGRATIONS_FOLDER, 'meta/_journal.json'), 'utf8'),
  ) as { entries: unknown[] }
  const applied = await db.execute<{ n: number }>(
    sql`SELECT count(*)::int AS n FROM drizzle.__drizzle_migrations`,
  )
  const n = applied.rows[0]?.n ?? 0
  if (n !== journal.entries.length) {
    throw new Error(
      `${journal.entries.length} migrations are committed but ${n} are applied. Drizzle's ` +
        'migrator compares only the newest applied row and never checks a hash, so an ' +
        'out-of-order file is skipped silently. Refusing to serve.',
    )
  }
  return n
}

/** Decision A, asserted at every boot: the request pool is not the migrator's role and is
 *  not a superuser, so nothing it can send can silence a trigger. */
export async function assertNotSuperuser(db: Db): Promise<void> {
  const who = await db.execute<{ rolname: string; rolsuper: boolean }>(
    sql`SELECT rolname, rolsuper FROM pg_roles WHERE rolname = current_user`,
  )
  const row = who.rows[0]
  if (row === undefined) throw new Error('current_user has no pg_roles row')
  if (row.rolsuper) {
    throw new Error(
      `the request pool is connected as ${row.rolname}, a SUPERUSER. A superuser can SET ` +
        'session_replication_role = replica and silence every immutability trigger. Point ' +
        'DATABASE_URL at coinpicks_app. Refusing to serve.',
    )
  }
}
