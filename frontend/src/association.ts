/**
 * Make the Open Targets association score self-explaining (B5).
 *
 * The 0–1 score was read across three harness tasks as "a 0.5 threshold required to be a target"
 * or "how reliable the info is" -- because a bare number with a "≥ 0.5" gate explains nothing. The
 * field's answer (Pharos' pass/fail criteria, Open Targets' Locus-to-Gene Shapley contributions)
 * is NOT to explain the formula but to SHOW WHAT CONTRIBUTED, led by a qualitative reading. So:
 * a strength word (strong vs moderate, against the documented 0.5 cut) leads, the contributing
 * evidence TYPES name what the score is built from, and the number itself drops to a detail.
 *
 * Wording/synthesis only -- the metric is unchanged, and the honest states are untouched.
 */

/** Open Targets' documented "strong association" cut. A judgement, disclosed -- not a probability. */
export const STRONG_ASSOCIATION = 0.5

/** The score's qualitative strength, so "≥ 0.5" reads as a meaning rather than a bare threshold. */
export function associationStrength(score: number): 'strong' | 'moderate' {
  return score >= STRONG_ASSOCIATION ? 'strong' : 'moderate'
}

// Open Targets datatype ids -> the words a reader uses. Unknown ids are de-slugged, never dropped:
// showing an unlabelled contribution honestly beats hiding it.
const EVIDENCE_LABEL: Record<string, string> = {
  genetic_association: 'genetic',
  somatic_mutation: 'somatic mutation',
  known_drug: 'known drug',
  affected_pathway: 'pathway',
  literature: 'literature',
  rna_expression: 'expression',
  animal_model: 'animal model',
  clinical: 'clinical',
}

/** The evidence types that CONTRIBUTED to the score, in readable words -- what the score is built
 *  from, which is the interpretable thing (not the weighting formula). */
export function evidenceContributions(types: string[]): string[] {
  return types.map((t) => EVIDENCE_LABEL[t] ?? t.replace(/_/g, ' '))
}

/** The one-line qualitative reading that LEADS wherever the score appears: the strength, then the
 *  contributing evidence where we have it. The number travels alongside as detail, never alone. */
export function associationReading(score: number, evidenceTypes?: string[]): string {
  const strength = associationStrength(score)
  const kinds = evidenceContributions(evidenceTypes ?? [])
  if (kinds.length === 0) return `${strength} association`
  const shown = kinds.slice(0, 2).join(' + ')
  const more = kinds.length > 2 ? ` +${kinds.length - 2}` : ''
  return `${strength} — ${shown}${more}`
}
