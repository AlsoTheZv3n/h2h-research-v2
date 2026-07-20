import { describe, expect, it } from 'vitest'
import type { SourcedFact } from './api/types'
import { chooseTitleFacts } from './titles'

function f(over: Partial<SourcedFact>): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'pubmed',
    source_url: 'https://pubmed.ncbi.nlm.nih.gov/?term=x',
    retrieved_at: '2026-07-20T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const OLD = '2026-06-01T00:00:00Z'
const NEW = '2026-07-20T00:00:00Z'

describe('chooseTitleFacts (B4 staleness guard)', () => {
  it('prefers the oncology-reranked titles when they are ok and co-fresh with sample', () => {
    const sample = [f({ value: ['recency'], retrieved_at: NEW })]
    const relevant = [f({ value: ['relevance'], retrieved_at: NEW })]
    const chosen = chooseTitleFacts(sample, relevant)
    expect(chosen.ranked).toBe(true)
    expect(chosen.facts).toBe(relevant)
  })

  it('falls back to sample when there is no reranked fact (pre-B4 / rerank unavailable)', () => {
    const sample = [f({ value: ['recency'] })]
    const chosen = chooseTitleFacts(sample, undefined)
    expect(chosen.ranked).toBe(false)
    expect(chosen.facts).toBe(sample)
  })

  it('does NOT mask a PubMed outage: a stale ranked list never wins over a source_failed sample', () => {
    // Re-enrichment during an NCBI outage: sample_titles is freshly source_failed, relevant_titles
    // is a leftover ok row from a prior run. The block must show the outage, not the stale titles.
    const sample = [f({ status: 'source_failed', value: null, retrieved_at: NEW })]
    const relevant = [f({ value: ['stale relevance'], retrieved_at: OLD })]
    const chosen = chooseTitleFacts(sample, relevant)
    expect(chosen.ranked).toBe(false)
    expect(chosen.facts).toBe(sample) // carries the source_failed state -> the card shows the outage
  })

  it('does NOT show a stale ranked list over a FRESH recency list (rerank failed this run)', () => {
    // pubmed ok (fresh sample), but the embedder was down so relevant_titles is a stale prior row.
    const sample = [f({ value: ['fresh recency'], retrieved_at: NEW })]
    const relevant = [f({ value: ['stale relevance'], retrieved_at: OLD })]
    const chosen = chooseTitleFacts(sample, relevant)
    expect(chosen.ranked).toBe(false)
    expect(chosen.facts).toBe(sample)
  })
})
