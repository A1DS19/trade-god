import { createFileRoute, Link } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { AccrualSection } from '../editor/AccrualSection.tsx'
import { Blockers } from '../editor/Blockers.tsx'
import { LANDED_UNREAD } from '../editor/common.tsx'
import { LiquiditySection } from '../editor/LiquiditySection.tsx'
import { NarrativeSection } from '../editor/NarrativeSection.tsx'
import { ProductSection } from '../editor/ProductSection.tsx'
import { RiskSection } from '../editor/RiskSection.tsx'
import { TeamSection } from '../editor/TeamSection.tsx'
import {
  type AccrualBody,
  type ApiError,
  type CitationBody,
  client,
  type Fields,
  type LiquidityBody,
  type NarrativeBody,
  type ProductBody,
  type ReportPayload,
  type RiskBody,
  readError,
  type TeamBody,
} from '../lib/client.ts'

type SectionKey = 'product' | 'liquidity' | 'narrative' | 'team' | 'accrual' | 'risk'

const FRESH_SEEDS: Record<SectionKey, number> = {
  product: 0,
  liquidity: 0,
  narrative: 0,
  team: 0,
  accrual: 0,
  risk: 0,
}

/** A 409 that means the page is behind the database: every section re-seeds from it. */
const CONFLICTS: ReadonlySet<string> = new Set([
  'STALE_VERSION',
  'ALREADY_COMMITTED',
  'REPORT_COMMITTED',
])

const reason = (error: unknown): string => (error instanceof Error ? error.message : String(error))

/**
 * The payload with a landed write's own answer applied.
 *
 * Every write route answers `{ version }` plus the part of the report it changed -- `scores`
 * (a section patch), `team` (the team put) or `citations` (evidence) -- in the shape the report
 * read serves, because both are the same rows through the same `c.json`.
 */
function withAnswer(payload: ReportPayload, answer: object): ReportPayload {
  const landed = answer as Partial<Pick<ReportPayload, 'citations' | 'scores' | 'team'>> & {
    version?: unknown
  }
  return {
    ...payload,
    citations: landed.citations ?? payload.citations,
    report:
      typeof landed.version === 'number'
        ? { ...payload.report, version: landed.version }
        : payload.report,
    scores: landed.scores ?? payload.scores,
    team: landed.team ?? payload.team,
  }
}

/*
 * This file IS the route, so the report id comes from the router's typed params rather than from
 * a prop nobody passes: `createFileRoute('/reports/$reportId')` is what puts the route in the
 * generated tree, and `Route.useParams()` is what types `reportId` as a string off it.
 *
 * ReportRoute keys the editor on that id. The router keeps a matched component mounted across a
 * param change, so without the key a navigation from one report to another kept the first
 * report's forms, and the next Save wrote report A's text into report B.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportRoute })

function ReportRoute() {
  const { reportId } = Route.useParams()
  return <ReportEditor key={reportId} reportId={reportId} />
}

function ReportEditor({ reportId }: { reportId: string }) {
  const [payload, setPayload] = useState<ReportPayload | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [seeds, setSeeds] = useState(FRESH_SEEDS)
  const [errors, setErrors] = useState<Partial<Record<SectionKey, ApiError | null>>>({})
  const [conflict, setConflict] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  /*
   * The CAS token, in a ref that load() writes the moment a read lands.
   *
   * `reports.version` is bumped by EVERY successful write, so a write must carry the version the
   * latest read returned. Reading it off `payload` meant reading the last RENDER, which trails the
   * last read -- and together with unserialised writes, two actions started within one round trip
   * sent the same spent token, and this tab's own second write came back STALE_VERSION, blamed on
   * "another tab".
   */
  const current = useRef<ReportPayload | null>(null)
  /** True while a write is in flight. One at a time; see writeOnce. */
  const writing = useRef(false)

  /** Never rejects: a read that fails ends as a named refusal, not as "Loading…" forever. */
  const load = useCallback(async (): Promise<ApiError | null> => {
    try {
      const response = await client.reports[':reportId'].$get({ param: { reportId } })
      if (!response.ok) {
        const refusal = await readError(response)
        setLoadError(refusal)
        return refusal
      }
      const next = await response.json()
      current.current = next
      setPayload(next)
      setLoadError(null)
      return null
    } catch (error) {
      const refusal = { code: 'UNREACHABLE', message: `the API did not answer (${reason(error)})` }
      setLoadError(refusal)
      return refusal
    }
  }, [reportId])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * After a 409: re-read, re-seed every section from the database, and say so.
   *
   * The naive editor seeded each input with `useState(value)` and never re-synced, so after a
   * conflict the boxes kept the losing text and the next save wrote it over the winner. Evidence
   * typed but not yet added is kept: it is not report data, and the database has no version of it
   * to prefer.
   */
  const reseedAll = useCallback(
    async (refusal: ApiError) => {
      const why =
        refusal.code === 'STALE_VERSION'
          ? 'This report moved on in another tab.'
          : 'This report is committed and the database refuses every write to it.'
      const reread = await load()
      if (reread !== null) {
        setConflict(
          `${refusal.code} — ${refusal.message}. ${why} Re-reading it failed as well ` +
            `(${reread.code}), so reload the page before editing further.`,
        )
        return
      }
      setSeeds((previous) => {
        const next = { ...previous }
        for (const key of Object.keys(next) as SectionKey[]) next[key] = previous[key] + 1
        return next
      })
      setErrors({})
      setConflict(
        `${refusal.code} — ${refusal.message}. ${why} Every section has been reloaded from the ` +
          'database and its unsaved edits were discarded; evidence typed but not yet added is ' +
          'still in its box.',
      )
    },
    [load],
  )

  /**
   * One write: one CAS bump, then a re-read. It never rejects -- every way it can end is a named
   * refusal or null -- so nothing that called it can be left on "Saving…".
   *
   * The re-read is deliberate. The blocker list is computed by the API from the same array that
   * generates the CHECK constraint, and re-reading is what keeps the screen showing the database
   * rather than a client-side guess at what the write did.
   *
   * ONE WRITE AT A TIME. A second write started while one is in flight is refused as BUSY, beside
   * the control that was pressed. Queuing it instead would send a body built from the screen as it
   * stood BEFORE the first write's outcome -- after a 409, text the database has just refused.
   */
  const writeOnce = useCallback(
    async (
      section: SectionKey | null,
      call: (version: number) => Promise<Response>,
    ): Promise<ApiError | null> => {
      const report = current.current
      if (report === null) return { code: 'NOT_LOADED', message: 'the report has not loaded yet' }
      if (writing.current) {
        return {
          code: 'BUSY',
          message: 'another save on this page is still in flight — press again once it lands',
        }
      }
      writing.current = true
      setNotice(null)
      try {
        const response = await call(report.report.version)
        if (!response.ok) {
          const refusal = await readError(response)
          if (CONFLICTS.has(refusal.code)) await reseedAll(refusal)
          return refusal
        }
        /*
         * Apply the landed write's own answer, THEN re-read. The answer is authoritative for what
         * this write changed, so if the re-read fails the page still holds the version this
         * write produced and the section re-seeds from what the database stored. Without it a
         * failed re-read left a spent token -- the next save came back STALE_VERSION, blamed on
         * "another tab" -- and a team form holding `id: null` for a person the database had just
         * created, whose next save re-created them and deleted their evidence. A write from a
         * genuinely other tab is still caught: this is the version our screen is based on.
         *
         * The body is read best-effort: `response.ok` already says the write landed, and a body
         * cut on the way back must not be reported as a write that did not happen.
         */
        const answer: unknown = await response.json().catch(() => null)
        const answered = typeof answer === 'object' && answer !== null
        if (answered) {
          const landed = withAnswer(report, answer)
          current.current = landed
          setPayload(landed)
        }
        setConflict(null)
        const reread = await load()
        /*
         * `null` means "no section owns this write": a citation belongs to whichever section
         * renders it, and bumping one fixed token would silently discard unsaved text in THAT
         * section whenever evidence was attached anywhere else on the page. The new row reaches
         * <Citations> through the `citations` prop. With neither the answer nor the re-read
         * there is nothing newer to re-seed from, so the section keeps what was typed.
         */
        if (section !== null && (answered || reread === null)) {
          setSeeds((previous) => ({ ...previous, [section]: previous[section] + 1 }))
        }
        if (reread !== null) {
          return {
            code: LANDED_UNREAD,
            message:
              `saved, but re-reading the report failed (${reread.code} — ${reread.message}). ` +
              'The blocker list may be behind; reload the page to see what the database holds.',
          }
        }
        return null
      } catch (error) {
        return {
          code: 'UNREACHABLE',
          message:
            `the request did not complete (${reason(error)}). Reload before saving again: if ` +
            'the write landed, the version has moved.',
        }
      } finally {
        writing.current = false
      }
    },
    [load, reseedAll],
  )

  /** A write, with its outcome filed under the section that made it. */
  const runSave = useCallback(
    async (section: SectionKey | null, call: (version: number) => Promise<Response>) => {
      const refusal = await writeOnce(section, call)
      if (section !== null) setErrors((previous) => ({ ...previous, [section]: refusal }))
      return refusal
    },
    [writeOnce],
  )

  const saveProduct = useCallback(
    (fields: Fields<ProductBody>) =>
      runSave('product', (version) =>
        client.reports[':reportId'].product.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveLiquidity = useCallback(
    (fields: Fields<LiquidityBody>) =>
      runSave('liquidity', (version) =>
        client.reports[':reportId'].liquidity.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveNarrative = useCallback(
    (fields: Fields<NarrativeBody>) =>
      runSave('narrative', (version) =>
        client.reports[':reportId'].narrative.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveAccrual = useCallback(
    (fields: Fields<AccrualBody>) =>
      runSave('accrual', (version) =>
        client.reports[':reportId'].accrual.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveRisk = useCallback(
    (fields: Fields<RiskBody>) =>
      runSave('risk', (version) =>
        client.reports[':reportId'].risk.$patch({
          param: { reportId },
          json: { ...fields, version },
        }),
      ),
    [reportId, runSave],
  )

  const saveTeam = useCallback(
    (fields: Fields<TeamBody>) =>
      runSave('team', async (version) => {
        const response = await client.reports[':reportId'].team.$put({
          param: { reportId },
          json: { ...fields, version },
        })
        if (response.ok) {
          // A clone: writeOnce reads the original for the version this write produced.
          const body = (await response.clone().json()) as Awaited<ReturnType<typeof response.json>>
          if (body.citationsRemoved > 0) {
            setNotice(
              `${String(body.citationsRemoved)} citation(s) belonging to removed team members ` +
                'were deleted. Evidence pointing at nobody would still have been counted.',
            )
          }
        }
        return response
      }),
    [reportId, runSave],
  )

  const addCitation = useCallback(
    (input: Fields<CitationBody>) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations.$post({
          param: { reportId },
          json: { ...input, version },
        }),
      ),
    [reportId, runSave],
  )

  const removeCitation = useCallback(
    (citationId: string) =>
      runSave(null, (version) =>
        client.reports[':reportId'].citations[':citationId'].$delete({
          param: { reportId, citationId },
          query: { version: String(version) },
        }),
      ),
    [reportId, runSave],
  )

  if (payload === null) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        {loadError === null ? (
          'Loading…'
        ) : (
          <>
            <p className="text-red-900" role="alert">
              <strong>{loadError.code}</strong> — {loadError.message}
            </p>
            <Link className="underline" to="/">
              back to the coin list
            </Link>
          </>
        )}
      </main>
    )
  }

  const closed = payload.report.status !== 'draft'
  const common = {
    bounds: payload.bounds,
    citations: payload.citations,
    disabled: closed,
    onAddCitation: addCitation,
    onRemoveCitation: removeCitation,
    scores: payload.scores,
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <Link className="text-sm underline" to="/">
        ← all coins
      </Link>
      <h1 className="mt-2 text-2xl font-medium">
        {payload.coin.symbol} — {payload.coin.name}
      </h1>
      <p className="text-sm text-neutral-600">
        {payload.coin.chain} · {payload.report.status} · version {payload.report.version} ·
        framework {payload.bounds.scoringVersion}
      </p>
      {closed ? (
        <p className="mt-3 border-l-4 border-neutral-700 bg-neutral-100 py-1 pl-2 text-sm">
          This report is committed. It is immutable at the database level; every field below is
          read-only.
        </p>
      ) : null}
      {/* A failed RE-read keeps the editor on screen: replacing it would discard every section's
          unsaved text over a read that may succeed on the next try. */}
      {loadError === null ? null : (
        <p
          className="mt-3 border-l-4 border-red-700 bg-red-50 py-1 pl-2 text-sm text-red-900"
          role="alert"
        >
          The last re-read failed: <strong>{loadError.code}</strong> — {loadError.message}. What is
          on screen may be behind the database; reload the page.
        </p>
      )}
      {conflict === null ? null : (
        <p
          className="mt-3 border-l-4 border-amber-700 bg-amber-50 py-1 pl-2 text-sm text-amber-900"
          role="alert"
        >
          {conflict}
        </p>
      )}
      {notice === null ? null : (
        <p className="mt-3 border-l-4 border-blue-700 bg-blue-50 py-1 pl-2 text-sm text-blue-900">
          {notice}
        </p>
      )}

      <ProductSection
        {...common}
        error={errors.product ?? null}
        onSave={saveProduct}
        seedToken={seeds.product}
      />
      <LiquiditySection
        {...common}
        error={errors.liquidity ?? null}
        onSave={saveLiquidity}
        seedToken={seeds.liquidity}
      />
      <NarrativeSection
        {...common}
        error={errors.narrative ?? null}
        onSave={saveNarrative}
        seedToken={seeds.narrative}
      />
      <TeamSection
        {...common}
        error={errors.team ?? null}
        onSave={saveTeam}
        seedToken={seeds.team}
        team={payload.team}
      />
      <AccrualSection
        {...common}
        error={errors.accrual ?? null}
        onSave={saveAccrual}
        seedToken={seeds.accrual}
      />
      <RiskSection
        {...common}
        error={errors.risk ?? null}
        onSave={saveRisk}
        seedToken={seeds.risk}
      />

      <Blockers blockers={payload.blockers} />
    </main>
  )
}
