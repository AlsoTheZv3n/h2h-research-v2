import type { Disagreement } from '../api/types'

const SOURCE_LABELS: Record<string, string> = {
  chembl: 'ChEMBL',
  clinicaltrials: 'ClinicalTrials.gov',
  opentargets: 'Open Targets',
  pubmed: 'PubMed',
  eurostat: 'Eurostat',
  seer: 'SEER',
}

/**
 * Source disagreement (E1): the honest state after ok / empty / source_failed. When two sources
 * give a comparable fact different values, this NAMES the conflict -- a reliability signal the
 * reader used to have to spot by scanning two rows and noticing. Both sides stay visible, each
 * linking to its own source; none silently wins.
 *
 * Amber, like the source-unavailable advisory: a heads-up, not an alarm -- and never on a
 * patient-outcome value (this is clinical phase, a process fact). Renders nothing when sources
 * agree, because the backend withholds a non-conflict rather than asserting one.
 */
export function DisagreementPanel({ disagreements }: { disagreements?: Disagreement[] }) {
  if (!disagreements || disagreements.length === 0) return null
  return (
    <section
      data-testid="disagreements"
      aria-label="Sources disagree"
      className="mb-4 rounded-lg border border-partial/40 bg-partial-bg p-3"
    >
      <h2 className="mb-1.5 text-xs font-medium text-partial">Sources disagree</h2>
      <ul className="space-y-1.5">
        {disagreements.map((d) => (
          <li key={`${d.block}-${d.label}`} className="text-sm text-ink" data-testid="disagreement">
            {/* The label links to the block, so the reader can jump to the conflicting rows. */}
            <a href={`#${d.block}`} className="font-medium hover:underline">
              {d.label}
            </a>
            {': '}
            {d.values.map((v, i) => (
              <span key={`${v.source}-${v.display}`}>
                {i > 0 && <span className="text-ink-faint"> · </span>}
                {v.source_url ? (
                  <a
                    href={v.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-accent hover:underline"
                  >
                    {SOURCE_LABELS[v.source] ?? v.source}
                  </a>
                ) : (
                  <span className="text-ink-muted">{SOURCE_LABELS[v.source] ?? v.source}</span>
                )}{' '}
                says {v.display}
              </span>
            ))}
          </li>
        ))}
      </ul>
    </section>
  )
}
