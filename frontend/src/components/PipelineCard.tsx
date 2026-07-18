import { Link } from 'react-router-dom'
import type { PipelineData, SourcedFact } from '../api/types'
import { formatCount } from '../format'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { useBriefState } from './Fact'

// Open Targets' maxClinicalStage enum, in human words. Most advanced first is the order
// the backend already sorts by.
const PHASE_LABELS: Record<string, string> = {
  APPROVAL: 'Approved',
  PHASE_4: 'Phase 4',
  PREAPPROVAL: 'Pre-registration',
  PHASE_3: 'Phase 3',
  PHASE_2_3: 'Phase 2/3',
  PHASE_2: 'Phase 2',
  PHASE_1_2: 'Phase 1/2',
  PHASE_1: 'Phase 1',
  EARLY_PHASE_1: 'Early Phase 1',
  PHASE_0: 'Phase 0',
  PRECLINICAL: 'Preclinical',
  UNKNOWN: 'Unknown stage',
}

/**
 * The drugs and clinical candidates for this cancer, grouped by highest clinical stage.
 * From Open Targets' disease->drugs list (which rolls the disease ontology up, so a drug
 * for a subtype counts for the parent). A drug we have a brief for links to it; the rest
 * are shown as plain text -- linkability is by exact ChEMBL id, never by name. Handles
 * the honest states itself: an outage is an amber chip, never an empty pipeline.
 */
export function PipelineCard({
  facts,
  catalogDrugIds,
}: {
  facts?: SourcedFact[]
  catalogDrugIds: string[]
}) {
  const briefState = useBriefState()
  const fact = facts?.[0]

  if (!fact) {
    return (
      <Card title="Pipeline">
        {briefState !== 'ready' ? (
          <p data-testid="fact-pending" className="text-sm text-ink-faint italic">
            Waiting for sources…
          </p>
        ) : (
          <p data-testid="fact-not-collected" className="text-sm text-ink-faint italic">
            Not collected
          </p>
        )}
      </Card>
    )
  }

  if (fact.status === 'source_failed') {
    return (
      <Card title="Pipeline">
        <p
          data-testid="fact-source-failed"
          className="inline-flex items-center gap-1.5 rounded bg-partial-bg px-1.5 py-0.5
                     text-xs font-medium text-partial"
          title={fact.error ?? undefined}
        >
          <span aria-hidden="true" className="size-1.5 rounded-full bg-partial" />
          {fact.source} unavailable
        </p>
      </Card>
    )
  }

  const data = fact.value as PipelineData | null
  if (fact.status === 'empty' || !data || !data.by_phase?.length) {
    return (
      <Card title="Pipeline">
        <p className="text-sm text-ink-faint">
          No drug programmes indicated for this cancer
          <CitationChip fact={fact} />
        </p>
      </Card>
    )
  }

  const inCatalog = new Set(catalogDrugIds)
  return (
    <Card
      title="Pipeline"
      note={`${formatCount(data.total)} drugs & clinical candidates · by highest stage · Open Targets`}
    >
      <div data-testid="pipeline" className="space-y-2.5">
        {data.by_phase.map((phase) => (
          <div key={phase.stage}>
            <div className="flex items-baseline justify-between border-b border-line pb-0.5">
              <span className="text-sm font-medium text-ink">
                {PHASE_LABELS[phase.stage] ?? phase.stage}
              </span>
              <span className="text-xs tabular-nums text-ink-muted">
                {formatCount(phase.count)}
              </span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              {phase.drugs.map((drug, i) => (
                <span key={drug.chembl_id}>
                  {i > 0 && ', '}
                  {inCatalog.has(drug.chembl_id) ? (
                    <Link to={`/drugs/${drug.chembl_id}`} className="text-accent hover:underline">
                      {drug.name}
                    </Link>
                  ) : (
                    <span>{drug.name}</span>
                  )}
                </span>
              ))}
              {phase.count > phase.drugs.length && (
                <span className="text-ink-faint">
                  {' '}
                  … +{formatCount(phase.count - phase.drugs.length)} more
                </span>
              )}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </Card>
  )
}
