import { describe, expect, it } from 'vitest'
import { lipinskiReading, type Physchem } from './physchem'

const base: Physchem = { mw: 350, alogp: 3, hbd: 2, hba: 5, ro5_violations: 0 }

describe('lipinskiReading', () => {
  it('names the single property that drives one violation (vatalanib-style)', () => {
    // LogP 5.01 is the one violation; the reading must say so, not just "1 violation".
    const r = lipinskiReading({ mw: 346, alogp: 5.01, hbd: 1, hba: 4, ro5_violations: 1 })
    expect(r).toEqual({ text: '1 Lipinski violation: LogP 5.01.', tone: 'caution' })
  })

  it('names every violated property when there is more than one', () => {
    const r = lipinskiReading({ mw: 812, alogp: 6.1, hbd: 2, hba: 5, ro5_violations: 2 })
    // LogP leads, then MW — the natural reading order, both named with their values.
    expect(r?.text).toBe('2 Lipinski violations: LogP 6.1, molecular weight 812 Da.')
    expect(r?.tone).toBe('caution')
  })

  it('reads a clean drug as passing all four rules', () => {
    const r = lipinskiReading(base)
    expect(r?.tone).toBe('ok')
    expect(r?.text).toMatch(/Passes all four Lipinski rules/)
  })

  it('is WITHHELD when the authoritative count is missing (never guesses druglikeness)', () => {
    // ro5_violations null = the source did not give us the count. Withhold, do not infer "passes"
    // from the individual values -- the None-vs-0 discipline.
    expect(lipinskiReading({ ...base, ro5_violations: null })).toBeNull()
  })

  it('states the count without naming a culprit it cannot confirm', () => {
    // The count says 1, but LogP (the likely culprit) is missing: never invent the property.
    const r = lipinskiReading({ mw: 400, alogp: null, hbd: 3, hba: 8, ro5_violations: 1 })
    expect(r).toEqual({ text: '1 Lipinski violation — see the values below.', tone: 'caution' })
  })

  it('treats the threshold as strictly greater-than (a value AT the limit is not a violation)', () => {
    // LogP exactly 5 and MW exactly 500 are within Ro5, not over it.
    const r = lipinskiReading({ mw: 500, alogp: 5, hbd: 5, hba: 10, ro5_violations: 0 })
    expect(r?.tone).toBe('ok')
  })
})
