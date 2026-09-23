import { z } from 'zod'
import { NARRATIVE_MAX } from '../scoring/narrative.ts'
import { assertIntegerRange, assertNonNegative, assertRange } from '../scoring/ranges.ts'
import { PRODUCT_SUB_SCORE_MAX, TEAM_MAX_PEOPLE, TEAM_RUNG_MAX } from './bounds.ts'
import { isCitableField } from './citable-fields.ts'

/*
 * EVERY NUMBER ARRIVES AS THE STRING THE OPERATOR TYPED.
 *
 * The naive editor called `Number(typed)` in the browser and sent the result. Verified in Node
 * 26: `JSON.stringify({ productEase: Number('seven') })` is `{"productEase":null}`, and the same
 * for '1,000', '7%' and '1e999' (Infinity -> null). `null` is this API's "clear this field", so
 * no validator downstream can tell a typo from a deliberate clear: the save returns 200, bumps
 * the CAS version, and silently empties the column.
 *
 * Sending the raw string moves the parse to one place that can REFUSE. `null` still means clear,
 * and it can now only be produced by a box the operator actually emptied.
 *
 * `.trim()` first, then a regex that admits digits and nothing else. '' and '   ' fail it, so a
 * blank string can never reach `Number('')` -> 0 either.
 */

const WHOLE = /^(0|[1-9]\d*)$/
const DECIMAL = /^(0|[1-9]\d*)(\.\d+)?$/

/*
 * The refusal describes exactly what DECIMAL admits. The old wording -- "digits, with at most one
 * decimal point" -- was satisfied by '.35', '5.' and '07', all of which DECIMAL refuses, so the
 * operator was told their input broke a rule it visibly kept.
 */
const decimalMessage = (field: string): string =>
  `${field} must be written like 1250000.5 or 0.35: whole digits with no leading zero (a lone 0 ` +
  "is fine), then optionally a point and at least one more digit — so not '.35', '5.' or '07', " +
  'and no commas, signs or exponents'

/**
 * No measurement predates the Bitcoin genesis block. Ruled 2026-09-22: a typo in the year --
 * '0026' for '2026' -- passed `z.iso.datetime` and saved with 200, but did not read back.
 * drizzle maps a timestamptz with `new Date(pgText)`, and V8 reads a year below 100 in that text
 * form as a two-digit year: '0026' becomes an Invalid Date (null on the wire), so the figure
 * comes back with four of its five boxes filled and no untouched re-save can pass; '0075' comes
 * back as 1975 and an untouched re-save writes 1975 into the row. Wire validation, not a frozen
 * formula.
 */
export const MEASURED_AT_FLOOR = '2009-01-03T00:00:00Z'

/**
 * A whole-number sub-score, validated by the FROZEN `assertIntegerRange` before it can reach
 * Postgres. That order is load-bearing: `INSERT INTO t (ease integer) VALUES (7.5)` stores 8 on
 * 16.13 and `BETWEEN 0 AND 10` then passes on the rounded value, so the CHECK cannot defend the
 * 2026-09-21 integer ruling on its own. Verified live.
 *
 * One builder, used by all nine sub-scores and all three team rungs, so there is one place to
 * forget rather than fifteen.
 */
export function subScore(field: string, max: number) {
  return z
    .string()
    .trim()
    .regex(
      WHOLE,
      `${field} must be a whole number in plain digits, like 7 — no decimal point, sign or leading zero`,
    )
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertIntegerRange(field, parsed, 0, max)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** A non-negative dollar amount, validated by the frozen `assertNonNegative`. */
export function money(field: string) {
  return z
    .string()
    .trim()
    .regex(DECIMAL, decimalMessage(field))
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertNonNegative(field, parsed)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** A fraction in [0, 1] — never a percentage. `assertRange` rejects 50 rather than dividing it. */
export function fraction(field: string) {
  return z
    .string()
    .trim()
    .regex(DECIMAL, decimalMessage(field))
    .transform(Number)
    .superRefine((parsed, ctx) => {
      try {
        assertRange(field, parsed, 0, 1)
      } catch (error) {
        ctx.addIssue({ code: 'custom', message: (error as Error).message })
      }
    })
}

/** Prose: trimmed, and an empty box is an explicit null rather than a blank string. */
const prose = z
  .string()
  .trim()
  .transform((text) => (text === '' ? null : text))
  .nullable()

/**
 * A measured figure and the story of where it came from, as ONE object.
 *
 * `rs_depth_provenance_complete` and its two siblings are biconditionals, so five separate
 * nullable fields can express a state the database refuses. One object cannot: it is all five or
 * it is `null`.
 *
 * The figure is `money(...)`, so a blank box is a 422 and never `Number('') === 0`. The naive
 * version wrote `value: Number(figure)` with no blank guard, which stored "+/-2% depth = $0,
 * verified, DefiLlama, 14:32" — a fabricated measured zero, immutable after commit.
 */
export function measured(field: string) {
  return z
    .object({
      value: money(field),
      source: z.string().trim().min(1, `${field} needs a source`),
      url: z.url(`${field} needs a source URL`),
      label: z.enum(['verified', 'vendor_claim']),
      measuredAt: z.iso
        .datetime({
          offset: true,
          error: `${field}: measured-at must be ISO 8601 with seconds and an offset, like 2026-09-21T14:32:00+02:00 or 2026-09-21T12:32:00Z`,
        })
        .refine(
          (text) => Date.parse(text) <= Date.now(),
          `${field}: a measurement cannot be in the future`,
        )
        .refine(
          (text) => Date.parse(text) >= Date.parse(MEASURED_AT_FLOOR),
          `${field}: a measurement cannot predate ${MEASURED_AT_FLOOR.slice(0, 10)}, the Bitcoin genesis block`,
        )
        .transform((text) => new Date(text)),
    })
    .nullable()
}

export const reportParam = z.object({ reportId: z.uuid() })

/** The CAS token on a DELETE, where there is no body to put it in. */
export const versionQuery = z.object({
  version: z
    .string()
    .regex(/^[1-9]\d*$/, 'version must be a positive whole number')
    .transform(Number),
})
export const citationParam = z.object({ reportId: z.uuid(), citationId: z.uuid() })

/** The CAS token. Rule 4: good for exactly one write. */
const version = z.number().int().min(1)

export const productPatch = z.strictObject({
  version,
  overviewSentence: prose,
  productEase: subScore('ease', PRODUCT_SUB_SCORE_MAX).nullable(),
  productHairFire: subScore('hairFire', PRODUCT_SUB_SCORE_MAX).nullable(),
  productExclusivity: subScore('exclusivity', PRODUCT_SUB_SCORE_MAX).nullable(),
  productEaseRationale: prose,
  productHairFireRationale: prose,
  productExclusivityRationale: prose,
})

export const liquidityPatch = z.strictObject({
  version,
  depth: measured('liquidityDepth2pctUsd'),
  topPool: measured('liquidityTopPoolTvlUsd'),
  liquidityNoDexPool: z.boolean(),
  liquidityTier: z.enum(['low', 'medium', 'high']).nullable(),
  liquidityJustification: prose,
})

export const narrativePatch = z.strictObject({
  version,
  narrativeMaturity: subScore('maturity', NARRATIVE_MAX.maturity).nullable(),
  narrativeSmartMoney: subScore('smartMoney', NARRATIVE_MAX.smartMoney).nullable(),
  narrativeHairFire: subScore('hairFire', NARRATIVE_MAX.hairFire).nullable(),
  narrativeCommunication: subScore('communication', NARRATIVE_MAX.communication).nullable(),
  narrativeLineage: subScore('lineage', NARRATIVE_MAX.lineage).nullable(),
  narrativeMutation: subScore('mutation', NARRATIVE_MAX.mutation).nullable(),
  narrativeMaturityRationale: prose,
  narrativeSmartMoneyRationale: prose,
  narrativeHairFireRationale: prose,
  narrativeCommunicationRationale: prose,
  narrativeLineageRationale: prose,
  narrativeMutationRationale: prose,
})

export const accrualPatch = z.strictObject({
  version,
  accrualSegmentRevenueUsd: money('segmentRevenueUsd').nullable(),
  accrualCaptureShare: fraction('captureShare').nullable(),
  accrualPct: fraction('accrualPct').nullable(),
  accrualAnnualIssuanceUsd: money('annualIssuanceUsd').nullable(),
  accrualAbsentReason: prose,
  accrualRationale: prose,
  accrualFinding: prose,
  marketCap: measured('marketCapUsd'),
})

export const riskPatch = z.strictObject({
  version,
  riskNotes: prose,
})

/**
 * The WHOLE team, replaced in one transaction.
 *
 * Positions are the array index, so nothing on the wire can claim a slot twice and
 * `rt_report_position_uniq` (not deferrable) cannot be tripped by a reorder. An existing person
 * keeps their `id`, which is what keeps their `team:<uuid>` citations attached.
 */
export const teamPut = z.strictObject({
  version,
  members: z
    .array(
      z.strictObject({
        id: z.uuid().nullable(),
        name: z.string().trim().min(1, 'a team member needs a name'),
        roles: z.array(z.string().trim().min(1)).min(1, 'a team member needs at least one role'),
        isFounder: z.boolean(),
        h: subScore('h', TEAM_RUNG_MAX.h),
        m: subScore('m', TEAM_RUNG_MAX.m),
        l: subScore('l', TEAM_RUNG_MAX.l),
        summary: z.string().trim().min(1, 'a team member needs a prior-experience summary'),
      }),
    )
    // No minimum: a half-entered team is a legitimate draft state, and cardinality is
    // teamWeightedScore()'s to reject at commit. The maximum is enforced because an over-full
    // set is never valid under any later ruling.
    .max(TEAM_MAX_PEOPLE, `the framework allows at most ${TEAM_MAX_PEOPLE} people`),
})

export const citationPost = z.strictObject({
  version,
  field: z
    .string()
    .trim()
    .refine(
      isCitableField,
      'not a citable field: use a name from CITABLE_FIELDS or `team:<report_team.id>`',
    ),
  url: z.url('a citation needs a URL'),
  quote: z.string().trim().min(1, 'a citation needs the exact quote to search for'),
})

export const coinPost = z.strictObject({
  symbol: z.string().trim().min(1),
  name: z.string().trim().min(1),
  chain: z.string().trim().min(1),
  contractAddress: z.string().trim().min(1).nullable(),
  coingeckoId: z.string().trim().min(1).nullable(),
  addressSources: z.array(z.url()),
})

export const reportPost = z.strictObject({ coinId: z.uuid() })
