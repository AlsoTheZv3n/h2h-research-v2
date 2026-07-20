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

  // A source that was DOWN is surfaced regardless of what the others said. Testing only
  // facts.every(source_failed) would let an outage vanish the moment ANY other source answered --
  // including a source that answered EMPTY, collapsing "ChEMBL was down" into a definitive "none
  // annotated". That is this codebase's founding bug, so every failed source gets its amber chip.
  const failed = facts.filter((f) => f.status === 'source_failed')
  const mechanisms = dedupeMechanisms(facts)

  if (mechanisms.length === 0) {
    // No source that answered named a mechanism. If a source was down, that outage -- not a
    // definitive empty -- is (at least partly) why: show it, never render it as "none".
    if (failed.length > 0) {
      return (
        <>
          {failed.map((f) => (
            <SourceFailedChip key={f.source} fact={f} />
          ))}
        </>
      )
    }
    // Measured, none: a real empty.
    return (
      <span data-testid="fact-empty" className="text-ink-faint">
        None annotated
        <CitationChip fact={facts[0]} />
      </span>
    )
  }

  return (
    <>
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
      {/* A partial outage: mechanisms from the source(s) that answered, but another was down -- so
          the set never reads as complete when a source could not be asked. */}
      {failed.map((f) => (
        <SourceFailedChip key={f.source} fact={f} />
      ))}
    </>
  )
}
