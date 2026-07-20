import { describe, expect, it } from 'vitest'
import {
  associationReading,
  associationStrength,
  evidenceContributions,
  STRONG_ASSOCIATION,
} from './association'

describe('associationStrength', () => {
  it('calls >= 0.5 strong and below it moderate (the documented cut)', () => {
    expect(associationStrength(0.89)).toBe('strong')
    expect(associationStrength(STRONG_ASSOCIATION)).toBe('strong') // the cut itself is strong
    expect(associationStrength(0.49)).toBe('moderate')
  })
})

describe('evidenceContributions', () => {
  it('turns Open Targets datatype ids into reader words', () => {
    expect(evidenceContributions(['genetic_association', 'somatic_mutation', 'clinical'])).toEqual([
      'genetic',
      'somatic mutation',
      'clinical',
    ])
  })

  it('de-slugs an unknown id rather than dropping it', () => {
    expect(evidenceContributions(['brand_new_type'])).toEqual(['brand new type'])
  })
})

describe('associationReading', () => {
  it('leads with the strength and names the contributing evidence', () => {
    expect(associationReading(0.89, ['genetic_association', 'clinical'])).toBe(
      'strong — genetic + clinical',
    )
  })

  it('summarises extra contributions with a +N, not a wall of types', () => {
    expect(associationReading(0.8, ['genetic_association', 'clinical', 'literature', 'pathway'])).toBe(
      'strong — genetic + clinical +2',
    )
  })

  it('falls back to a strength-only reading when no evidence types are available', () => {
    // The target page's associated-cancers carries a score but no evidence-type breakdown.
    expect(associationReading(0.3)).toBe('moderate association')
    expect(associationReading(0.72, [])).toBe('strong association')
  })
})
