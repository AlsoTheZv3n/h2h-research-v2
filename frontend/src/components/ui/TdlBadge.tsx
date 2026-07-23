import type { TdlVerdict } from '../../api/types'

/**
 * A target's Pharos-style Target Development Level (C3) -- the drugged flag, extended with the
 * missing MIDDLE (Tchem: potent chemical matter, no approved drug) and self-explaining via the
 * criteria that produced it.
 *
 * The label is the backend's self-explaining text (verdict.label): it reuses the drugged-flag
 * wording the harness already validated -- "approved drug", "no drug anywhere", "not measured" --
 * so nothing regresses, and it lets one level carry two honest readings where needed. Tchem is the
 * decision-relevant middle, and it does NOT always read "none approved": when Open Targets never
 * resolved the drug status, a potent ligand still makes it Tchem, but the label reads "approval not
 * measured" -- claiming "none approved" from an unmeasured input would be a false fail. TDL_STYLE
 * supplies the per-level colour (and a label fallback for malformed data): distinct fills so the
 * levels never blur (Tclin approved-accent, Tchem amber for the middle, Tbio the high-contrast
 * inverted chip that pulls the eye to the finding, Tdark faint -- a gap, not a finding). The
 * pass/fail criteria travel in the title so the verdict explains itself with marks, no glossary;
 * "unknown" is a real third mark (–), never a false ✗.
 */
const TDL_STYLE: Record<TdlVerdict['level'], { label: string; className: string }> = {
  Tclin: { label: 'approved drug', className: 'bg-accent-bg text-accent' },
  Tchem: { label: 'chemical matter', className: 'bg-partial-bg text-partial' },
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
  // The backend's self-explaining label leads; TDL_STYLE's per-level text is only a fallback for a
  // malformed verdict with no label. This is what lets Tchem read "approval not measured" when the
  // drug status was never resolved, instead of a false "none approved".
  const label = verdict.label || s.label
  const criteria = verdict.criteria.map((c) => `${c.label}: ${MARK[c.state]}`).join(' · ')
  return (
    <span
      data-testid={`tdl-${verdict.level}`}
      title={`${verdict.level} — ${criteria}`}
      className={`rounded px-1 text-[10px] font-medium ${s.className}`}
    >
      <span className="opacity-70">{verdict.level}</span> {label}
    </span>
  )
}
