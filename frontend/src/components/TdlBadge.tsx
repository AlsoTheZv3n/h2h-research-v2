import type { TdlVerdict } from '../api/types'

/**
 * A target's Pharos-style Target Development Level (C3) -- the drugged flag, extended with the
 * missing MIDDLE (Tchem: potent chemical matter, no approved drug) and self-explaining via the
 * criteria that produced it.
 *
 * The four levels reuse the drugged-flag wording the harness already validated -- "approved drug",
 * "no drug anywhere", "not measured" -- so nothing regresses; Tchem is the new, decision-relevant
 * cell. Distinct fills per level (Tclin approved-accent, Tchem amber for the middle, Tbio the
 * high-contrast inverted chip that pulls the eye to the finding, Tdark faint -- a gap, not a
 * finding). The pass/fail criteria travel in the title so the verdict explains itself with marks,
 * no glossary; "unknown" is a real third mark (–), never a false ✗.
 */
const TDL_STYLE: Record<TdlVerdict['level'], { label: string; className: string }> = {
  Tclin: { label: 'approved drug', className: 'bg-accent-bg text-accent' },
  Tchem: { label: 'chemical matter, none approved', className: 'bg-partial-bg text-partial' },
  Tbio: { label: 'no drug anywhere', className: 'bg-ink text-card' },
  Tdark: { label: 'not measured', className: 'text-ink-faint ring-1 ring-line' },
}

const MARK: Record<TdlVerdict['criteria'][number]['state'], string> = {
  pass: '✓',
  fail: '✗',
  unknown: '–',
}

export function TdlBadge({ verdict }: { verdict: TdlVerdict }) {
  // Fall back to the Tdark style for any level outside the union (malformed persisted data),
  // rather than throwing and blanking the row (there is no error boundary here).
  const s = TDL_STYLE[verdict.level] ?? TDL_STYLE.Tdark
  const criteria = verdict.criteria.map((c) => `${c.label}: ${MARK[c.state]}`).join(' · ')
  return (
    <span
      data-testid={`tdl-${verdict.level}`}
      title={`${verdict.level} — ${criteria}`}
      className={`rounded px-1 text-[10px] font-medium ${s.className}`}
    >
      <span className="opacity-70">{verdict.level}</span> {s.label}
    </span>
  )
}
