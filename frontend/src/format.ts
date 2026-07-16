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
 * A concentration in nM. Sub-nanomolar values keep their precision; large ones lose
 * the decimals nobody reads.
 */
export function formatNm(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n !== 0 && Math.abs(n) < 0.01) return n.toExponential(1)
  return n >= 1000 ? INTEGER.format(n) : DECIMAL.format(n)
}
