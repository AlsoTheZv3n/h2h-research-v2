/**
 * The physchem block's one-line reading (B1): turn the six numbers into a statement a reader can
 * act on, instead of a table they must interpret. Adopts Open Targets' summary → detail shape --
 * the reading leads, the numbers stay beneath.
 *
 * Lipinski's Rule of Five flags likely-poor oral absorption when a property crosses a threshold:
 * MW > 500 Da, LogP > 5, > 5 H-bond donors, > 10 acceptors. ChEMBL's `ro5_violations` is the
 * authoritative COUNT; this rule names WHICH property drives it, by re-checking the same
 * thresholds over the displayed values. A derived rule, disclosed -- never generated prose.
 *
 * Honest states, the discipline this codebase is built on:
 *   - the count is missing  -> withhold (null). Druglikeness is never guessed.
 *   - count is 0            -> passes all four (authoritative).
 *   - count >= 1            -> name the over-limit properties we can see; if a value needed to
 *                             name one is missing, say the count and point to the values rather
 *                             than claim a property we cannot confirm.
 */

export interface Physchem {
  mw: number | null
  alogp: number | null
  hbd: number | null
  hba: number | null
  ro5_violations: number | null
}

interface Rule {
  label: string
  value: (p: Physchem) => number | null
  limit: number
  unit: string
}

// The four Ro5 thresholds, in the order they read most naturally when several are listed.
const RULES: Rule[] = [
  { label: 'LogP', value: (p) => p.alogp, limit: 5, unit: '' },
  { label: 'molecular weight', value: (p) => p.mw, limit: 500, unit: ' Da' },
  { label: 'H-bond donors', value: (p) => p.hbd, limit: 5, unit: '' },
  { label: 'H-bond acceptors', value: (p) => p.hba, limit: 10, unit: '' },
]

export interface Reading {
  /** The one-line statement. */
  text: string
  /** ok = passes all four; caution = has a violation. Not a good/bad verdict on the drug -- Ro5
   *  is a rough oral-absorption heuristic -- so the caller styles it quietly, never red/green. */
  tone: 'ok' | 'caution'
}

export function lipinskiReading(p: Physchem): Reading | null {
  // Withheld when the authoritative count is missing: a source_failed or absent ro5_violations
  // must not be read as "drug-like". The block simply shows whatever values it has.
  if (p.ro5_violations === null) return null

  if (p.ro5_violations === 0) {
    return {
      text: 'Passes all four Lipinski rules — MW ≤ 500 Da, LogP ≤ 5, ≤ 5 H-bond donors, ≤ 10 acceptors.',
      tone: 'ok',
    }
  }

  const over = RULES.filter((r) => {
    const v = r.value(p)
    return v !== null && v > r.limit
  }).map((r) => `${r.label} ${r.value(p)}${r.unit}`)

  const n = p.ro5_violations
  const word = n === 1 ? '1 Lipinski violation' : `${n} Lipinski violations`
  // If the values we hold cannot account for the count (a value missing, or a rounding boundary
  // where ChEMBL counted what our threshold does not), state the count without naming a property
  // we cannot stand behind -- never invent the culprit.
  if (over.length === 0) return { text: `${word} — see the values below.`, tone: 'caution' }
  return { text: `${word}: ${over.join(', ')}.`, tone: 'caution' }
}
