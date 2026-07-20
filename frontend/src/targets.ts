import type { SelectivityTarget } from './api/types'

/**
 * Order the mechanism card's target list by measured potency (B3), so it tells the same story as
 * the potency card instead of contradicting it.
 *
 * The mechanism card lists targets as gene symbols (Open Targets: KDR, FLT1, KIT …) in the
 * source's own order, while the potency card ranks them by measured affinity (VEGFR2, VEGFR1 …).
 * A reader saw a different "first target" on each card. Epic A's selectivity targets now carry a
 * gene symbol, so this orders the symbol list by the SAME ranking: the targets the profile
 * measured, in potency order, then the annotated-but-unmeasured ones in their source order (a
 * stable sort preserves it). Matched case-insensitively on the symbol; an unresolved symbol on the
 * potency side (no lookup) simply does not reorder anything, never drops a target.
 */
export function orderTargetsByPotency(symbols: string[], profileTargets: SelectivityTarget[]): string[] {
  const rank = new Map<string, number>()
  profileTargets.forEach((t, i) => {
    if (t.gene_symbol) rank.set(t.gene_symbol.toUpperCase(), i)
  })
  if (rank.size === 0) return symbols // nothing to rank against -> leave the source order untouched

  return symbols
    .map((symbol, i) => ({ symbol, i, rank: rank.get(symbol.toUpperCase()) }))
    .sort((a, b) => {
      // Measured targets first, in potency order; unmeasured keep their original relative order.
      if (a.rank === undefined && b.rank === undefined) return a.i - b.i
      if (a.rank === undefined) return 1
      if (b.rank === undefined) return -1
      return a.rank - b.rank
    })
    .map((x) => x.symbol)
}
