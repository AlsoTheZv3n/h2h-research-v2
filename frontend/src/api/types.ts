/**
 * The Phase-1 API shapes.
 *
 * `FactStatus` is the load-bearing type in this whole codebase. A fact's value can
 * be null for two completely different reasons, and only the status tells them
 * apart:
 *
 *   ok             the source measured it, and here it is
 *   empty          the source measured it, and the answer is nothing (0, [], "")
 *   source_failed  we never measured it -- the source was down. NOT a finding.
 *
 * Collapsing the last two is the defect this product exists to prevent, so the UI
 * renders them differently and the type refuses to let you forget one.
 */

export type FactStatus = 'ok' | 'empty' | 'source_failed'

export interface SourcedFact<T = unknown> {
  value: T | null
  status: FactStatus
  source: string
  source_url: string | null
  retrieved_at: string
  /** Only set when status is source_failed: what went wrong. */
  error: string | null
  confidence: number | null
}

export type DataMaturity = 'full' | 'partial' | 'index_only'

/** An overview row. Index columns only -- no molecular detail. */
export interface DrugSummary {
  chembl_id: string
  pref_name: string | null
  drug_type: string | null
  max_phase: number | null
  primary_target: string | null
  primary_indication: string | null
  maturity: DataMaturity
  updated_at: string
}

export interface DrugList {
  items: DrugSummary[]
  total: number
  limit: number
  offset: number
}

/** The on-target potency answer -- not a raw count of activity rows. */
export interface PotencySummary {
  target_chembl_ids: string[]
  n_activities: number
  n_on_target: number
  n_censored: number
  n_exact: number
  median_nm: number | null
  min_nm: number | null
  max_nm: number | null
  units: string
  off_target: Record<string, number>
  other_units: Record<string, number>
}

/**
 * Where a brief is in its life -- a different axis from any fact's status.
 *
 *   not_analyzed  nobody has asked the sources about this drug yet
 *   enriching     a fetch is in flight; the facts are on their way
 *   ready         the facts are stored and served
 *
 * The first two mean "we have not looked", which is not "we looked and found
 * nothing" (empty) and not "we looked and the source fell over" (source_failed).
 * Four states, four different sentences, and the UI owes the reader the right one.
 */
export type BriefState = 'not_analyzed' | 'enriching' | 'ready'

export interface DrugDetail {
  chembl_id: string
  pref_name: string | null
  maturity: DataMaturity
  state: BriefState
  last_enriched_at: string | null
  /**
   * Keyed by fact name; a list because sources disagree. ChEMBL and Open Targets
   * both assert a mechanism, and keeping both is the evidence.
   */
  facts: Record<string, SourcedFact[]>
  /** Keys where *every* source failed. Hoisted so a client cannot miss an outage. */
  unavailable: string[]
}

export interface DrugListParams {
  /** Free text: drug name, ChEMBL id or target. Partial, case-insensitive. */
  q?: string
  /** Exact target symbol. A facet, not a search box. */
  target?: string
  max_phase?: number
  limit?: number
  offset?: number
}
