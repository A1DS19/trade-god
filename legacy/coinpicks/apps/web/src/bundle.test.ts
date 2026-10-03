import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/*
 * THE BUNDLE SCAN. TanStack Start emits TWO bundles and only one of them is the browser's:
 *
 *   apps/web/dist/client/assets/*.js   <- served as files; this is what a browser downloads
 *   apps/web/dist/server/**\/*.js      <- the SSR fetch handler; runs in node
 *
 * The directory is NAMED here rather than globbed loosely, because the obvious wrong answer
 * passes silently. The command a plain-Vite SPA would use --
 * `grep -c -e drizzle dist/assets/index-*.js || true` -- run against a Start build prints
 * "grep: dist/assets/index-*.js: No such file or directory" and, with the `|| true`, the
 * pipeline EXITS 0. That is a guard reporting success having read zero bytes. Both the existence
 * of each directory and a byte floor are asserted below so that cannot happen quietly.
 *
 * `apps/web`'s `test` script runs `vite build` before vitest for the same reason: a scan of a
 * dist left over from an earlier source tree is the same failure wearing a different hat.
 */

const WEB = dirname(dirname(fileURLToPath(import.meta.url)))
const CLIENT = join(WEB, 'dist', 'client')
const SERVER = join(WEB, 'dist', 'server')

/*
 * NEEDLES THAT SURVIVE MINIFICATION.
 *
 * This list was written wrong first and the mistake is the reason it is spelled out. With a real
 * leak in place, the built client chunk contains
 *
 *   drizzle: x15   PgTable x1   PgColumn x2   report_scores x1   rs_gate x1
 *   drizzle-orm x0   pg-protocol x0   node:crypto x0   DATABASE_URL x0   coinpicks_app x0
 *
 * The module SPECIFIER is gone -- rolldown rewrote it -- and the `pg` driver never arrives at
 * all, because `db/client.ts` reaches apps/web only as a type. What survives is the string
 * literals drizzle builds its class registry from (`Symbol.for('drizzle:entityKind')`) and, more
 * to the point, the DDL: this project's table and constraint names, in the browser, for anyone
 * to read. So `pg-protocol`, `node:crypto`, `DATABASE_URL` and `coinpicks_app` are kept as
 * belt-and-braces and are NOT what catches this.
 */
const FORBIDDEN = [
  'drizzle:',
  'PgTable',
  'PgColumn',
  'report_scores',
  'rs_gate',
  'pg-protocol',
  'DATABASE_URL',
  'coinpicks_app',
] as const

/*
 * The client bundle's ceiling, in characters as `readFileSync(..., 'utf8').length` counts them --
 * which is a few dozen fewer than `dist` on disk, and the same either way.
 *
 * The needle list catches what it knows to look for; this catches the rest. Measured on the Task 4
 * tree: clean 583,321, and a value import of `@coinpicks/api` 727,172 -- with `vite build` exiting
 * 0 and silent either way once importProtection is off. The SPA draft of this plan grew its own
 * tree by about 36 kB between Task 4 and Task 7, so 660,000 sits roughly 40,000 above a clean
 * finished tree and 59,000 below a leaking one.
 *
 * Raise it deliberately, in the commit that makes the app bigger, with the measured number
 * written into this comment -- and never to make a red test green.
 */
const CLIENT_CHAR_CEILING = 660_000

function jsFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return jsFiles(path)
    return /\.m?js$/.test(path) ? [path] : []
  })
}

function scan(directory: string): { files: number; characters: number; hits: string[] } {
  const files = jsFiles(directory)
  const hits: string[] = []
  let characters = 0
  for (const path of files) {
    const source = readFileSync(path, 'utf8')
    characters += source.length
    for (const needle of FORBIDDEN) {
      const count = source.split(needle).length - 1
      if (count > 0) hits.push(`${relative(WEB, path)}: ${needle} x${String(count)}`)
    }
  }
  return { characters, files: files.length, hits }
}

describe('the built client bundle', () => {
  it('exists, which means `vite build` ran', () => {
    expect(existsSync(CLIENT), `${relative(WEB, CLIENT)} is missing -- run \`pnpm build\``).toBe(
      true,
    )
    expect(existsSync(SERVER), 'dist/server is missing, so this is not a Start build').toBe(true)
  })

  it('is big enough to be a real bundle, so a clean scan means something', () => {
    const { files, characters } = scan(CLIENT)
    expect(files).toBeGreaterThanOrEqual(2)
    expect(characters).toBeGreaterThan(200_000)
  })

  it('carries no ORM, no schema, no driver and no connection string', () => {
    expect(scan(CLIENT).hits).toEqual([])
  })

  it('has not silently grown by the size of a dependency nobody meant to ship', () => {
    expect(scan(CLIENT).characters).toBeLessThan(CLIENT_CHAR_CEILING)
  })
})

describe('the built server bundle', () => {
  it('carries no ORM, no schema and no connection string either', () => {
    // The renderer is not the tier that holds a database handle; apps/api is. A value import used
    // only inside a createServerFn body leaves the CLIENT bundle spotless and lands here instead
    // -- measured on the Task 4 tree: client 587,978 bytes with ZERO needles and comfortably under
    // the ceiling, while dist/server carries drizzle: x15, PgTable x6, PgColumn x88,
    // report_scores x2, rs_gate x1. This case is the only one that sees it.
    expect(scan(SERVER).hits).toEqual([])
  })
})
