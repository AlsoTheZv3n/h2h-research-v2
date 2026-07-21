import type { SourcedFact, TrialReality } from '../api/types'
import { formatCount } from '../format'
import { ctgovPhaseLabel, humanize } from '../phases'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'

// overallStatus enum, in human words.
const STATUS_LABELS: Record<string, string> = {
  RECRUITING: 'Recruiting',
  NOT_YET_RECRUITING: 'Not yet recruiting',
  ENROLLING_BY_INVITATION: 'Enrolling by invitation',
  ACTIVE_NOT_RECRUITING: 'Active, not recruiting',
  COMPLETED: 'Completed',
  TERMINATED: 'Terminated',
  SUSPENDED: 'Suspended',
  WITHDRAWN: 'Withdrawn',
  UNKNOWN: 'Unknown status',
  NO_LONGER_AVAILABLE: 'No longer available',
  APPROVED_FOR_MARKETING: 'Approved for marketing',
  AVAILABLE: 'Available',
}

const statusLabel = (s: string) => STATUS_LABELS[s] ?? humanize(s)

/**
 * The cancer's real registered-trial landscape from ClinicalTrials.gov (queried by condition text,
 * so a SOFT match the card owns in words). Distinct from the pipeline card: pipeline is the drug-
 * development roll-up (which drugs); this is the actual registered trials and their state.
 *
 * Honest states throughout: an outage is an amber chip (FactGate), never "no trials"; a real EMPTY
 * is "no registered trials"; the true count travels with the scanned sample so a distribution never
 * reads as the whole; and the two nullable sub-signals (count, DACH) render as "unavailable"/
 * "unknown", never as zero.
 */
export function TrialRealityCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card id={id} title="Trial reality">
      <FactGate facts={facts}>
        {(fact) => {
          const data = fact.value as TrialReality | null
          // An outage never reaches here (FactGate renders the amber chip). This is the real
          // empty -- the source looked and there are no registered trials -- carrying its chip.
          if (fact.status === 'empty' || !data) {
            return (
              <p className="text-sm text-ink-faint">
                No registered trials mention this condition
                <CitationChip fact={fact} />
              </p>
            )
          }
          return <TrialRealityBody data={data} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

function TrialRealityBody({ data, fact }: { data: TrialReality; fact: SourcedFact }) {
  const total = data.n_trials
  return (
    <>
      {/* The headline count is the TRUE total (countTotal), or an honest "unavailable" -- never
          zero, because a true zero is an EMPTY fact handled above. The soft condition match is
          owned in words, not implied away. */}
      <p className="text-xs text-ink-muted" data-testid="trial-count">
        {total !== null ? (
          <>
            <span className="font-medium text-ink">{formatCount(total)}</span> registered trials
            mentioning <span className="font-medium text-ink">{data.condition}</span>
          </>
        ) : (
          <span className="italic text-ink-faint">
            Trial count unavailable — the source returned trials but no total.
          </span>
        )}
        <span className="mt-0.5 block text-ink-faint">
          Matched on condition text (ClinicalTrials.gov keys by condition, not a disease id), so this
          is a broad set — some trials list this cancer among several.
        </span>
        {total !== null && data.n_trials_scanned < total && (
          <span className="mt-0.5 block text-ink-faint" data-testid="trial-sample-note">
            Phase &amp; status below are over the {formatCount(data.n_trials_scanned)} most-relevant
            trials scanned, not all {formatCount(total)}.
          </span>
        )}
      </p>

      {/* DACH recruiting: a TRUE query-side count, or "unknown" (never 0) when the sub-query failed. */}
      <p className="mt-2 text-xs" data-testid="trial-dach">
        <span className="text-ink-muted">Recruiting in DE/AT/CH: </span>
        {data.dach_recruiting !== null ? (
          <span className="font-medium text-ink">{formatCount(data.dach_recruiting)}</span>
        ) : (
          <span className="italic text-ink-faint">unknown (sub-query unavailable)</span>
        )}
      </p>

      {/* E3: how fresh the trial landscape is -- the most-recent registration year. The derived
          silent-stalling signal (in the synthesis up top) reads from this same date. Shown only when
          known; a missing date is silent, never "0" or "never". */}
      {data.latest_registration && (
        <p className="mt-1 text-xs" data-testid="trial-latest-registration">
          <span className="text-ink-muted">Last new trial registered: </span>
          <span className="font-medium text-ink">{data.latest_registration.slice(0, 4)}</span>
        </p>
      )}

      {/* Phase distribution as COUNTS, never shares: a combined-design trial (Phase 1/2) counts in
          each of its phases, so these need not sum to the scanned total. */}
      <Distribution
        title="Phase (trials per phase)"
        testid="trial-phase-distribution"
        items={data.by_phase.map((p) => ({
          key: p.phase,
          label: ctgovPhaseLabel(p.phase),
          count: p.count,
        }))}
      />

      <Distribution
        title="Status"
        testid="trial-status-distribution"
        items={data.by_status.map((s) => ({
          key: s.status,
          label: statusLabel(s.status),
          count: s.count,
        }))}
      />

      {/* The honesty angle: not just "N trials" but "M stopped, and why". A stopped trial with no
          stated whyStopped is counted but contributes no reason -- never an invented one. */}
      <div className="mt-3 text-xs" data-testid="trial-stopped">
        <p className="text-ink-muted">
          <span className="font-medium text-ink">{formatCount(data.stopped.count)}</span> stopped
          (terminated, withdrawn or suspended) in the scanned sample
        </p>
        {data.stopped.reasons.length > 0 ? (
          <ul className="mt-1 space-y-0.5">
            {data.stopped.reasons.map((r) => (
              <li key={r.reason} className="flex gap-2 text-ink-faint">
                <span className="shrink-0 tabular-nums text-ink-muted">{formatCount(r.count)}×</span>
                <span>{r.reason}</span>
              </li>
            ))}
          </ul>
        ) : (
          data.stopped.count > 0 && (
            <p className="mt-1 italic text-ink-faint">No stated reason recorded.</p>
          )
        )}
      </div>

      <div className="mt-3 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

function Distribution({
  title,
  testid,
  items,
}: {
  title: string
  testid: string
  items: { key: string; label: string; count: number }[]
}) {
  if (items.length === 0) return null
  const max = Math.max(...items.map((i) => i.count), 1)
  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] font-medium text-ink-faint">{title}</p>
      <div className="space-y-1" data-testid={testid}>
        {items.map((i) => (
          <div key={i.key} className="flex items-center gap-2 text-xs">
            <span className="w-32 shrink-0 text-ink-muted">{i.label}</span>
            <div className="h-2 flex-1 rounded bg-surface">
              <div
                className="h-2 rounded bg-accent"
                style={{ width: `${(i.count / max) * 100}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right tabular-nums text-ink-muted">
              {formatCount(i.count)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
