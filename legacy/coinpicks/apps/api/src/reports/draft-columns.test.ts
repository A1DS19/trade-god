import { getTableColumns } from 'drizzle-orm'
import { describe, expect, it } from 'vitest'
import { reportScores } from '../db/schema.ts'
import { CITABLE_FIELDS } from './citable-fields.ts'
import {
  DERIVED_COLUMNS,
  DRAFT_COLUMNS,
  PHASE_A2_COLUMNS,
  UNWRITABLE_COLUMNS,
} from './draft-columns.ts'

const columns = Object.keys(getTableColumns(reportScores))

describe('report_scores is partitioned exactly', () => {
  it('classifies every column exactly once', () => {
    const classified = [
      ...DRAFT_COLUMNS,
      ...DERIVED_COLUMNS,
      ...PHASE_A2_COLUMNS,
      ...UNWRITABLE_COLUMNS,
    ]
    expect(new Set(classified).size, 'a column is classified twice').toBe(classified.length)
    // A column with no home is a column nobody decided about, and the write path defaults it
    // into "the editor may set this".
    expect([...columns].sort()).toEqual([...classified].sort())
  })

  it('keeps every derived column out of the editor list', () => {
    for (const derived of DERIVED_COLUMNS) {
      expect(DRAFT_COLUMNS as readonly string[]).not.toContain(derived)
    }
  })
})

describe('the citation vocabulary', () => {
  it('uses the drizzle columns own spelling', () => {
    const real = new Set(Object.values(getTableColumns(reportScores)).map((column) => column.name))
    for (const [key, name] of Object.entries(CITABLE_FIELDS)) {
      expect(real.has(name), `${key} -> ${name} is not a report_scores column`).toBe(true)
    }
  })

  it('spells the one column with a digit in it correctly', () => {
    // The regex derivation this replaces produced `liquidity_depth2pct_usd`: /[A-Z]/ never
    // separates a digit run. Every other name round-tripped, which is what made it silent.
    expect(CITABLE_FIELDS.liquidityDepth2pctUsd).toBe('liquidity_depth_2pct_usd')
  })
})
