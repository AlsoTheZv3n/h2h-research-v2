/**
 * Clinical-phase and development-stage enums in human words.
 *
 * Two different vocabularies, kept apart because they are: ClinicalTrials.gov phases (PHASE1, NA,
 * EARLY_PHASE1) and Open Targets maximumClinicalStage (APPROVAL, PHASE_2_3, PRECLINICAL). The
 * harness read the raw SCREAMING tokens ("EARLY_PHASE1", "APPROVAL") as jargon; shown through these
 * they read as English. Shared by the drug page and the pipeline/trial cards so the same token is
 * never humanised two different ways.
 */

/** A fallback so a NEW enum lands readable rather than a raw token: PHASE_2_3 -> "Phase 2 3". */
export const humanize = (s: string): string =>
  s
    .split('_')
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : ''))
    .join(' ')
    .trim()

// ClinicalTrials.gov phase enum. NA is a REAL value (a device/observational trial with no phase),
// not "unknown".
const CTGOV_PHASE: Record<string, string> = {
  EARLY_PHASE1: 'Early Phase 1',
  PHASE1: 'Phase 1',
  PHASE2: 'Phase 2',
  PHASE3: 'Phase 3',
  PHASE4: 'Phase 4',
  NA: 'Not applicable',
}

export const ctgovPhaseLabel = (p: string): string => CTGOV_PHASE[p] ?? humanize(p)

// Open Targets maximumClinicalStage enum: underscored, with fractional stages and the
// APPROVAL/PREAPPROVAL tail above phase 4.
const OT_STAGE: Record<string, string> = {
  APPROVAL: 'Approved',
  PHASE_4: 'Phase 4',
  PREAPPROVAL: 'Pre-registration',
  PHASE_3: 'Phase 3',
  PHASE_2_3: 'Phase 2/3',
  PHASE_2: 'Phase 2',
  PHASE_1_2: 'Phase 1/2',
  PHASE_1: 'Phase 1',
  EARLY_PHASE_1: 'Early Phase 1',
  PHASE_0: 'Phase 0',
  PRECLINICAL: 'Preclinical',
  UNKNOWN: 'Unknown stage',
}

export const otStageLabel = (s: string): string => OT_STAGE[s] ?? humanize(s)
