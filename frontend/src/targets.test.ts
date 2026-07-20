import { describe, expect, it } from 'vitest'
import type { SelectivityTarget } from './api/types'
import { orderTargetsByPotency } from './targets'

function t(gene_symbol: string | null, i: number): SelectivityTarget {
  return {
    target_chembl_id: `CHEMBL${i}`,
    target_pref_name: `Target ${i}`,
    median_nm: (i + 1) * 10,
    n: 3,
    fold_vs_reference: i + 1,
    is_target: true,
    gene_symbol,
  }
}

// Vatalanib: OT lists 7 symbols; the potency profile measured VEGFR2 (KDR) then VEGFR1 (FLT1).
const SYMBOLS = ['CSF1R', 'FLT1', 'FLT4', 'KDR', 'KIT', 'PDGFRA', 'PDGFRB']
const PROFILE = [t('KDR', 0), t('FLT1', 1)] // ranked most-potent-first

describe('orderTargetsByPotency', () => {
  it('leads with the measured targets in potency order, matching the selectivity profile', () => {
    const out = orderTargetsByPotency(SYMBOLS, PROFILE)
    // KDR (VEGFR2, most potent) then FLT1 (VEGFR1) -- the exact selectivity order.
    expect(out.slice(0, 2)).toEqual(['KDR', 'FLT1'])
  })

  it('keeps the unmeasured targets after, in their original source order', () => {
    const out = orderTargetsByPotency(SYMBOLS, PROFILE)
    expect(out).toEqual(['KDR', 'FLT1', 'CSF1R', 'FLT4', 'KIT', 'PDGFRA', 'PDGFRB'])
  })

  it('matches case-insensitively', () => {
    const out = orderTargetsByPotency(['kdr', 'CSF1R'], [t('KDR', 0)])
    expect(out).toEqual(['kdr', 'CSF1R'])
  })

  it('leaves the source order untouched when no potency symbol resolved (pre-B3 / failed lookup)', () => {
    // gene_symbol null on every profile target -> nothing to rank against -> unchanged.
    const out = orderTargetsByPotency(SYMBOLS, [t(null, 0), t(null, 1)])
    expect(out).toEqual(SYMBOLS)
  })

  it('never drops a target', () => {
    const out = orderTargetsByPotency(SYMBOLS, PROFILE)
    expect([...out].sort()).toEqual([...SYMBOLS].sort())
  })
})
