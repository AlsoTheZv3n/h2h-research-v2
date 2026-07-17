import type { PotencySummary, SourcedFact } from '../api/types'
import { CitationChip } from './CitationChip'
import { useBriefState } from './Fact'
import { Card, NotApplicable } from './Card'
import { formatNm } from '../format'

/**
 * Binding & potency.
 *
 * Deliberately NOT "n IC50s". Measured on adagrasib: 23 of its 30 IC50 rows are
 * off-target -- cell lines, a CDK7 assay, two SARS-CoV-2 screens -- and the raw
 * range runs to 50,000 nM. The count is a row count; the median over exact,
 * on-target measurements is the answer. So the card leads with the median and
 * shows, rather than hides, everything that had to be discarded to get it.
 */
export function PotencyCard({
  facts,
  isBiologic,
}: {
  facts?: SourcedFact[]
  isBiologic: boolean
}) {
  const briefState = useBriefState()
  if (isBiologic) {
    return (
      <Card title="Binding & potency">
        <NotApplicable reason="Not applicable — biologics have no small-molecule binding curve. Their data model is out of scope for v1." />
      </Card>
    )
  }

  const fact = facts?.[0]

  if (!fact) {
    // Absent means two opposite things, and only the brief's state tells them apart.
    // This card branched on presence alone, so every not-yet-enriched drug -- which
    // is every catalog drug on first open -- was told "not collected": a measured
    // absence asserted before anyone had measured.
    return (
      <Card title="Binding & potency">
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
      <Card title="Binding & potency">
        <p
          data-testid="fact-source-failed"
          className="inline-flex items-center gap-1.5 rounded bg-unavailable-bg px-1.5 py-0.5
                     text-xs font-medium text-unavailable"
          title={fact.error ?? undefined}
        >
          <span aria-hidden="true" className="size-1.5 rounded-full bg-unavailable" />
          {fact.source} unavailable
        </p>
      </Card>
    )
  }

  const summary = fact.value as PotencySummary | null
  if (!summary) {
    return (
      <Card title="Binding & potency">
        <p className="text-sm text-ink-faint">No activities found</p>
      </Card>
    )
  }

  const discarded = summary.n_activities - summary.n_exact
  const offTarget = Object.entries(summary.off_target).sort((a, b) => b[1] - a[1])

  return (
    <Card title="Binding & potency" note="On-target IC50, excluding off-target assays">
      {summary.median_nm === null ? (
        // The honest case: without a known target there is no on/off-target split,
        // so no potency gets quoted. Reported, not silently averaged over everything.
        <p className="text-sm text-ink-muted">
          No on-target potency can be quoted
          <span className="mt-1 block text-xs text-ink-faint">
            {summary.target_chembl_ids.length === 0
              ? 'The drug’s target is unknown, so on-target and off-target measurements cannot be told apart.'
              : `${summary.n_on_target} on-target rows, none of them an exact measurement.`}
          </span>
          <CitationChip fact={fact} />
        </p>
      ) : (
        <>
          <p className="flex items-baseline gap-1.5">
            <span className="text-2xl font-semibold tracking-tight text-ink" data-testid="median-ic50">
              {formatNm(summary.median_nm)}
            </span>
            <span className="text-sm text-ink-muted">nM median</span>
            <CitationChip fact={fact} />
          </p>
          <p className="mt-0.5 text-xs text-ink-muted">
            Range {formatNm(summary.min_nm)}–{formatNm(summary.max_nm)} nM over{' '}
            {summary.n_exact} exact on-target {summary.n_exact === 1 ? 'measurement' : 'measurements'}
          </p>
        </>
      )}

      <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-2 text-xs">
        <div>
          <dt className="text-ink-faint">On target</dt>
          <dd className="text-ink">{summary.n_on_target}</dd>
        </div>
        <div>
          <dt className="text-ink-faint" title="Bounds like >10000 nM: not measurements, never averaged">
            Censored
          </dt>
          <dd className="text-ink">{summary.n_censored}</dd>
        </div>
        <div>
          <dt className="text-ink-faint">Activities</dt>
          <dd className="text-ink">{summary.n_activities}</dd>
        </div>
      </dl>

      {discarded > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-ink-faint hover:text-ink-muted">
            {discarded} of {summary.n_activities} rows excluded
          </summary>
          <ul className="mt-1.5 space-y-0.5 text-ink-muted">
            {offTarget.map(([name, n]) => (
              <li key={name} className="flex justify-between gap-2">
                <span className="truncate">{name}</span>
                <span className="text-ink-faint">{n}</span>
              </li>
            ))}
            {summary.n_censored > 0 && (
              <li className="flex justify-between gap-2 border-t border-line pt-0.5">
                <span>Censored bounds (&gt; or &lt;)</span>
                <span className="text-ink-faint">{summary.n_censored}</span>
              </li>
            )}
          </ul>
        </details>
      )}
    </Card>
  )
}
