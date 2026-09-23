import { createFileRoute, Link } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ProductSection } from '../editor/ProductSection.tsx'
import { RiskSection } from '../editor/RiskSection.tsx'
import {
  type ApiError,
  type CitationBody,
  client,
  type Fields,
  type ProductBody,
  type ReportPayload,
  type RiskBody,
  readError,
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

/*
 * This file IS the route, so the report id comes from the router's typed params rather than from
 * a prop nobody passes: `createFileRoute('/reports/$reportId')` is what puts the route in the
 * generated tree, and `Route.useParams()` is what types `reportId` as a string off it.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportEditor })

function ReportEditor() {
  const { reportId } = Route.useParams()
  const [payload, setPayload] = useState<ReportPayload | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [seeds, setSeeds] = useState(FRESH_SEEDS)
  const [conflict, setConflict] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  /*
   * The CAS token, held in a ref as well as in state.
   *
   * `reports.version` is bumped by EVERY successful write, so the token a save sends has to be
   * the one the last response produced — not one read out of a render that may not have happened
   * yet. Deriving it from `payload` inside an async callback is how two saves started close
   * together end up sending the same spent token.
   */
  const current = useRef<ReportPayload | null>(null)
  current.current = payload

  const load = useCallback(async () => {
    const response = await client.reports[':reportId'].$get({ param: { reportId } })
    if (!response.ok) {
      setLoadError(await readError(response))
      return
    }
    setPayload(await response.json())
    setLoadError(null)
  }, [reportId])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * One save: one CAS bump, then a re-read.
   *
   * The re-read is deliberate. The blocker list is computed by the API from the same array that
   * generates the CHECK constraint, and re-reading is what keeps the screen showing the database
   * rather than a client-side guess at what the write did.
   *
   * On a 409 every section is re-seeded from the server and the operator is told. The naive
   * editor seeded each input with `useState(value)` and never re-synced, so after a conflict the
   * boxes kept the losing text and the next save wrote it over the winner.
   */
  const runSave = useCallback(
    async (section: SectionKey | null, call: (version: number) => Promise<Response>) => {
      const report = current.current
      if (report === null) {
        return { code: 'NOT_LOADED', message: 'the report has not loaded yet' }
      }
      setNotice(null)
      const response = await call(report.report.version)
      if (!response.ok) {
        const refusal = await readError(response)
        if (refusal.code === 'STALE_VERSION' || refusal.code === 'ALREADY_COMMITTED') {
          await load()
          setSeeds((previous) => {
            const next = { ...previous }
            for (const key of Object.keys(next) as SectionKey[]) next[key] = previous[key] + 1
            return next
          })
          /*
           * The banner carries the refusal, because the section cannot.
           *
           * Re-seeding changes every section's React `key`, so the component the save was
           * started from unmounts: the `setError(refusal)` useSection runs next lands on an
           * instance that is being replaced, and the red per-section message never renders.
           * ReportEditor itself is not keyed, so this banner survives the remount.
           */
          const why =
            refusal.code === 'STALE_VERSION'
              ? 'This report moved on in another tab.'
              : 'This report is committed and the database refuses every write to it.'
          setConflict(
            `${refusal.code} — ${refusal.message}. ${why} Every section has been reloaded ` +
              'from the database and any unsaved text on this page was discarded.',
          )
        }
        return refusal
      }
      setConflict(null)
      await load()
      /*
       * `null` means "no section owns this write": a citation belongs to whichever section
       * renders it, and bumping one fixed key would silently discard unsaved text in THAT
       * section whenever evidence was attached anywhere else on the page. The new row reaches
       * <Citations> through the `citations` prop that load() refreshed, so no remount is needed.
       */
      if (section !== null) {
        setSeeds((previous) => ({ ...previous, [section]: previous[section] + 1 }))
      }
      return null
    },
    [load],
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

  if (loadError !== null) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p className="text-red-900">
          <strong>{loadError.code}</strong> — {loadError.message}
        </p>
        <Link className="underline" to="/">
          back to the coin list
        </Link>
      </main>
    )
  }

  if (payload === null) return <main className="mx-auto max-w-5xl p-6">Loading…</main>

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
      {conflict === null ? null : (
        <p className="mt-3 border-l-4 border-amber-700 bg-amber-50 py-1 pl-2 text-sm text-amber-900">
          {conflict}
        </p>
      )}
      {notice === null ? null : (
        <p className="mt-3 border-l-4 border-blue-700 bg-blue-50 py-1 pl-2 text-sm text-blue-900">
          {notice}
        </p>
      )}

      <ProductSection {...common} key={`product-${String(seeds.product)}`} onSave={saveProduct} />
      <RiskSection {...common} key={`risk-${String(seeds.risk)}`} onSave={saveRisk} />

      <p className="mt-10 border-t-2 border-neutral-400 pt-4 text-sm text-neutral-600">
        The blocker list lands in Task 6 and the four remaining sections in Task 7.
      </p>
    </main>
  )
}
