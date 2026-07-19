import { describe, expect, it } from 'vitest'
// The recording script as raw text (Vite ?raw): it is NOT executed -- importing it normally
// would launch a browser on import -- and it lives in e2e/, which Vitest excludes from its own
// run, so text is the only safe way to inspect it here.
import SOURCE from '../../e2e/demo.record.ts?raw'

/**
 * The published hero GIF must never show a synthetic E2E fixture. The dev DB is reseeded with
 * MONDO_E2E_* / CHEMBL_E2E_* fixtures on every Playwright run, so "record then convert
 * regenerates the GIF" must not depend on someone deleting them by hand. This is the
 * CI-enforced backstop for the runtime guard inside the script.
 */
describe('demo recording is free of E2E fixtures', () => {
  it('pins only real entity ids to navigate to, never an E2E fixture', () => {
    // The id-shaped constants the script navigates to (OSIMERTINIB, AFATINIB, ADC, NSCLC).
    const ids = [...SOURCE.matchAll(/const \w+ = '([^']+)'/g)]
      .map((m) => m[1])
      .filter((v) => /^(MONDO|CHEMBL|EFO)/.test(v))
    // The regex must still find them -- an empty set would make the assertion below vacuous
    // and silently stop guarding anything.
    expect(ids.length).toBeGreaterThan(0)
    for (const id of ids) {
      expect(id, `${id} is an E2E fixture; the recording must navigate to real entities`).not.toMatch(
        /E2E/i,
      )
    }
  })

  it('keeps the defensive strip over the cancer list -- the one view that renders fixtures', () => {
    // The cancer overview is the only step that lists every catalog row, so it is the only
    // place a fixture can leak in. If this filter is ever removed, that vector reopens.
    expect(SOURCE).toMatch(/cancer-row[\s\S]{0,300}MONDO_E2E_[\s\S]{0,80}remove/)
  })
})
