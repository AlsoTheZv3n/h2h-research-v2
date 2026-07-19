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

/**
 * Why there is (or is not) an answer. The same discipline as FactStatus, one layer
 * up -- and for the same reason: every one of these means something different to a
 * reader, and a UI that renders them all as "sorry, something went wrong" throws
 * away the only thing that makes this tool worth using.
 *
 *   ok              an answer, grounded in retrieved evidence
 *   not_configured  nobody set up a model. A gap the reader can close, not a fault
 *   no_evidence     nothing gathered about this drug, and nothing is running to gather it
 *   enriching       nothing gathered YET -- a background job is fetching it. Async empty
 *                   is not empty: "still gathering" differs from "we looked, nothing there"
 *   unavailable     a model exists but did not answer. Transient; try again
 *   ungrounded      the model cited a source we never retrieved, so the answer was
 *                   withheld. The rarest and most important one: it means the guard
 *                   fired, and the reader is being told rather than shown a
 *                   confident answer nobody can stand behind
 *   withheld        the answer was accurate but quoted a paper's abstract verbatim,
 *                   and that text is not ours to republish. Nothing is wrong with
 *                   the answer or the evidence — it is a licensing boundary, and
 *                   telling the reader that is different from telling them the tool
 *                   failed
 */
export type AnswerState =
  | 'ok'
  | 'not_configured'
  | 'no_evidence'
  | 'enriching'
  | 'unavailable'
  | 'ungrounded'
  | 'withheld'

export interface Citation {
  pmid: string
  title: string | null
  url: string
}

export interface Answer {
  state: AnswerState
  text: string
  citations: Citation[]
  /** Why there is no answer, when state is not ok. Written for the reader. */
  detail: string | null
}

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
  /** The primary target's protein family ("Kinase", ...). null = no class recorded. */
  target_class: string | null
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
  drug_type: string | null
  /** Whether the small-molecule data model applies. Answered by the server: the
   *  obvious client-side guess ("index_only and no SMILES = biologic") is wrong for
   *  the 87 catalog drugs that are small molecules with no structure on record. */
  is_small_molecule: boolean
  /** Whether there is a structure to draw. A separate axis from modality. */
  has_structure: boolean
  /** The canonical SMILES the structure is drawn from — the single source of truth for
   *  the structure card, replacing a separately-fetched ChEMBL fact that could disagree
   *  with has_structure. null when there is no structure. */
  smiles: string | null
  state: BriefState
  /** A READY brief whose facts aged past the freshness window: shown now from storage
   *  while a background refresh runs (stale-while-revalidate). Poll until it clears. */
  refreshing: boolean
  last_enriched_at: string | null
  /**
   * Keyed by fact name; a list because sources disagree. ChEMBL and Open Targets
   * both assert a mechanism, and keeping both is the evidence.
   */
  facts: Record<string, SourcedFact[]>
  /** Keys where *every* source failed. Hoisted so a client cannot miss an outage. */
  unavailable: string[]
}

/** Columns the overview can sort by; must match the API's accepted `sort` values. */
export type SortField = 'data' | 'name' | 'phase' | 'target' | 'class' | 'indication'
export type SortOrder = 'asc' | 'desc'

export interface DrugListParams {
  /** Free text: drug name, ChEMBL id or target. Partial, case-insensitive. */
  q?: string
  /** Exact target symbol. A facet, not a search box. */
  target?: string
  max_phase?: number
  /** Exact drug type, e.g. "Small molecule", "Antibody". */
  modality?: string
  /** Data completeness. */
  maturity?: DataMaturity
  /** Only drugs with (true) or without (false) an annotated target. */
  has_target?: boolean
  /** Exact target family, e.g. "Kinase". "unclassified" selects rows with no class. */
  target_class?: string
  /** Include drugs scoped out as non-oncology. Off by default: the catalog is oncology. */
  include_out_of_scope?: boolean
  sort?: SortField
  order?: SortOrder
  limit?: number
  offset?: number
}

/** A cancer overview row. Index columns only, mirroring DrugSummary. */
export interface CancerSummary {
  /** The Open Targets canonical disease id (mostly MONDO_), the spine everything joins on. */
  disease_id: string
  name: string
  therapeutic_area: string | null
  /** Drugs/clinical candidates for this cancer, per Open Targets. A sort key and a signal. */
  n_drugs: number
  /** Associated targets, per Open Targets. */
  n_targets: number
  last_enriched_at: string | null
  updated_at: string
}

export interface CancerList {
  items: CancerSummary[]
  total: number
  limit: number
  offset: number
}

/**
 * Whether the world (Open Targets, not our catalog) has a drug against a target.
 *   approved     an approved drug hits this target (indication-agnostic)
 *   clinical     candidates exist against it, none approved
 *   unexploited  Open Targets resolved it and it has no drugs — the finding
 *   unknown      Open Targets failed or did not resolve it — NOT the same as unexploited
 * `unknown` and `unexploited` must never render alike: one is "not measured", the other
 * is "measured, none". Absent on facts stored before the flag shipped -> treat as unknown.
 */
export type DrugStatus = 'approved' | 'clinical' | 'unexploited' | 'unknown'

/** One associated target in a cancer's target-landscape fact (Open Targets). */
export interface TargetLandscapeEntry {
  symbol: string
  /** Stable Ensembl gene id (ENSG…). The join key for the flag and the catalog link. */
  ensembl_id: string | null
  /** Open Targets association score, 0–1. */
  score: number
  /** The typed evidence channels behind the association, e.g. "clinical". */
  evidence_types: string[]
  /** Whether a small-molecule / antibody modality is tractable at all. */
  sm_tractable: boolean
  ab_tractable: boolean
  /** Whether the world has a drug against this target. Optional: pre-flag facts lack it. */
  drug_status?: DrugStatus
}

/**
 * The target-landscape fact's value: the top displayed targets plus the count of strong
 * associations (score ≥ `threshold`). The strong count is the headline metric; the raw
 * "any evidence" total lives on the catalog row (n_targets).
 */
export interface TargetLandscape {
  threshold: number
  n_strong: number
  targets: TargetLandscapeEntry[]
}

/**
 * A cancer's evidence brief: the catalog facts plus every fact we hold, with
 * provenance. `state` is enriching while the brief is built, ready once stored --
 * never "ready with nothing", which would claim a cancer has no evidence when the
 * truth is we have not looked.
 */
export interface CancerDetail {
  disease_id: string
  name: string
  therapeutic_area: string | null
  n_drugs: number
  n_targets: number
  last_enriched_at: string | null
  state: BriefState
  /** A ready brief being revalidated in the background (stale-while-revalidate). */
  refreshing: boolean
  /** Keyed by fact name, e.g. 'target_landscape', 'pipeline'. A list because sources disagree. */
  facts: Record<string, SourcedFact[]>
  /** Fact keys where every source failed -- an outage, not an absence. */
  unavailable: string[]
  /** Of the pipeline's drugs, the ChEMBL ids the catalog holds -- the ones we can link
   *  to a brief. Matched by exact id (catalog membership), never by name. */
  catalog_drug_ids: string[]
  /** For each landscape target's Ensembl id, one catalog drug (ChEMBL id) that acts on it
   *  -- the drugged flag's separate, weaker catalog-link. A target absent here has no drug
   *  in our catalog (NOT "unexploited", which is the world's answer); it gets no link. */
  target_catalog_drug: Record<string, string>
}

/** One drug/candidate in a cancer's pipeline, at its most advanced stage. */
export interface PipelineDrug {
  chembl_id: string
  name: string
  stage: string
  /** Open Targets drugType (small molecule, antibody, ADC…). null when unannotated. */
  modality: string | null
  /** The drug's mechanism of action. null when Open Targets has none -> render "—". */
  mechanism: string | null
}

/** One clinical-stage bucket: its stage and true count, for the distribution bars. */
export interface PipelinePhase {
  stage: string
  count: number
}

/** The pipeline fact's value: the flat drug list plus the per-stage distribution. */
export interface PipelineData {
  total: number
  by_phase: PipelinePhase[]
  drugs: PipelineDrug[]
}

/** Columns the cancer overview can sort by; must match the API's accepted `sort` values. */
export type CancerSortField = 'drugs' | 'targets' | 'name' | 'area'

export interface CancerListParams {
  /** Free text: cancer name or disease id. Partial, case-insensitive. */
  q?: string
  /** Exact therapeutic area, e.g. "hematologic disorder". A facet, not a search box. */
  therapeutic_area?: string
  /** Only cancers that have (true) or lack (false) a drug/clinical candidate programme. */
  has_drugs?: boolean
  sort?: CancerSortField
  order?: SortOrder
  limit?: number
  offset?: number
}

/**
 * How a cancer resolved against an external source's vocabulary (Eurostat, SEER), mirroring
 * the backend disease_map MatchType. The load-bearing distinction lives here too:
 *
 *   exact     the cancer IS the mapped category.
 *   rollup    the figures describe a BROADER ancestor entity, whose label the UI MUST show
 *             ("broader than NSCLC") so a specific page never passes them off as its own.
 *   unmapped  no source category applies -- the honest "not available for this cancer",
 *             distinct from empty (source had nothing) and source_failed (an outage).
 */
export type SourceMatch = 'exact' | 'rollup' | 'unmapped'

/** The metadata every resolved-source fact carries, alongside its own data. */
export interface Resolved {
  match_type: SourceMatch
  /** The external category code (ICD-10 site, SEER site). Absent when unmapped. */
  source_code?: string | null
  /** The entity the figures describe -- the name a rollup must show. Absent when unmapped. */
  source_label?: string | null
  target_mondo?: string | null
}

/** One country's age-standardised mortality rate (deaths per 100k), for the Block A bars. */
export interface EpiCountry {
  geo: string
  country: string
  asr: number
}

/** The epidemiology fact's value: European mortality for the resolved cancer (Eurostat). */
export interface Epidemiology extends Resolved {
  year: number
  unit: string
  /** EU aggregate and Switzerland ASR headlines; null when that geography has no rate. */
  eu_asr: number | null
  ch_asr: number | null
  /** EU total deaths for the year (absolute); null if the absolute dataset was unavailable. */
  total_deaths: number | null
  by_country: EpiCountry[]
}

/** One SEER summary stage's 5-year relative survival, with CI, case count and share. */
export interface SurvivalStage {
  stage: string
  rate: number
  /** 95% CI bounds; null when the rate is capped (e.g. 100%) and the bound is suppressed. */
  ci_low: number | null
  ci_high: number | null
  n: number | null
  /** This stage's share of all cases (0-1); may not sum to 1 (unstaged cases remain). */
  share: number | null
}

/** The survival fact's value: SEER 5-year relative survival for the resolved cancer. */
export interface Survival extends Resolved {
  metric: string
  /** False for leukemias: not decomposed into Localized/Regional/Distant. Then by_stage is []
   *  and only all_stages is shown -- a real EMPTY for the stage block, never a zero. */
  staged: boolean
  all_stages: { rate: number; ci_low: number | null; ci_high: number | null; n: number | null }
  by_stage: SurvivalStage[]
}
