import { useEffect, useRef, useState } from 'react'

/**
 * A numbered pager whose *current* page is an editable field, not a static cell.
 *
 * The catalog runs to a few thousand drugs at 25 a page -- ~150 pages -- so
 * Previous/Next alone means clicking to the horizon to reach the end. The usual
 * remedy is a separate "go to page" box tacked on beside the numbers, but that is one
 * more control to notice. Here the active page number *is* the input: click the
 * highlighted cell, type a page, press Enter -- you are there. The cells on either
 * side stay clickable for one-step moves, matching an ordinary pager.
 */

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n))

/** Up to `size` consecutive page numbers, a window that slides to keep `page` centred. */
function pageWindow(page: number, total: number, size: number): number[] {
  if (total <= size) return Array.from({ length: total }, (_, i) => i + 1)
  const start = clamp(page - Math.floor(size / 2), 1, total - size + 1)
  return Array.from({ length: size }, (_, i) => start + i)
}

const CELL = 'min-w-8 rounded border px-2 py-1 text-center tabular-nums'

export function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number
  totalPages: number
  onPage: (page: number) => void
}) {
  // One page is no pager. Guarding here keeps every call site from repeating it.
  if (totalPages <= 1) return null

  return (
    <nav aria-label="Pagination" className="flex items-center gap-1">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className={`${CELL} border-line disabled:opacity-40 enabled:hover:border-accent enabled:hover:text-accent`}
      >
        Previous
      </button>

      {pageWindow(page, totalPages, 5).map((p) =>
        p === page ? (
          <PageInput key="current" page={page} totalPages={totalPages} onPage={onPage} />
        ) : (
          <button
            key={p}
            type="button"
            onClick={() => onPage(p)}
            aria-label={`Go to page ${p}`}
            className={`${CELL} border-line hover:border-accent hover:text-accent`}
          >
            {p}
          </button>
        ),
      )}

      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        className={`${CELL} border-line disabled:opacity-40 enabled:hover:border-accent enabled:hover:text-accent`}
      >
        Next
      </button>
    </nav>
  )
}

/**
 * The active page, rendered as an input. It looks like the highlighted cell of an
 * ordinary pager but accepts typing: Enter (or blur) commits the jump, Escape or a
 * non-number reverts. `page` is the source of truth -- local state holds only the
 * in-progress edit and re-syncs whenever navigation moves the page from outside.
 */
function PageInput({
  page,
  totalPages,
  onPage,
}: {
  page: number
  totalPages: number
  onPage: (page: number) => void
}) {
  const [draft, setDraft] = useState(String(page))
  // Escape blurs the field, which fires onBlur synchronously -- before setDraft has
  // flushed -- so commit would still see the abandoned value. This flag tells commit
  // to stand down for that one blur.
  const reverting = useRef(false)

  // Prev/Next/number-cell clicks move `page` from outside this input; follow them.
  useEffect(() => setDraft(String(page)), [page])

  function commit() {
    if (reverting.current) {
      reverting.current = false
      setDraft(String(page))
      return
    }
    const n = Number(draft)
    if (!draft || !Number.isInteger(n)) {
      setDraft(String(page))
      return
    }
    const target = clamp(n, 1, totalPages)
    // Snap the field back to the clamped/unchanged value; navigation (if any) will
    // re-sync it through the effect once `page` actually changes.
    if (target === page) setDraft(String(page))
    else onPage(target)
  }

  return (
    <input
      type="text"
      inputMode="numeric"
      data-testid="page-input"
      value={draft}
      aria-label={`Page ${page} of ${totalPages}. Type a page number and press Enter to jump.`}
      aria-current="page"
      title="Type a page number and press Enter"
      onChange={(e) => setDraft(e.target.value.replace(/\D/g, '').slice(0, String(totalPages).length))}
      onFocus={(e) => e.target.select()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        else if (e.key === 'Escape') {
          reverting.current = true
          e.currentTarget.blur()
        }
      }}
      onBlur={commit}
      className={`${CELL} border-accent bg-accent-bg font-medium text-accent outline-none focus:ring-2 focus:ring-accent/30`}
      style={{ width: `${String(totalPages).length + 2}ch` }}
    />
  )
}
