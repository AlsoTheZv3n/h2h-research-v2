import { Link } from 'react-router-dom'
import type {
  SourcedFact,
  TargetAlterationCancer,
  TargetAlterationFrequency,
} from '../../api/types'
import { Card } from '../ui/Card'
import { CitationChip } from '../ui/CitationChip'
import { FactGate } from '../ui/FactGate'

/**
 * The transpose of the cancer page's mutation-frequency block (#43): for THIS gene, how often it is
 * somatically mutated in each of the cancers it drives (cBioPortal, TCGA cohorts). It answers "where
 * is my target actually mutated" — the orthogonal quantitative signal beside the association score.
 *
 * Honest states, kept apart:
 *   no_cohort      none of the cancers this gene drives have a curated cohort — a coverage gap.
 *   gene_unmapped  this gene could not be joined to a cBioPortal id — not measurable, not a zero.
 *   measured       per-cancer readings; each row is measured, a measured 0%, or that cohort's outage.
 *
 * SCOPE (mutation-only) is stated, and the ODbL attribution is on the surface.
 */
export function TargetAlterationCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card
      id={id}
      title="Mutation frequency by cancer"
      note="How often this gene is mutated in the cancers it drives · cBioPortal (TCGA)"
    >
      <FactGate facts={facts}>
        {(fact) => {
          const value = fact.value as TargetAlterationFrequency | null
          if (!value || value.state === 'gene_unmapped') {
            return (
              <p className="text-sm text-ink-faint" data-testid="target-alt-gene-unmapped">
                This gene could not be matched to a cBioPortal identifier, so its mutation frequency
                is <span className="italic">not measured</span> — which is not zero.
                <CitationChip fact={fact} />
              </p>
            )
          }
          if (value.state === 'no_cohort') {
            return (
              <p className="text-sm text-ink-faint" data-testid="target-alt-no-cohort">
                None of the cancers this gene drives has a matched cBioPortal cohort, so mutation
                frequency is <span className="italic">not measured</span> here — which is not zero.
                <CitationChip fact={fact} />
              </p>
            )
          }
          return <TargetAlterationBody value={value} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

// Measured cancers first, by descending frequency; a cohort outage sinks to the end (an amber gap,
// never a low frequency). measured_zero keeps its real 0% among the measured rows.
function sortCancers(cancers: TargetAlterationCancer[]): TargetAlterationCancer[] {
  return [...cancers].sort((a, b) => {
    if (a.state === 'source_failed' && b.state !== 'source_failed') return 1
    if (b.state === 'source_failed' && a.state !== 'source_failed') return -1
    return (b.pct ?? 0) - (a.pct ?? 0)
  })
}

function TargetAlterationBody({
  value,
  fact,
}: {
  value: TargetAlterationFrequency
  fact: SourcedFact
}) {
  const cancers = sortCancers(value.cancers ?? [])
  const max = Math.max(...cancers.map((c) => c.pct ?? 0), 1)

  return (
    <>
      <p className="mb-3 text-[11px] text-ink-faint" data-testid="target-alt-scope">
        {value.alteration_scope} — a floor on the true alteration frequency. Cohorts: TCGA PanCancer
        Atlas.
      </p>

      <ul className="divide-y divide-line" data-testid="target-alt-cancers">
        {cancers.map((c) => (
          <li
            key={c.disease_id}
            data-testid="target-alt-row"
            className="flex items-center gap-2 py-1.5 text-sm"
          >
            <Link
              to={`/cancers/${c.disease_id}`}
              className="w-40 shrink-0 truncate text-accent hover:underline"
              title={c.name ?? c.disease_id}
            >
              {c.name ?? c.disease_id}
            </Link>
            <CancerReading cancer={c} max={max} />
          </li>
        ))}
      </ul>

      {value.n_more ? (
        <p className="mt-2 text-[11px] text-ink-faint">
          + {value.n_more} more cohort{value.n_more === 1 ? '' : 's'} not shown.
        </p>
      ) : null}

      {value.attribution && (
        <details className="mt-3 text-[11px] text-ink-faint" data-testid="target-alt-attribution">
          <summary className="cursor-pointer text-ink-muted">Data &amp; attribution</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {value.attribution.portal.map((cite) => (
              <li key={cite}>{cite}</li>
            ))}
          </ul>
          <p className="mt-1">
            cBioPortal data is under the ODC Open Database License (ODbL); attribution required. Each
            row names its source cohort.
          </p>
        </details>
      )}

      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

function CancerReading({ cancer, max }: { cancer: TargetAlterationCancer; max: number }) {
  if (cancer.state === 'source_failed') {
    return (
      <span
        className="text-[11px] text-partial italic"
        data-testid="target-alt-cohort-failed"
        title={`Could not fetch ${cancer.study_label} — unavailable, not zero.`}
      >
        cohort unavailable
      </span>
    )
  }
  const pct = cancer.pct ?? 0
  const isZero = cancer.state === 'measured_zero' || pct === 0
  return (
    <span className="flex flex-1 items-center gap-2">
      <span className="h-2 flex-1 rounded bg-surface">
        <span
          className={`block h-2 rounded ${isZero ? 'bg-transparent' : 'bg-accent'}`}
          style={{ width: `${(pct / max) * 100}%` }}
        />
      </span>
      <span
        className={`w-24 shrink-0 text-right text-xs tabular-nums ${isZero ? 'text-ink-faint' : 'text-ink'}`}
        title={
          isZero
            ? `Profiled in ${cancer.study_label}, never mutated — a measured 0%, not "not measured".`
            : `${cancer.altered_n} of ${cancer.denominator_n} samples in ${cancer.study_label} carry a mutation.`
        }
        data-testid={isZero ? 'target-alt-zero' : 'target-alt-measured'}
      >
        {pct.toFixed(1)}%{isZero && <span className="ml-1 text-ink-faint">· none</span>}
      </span>
    </span>
  )
}
