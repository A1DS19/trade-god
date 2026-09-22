import type { AppType } from '@coinpicks/api'
import { hc, type InferRequestType, type InferResponseType } from 'hono/client'

/*
 * `import type`, and the whole line is type-only.
 *
 * The mixed form -- `import` then `{ type AppType, createApp }` -- is one word different and a
 * genuine value use. tsc accepts it under `verbatimModuleSyntax`, biome's `useImportType` does
 * not fire on it, and the client bundle goes from 583,379 to 727,230 bytes with this project's
 * DDL in it. Three things hold this line in place, in the order they fire: the Start plugin's
 * `importProtection` (vite.config.ts) fails the BUILD with an import trace, `boundary.test.ts`
 * reads this source, and `bundle.test.ts` reads dist/client -- which is the browser's half of a
 * Start build, and the only half a client-side scan may look at.
 */

/*
 * TanStack Start renders this app on the server as well as in the browser, so this module is
 * evaluated in a place where `window` does not exist. `import.meta.env.SSR` is replaced by a
 * literal at build time — `true` in the server bundle, `false` in the client bundle — so the
 * branch not taken is eliminated rather than guarded, and neither bundle carries a reference to
 * a global it does not have.
 *
 * Browser: same-origin `/api`, which `src/routes/api.$.ts` forwards to the Hono API in dev and
 * in production alike. Server: the loopback origin directly, no hop.
 */
const API_BASE = import.meta.env.SSR
  ? (import.meta.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:8789')
  : `${window.location.origin}/api`

export const client = hc<AppType>(API_BASE)

export type ReportPayload = InferResponseType<(typeof client.reports)[':reportId']['$get'], 200>
export type Scores = ReportPayload['scores']
export type TeamRow = ReportPayload['team'][number]
export type Citation = ReportPayload['citations'][number]
export type Blocker = ReportPayload['blockers'][number]
export type Bounds = ReportPayload['bounds']

export type CoinRows = InferResponseType<typeof client.coins.$get, 200>['rows']

type JsonOf<T> = T extends { json: infer J } ? J : never

export type ProductBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['product']['$patch']>
>
export type LiquidityBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['liquidity']['$patch']>
>
export type NarrativeBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['narrative']['$patch']>
>
export type AccrualBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['accrual']['$patch']>
>
export type RiskBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['risk']['$patch']>
>
export type TeamBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['team']['$put']>
>
export type CitationBody = JsonOf<
  InferRequestType<(typeof client.reports)[':reportId']['citations']['$post']>
>

/** A section's fields, with the CAS token removed — the editor never chooses it. */
export type Fields<T> = Omit<T, 'version'>

export interface ApiError {
  code: string
  message: string
  actualVersion?: number
}

/**
 * The refusal, in the shape every route's `onError` and validator hook produce.
 *
 * Never throws: a failed save must always end with something legible beside the Save button, and
 * "the server said something I could not parse" is legible.
 */
export async function readError(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return { code: 'UNREADABLE', message: `HTTP ${response.status} with no JSON body` }
  }
  const record = body as Record<string, unknown>
  const code = typeof record.code === 'string' ? record.code : `HTTP_${response.status}`
  const message =
    typeof record.message === 'string' ? record.message : `the server refused it (${code})`
  const actualVersion = typeof record.actualVersion === 'number' ? record.actualVersion : undefined
  return actualVersion === undefined ? { code, message } : { code, message, actualVersion }
}
