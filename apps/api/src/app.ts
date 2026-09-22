import { zValidator } from '@hono/zod-validator'
import { asc, eq, sql } from 'drizzle-orm'
import type { ValidationTargets } from 'hono'
import { Hono } from 'hono'
import type { ZodType } from 'zod'
import type { Db } from './db/client.ts'
import { coins, reports } from './db/schema.ts'
import { evaluateBlockers } from './reports/blockers.ts'
import {
  PRODUCT_SUB_SCORE_MAX,
  TEAM_MAX_PEOPLE,
  TEAM_MIN_PEOPLE,
  TEAM_RUNG_MAX,
} from './reports/bounds.ts'
import { CITABLE_FIELDS, TEAM_FIELD_PREFIX } from './reports/citable-fields.ts'
import type { ScoresPatch } from './reports/draft-columns.ts'
import {
  AlreadyCommittedError,
  ReportNotFoundError,
  StaleVersionError,
  sqlstateOf,
  UnknownTeamMemberError,
} from './reports/errors.ts'
import {
  accrualPatch,
  citationParam,
  citationPost,
  coinPost,
  liquidityPatch,
  narrativePatch,
  productPatch,
  reportParam,
  reportPost,
  riskPatch,
  teamPut,
  versionQuery,
} from './reports/patch-schemas.ts'
import {
  addCitation,
  readReport,
  removeCitation,
  replaceTeam,
  saveSection,
} from './reports/store.ts'
import { NARRATIVE_MAX, NARRATIVE_TOTAL_MAX } from './scoring/narrative.ts'
import { PRODUCT_GATE_THRESHOLD } from './scoring/product.ts'
import { SCORING_VERSION, ScoreRangeError } from './scoring/ranges.ts'

/**
 * Every bound, threshold and closed vocabulary the editor needs, served rather than copied.
 *
 * `apps/web` holds no rubric literal at all. The naive editor wrote `draft.length >= 5` and
 * `const TIERS = ['low','medium','high']`, which are a frozen bound and a pgEnum reproduced in a
 * tier where nothing pins them — and the guard test that was supposed to catch that only grepped
 * for two constant names. `teamFieldPrefix` is here for the same reason: `team:` is this API's
 * citation vocabulary, one string away from the `liquidity_depth2pct_usd` finding, and
 * `boundary.test.ts` cannot see a bare prefix the way it sees a bare number.
 */
const BOUNDS = {
  productSubScoreMax: PRODUCT_SUB_SCORE_MAX,
  productGateThreshold: PRODUCT_GATE_THRESHOLD,
  narrativeMax: NARRATIVE_MAX,
  narrativeTotalMax: NARRATIVE_TOTAL_MAX,
  teamRungMax: TEAM_RUNG_MAX,
  teamMinPeople: TEAM_MIN_PEOPLE,
  teamMaxPeople: TEAM_MAX_PEOPLE,
  liquidityTiers: ['low', 'medium', 'high'],
  provenanceLabels: ['verified', 'vendor_claim'],
  citableFields: CITABLE_FIELDS,
  teamFieldPrefix: TEAM_FIELD_PREFIX,
  scoringVersion: SCORING_VERSION,
} as const

/**
 * ONE refusal shape for every validation failure, and 422 rather than zod-validator's default
 * 400.
 *
 * It matters because the message carries the FROZEN text: `subScore()` runs
 * `assertIntegerRange` inside a superRefine, so typing 11 into Ease of Use comes back as
 * "ease must be between 0 and 10, got 11" — the same sentence the commit route will raise. The
 * default hook returns a serialised ZodError the editor would have had to re-interpret.
 */
function check<T extends ZodType, Target extends keyof ValidationTargets>(
  target: Target,
  schema: T,
) {
  return zValidator(target, schema, (result, c) => {
    if (result.success) return undefined
    const issues = result.error.issues.map((issue) => ({
      path: issue.path.map(String).join('.'),
      message: issue.message,
    }))
    const first = issues[0]
    return c.json(
      {
        code: 'INVALID',
        message:
          first === undefined
            ? 'the request is not valid'
            : `${first.path === '' ? 'body' : first.path}: ${first.message}`,
        issues,
      },
      422,
    )
  })
}

/**
 * The editor's API. Build-order step 4: it creates and edits a DRAFT.
 *
 * `createApp` takes the pool rather than opening one, so `server.ts` keeps decision A's ordering
 * (migrate as the owner, close that pool, THEN open the request pool) and so the route tests can
 * run the real routes against `coinpicks_test` through `app.request()`.
 */
export function createApp(db: Db, migrations: number) {
  /*
   * ONE chained expression, deliberately, and it must stay one.
   *
   * Split it into `const app = new Hono()` followed by `app.get(...)` and `AppType` — which is
   * `ReturnType<typeof createApp>` — collapses to `unknown` (TS18046). `hc<AppType>` in apps/web
   * then loses every response type, and it does so SILENTLY: the client still compiles, because
   * `unknown` accepts any property access the RPC proxy makes. The boundary this whole plan rests
   * on would be gone with nothing red to show for it.
   *
   * The sibling repo learned the same thing and records it at profe/apps/api/src/app.ts:549.
   * Retrofitting the chain later means rewriting every call site, so it starts chained and stays
   * chained — including when a route is added.
   */
  return (
    new Hono()
      .onError((error, c) => {
        if (error instanceof StaleVersionError) {
          return c.json(
            {
              code: 'STALE_VERSION',
              message: error.message,
              actualVersion: error.actualVersion,
            },
            409,
          )
        }
        if (error instanceof AlreadyCommittedError) {
          return c.json({ code: 'ALREADY_COMMITTED', message: error.message }, 409)
        }
        if (error instanceof ReportNotFoundError) {
          return c.json({ code: 'NOT_FOUND', message: error.message }, 404)
        }
        if (error instanceof UnknownTeamMemberError) {
          return c.json({ code: 'UNKNOWN_TEAM_MEMBER', message: error.message }, 422)
        }
        if (error instanceof ScoreRangeError) {
          return c.json({ code: 'OUT_OF_RANGE', message: error.message, field: error.field }, 422)
        }
        // drizzle 0.45.3 wraps every driver error, so `error.code` is always undefined; the
        // SQLSTATE is on `.cause`. sqlstateOf walks the chain.
        const sqlstate = sqlstateOf(error)
        if (sqlstate === 'CP001') {
          return c.json(
            { code: 'REPORT_COMMITTED', message: 'this report is committed and immutable' },
            409,
          )
        }
        if (sqlstate === '23514' || sqlstate === '23505') {
          const constraint = (error as { cause?: { constraint?: string } }).cause?.constraint
          return c.json(
            {
              code: sqlstate === '23514' ? 'CONSTRAINT_REFUSED' : 'DUPLICATE',
              message: `the database refused it: ${constraint ?? sqlstate}`,
            },
            422,
          )
        }
        console.error(error)
        return c.json({ code: 'INTERNAL', message: 'the request failed' }, 500)
      })

      /**
       * Carries the migration count AND the scoring version. The count is what proves the journal
       * applied; the version string is what distinguishes this application from anything else
       * answering on a nearby port — this machine has recorded a green /health read off another
       * application's process.
       */
      .get('/health', async (c) => {
        await db.execute(sql`SELECT 1`)
        return c.json({ ok: true, migrations, scoringVersion: SCORING_VERSION })
      })

      .get('/coins', async (c) => {
        const rows = await db
          .select({
            coin: coins,
            reportId: reports.id,
            reportStatus: reports.status,
            reportCreatedAt: reports.createdAt,
          })
          .from(coins)
          .leftJoin(reports, eq(reports.coinId, coins.id))
          .orderBy(asc(coins.symbol), asc(reports.createdAt))
        return c.json({ rows })
      })

      .post('/coins', check('json', coinPost), async (c) => {
        const input = c.req.valid('json')
        const inserted = await db.insert(coins).values(input).returning()
        const coin = inserted[0]
        if (coin === undefined) throw new Error('insert into coins returned no row')
        return c.json({ coin })
      })

      .post('/reports', check('json', reportPost), async (c) => {
        const { coinId } = c.req.valid('json')
        const inserted = await db.insert(reports).values({ coinId }).returning()
        const report = inserted[0]
        if (report === undefined) throw new Error('insert into reports returned no row')
        return c.json({ report })
      })

      .get('/reports/:reportId', check('param', reportParam), async (c) => {
        const { reportId } = c.req.valid('param')
        const payload = await readReport(db, reportId)
        if (payload === null) throw new ReportNotFoundError(reportId)
        return c.json({
          ...payload,
          blockers: evaluateBlockers(payload.scores),
          bounds: BOUNDS,
        })
      })

      .patch(
        '/reports/:reportId/product',
        check('param', reportParam),
        check('json', productPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/liquidity',
        check('param', reportParam),
        check('json', liquidityPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, depth, topPool, ...fields } = c.req.valid('json')
          /*
           * The tier's timestamp is re-stamped on every liquidity save that carries a tier, and
           * that is what makes `rs_tier_not_older_than_its_inputs` unfailable rather than merely
           * unlikely: the section always saves the tier and both measurements together, every
           * `measured_at` was already refused if it was in the future, and `now()` runs after the
           * request was parsed. Do not "fix" this into a stale-tier flag the UI then has to
           * announce — the naive design chose a `tierCleared` boolean that nothing rendered.
           */
          const patch: ScoresPatch = {
            ...fields,
            liquidityTierAssignedAt: fields.liquidityTier === null ? null : new Date(),
            liquidityDepth2pctUsd: depth === null ? null : depth.value,
            liquidityDepthSource: depth === null ? null : depth.source,
            liquidityDepthUrl: depth === null ? null : depth.url,
            liquidityDepthLabel: depth === null ? null : depth.label,
            liquidityDepthMeasuredAt: depth === null ? null : depth.measuredAt,
            liquidityTopPoolTvlUsd: topPool === null ? null : topPool.value,
            liquidityTopPoolSource: topPool === null ? null : topPool.source,
            liquidityTopPoolUrl: topPool === null ? null : topPool.url,
            liquidityTopPoolLabel: topPool === null ? null : topPool.label,
            liquidityTopPoolMeasuredAt: topPool === null ? null : topPool.measuredAt,
          }
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/narrative',
        check('param', reportParam),
        check('json', narrativePatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/accrual',
        check('param', reportParam),
        check('json', accrualPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, marketCap, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = {
            ...fields,
            discoveryMarketCapUsd: marketCap === null ? null : marketCap.value,
            discoveryMarketCapSource: marketCap === null ? null : marketCap.source,
            discoveryMarketCapUrl: marketCap === null ? null : marketCap.url,
            discoveryMarketCapLabel: marketCap === null ? null : marketCap.label,
            discoveryMarketCapMeasuredAt: marketCap === null ? null : marketCap.measuredAt,
          }
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .patch(
        '/reports/:reportId/risk',
        check('param', reportParam),
        check('json', riskPatch),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...fields } = c.req.valid('json')
          const patch: ScoresPatch = fields
          return c.json(await saveSection(db, reportId, version, patch))
        },
      )

      .put(
        '/reports/:reportId/team',
        check('param', reportParam),
        check('json', teamPut),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, members } = c.req.valid('json')
          const founders = members.filter((member) => member.isFounder).length
          if (founders > 1) {
            return c.json(
              {
                code: 'TWO_FOUNDERS',
                message: `the framework allows one founder, got ${founders}`,
              },
              422,
            )
          }
          return c.json(await replaceTeam(db, reportId, version, members))
        },
      )

      .post(
        '/reports/:reportId/citations',
        check('param', reportParam),
        check('json', citationPost),
        async (c) => {
          const { reportId } = c.req.valid('param')
          const { version, ...input } = c.req.valid('json')
          return c.json(await addCitation(db, reportId, version, input))
        },
      )

      .delete(
        '/reports/:reportId/citations/:citationId',
        check('param', citationParam),
        check('query', versionQuery),
        async (c) => {
          const { reportId, citationId } = c.req.valid('param')
          const { version } = c.req.valid('query')
          return c.json(await removeCitation(db, reportId, version, citationId))
        },
      )
  )
}

export type AppType = ReturnType<typeof createApp>
