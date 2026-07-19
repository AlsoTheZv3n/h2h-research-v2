import { Link } from 'react-router-dom'
import type { AssociatedCancers, SourcedFact } from '../api/types'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'

/**
 * The cancers a target is associated with -- the cancer target-landscape run backwards. Open
 * Targets' reverse query returns a target's associated diseases (cancers AND non-cancers);
 * enrichment already filtered them to the cancers our catalog lists, so every row here is a
 * live link into its brief. Handles the honest states via FactGate: pending while enriching,
 * a calm amber chip on an outage, a muted "none" for a real empty -- never an outage rendered
 * as "drives no cancers".
 *
 * The count (n_cancers) is over the whole filtered set; the list is the top slice by score.
 */
export function AssociatedCancersCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card
      id={id}
      title="Associated cancers"
      note="Cancers this target is associated with · Open Targets association score, filtered to the catalog"
    >
      <FactGate facts={facts}>
        {(fact) => {
          const value = fact.value as AssociatedCancers | null
          const cancers = value?.cancers ?? []
          if (fact.status === 'empty' || cancers.length === 0) {
            return (
              <p className="text-sm text-ink-faint">
                No associated cancers in the catalog
                <CitationChip fact={fact} />
              </p>
            )
          }
          const total = value?.n_cancers ?? cancers.length
          return (
            <>
              {total > cancers.length && (
                <p className="mb-2 text-[11px] text-ink-faint">
                  Top {cancers.length} of {total} associated cancers, by score.
                </p>
              )}
              <ul className="divide-y divide-line" data-testid="associated-cancers">
                {cancers.map((c) => (
                  <li
                    key={c.disease_id}
                    data-testid="associated-cancer-row"
                    className="flex items-center gap-2 py-1.5 text-sm"
                  >
                    <span className="w-10 shrink-0 tabular-nums text-xs text-ink-muted">
                      {c.score.toFixed(2)}
                    </span>
                    <Link
                      to={`/cancers/${c.disease_id}`}
                      className="text-accent hover:underline"
                      title="Open this cancer's brief"
                    >
                      {c.name}
                    </Link>
                    <span className="ml-auto font-mono text-[11px] text-ink-faint">
                      {c.disease_id}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-2 text-right">
                <CitationChip fact={fact} />
              </div>
            </>
          )
        }}
      </FactGate>
    </Card>
  )
}
