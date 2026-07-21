import { describe, expect, it } from 'vitest'
import { ctgovPhaseLabel, humanize, otStageLabel } from './phases'

describe('ctgovPhaseLabel', () => {
  it('humanises the ClinicalTrials.gov phase enums the harness read as jargon', () => {
    expect(ctgovPhaseLabel('EARLY_PHASE1')).toBe('Early Phase 1')
    expect(ctgovPhaseLabel('PHASE1')).toBe('Phase 1')
    expect(ctgovPhaseLabel('PHASE4')).toBe('Phase 4')
    // NA is a real value (a device/observational trial with no phase), not "unknown".
    expect(ctgovPhaseLabel('NA')).toBe('Not applicable')
  })

  it('falls back to a readable form for a new enum, never a raw SCREAMING token', () => {
    expect(ctgovPhaseLabel('SOME_NEW_PHASE')).toBe('Some New Phase')
  })
})

describe('otStageLabel', () => {
  it('humanises the Open Targets stage enums, including the approval tail and fractions', () => {
    expect(otStageLabel('APPROVAL')).toBe('Approved')
    expect(otStageLabel('PHASE_2_3')).toBe('Phase 2/3')
    expect(otStageLabel('PREAPPROVAL')).toBe('Pre-registration')
    expect(otStageLabel('PRECLINICAL')).toBe('Preclinical')
  })

  it('falls back readably for an unknown stage', () => {
    expect(otStageLabel('BRAND_NEW')).toBe('Brand New')
  })
})

describe('humanize', () => {
  it('title-cases a SCREAMING_SNAKE token as a last resort', () => {
    expect(humanize('APPROVED_FOR_MARKETING')).toBe('Approved For Marketing')
  })
})
