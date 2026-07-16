import type { ReactNode } from 'react'

export function Card({
  title,
  children,
  note,
}: {
  title: string
  children: ReactNode
  note?: string
}) {
  return (
    <section className="rounded-lg border border-line bg-card p-4">
      <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>
      {note && <p className="mt-0.5 text-xs text-ink-faint">{note}</p>}
      <div className="mt-2">{children}</div>
    </section>
  )
}

/**
 * What a card shows for a biologic.
 *
 * "Not applicable" and "we have no data" are different statements, and this is the
 * first: an antibody has no small-molecule structure to draw and no clean binding
 * curve to quote. Saying so is an answer -- rendering an empty card would imply
 * something is missing.
 */
export function NotApplicable({ reason }: { reason: string }) {
  return (
    <p
      data-testid="not-applicable"
      className="rounded-md border border-dashed border-line px-3 py-4 text-center text-xs
                 text-ink-muted"
    >
      {reason}
    </p>
  )
}
