import type { ReactNode } from 'react'
import type { Resolved, SourcedFact } from '../api/types'
import { NotApplicable } from './Card'
import { CitationChip } from './CitationChip'

/**
 * The match-type layer for a disease-map-resolved section (epidemiology, survival).
 *
 * FactGate has already handled pending / not-collected / source_failed. What is left is what an
 * OK or EMPTY *resolved* fact means, and the Gate-1 distinction that must survive into the UI:
 *
 *   unmapped  -> "not available for this cancer" -- its own answer, a NotApplicable box, never
 *                dressed up as empty or as an outage.
 *   rollup    -> the figures describe a BROADER entity, so a banner NAMES it ("broader than
 *                {cancer}") before the data -- a specific page must never pass broader figures
 *                off as its own. This is the whole reason the fact carries source_label.
 *   exact     -> just the data.
 *   empty     -> the source resolved but reported nothing (a measured EMPTY).
 */
export function ResolvedSection<T extends Resolved>({
  fact,
  cancerName,
  emptyLabel,
  children,
}: {
  fact: SourcedFact
  cancerName: string
  emptyLabel: string
  children: (value: T) => ReactNode
}) {
  if (fact.status === 'empty' || !fact.value) {
    return (
      <p data-testid="fact-empty" className="text-sm text-ink-faint">
        {emptyLabel}
        <CitationChip fact={fact} />
      </p>
    )
  }

  const value = fact.value as T
  if (value.match_type === 'unmapped') {
    return (
      <NotApplicable
        reason={`Not available for ${cancerName} — no matching category in this source.`}
      />
    )
  }

  return (
    <>
      {value.match_type === 'rollup' && value.source_label && (
        <p
          data-testid="rollup-note"
          className="mb-2 rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink-muted"
        >
          Showing <span className="font-medium text-ink">{value.source_label}</span> — broader
          than {cancerName}. These figures describe the wider category, not {cancerName} alone.
        </p>
      )}
      {children(value)}
    </>
  )
}
