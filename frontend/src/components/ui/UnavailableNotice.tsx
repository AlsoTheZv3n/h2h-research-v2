import type { ReactNode } from 'react'

/**
 * The page-level "could not load X" box. Five pages rendered the same rounded
 * unavailable panel inline with the same class string; this gives that panel one
 * home, so a change to how a load failure looks is a single edit.
 *
 * Distinct from SourceFailedChip / SourceAdvisory, which mark a *source* failing
 * inside an otherwise-working card -- this is the whole page failing to load.
 */
export function UnavailableNotice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">{children}</p>
  )
}
