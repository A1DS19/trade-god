import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/*
 * THE TIER BOUNDARY, ENFORCED MECHANICALLY — the SOURCE half.
 *
 * `bundle.test.ts` reads the built output; this reads the source. Both are needed and neither
 * replaces the other: a source scan names the offending line, and only a bundle scan can catch a
 * leak that arrives through a dependency nobody typed.
 *
 * Measured, not assumed, against a real build of this tree: with `import type { AppType } from
 * '@coinpicks/api'` the client bundle is 583,379 bytes and carries no ORM. Changing that one line
 * to `import { type AppType, createApp } from '@coinpicks/api'` plus one value use makes it
 * 727,230 bytes, with this project's table and constraint names in it. Biome's useImportType does
 * not fire on the mixed form and tsc under verbatimModuleSyntax accepts it.
 *
 * Three signals fire on that slip, in this order: the Start plugin's importProtection fails the
 * BUILD (vite.config.ts), this test names the line, and bundle.test.ts reads dist/client. This
 * one is the signal that survives someone turning the first one off.
 *
 * The second rule is the arithmetic ban. The frozen formulas are evaluated in exactly one place
 * and apps/web is not it, so no rubric bound is written here at all — every maximum, threshold
 * and vocabulary arrives in the report payload as `bounds`.
 *
 * Comments are blanked before scanning and test files are skipped, so the prose above (which
 * names every banned construct on purpose) does not indict itself.
 */

const SRC = dirname(fileURLToPath(import.meta.url))

/** Replaces comment bodies with spaces, keeping every line number intact. */
function stripComments(source: string): string {
  const blank = (text: string) => text.replace(/[^\n]/g, ' ')
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + blank(match.slice(lead.length)))
}

interface SourceFile {
  path: string
  lines: string[]
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    if (!/\.tsx?$/.test(path)) return []
    if (path.endsWith('.test.ts')) return []
    // The generated route tree is an OUTPUT of the files this scan already reads, and it is
    // excluded from biome for the same reason.
    if (path.endsWith('routeTree.gen.ts')) return []
    return [path]
  })
}

const FILES: SourceFile[] = sourceFiles(SRC).map((path) => ({
  path: path.slice(SRC.length + 1),
  lines: stripComments(readFileSync(path, 'utf8')).split('\n'),
}))

function offenders(pattern: RegExp, only?: (file: SourceFile) => boolean): string[] {
  return FILES.filter((file) => only === undefined || only(file)).flatMap((file) =>
    file.lines
      .map((line, index) => ({ line, number: index + 1 }))
      .filter((entry) => pattern.test(entry.line))
      .map((entry) => `${file.path}:${String(entry.number)} ${entry.line.trim()}`),
  )
}

/** Everything but the one route that is allowed to make an outbound loopback request. */
const RENDERER = (file: SourceFile): boolean => file.path !== join('routes', 'api.$.ts')

describe('the web tier cannot reach the api tier at runtime', () => {
  it('scans every source file', () => {
    // Six at the end of Task 4 — router, lib/client, routes/__root, routes/index,
    // routes/reports.$reportId, routes/api.$ — and fifteen once Task 7 lands. The bound is the
    // lower number on purpose: this case exists to stop the scan passing because it matched
    // nothing, not to count the tree.
    expect(FILES.length).toBeGreaterThanOrEqual(6)
  })

  it('imports @coinpicks/api only with `import type`', () => {
    const found = FILES.flatMap((file) =>
      file.lines
        .map((line, index) => ({ line, number: index + 1 }))
        .filter(
          (entry) =>
            entry.line.includes("'@coinpicks/api'") &&
            !entry.line.trimStart().startsWith('import type '),
        )
        .map((entry) => `${file.path}:${String(entry.number)} ${entry.line.trim()}`),
    )
    expect(
      found,
      'a value import of @coinpicks/api ships the ORM and the DDL to the browser',
    ).toEqual([])
  })

  it('imports no node builtin, no driver and no ORM', () => {
    expect(offenders(/from '(node:[a-z/]+|pg|drizzle-orm[a-z/-]*)'/)).toEqual([])
  })
})

describe('the renderer never fetches', () => {
  it('has exactly one file allowed to make an outbound request', () => {
    expect(offenders(/\bfetch\(/, RENDERER)).toEqual([])
  })

  it('declares no loader, beforeLoad or server function in the shell', () => {
    const root = FILES.find((file) => file.path === join('routes', '__root.tsx'))
    expect(root, 'routes/__root.tsx is gone or was renamed').toBeDefined()
    const shell = (root?.lines ?? []).join('\n')
    for (const forbidden of ['loader', 'beforeLoad', 'createServerFn', 'fetch(', 'ssr:']) {
      expect(shell, `__root.tsx must not declare ${forbidden}`).not.toContain(forbidden)
    }
  })

  it('points the one proxy at an origin this process configures, never at a request URL', () => {
    const proxy = FILES.find((file) => file.path === join('routes', 'api.$.ts'))
    expect(proxy, 'routes/api.$.ts is gone or was renamed').toBeDefined()
    const source = (proxy?.lines ?? []).join('\n')
    expect(source).toContain("process.env.COINPICKS_API_ORIGIN ?? 'http://127.0.0.1:8789'")
    // Built from API_ORIGIN and the request's PATH only. Asserted in three pieces rather than as
    // one template literal, which biome reads as a placeholder in a plain string.
    expect(source).toContain('const target = ')
    expect(source).toContain('API_ORIGIN')
    expect(source).toContain('url.pathname.replace')
    expect(source, 'the proxy target must never come from the request body').not.toContain(
      'await request.json()',
    )
  })
})

describe('the web tier does no rubric arithmetic', () => {
  it('writes no bare rubric number', () => {
    expect(
      offenders(/(?<![\w.$-])(16|31)(?![\w.%-])/),
      'a rubric bound is written in apps/web instead of arriving in `bounds`',
    ).toEqual([])
  })

  it('never calls Number() on operator input', () => {
    expect(
      offenders(/(?<![\w.$])Number\(/),
      'apps/web parses a number instead of sending the string the operator typed',
    ).toEqual([])
  })
})
