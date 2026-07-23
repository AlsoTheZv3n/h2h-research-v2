import { Link } from 'react-router-dom'
import type { ExtractedRelation, ExtractedRelations, SourcedFact } from '../../api/types'
import { formatCount } from '../../format'
import { Card } from '../ui/Card'
import { CitationChip } from '../ui/CitationChip'
import { FactGate } from '../ui/FactGate'

/**
 * A target's machine-EXTRACTED literature relations (#44, PubTator3): the diseases and chemicals it
 * co-occurs with, each with a relation type and a co-mention count.
 *
 * The whole point of this card is the distinction the usability harness exists to protect, one rung
 * up: these are NLP-extracted, NOT curated. A relation is a statistical co-occurrence, not a fact a
 * human verified. So the card is deliberately set apart from the curated cards -- a dashed amber
 * frame and an explicit banner -- so a reader can tell at a glance that it is a different KIND of
 * evidence, and the count is labelled co-mention VOLUME, never curated weight. It is never blended
 * with the sourced facts above it.
 */

// PubTator's relation labels, in reader words. Unknown types fall back to the raw label rather than
// being dropped, so a new PubTator relation is visible rather than silently hidden.
const REL_LABEL: Record<string, string> = {
  associate: 'associated with',
  positive_correlate: 'positively correlated',
  negative_correlate: 'negatively correlated (e.g. inhibited by)',
  inhibit: 'inhibited by',
  stimulate: 'stimulated by',
  interact: 'interacts with',
  cause: 'implicated in',
  treat: 'treats',
}
const relLabel = (t: string) => REL_LABEL[t] ?? t.replace(/_/g, ' ')

export function ExtractedRelationsCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card
      id={id}
      title="Extracted literature relations"
      note="Machine-extracted, not curated · PubTator3 (NLM), NLP over the literature"
    >
      <FactGate facts={facts}>
        {(fact) => {
          const value = fact.value as ExtractedRelations | null
          if (!value || value.state === 'gene_unmapped') {
            return (
              <p className="text-sm text-ink-faint" data-testid="extracted-gene-unmapped">
                This gene could not be matched to a literature identifier, so no extracted relations
                are shown. <CitationChip fact={fact} />
              </p>
            )
          }
          return <ExtractedBody value={value} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

function ExtractedBody({ value, fact }: { value: ExtractedRelations; fact: SourcedFact }) {
  const diseases = value.diseases ?? []
  const chemicals = value.chemicals ?? []
  return (
    <div
      className="rounded-md border border-dashed border-partial/60 bg-partial-bg/30 p-3"
      data-testid="extracted-frame"
    >
      {/* The banner: the single most important thing on this card is that it is NOT curated. */}
      <p className="mb-3 text-xs text-partial" data-testid="extracted-banner">
        <span className="font-semibold">Extracted, not curated.</span> These are machine-found
        co-occurrences from the literature (PubTator3), <span className="italic">not verified
        facts</span>. The count is <span className="italic">co-mentions</span> — how many papers
        mention both — a measure of attention, not of evidence.
      </p>

      <RelationList
        title="Diseases"
        testid="extracted-diseases"
        total={value.n_disease_relations}
        relations={diseases}
      />
      <div className="mt-3">
        <RelationList
          title="Chemicals & drugs"
          testid="extracted-chemicals"
          total={value.n_chemical_relations}
          relations={chemicals}
        />
      </div>

      {value.attribution && (
        <details className="mt-3 text-[11px] text-ink-faint" data-testid="extracted-attribution">
          <summary className="cursor-pointer text-ink-muted">Data &amp; attribution</summary>
          <p className="mt-1">{value.attribution}</p>
        </details>
      )}
      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </div>
  )
}

function RelationList({
  title,
  testid,
  total,
  relations,
}: {
  title: string
  testid: string
  total?: number
  relations: ExtractedRelation[]
}) {
  if (relations.length === 0) {
    return (
      <p className="text-xs text-ink-faint">
        {title}: <span className="italic">none extracted</span>
      </p>
    )
  }
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-ink-muted">
        {title}
        {typeof total === 'number' && total > relations.length && (
          <span className="font-normal text-ink-faint"> · top {relations.length} of {total}</span>
        )}
      </p>
      <ul className="divide-y divide-line/60" data-testid={testid}>
        {relations.map((r) => (
          <li key={r.name} data-testid="extracted-row" className="flex items-center gap-2 py-1 text-sm">
            <span className="min-w-0 flex-1 truncate">
              {/* A disease links to our cancer page ONLY when the MeSH id bridged to our catalog;
                  otherwise it is an unlinked extracted mention (a name, not a claim of coverage). */}
              {r.mondo_id ? (
                <Link
                  to={`/cancers/${r.mondo_id}`}
                  className="text-accent hover:underline"
                  title={`Open ${r.mondo_label ?? r.name} in the catalog`}
                >
                  {r.name}
                </Link>
              ) : (
                <span className="text-ink">{r.name}</span>
              )}
              <span className="ml-1 text-[11px] text-ink-faint">· {relLabel(r.rel_type)}</span>
            </span>
            <span
              className="shrink-0 text-[11px] tabular-nums text-ink-faint"
              title={`${r.co_mentions} papers mention both this gene and ${r.name} (co-mentions, not evidence)`}
            >
              {formatCount(r.co_mentions)} co-mentions
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
