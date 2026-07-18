import { useMemo, useState } from 'react'
import type { DrugStatus, SourcedFact, TargetLandscape, TargetLandscapeEntry } from '../api/types'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { useBriefState } from './Fact'

/**
 * The cancer's target landscape: the top associated targets from Open Targets, each with
 * its association score, tractability, drugged/unexploited status and the evidence behind
 * it. Handles the honest states itself (mirroring PotencyCard): pending while enriching, a
 * calm amber chip on an outage, a muted "none" for a real empty -- never an outage rendered
 * as "no targets".
 *
 * The drugged status is the cell this card exists for: a high-association target with no
 * drug ANYWHERE is the finding. It comes from Open Targets (the world), not our catalog,
 * and is indication-agnostic and target-level -- "a drug exists against this target", never
 * "approved for this cancer". `unknown` (not measured) and `unexploited` (measured, none)
 * are kept visibly distinct: collapsing them would resurrect the None-vs-0 lie one level up.
 */
export function TargetLandscapeCard({ facts }: { facts?: SourcedFact[] }) {
  const briefState = useBriefState()
  const fact = facts?.[0]

  if (!fact) {
    return (
      <Card title="Target landscape">
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
      <Card title="Target landscape">
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

  // Tolerate both fact shapes. The current value is {threshold, n_strong, targets}; a fact
  // stored before that reshape is a bare target array. Reading either keeps an already-
  // enriched cancer's card rendering its targets until stale-while-revalidate upgrades it --
  // an old fact just lacks the strong count, which lives on the stat card, not here.
  const value = fact.value as TargetLandscape | TargetLandscapeEntry[] | null
  const targets = Array.isArray(value) ? value : (value?.targets ?? [])
  if (fact.status === 'empty' || targets.length === 0) {
    return (
      <Card title="Target landscape">
        <p className="text-sm text-ink-faint">
          No associated targets
          <CitationChip fact={fact} />
        </p>
      </Card>
    )
  }

  return (
    <Card title="Target landscape" note="Top associated targets · Open Targets association score">
      <TargetLandscapeBody targets={targets} fact={fact} />
    </Card>
  )
}

// The four drugged states, each with a distinct look (fill vs contrast vs faint) AND a
// distinct label, so no two ever read alike. Only accent (blue) and partial (amber) exist
// in the theme, so "unexploited" -- the finding -- takes the high-contrast inverted chip to
// pull the eye, and "unknown" stays faint because a gap in our data is not a finding.
const STATUS_STYLE: Record<DrugStatus, { label: string; className: string; title: string }> = {
  approved: {
    label: 'approved',
    className: 'bg-accent-bg text-accent',
    title:
      'An approved drug exists against this target. Indication-agnostic — it may be ' +
      'approved for a different cancer, not necessarily this one.',
  },
  clinical: {
    label: 'in dev',
    className: 'bg-partial-bg text-partial',
    title: 'In clinical development against this target — candidates exist, none approved yet.',
  },
  unexploited: {
    label: 'unexploited',
    className: 'bg-ink text-card',
    title: 'No drugs against this target anywhere — a strong association with no therapeutic.',
  },
  unknown: {
    label: 'unknown',
    className: 'text-ink-faint ring-1 ring-line',
    title: 'Drug status unavailable from Open Targets — not measured, which is not "no drug".',
  },
}

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'unexploited', label: 'Unexploited only' },
  { value: 'approved', label: 'Approved' },
  { value: 'clinical', label: 'In development' },
  { value: 'unknown', label: 'Unknown' },
]

// Pre-flag facts (before drug_status shipped) have no status -> "unknown", never a guess.
const statusOf = (t: TargetLandscapeEntry): DrugStatus => t.drug_status ?? 'unknown'

function TargetLandscapeBody({ targets, fact }: { targets: TargetLandscapeEntry[]; fact: SourcedFact }) {
  const [status, setStatus] = useState('')
  const filtered = useMemo(
    () => (status ? targets.filter((t) => statusOf(t) === status) : targets),
    [targets, status],
  )

  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-2">
        <select
          aria-label="Filter targets by drug status"
          data-testid="landscape-filter-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-line bg-card px-2 py-1 text-xs text-ink focus:outline-none"
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-ink-faint">status is against the target, any indication</span>
      </div>

      <ul className="divide-y divide-line" data-testid="target-landscape">
        {filtered.map((t) => (
          <li key={t.symbol} data-testid="landscape-row" className="flex items-center gap-2 py-1.5 text-sm">
            <span className="w-16 shrink-0 font-medium text-ink">{t.symbol}</span>
            <span className="w-9 shrink-0 tabular-nums text-xs text-ink-muted">
              {t.score.toFixed(2)}
            </span>
            <span className="flex shrink-0 items-center gap-1">
              <Tractable on={t.sm_tractable} label="SM" title="Small-molecule tractable" />
              <Tractable on={t.ab_tractable} label="AB" title="Antibody tractable" />
              <DrugStatusBadge status={statusOf(t)} />
            </span>
            <span
              className="ml-auto truncate text-[11px] text-ink-faint"
              title={t.evidence_types.join(', ')}
            >
              {t.evidence_types.slice(0, 2).join(' · ')}
            </span>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="py-3 text-center text-sm text-ink-faint">No targets with this status.</li>
        )}
      </ul>
      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

/** A modality badge: lit when the target is tractable that way, struck through when not. */
function Tractable({ on, label, title }: { on: boolean; label: string; title: string }) {
  return (
    <span
      title={title}
      className={`rounded px-1 text-[10px] font-medium ${
        on ? 'bg-accent-bg text-accent' : 'text-ink-faint line-through'
      }`}
    >
      {label}
    </span>
  )
}

/** The drugged/unexploited/unknown marker — the card's reason to exist. */
function DrugStatusBadge({ status }: { status: DrugStatus }) {
  const s = STATUS_STYLE[status]
  return (
    <span
      data-testid={`drug-status-${status}`}
      title={s.title}
      className={`rounded px-1 text-[10px] font-medium ${s.className}`}
    >
      {s.label}
    </span>
  )
}
