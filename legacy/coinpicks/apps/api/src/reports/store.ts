import { and, asc, eq } from 'drizzle-orm'
import type { Db, Tx } from '../db/client.ts'
import {
  type CitationRow,
  type CoinRow,
  citations,
  coins,
  type ReportRow,
  type ReportScoresRow,
  type ReportTeamRow,
  reportScores,
  reports,
  reportTeam,
} from '../db/schema.ts'
import { casBumpVersion } from './cas.ts'
import { teamMemberIdOf } from './citable-fields.ts'
import type { ScoresPatch } from './draft-columns.ts'
import { ReportNotFoundError, UnknownTeamMemberError } from './errors.ts'

export interface ReportPayload {
  report: ReportRow
  coin: CoinRow
  scores: ReportScoresRow
  team: ReportTeamRow[]
  citations: CitationRow[]
}

/** Either handle reads the same way; only writes care which one they are on. */
type Reader = Pick<Db | Tx, 'select'>

function readTeam(reader: Reader, reportId: string): Promise<ReportTeamRow[]> {
  return reader
    .select()
    .from(reportTeam)
    .where(eq(reportTeam.reportId, reportId))
    .orderBy(asc(reportTeam.position))
}

function readCitations(reader: Reader, reportId: string): Promise<CitationRow[]> {
  return reader
    .select()
    .from(citations)
    .where(eq(citations.reportId, reportId))
    .orderBy(asc(citations.createdAt))
}

/**
 * The whole report, or null when there is no such row.
 *
 * The `scores` row is joined rather than left optional. `reports_seed_scores` guarantees it
 * exists, but `rows[0]` is `T | undefined` under `noUncheckedIndexedAccess`, and a bare
 * `c.json({ scores })` would put that `| undefined` on the wire — roughly forty TS18048s in the
 * editor, none of which the operator can do anything about.
 */
export async function readReport(db: Db, reportId: string): Promise<ReportPayload | null> {
  const rows = await db
    .select({ report: reports, coin: coins, scores: reportScores })
    .from(reports)
    .innerJoin(coins, eq(coins.id, reports.coinId))
    .innerJoin(reportScores, eq(reportScores.reportId, reports.id))
    .where(eq(reports.id, reportId))
    .limit(1)

  const row = rows[0]
  if (row === undefined) return null

  return {
    report: row.report,
    coin: row.coin,
    scores: row.scores,
    team: await readTeam(db, reportId),
    citations: await readCitations(db, reportId),
  }
}

/**
 * One section, one CAS bump, one transaction.
 *
 * Ruled 2026-09-21: an explicit Save per section, not save-on-blur. `casBumpVersion` bumps
 * `reports.version` on EVERY successful call, so per-field blur saves fire many CAS writes, and
 * two edits started before the first response lands means the second is refused 409 while the
 * screen still shows it as entered.
 */
export function saveSection(
  db: Db,
  reportId: string,
  expectedVersion: number,
  patch: ScoresPatch,
): Promise<{ version: number; scores: ReportScoresRow }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)
    const saved = await tx
      .update(reportScores)
      .set(patch)
      .where(eq(reportScores.reportId, reportId))
      .returning()
    const scores = saved[0]
    if (scores === undefined) throw new ReportNotFoundError(reportId)
    return { version, scores }
  })
}

export interface TeamMemberInput {
  id: string | null
  name: string
  roles: string[]
  isFounder: boolean
  h: number
  m: number
  l: number
  summary: string
}

/**
 * The whole team, replaced in one transaction.
 *
 * Row-by-row editing cannot express a reorder: `rt_report_position_uniq` is not deferrable, so
 * swapping two people trips 23505 halfway through, and moving the founder trips
 * `rt_one_founder_per_report` the same way. Deleting every row and re-inserting in array order
 * sidesteps both, and the array index IS the position, so nothing on the wire can claim a slot
 * twice.
 *
 * A person who already exists keeps their `id`, which is what keeps their `team:<uuid>`
 * citations attached. Citations naming a member who did not survive are deleted here: evidence
 * pointing at nobody would otherwise still be counted by the commit gate.
 */
export function replaceTeam(
  db: Db,
  reportId: string,
  expectedVersion: number,
  members: TeamMemberInput[],
): Promise<{ version: number; team: ReportTeamRow[]; citationsRemoved: number }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)

    await tx.delete(reportTeam).where(eq(reportTeam.reportId, reportId))

    const inserted =
      members.length === 0
        ? []
        : await tx
            .insert(reportTeam)
            .values(
              members.map((member, index) => ({
                // A null id is a person who has never been saved; Postgres mints one.
                ...(member.id === null ? {} : { id: member.id }),
                reportId,
                position: index + 1,
                name: member.name,
                roles: member.roles,
                isFounder: member.isFounder,
                h: member.h,
                m: member.m,
                l: member.l,
                summary: member.summary,
              })),
            )
            .returning()

    const surviving = new Set(inserted.map((row) => row.id))
    const existing = await tx
      .select({ id: citations.id, field: citations.field })
      .from(citations)
      .where(eq(citations.reportId, reportId))

    let citationsRemoved = 0
    for (const citation of existing) {
      const memberId = teamMemberIdOf(citation.field)
      if (memberId === null || surviving.has(memberId)) continue
      await tx.delete(citations).where(eq(citations.id, citation.id))
      citationsRemoved += 1
    }

    return { version, team: inserted, citationsRemoved }
  })
}

export interface CitationInput {
  field: string
  url: string
  quote: string
}

/**
 * Add a human citation.
 *
 * `origin` is always `'human'` and `status` keeps its `'unverified'` default — step 4 writes no
 * other value. `selected_at` is stamped on insert: a citation the operator typed is selected by
 * definition, and `selected_at IS NULL` is reserved for an unselected MODEL candidate (step 8).
 *
 * A `team:<uuid>` field is checked against `report_team` INSIDE the transaction. `citations.field`
 * is plain text with no foreign key, and the naive editor minted a browser-side uuid for a new
 * person and offered their evidence box before the person was ever saved — so a citation could
 * point at a `report_team.id` that does not exist, and the commit gate would count it as evidence.
 */
export function addCitation(
  db: Db,
  reportId: string,
  expectedVersion: number,
  input: CitationInput,
): Promise<{ version: number; citations: CitationRow[] }> {
  return db.transaction(async (tx) => {
    const memberId = teamMemberIdOf(input.field)
    if (memberId !== null) {
      const member = await tx
        .select({ id: reportTeam.id })
        .from(reportTeam)
        .where(and(eq(reportTeam.reportId, reportId), eq(reportTeam.id, memberId)))
        .limit(1)
      if (member[0] === undefined) throw new UnknownTeamMemberError(input.field)
    }

    const version = await casBumpVersion(tx, reportId, expectedVersion)
    await tx.insert(citations).values({
      reportId,
      field: input.field,
      url: input.url,
      quote: input.quote,
      origin: 'human',
      selectedAt: new Date(),
    })
    return { version, citations: await readCitations(tx, reportId) }
  })
}

export function removeCitation(
  db: Db,
  reportId: string,
  expectedVersion: number,
  citationId: string,
): Promise<{ version: number; citations: CitationRow[] }> {
  return db.transaction(async (tx) => {
    const version = await casBumpVersion(tx, reportId, expectedVersion)
    await tx
      .delete(citations)
      .where(and(eq(citations.reportId, reportId), eq(citations.id, citationId)))
    return { version, citations: await readCitations(tx, reportId) }
  })
}
