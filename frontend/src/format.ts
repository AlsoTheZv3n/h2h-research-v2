/**
 * Number formatting for scientific values.
 *
 * Explicitly en-US, never toLocaleString()'s default. On a German browser the
 * default renders 480000 as "480.000" and 12.66 as "12,66" -- so an IC50 reads as
 * 480 nM to anyone expecting English conventions, a 1000x misreading of a potency,
 * decided by a browser setting. The UI is English; its numbers have to be too.
 */

const INTEGER = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const DECIMAL = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

/** Counts and other whole numbers: 1234 -> "1,234". */
export function formatCount(n: number): string {
  return INTEGER.format(n)
}

/**
 * The overview's result-count label, kept honest across three distinct states:
 *
 *   "X of Y shown"   a subset of a known corpus -- a filter narrowed it, or scoping
 *                    hid the non-oncology tail. Only when the corpus size Y is known.
 *   "X match"        filtered, but the corpus-size probe failed or has not resolved,
 *                    so Y is unknown. Never "in catalog": a filtered subset is not the
 *                    whole catalog, and saying so when the probe is down would assert a
 *                    catalog the size of the current query.
 *   "X in catalog"   the unfiltered view (Y unknown, or the whole corpus is showing).
 */
export function countLabel(total: number, catalogTotal: number | null, hasFilter: boolean): string {
  if (catalogTotal !== null && total < catalogTotal) {
    return `${formatCount(total)} of ${formatCount(catalogTotal)} shown`
  }
  if (hasFilter) return `${formatCount(total)} match`
  return `${formatCount(total)} in catalog`
}

/**
 * A concentration in nM. Sub-nanomolar values keep their precision; large ones lose
 * the decimals nobody reads.
 */
export function formatNm(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n !== 0 && Math.abs(n) < 0.01) return n.toExponential(1)
  return n >= 1000 ? INTEGER.format(n) : DECIMAL.format(n)
}

const MS_PER_DAY = 86_400_000
// Explicit en-US, like the number formatters above: the UI is English, so "3 months
// ago" must not become a localized string on a German browser. numeric:'auto' gives the
// natural "yesterday" / "last week" for the -1 buckets instead of "1 day ago".
const RELATIVE = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' })

/**
 * How long ago a fact was checked, from its `retrieved_at` ISO string -- "today",
 * "yesterday", "3 months ago". This is FRESHNESS (when we last verified the value), a
 * separate axis from the change feed (when the value last moved) and from the honest
 * states; it never becomes a state, only a per-fact age the citation chip can show.
 *
 * Computed against the render-time clock, so callers/tests must control "now" (the date
 * moves). Degrades to the raw string on an unparseable input, exactly as the absolute
 * date formatter does -- a bad timestamp is shown, never a fabricated "today".
 */
export function formatAge(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  // Negative = in the past (the normal case); Math.round keeps the nearest whole unit.
  const days = Math.round((then - Date.now()) / MS_PER_DAY)
  const abs = Math.abs(days)
  if (abs < 1) return 'today'
  if (abs < 7) return RELATIVE.format(days, 'day')
  if (abs < 30) return RELATIVE.format(Math.round(days / 7), 'week')
  if (abs < 365) return RELATIVE.format(Math.round(days / 30), 'month')
  return RELATIVE.format(Math.round(days / 365), 'year')
}
