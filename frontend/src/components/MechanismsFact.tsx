import type { SourcedFact } from '../api/types'
import { CitationChip } from './CitationChip'
import { useBriefState } from './Fact'
import { SourceFailedChip } from './SourceFailedChip'
import { dedupeMechanisms } from '../mechanisms'

/**
 * The "All mechanisms" row (B2), deduplicated across sources.
 *
 * ChEMBL and Open Targets each assert the whole mechanism list, so rendered one fact after another
 * (as a plain multi-fact Fact does) the card repeats the same mechanisms twice, in different order
 * -- noise that also hides that the two sources AGREE. This renders one deduped set, each mechanism
 * carrying a provenance chip per source that named it. It owns the honest states itself, the same
 * three every fact-backed row must keep distinct: pending vs not-collected vs source_failed.
 */
export function MechanismsFact({ facts }: { facts?: SourcedFact[] }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-line py-2 last:border-b-0">
      <dt className="text-xs text-ink-faint">All mechanisms</dt>
      <dd className="text-sm text-ink">
        <MechanismsValue facts={facts} />
      </dd>
    </div>
  )
}

function MechanismsValue({ facts }: { facts?: SourcedFact[] }) {
  const briefState = useBriefState()

  if (!facts || facts.length === 0) {
    // Absent means opposite things by brief state -- the founding distinction, kept here too.
    return briefState !== 'ready' ? (
      <span data-testid="fact-pending" className="text-ink-faint italic">
        Waiting for sources…
      </span>
    ) : (
      <span data-testid="fact-not-collected" className="text-ink-faint italic">
        Not collected
      </span>
    )
  }

  // Every source failed -> an outage, never "no mechanisms". A single ok source still yields a set.
  if (facts.every((f) => f.status === 'source_failed')) {
    return <SourceFailedChip fact={facts[0]} />
  }

  const mechanisms = dedupeMechanisms(facts)
  if (mechanisms.length === 0) {
    // Measured, none: a real empty. Cite a source that answered (not the failed one).
    const cite = facts.find((f) => f.status !== 'source_failed') ?? facts[0]
    return (
      <span data-testid="fact-empty" className="text-ink-faint">
        None annotated
        <CitationChip fact={cite} />
      </span>
    )
  }

  return (
    <ul data-testid="mechanisms" className="space-y-0.5">
      {mechanisms.map((m) => (
        <li key={m.text} className="flex flex-wrap items-baseline gap-x-1">
          <span>{m.text}</span>
          {/* One chip per source that named it -- the provenance stays on the fact, and two chips
              is the visible sign the sources agree. */}
          {m.facts.map((f) => (
            <CitationChip key={f.source} fact={f} />
          ))}
        </li>
      ))}
    </ul>
  )
}
