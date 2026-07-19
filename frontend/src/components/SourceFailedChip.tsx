import type { SourcedFact } from '../api/types'

/**
 * A source we could not reach, rendered per fact.
 *
 * Amber, not red: a source that was down is a gap in our pipeline, not a fault in the
 * entity. And never rendered as an empty "none found" -- telling a reader a cancer has no
 * pipeline when Open Targets was merely down is the exact lie this codebase refuses. This is
 * the ONE place that chip's markup lives; Fact and every section card render it through here,
 * so the wording and the amber-not-red decision can never drift between copies.
 */
export function SourceFailedChip({ fact }: { fact: SourcedFact }) {
  return (
    <span
      data-testid="fact-source-failed"
      className="inline-flex items-center gap-1.5 rounded bg-partial-bg px-1.5 py-0.5
                 text-xs font-medium text-partial"
      title={fact.error ?? undefined}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full bg-partial" />
      {fact.source} unavailable
    </span>
  )
}
