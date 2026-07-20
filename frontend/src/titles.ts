import type { SourcedFact } from './api/types'

/**
 * Which titles the drug page's "Key papers" block shows (B4), chosen so a stale oncology-reranked
 * list can never mask the canonical PubMed titles fact.
 *
 * Prefer `relevant_titles` only when it is `ok` AND at least as fresh as `sample_titles` -- because
 * the two are co-written in the same enrichment, a relevant_titles OLDER than sample_titles is a
 * leftover from a prior run, and sample_titles now carries the current state (a fresh recency list,
 * or a source_failed outage). Preferring the stale ranked list there would render old titles as
 * current, or hide a PubMed outage behind them -- the honest-state collapse this guard prevents.
 */
export function chooseTitleFacts(
  sample?: SourcedFact[],
  relevant?: SourcedFact[],
): { facts?: SourcedFact[]; ranked: boolean } {
  const r = relevant?.[0]
  const s = sample?.[0]
  const useRanked =
    !!r && r.status === 'ok' && (!s || new Date(r.retrieved_at) >= new Date(s.retrieved_at))
  return { facts: useRanked ? relevant : sample, ranked: useRanked }
}
