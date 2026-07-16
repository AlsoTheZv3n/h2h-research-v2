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
    className: 'bg-unavailable-bg text-unavailable',
    title: 'In the catalog, but no structure or binding data — biologics land here',
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
  if (phase === null) return <span className="text-ink-faint">—</span>
  const label = phase === 4 ? 'Approved' : `Phase ${phase}`
  return (
    <span className="inline-block rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-muted">
      {label}
    </span>
  )
}
