import { createContext, useContext, type ReactNode } from 'react'
import type { BriefState, SourcedFact } from '../../api/types'
import { CitationChip } from './CitationChip'
import { SourceFailedChip } from './SourceFailedChip'

/**
 * The brief's state, available to every Fact without threading it through twenty
 * call sites.
 *
 * A Fact needs it for one reason, and it is the important one: a missing fact means
 * something completely different depending on whether we have looked yet. Mid-
 * enrichment, "no mechanism row" means "not back from ChEMBL". Afterwards it means
 * "no source asserted one". Same absence, opposite readings.
 */
export const BriefStateContext = createContext<BriefState>('ready')

/** The brief's state, for cards that render outside <Fact>. */
export const useBriefState = () => useContext(BriefStateContext)

export const BriefStateProvider = BriefStateContext.Provider

/**
 * One fact, rendered according to its status. This component is the product.
 *
 * The three states are visually distinct on purpose:
 *
 *   ok             the value, plus a citation chip
 *   empty          a muted "none found" -- the source looked, and there is nothing.
 *                  A real, measured negative.
 *   source_failed  an amber "source unavailable" (via SourceFailedChip) -- we never
 *                  measured it. Amber, not red: a gap in our pipeline, not a fault in the drug.
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
  /**
   * Render a measured NUMERIC zero (an EMPTY fact whose value is 0) as the value, not the
   * emptyLabel. For a physical property -- 0 H-bond donors, 0 Lipinski violations, an
   * early-phase-1 highest phase -- a zero is a real answer, and "None found" is the exact
   * 0-vs-None lie base.py warns about. Off by default: for a COUNT (0 trials, 0 publications)
   * the emptyLabel ("None registered") is the honest read, so counts stay as they are.
   */
  showZero?: boolean
}

export function Fact({ label, facts, render, emptyLabel = 'None found', showZero }: FactProps) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-line py-2 last:border-b-0">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-sm text-ink">
        <FactValue facts={facts} render={render} emptyLabel={emptyLabel} showZero={showZero} />
      </dd>
    </div>
  )
}

function FactValue({ facts, render, emptyLabel, showZero }: Omit<FactProps, 'label'>) {
  const briefState = useContext(BriefStateContext)

  if (!facts || facts.length === 0) {
    // An absent fact says one of two opposite things, and only the brief's state
    // tells them apart: mid-enrichment it has not arrived yet; afterwards no source
    // asserted it. Showing "not collected" while a fetch is in flight would be this
    // codebase's founding bug wearing a new hat.
    if (briefState !== 'ready') {
      return (
        <span data-testid="fact-pending" className="text-ink-faint italic">
          Waiting for sources…
        </span>
      )
    }
    return (
      <span data-testid="fact-not-collected" className="text-ink-faint italic">
        Not collected
      </span>
    )
  }

  return (
    <>
      {facts.map((fact, i) => (
        <div key={`${fact.source}-${i}`} className={i > 0 ? 'mt-1' : undefined}>
          <SingleFact fact={fact} render={render} emptyLabel={emptyLabel} showZero={showZero} />
        </div>
      ))}
    </>
  )
}

function SingleFact({
  fact,
  render,
  emptyLabel,
  showZero,
}: {
  fact: SourcedFact
  render?: FactProps['render']
  emptyLabel?: string
  showZero?: boolean
}) {
  // Amber, not red, and never an empty "none found": the calm per-fact outage marker,
  // shared with every section card so the three states never blur (see SourceFailedChip).
  if (fact.status === 'source_failed') return <SourceFailedChip fact={fact} />

  if (fact.status === 'empty') {
    // A measured numeric zero is a value, not an absence -- but only for a field that opts in
    // (see showZero). The backend classifies 0 as EMPTY, so this is the one place a measured
    // zero (rendered as the value) can be told from a measured nothing (the emptyLabel).
    if (showZero && typeof fact.value === 'number') {
      return (
        <span data-testid="fact-ok">
          {render ? render(fact.value, fact) : String(fact.value)}
          <CitationChip fact={fact} />
        </span>
      )
    }
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
