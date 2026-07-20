import { describe, expect, it } from 'vitest'
import type { SourcedFact } from './api/types'
import { dedupeMechanisms } from './mechanisms'

function fact(source: string, value: unknown, status: SourcedFact['status'] = 'ok'): SourcedFact {
  return {
    value,
    status,
    source,
    source_url: `https://example/${source}`,
    retrieved_at: '2026-07-20T00:00:00Z',
    error: null,
    confidence: null,
  }
}

// The vatalanib case: the same four mechanisms from both sources, in a different order.
const CHEMBL = ['Stem cell growth factor receptor inhibitor', 'PDGFR inhibitor', 'VEGFR inhibitor']
const OT = ['VEGFR inhibitor', 'PDGFR inhibitor', 'Stem cell growth factor receptor inhibitor']

describe('dedupeMechanisms', () => {
  it('merges the same mechanism from two sources into one row with both sources', () => {
    const out = dedupeMechanisms([fact('chembl', CHEMBL), fact('opentargets', OT)])
    // Three distinct mechanisms, not six.
    expect(out).toHaveLength(3)
    // Every one is attributed to BOTH sources (they agree), and each source once.
    for (const m of out) {
      expect(m.facts.map((f) => f.source).sort()).toEqual(['chembl', 'opentargets'])
    }
  })

  it('deduplicates by content, not by list position', () => {
    // Index 0 differs between the sources, so a position-based merge would wrongly pair
    // "Stem cell..." with "VEGFR...". Content dedup keeps them distinct.
    const out = dedupeMechanisms([fact('chembl', CHEMBL), fact('opentargets', OT)])
    const vegfr = out.find((m) => m.text === 'VEGFR inhibitor')
    expect(vegfr?.facts).toHaveLength(2) // both sources, correctly matched by text
  })

  it('is case-insensitive but keeps the first spelling for display', () => {
    const out = dedupeMechanisms([fact('chembl', ['EGFR Inhibitor']), fact('opentargets', ['egfr inhibitor'])])
    expect(out).toHaveLength(1)
    expect(out[0].text).toBe('EGFR Inhibitor')
    expect(out[0].facts).toHaveLength(2)
  })

  it('orders by corroboration then alphabetically, independent of either source order', () => {
    // "shared" is named by both; "chembl-only" and "ot-only" by one each.
    const out = dedupeMechanisms([
      fact('chembl', ['zzz shared', 'chembl-only']),
      fact('opentargets', ['zzz shared', 'ot-only']),
    ])
    expect(out.map((m) => m.text)).toEqual(['zzz shared', 'chembl-only', 'ot-only'])
  })

  it('skips source_failed and non-array facts, and blank strings', () => {
    const out = dedupeMechanisms([
      fact('chembl', null, 'source_failed'),
      fact('opentargets', ['  ', 'Real mechanism']),
    ])
    expect(out.map((m) => m.text)).toEqual(['Real mechanism'])
    expect(out[0].facts.map((f) => f.source)).toEqual(['opentargets'])
  })

  it('returns nothing when no source annotated a mechanism', () => {
    expect(dedupeMechanisms([fact('chembl', [])])).toEqual([])
  })
})
