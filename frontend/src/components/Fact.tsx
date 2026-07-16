import type { ReactNode } from 'react'
import type { SourcedFact } from '../api/types'
import { CitationChip } from './CitationChip'

/**
 * One fact, rendered according to its status. This component is the product.
 *
 * The three states are visually distinct on purpose:
 *
 *   ok             the value, plus a citation chip
 *   empty          a muted "none found" -- the source looked, and there is nothing.
 *                  A real, measured negative.
 *   source_failed  a red "source unavailable" -- we never measured it.
 *
 * Rendering source_failed as "none found" would tell the reader a drug has no
 * mechanism when the truth is that ChEMBL was down. That is the exact lie this
 * whole codebase is built to refuse, and the UI is the last place it could sneak
 * back in.
 */

interface FactProps {
  label: string
  facts?: SourcedFact[]
  /** How to display an `ok` value. Defaults to String(value). */
  render?: (value: unknown, fact: SourcedFact) => ReactNode
  /** What "nothing" reads as for this field, e.g. "No mechanism annotated". */
  emptyLabel?: string
}

export function Fact({ label, facts, render, emptyLabel = 'None found' }: FactProps) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-line py-2 last:border-b-0">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-sm text-ink">
        <FactValue facts={facts} render={render} emptyLabel={emptyLabel} />
      </dd>
    </div>
  )
}

function FactValue({ facts, render, emptyLabel }: Omit<FactProps, 'label'>) {
  // No row at all: this source was never asked about this field. Distinct again
  // from both "nothing found" and "the source fell over".
  if (!facts || facts.length === 0) {
    return <span className="text-ink-faint italic">Not collected</span>
  }

  return (
    <>
      {facts.map((fact, i) => (
        <div key={`${fact.source}-${i}`} className={i > 0 ? 'mt-1' : undefined}>
          <SingleFact fact={fact} render={render} emptyLabel={emptyLabel} />
        </div>
      ))}
    </>
  )
}

function SingleFact({
  fact,
  render,
  emptyLabel,
}: {
  fact: SourcedFact
  render?: FactProps['render']
  emptyLabel?: string
}) {
  if (fact.status === 'source_failed') {
    return (
      <span
        data-testid="fact-source-failed"
        className="inline-flex items-center gap-1.5 rounded bg-unavailable-bg px-1.5 py-0.5
                   text-xs font-medium text-unavailable"
        title={fact.error ?? undefined}
      >
        <span aria-hidden="true" className="size-1.5 rounded-full bg-unavailable" />
        {fact.source} unavailable
      </span>
    )
  }

  if (fact.status === 'empty') {
    return (
      <span data-testid="fact-empty" className="text-ink-faint">
        {emptyLabel}
        <CitationChip fact={fact} />
      </span>
    )
  }

  return (
    <span data-testid="fact-ok">
      {render ? render(fact.value, fact) : String(fact.value)}
      <CitationChip fact={fact} />
    </span>
  )
}
