import type { SourcedFact, TargetLandscape, TargetLandscapeEntry } from '../api/types'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { useBriefState } from './Fact'

/**
 * The cancer's target landscape: the top associated targets from Open Targets, each
 * with its association score, tractability and the evidence channels behind it. Handles
 * the honest states itself (mirroring PotencyCard): pending while enriching, a calm
 * amber chip on an outage, a muted "none" for a real empty -- never an outage rendered
 * as "no targets". The drugged/undrugged story starts with the SM/AB tractability badges.
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
      <ul className="divide-y divide-line" data-testid="target-landscape">
        {targets.map((t) => (
          <li key={t.symbol} className="flex items-center gap-2 py-1.5 text-sm">
            <span className="w-16 shrink-0 font-medium text-ink">{t.symbol}</span>
            <span className="w-9 shrink-0 tabular-nums text-xs text-ink-muted">
              {t.score.toFixed(2)}
            </span>
            <span className="flex shrink-0 gap-1">
              <Tractable on={t.sm_tractable} label="SM" title="Small-molecule tractable" />
              <Tractable on={t.ab_tractable} label="AB" title="Antibody tractable" />
            </span>
            <span
              className="ml-auto truncate text-[11px] text-ink-faint"
              title={t.evidence_types.join(', ')}
            >
              {t.evidence_types.slice(0, 3).join(' · ')}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </Card>
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
