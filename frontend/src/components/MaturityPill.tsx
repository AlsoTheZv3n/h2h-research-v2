import type { DataMaturity } from '../api/types'

/**
 * Data maturity, not clinical stage: how much of a brief we can actually carry.
 *
 * This is what keeps the overview honest. A biologic appears in the list and says
 * out loud that there is no structure or binding card behind it, rather than
 * offering a page of empty cards that read as missing data.
 */
const STYLES: Record<DataMaturity, { label: string; className: string; title: string }> = {
  full: {
    label: 'Full brief',
    className: 'bg-confident-bg text-confident',
    title: 'Structure, potency and mechanism are all available',
  },
  partial: {
    label: 'Partial',
    className: 'bg-partial-bg text-partial',
    title: 'Resolved with a structure, but some cards will be empty',
  },
  index_only: {
    label: 'Index only',
    // Muted, not red. "Index only" means "no brief loaded yet", which for most rows
    // is a matter of the pre-warmer not having reached them -- a pending state, not
    // an error. Rendering it in the error colour told the reader something was wrong
    // on two-thirds of the catalog. Red is reserved for genuine failures.
    className: 'bg-surface text-ink-muted',
    title: 'In the catalog, but no brief loaded yet — biologics also land here',
  },
}

export function MaturityPill({ maturity }: { maturity: DataMaturity }) {
  const style = STYLES[maturity]
  return (
    <span
      title={style.title}
      className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}
    >
      {style.label}
    </span>
  )
}

export function PhasePill({ phase }: { phase: number | null }) {
  // Plain muted text, not a pill. The Data pill is the one meaningful pill on the row;
  // a second bordered pill for the phase just competed with it for the eye. Clinical
  // phase is a plain fact, so it reads as plain text.
  if (phase === null) return <span className="text-ink-faint">—</span>
  const label = phase === 4 ? 'Approved' : `Phase ${phase}`
  return <span className="text-ink-muted">{label}</span>
}
