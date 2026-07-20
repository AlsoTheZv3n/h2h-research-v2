import type { SourcedFact } from './api/types'

/**
 * Dedupe a drug's mechanisms across sources (B2).
 *
 * ChEMBL and Open Targets both assert an `all_moas` list, and for a multi-target drug they carry
 * the SAME mechanisms in a different order -- so rendered one fact after another the card repeats
 * itself four times over and hides that the two sources actually AGREE. Merge them into one set:
 * each distinct mechanism once, carrying the source facts that asserted it (for its provenance
 * chips). Dedup is by content -- case-insensitive exact text -- never by trusting one source's
 * position in its list (index N in ChEMBL's order is not index N in Open Targets').
 *
 * Order is source-independent: most-corroborated first (a mechanism both sources name outranks one
 * only ChEMBL does), then alphabetical -- so neither source's ordering decides the display.
 */

export interface DedupedMechanism {
  /** The display text (first spelling seen). */
  text: string
  /** One fact per source that asserted this mechanism -- the provenance to attribute it. */
  facts: SourcedFact[]
}

export function dedupeMechanisms(facts: SourcedFact[]): DedupedMechanism[] {
  const byNorm = new Map<string, DedupedMechanism>()
  for (const fact of facts) {
    if (fact.status !== 'ok' || !Array.isArray(fact.value)) continue
    for (const raw of fact.value) {
      const text = String(raw).trim()
      if (!text) continue
      const norm = text.toLowerCase()
      const seen = byNorm.get(norm)
      if (seen) {
        // Same mechanism from another source -> attribute the source, do not add a second row.
        if (!seen.facts.some((f) => f.source === fact.source)) seen.facts.push(fact)
      } else {
        byNorm.set(norm, { text, facts: [fact] })
      }
    }
  }
  return [...byNorm.values()].sort(
    (a, b) => b.facts.length - a.facts.length || a.text.localeCompare(b.text),
  )
}
