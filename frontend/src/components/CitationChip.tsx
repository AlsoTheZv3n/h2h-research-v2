import { useId, useState } from 'react'
import type { SourcedFact } from '../api/types'
import { formatAge } from '../format'

const SOURCE_LABELS: Record<string, string> = {
  chembl: 'ChEMBL',
  clinicaltrials: 'ClinicalTrials.gov',
  opentargets: 'Open Targets',
  pubmed: 'PubMed',
  eurostat: 'Eurostat',
  seer: 'SEER',
}

function confidenceTone(confidence: number | null): string {
  if (confidence === null) return 'text-ink-faint'
  if (confidence >= 0.75) return 'text-confident'
  if (confidence >= 0.4) return 'text-partial'
  return 'text-unavailable'
}

function formatRetrieved(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toISOString().slice(0, 10)
}

/**
 * The signature interaction: small and quiet until you look at it, then it tells
 * you exactly where a fact came from and when.
 *
 * Not decoration -- ChEMBL is CC BY-SA, so attribution is a licensing obligation,
 * and "where did this number come from" is the question the product exists to
 * answer.
 */
export function CitationChip({ fact }: { fact: SourcedFact }) {
  // Hover and pin are tracked apart on purpose. Toggling one shared flag on click
  // means a click after a hover *closes* the panel -- the pointer is already over
  // the chip, so the click reads as "hide this", which is the opposite of what
  // clicking a citation means. Hover peeks; click pins; the panel is open if either.
  const [hovered, setHovered] = useState(false)
  const [pinned, setPinned] = useState(false)
  const open = hovered || pinned
  const panelId = useId()
  const label = SOURCE_LABELS[fact.source] ?? fact.source

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Source: ${label}`}
        data-testid="source-info"
        onClick={() => setPinned((v) => !v)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        // An "i" icon, not the source's name spelled out on every value. The name was
        // visual noise repeated down the whole brief; the provenance -- which is the
        // point -- lives one hover away, in the panel below, where it always did.
        className="ml-1 inline-flex size-3.5 cursor-pointer items-center justify-center rounded-full
                   border border-line align-middle font-serif text-[9px] font-semibold italic
                   leading-none text-ink-faint transition-colors hover:border-accent
                   hover:text-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span aria-hidden="true">i</span>
      </button>

      {open && (
        <span
          id={panelId}
          role="tooltip"
          className="absolute bottom-full left-0 z-20 mb-1 block w-64 rounded-md border
                     border-line bg-card p-2.5 text-xs shadow-lg"
        >
          <span className="block font-medium text-ink">{label}</span>
          {/* E4: freshness in words -- "checked 3 months ago" reads at a glance where an ISO
              date does not, so a stale fact and a fresh one no longer look identical. The exact
              date stays underneath, faint, so nothing is lost. */}
          <span className="mt-1 block text-ink-muted" data-testid="fact-age">
            Checked {formatAge(fact.retrieved_at)}
          </span>
          <span className="block text-[10px] text-ink-faint">
            {formatRetrieved(fact.retrieved_at)}
          </span>
          {fact.confidence !== null && (
            <span className={`mt-0.5 block ${confidenceTone(fact.confidence)}`}>
              Confidence {(fact.confidence * 100).toFixed(0)}%
            </span>
          )}
          {fact.source_url && (
            <a
              href={fact.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-1.5 block truncate text-accent underline underline-offset-2"
            >
              {fact.source_url}
            </a>
          )}
        </span>
      )}
    </span>
  )
}
