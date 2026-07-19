import type { ReactNode } from 'react'
import type { SourcedFact } from '../api/types'
import { useBriefState } from './Fact'
import { SourceFailedChip } from './SourceFailedChip'

/**
 * The universal front half of every fact-backed section card.
 *
 * Three of a fact's states look the same in every card and mean the same thing everywhere:
 *
 *   pending        no fact yet AND the brief is not ready -- a fetch is still in flight.
 *   not-collected  no fact AND the brief is ready -- we looked, no source asserted it.
 *   source_failed  the source fell over. NOT a finding; an amber chip, never an empty.
 *
 * They were copy-pasted into four cards, and a fifth copy is one careless paste away from
 * re-committing this codebase's founding bug (source_failed rendered as "none found").
 * FactGate renders them once. The `ok` vs `empty` split is genuinely card-specific -- one
 * card's empty is `!drugs.length`, another's is `!summary` -- so that stays with the caller,
 * which receives the present fact through `children` and decides.
 */
export function FactGate({
  facts,
  children,
}: {
  facts?: SourcedFact[]
  children: (fact: SourcedFact) => ReactNode
}) {
  const briefState = useBriefState()
  const fact = facts?.[0]

  if (!fact) {
    // Absent says two opposite things, and only the brief's state tells them apart. Showing
    // "not collected" while a fetch is in flight is the founding bug wearing a new hat.
    return briefState !== 'ready' ? (
      <p data-testid="fact-pending" className="text-sm text-ink-faint italic">
        Waiting for sources…
      </p>
    ) : (
      <p data-testid="fact-not-collected" className="text-sm text-ink-faint italic">
        Not collected
      </p>
    )
  }

  if (fact.status === 'source_failed') return <SourceFailedChip fact={fact} />

  return <>{children(fact)}</>
}
