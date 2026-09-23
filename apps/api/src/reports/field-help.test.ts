import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { FIELD_HELP, type FieldHelp } from './field-help.ts'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')

/**
 * A lesson or a quote as plain words: the markdown emphasis, code ticks and blockquote markers the
 * lessons are written in are dropped, and every run of whitespace becomes one space. Nothing else
 * is forgiven -- not a dash, not a quotation mark, not a word.
 */
function plain(text: string): string {
  return text
    .replace(/^[ \t]*>[ \t]?/gm, '')
    .replace(/[*`]/g, '')
    .replace(/\s+/g, ' ')
}

const entries: [string, FieldHelp][] = Object.entries(FIELD_HELP)

describe('the field descriptions', () => {
  /*
   * This repo has already shipped a "worked example from the framework" that no lesson contained
   * (agents/decisions.md, 2026-09-21). A description shown in quotation marks with a lesson's name
   * beside it is a claim about that lesson, so every line of it is checked against the file.
   */
  it('quote every framework line verbatim from the lesson they name', () => {
    const missing: string[] = []
    for (const [key, help] of entries) {
      if (help.source === 'editor') continue
      const lesson = plain(readFileSync(resolve(REPO, help.source), 'utf8'))
      for (const quote of [...help.text, ...(help.details?.lines ?? [])]) {
        if (!lesson.includes(plain(quote))) missing.push(`${key} (${help.source}): ${quote}`)
      }
    }
    expect(missing, 'a description presented as framework text is not in its lesson').toEqual([])
  })

  it('never leave a line blank', () => {
    for (const [key, help] of entries) {
      expect(help.text.length, `${key} has no text`).toBeGreaterThan(0)
      for (const line of [...help.text, ...(help.details?.lines ?? [])]) {
        expect(line.trim(), `${key} has a blank line`).not.toBe('')
      }
    }
  })
})
