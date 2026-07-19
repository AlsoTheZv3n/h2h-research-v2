import { describe, expect, it } from 'vitest'
// The recording script as raw text (Vite ?raw): it is NOT executed -- importing it normally
// would launch a browser on import -- and it lives in e2e/, which Vitest excludes from its own
// run, so text is the only safe way to inspect it here.
import SOURCE from '../../e2e/demo.record.ts?raw'

/**
 * The published hero GIF must never show a synthetic E2E fixture. The dev DB is reseeded with
 * MONDO_E2E_* / CHEMBL_E2E_* fixtures on every Playwright run, so "record then convert
 * regenerates the GIF" must not depend on someone deleting them by hand. This is the CI backstop
 * for the two safety mechanisms in the script: the cancer-list strip and the runtime leak-throw
 * (CI never runs the recording itself -- it is a manual tsx script).
 */
describe('demo recording is free of E2E fixtures', () => {
  it('references no synthetic E2E fixture id -- not a const, an inline goto, or anywhere', () => {
    // Sanity: we are actually inspecting the recording script. A failed ?raw import or an emptied
    // file would make the fixture scan below vacuously pass.
    expect(SOURCE).toContain('page.goto')
    // A *full* fixture id (prefix + a suffix char, e.g. MONDO_E2E_NSCLC / CHEMBL_E2E_OSI) only
    // appears when the script points at a specific fixture entity -- whether via a const, an
    // inline goto, a nav, any quoting. The strip/guard below reference only the bare prefix
    // 'MONDO_E2E_' (no suffix char), so this catches a real leak without flagging them, and
    // survives DRY-ing the prefix into a const.
    const fixtures = SOURCE.match(/(?:MONDO|CHEMBL)_E2E_[A-Z0-9]/gi) ?? []
    expect(
      fixtures,
      `demo recording references E2E fixtures: ${[...new Set(fixtures)].join(', ')}`,
    ).toEqual([])
  })

  it('keeps the strip that removes E2E fixture rows from the cancer list', () => {
    // The cancer overview is the only step that lists every catalog row, so it is the only place
    // a fixture can enter. If this filter is ever removed, that vector reopens.
    expect(SOURCE).toMatch(/cancer-row[\s\S]{0,300}MONDO_E2E_[\s\S]{0,80}remove/)
  })

  it('keeps the runtime leak-assertion that aborts the recording if a fixture survives', () => {
    // The strip is view-only; this throw is what actually stops a tainted recording (a React
    // re-render could restore removed rows). It counts surviving fixture rows and throws --
    // deleting it must redden CI, not pass silently.
    expect(SOURCE).toMatch(/\.count\(\)[\s\S]{0,140}throw new Error/)
  })
})
