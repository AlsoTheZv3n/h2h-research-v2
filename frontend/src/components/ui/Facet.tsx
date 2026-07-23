import { useMemo } from 'react'
import type { FacetCount } from '../../api/types'

/**
 * A facet dropdown whose first option clears it, and whose options can carry a per-option count.
 *
 * `name` is the accessible name and the testid basis; `placeholder` is the empty option's text.
 * They are separate on purpose: the phase facet reads "Any phase" but is named "Minimum phase"
 * (what it does), and conflating the two once renamed the accessible label out from under an E2E.
 *
 * `counts` (the server's per-option counts, over the OTHER active filters) renders as a "(N)" beside
 * the option, so a reader sees what selecting it would narrow to. Only options the server returned a
 * count for get one; an option absent from `counts` (0 matches under the current filters) shows its
 * plain label -- no "(0)" invented on the client. Shared by the drug and cancer overviews.
 */
export function Facet({
  name,
  placeholder,
  value,
  onChange,
  options,
  counts,
}: {
  name: string
  placeholder: string
  value: string
  onChange: (v: string) => void
  options: [string, string][]
  counts?: FacetCount[]
}) {
  const countByValue = useMemo<Record<string, number>>(
    () => Object.fromEntries((counts ?? []).map((c) => [c.value, c.count])),
    [counts],
  )
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={name}
      data-testid={`facet-${name.toLowerCase().replace(/\s+/g, '-')}`}
      className="rounded-md border border-line bg-card px-2.5 py-1.5 text-sm text-ink
                 focus:border-accent focus:outline-none"
    >
      <option value="">{placeholder}</option>
      {options.map(([v, l]) => {
        const count = countByValue[v]
        return (
          <option key={v} value={v}>
            {count !== undefined ? `${l} (${count})` : l}
          </option>
        )
      })}
    </select>
  )
}
