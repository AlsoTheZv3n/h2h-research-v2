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

/** One facet option and how many rows match it, given the OTHER active filters -- shown as a
 *  "(N)" beside the option so a reader sees what selecting it would narrow to. */
export interface FacetCount {
  value: string
  count: number
}

/** Per-facet option counts, keyed by facet name ('modality', 'maturity', 'target_class',
 *  'has_target' for drugs; 'therapeutic_area', 'has_drugs' for cancers). */
export type FacetCounts = Record<string, FacetCount[]>

/** The on-target potency answer -- not a raw count of activity rows. Superseded on the drug
 *  page by SelectivityProfile (the `selectivity_profile` fact); still produced by the backend. */
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

/** One molecular target in a drug's selectivity profile, placed relative to the most-potent
 *  (reference) target. */
export interface SelectivityTarget {
  target_chembl_id: string
  target_pref_name: string
  /** Median of this target's exact single-protein nM IC50s. */
  median_nm: number
  /** Exact measurements the median is over (always >= the corroboration minimum). */
  n: number
  /** median_nm / the reference target's median_nm; 1.0 for the reference itself. */
  fold_vs_reference: number
  /** Within threshold_fold of the reference -- a real target, not incidental. */
  is_target: boolean
  /** The target's HGNC gene symbol (KDR for VEGFR2), for ordering the mechanism card's symbol
   *  list by this same potency ranking (B3). Optional: absent on pre-B3 facts / a failed lookup. */
  gene_symbol?: string | null
}

/**
 * A drug's measured molecular targets, ranked by potency, relative to the most potent
 * (reference). The field's selectivity read: it declares no primary target -- the reference
 * is whichever single-protein target the drug binds most potently, and every other target is a
 * fold-difference from it. `n_uncorroborated_targets` (measured only once) and `n_excluded_rows`
 * (cell-based / censored / non-nM) are the data set aside from the ranking -- counted, never
 * hidden. `reference` is null exactly when nothing corroborated could be ranked.
 */
export interface SelectivityProfile {
  targets: SelectivityTarget[]
  reference: SelectivityTarget | null
  /** Targets within threshold_fold of the reference -- the selectivity count (fewer = more
   *  selective), the reference included. */
  n_targets: number
  /** All ranked (corroborated) targets, within threshold or beyond it. */
  n_measured_targets: number
  threshold_fold: number
  /** Exact single-protein nM measurements the ranking is built from. */
  n_protein_rows: number
  /** Rows set aside from the ranking, total (= the three kind counts below, when present). */
  n_excluded_rows: number
  /** Molecular targets seen but measured fewer than the minimum, so not ranked. */
  n_uncorroborated_targets: number
  /**
   * The A3 assay-kind split. Optional: facts stored before A3 lack them, and the card falls back
   * to the single set-aside line then.
   *   n_cell_based_rows      cell-line readouts (cell response, not target binding).
   *   n_unassigned_rows      neither single-protein binding nor a cell line (organism/tissue/
   *                          complex/multi-protein/unspecified format).
   *   n_binding_nonexact_rows single-protein binding rows that could not rank (censored/non-nM).
   */
  n_cell_based_rows?: number
  n_unassigned_rows?: number
  n_binding_nonexact_rows?: number
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
  /** The page-level "so what" (C2): derived threshold statements over the facts, each linking to
   *  its block. Empty when no rule's inputs are present. Optional: absent on pre-C2 payloads. */
  synthesis?: SynthesisStatement[]
  /** Cross-source conflicts (E1): where two sources give a comparable fact different values.
   *  Empty when sources agree or only one answered. Optional: absent on pre-E1 payloads. */
  disagreements?: Disagreement[]
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

/** One page-level synthesis line (Epic C): a derived reading and the anchor id of the block it was
 *  derived from, so the reader can jump to the evidence behind it. */
export interface SynthesisStatement {
  text: string
  block: string
}

/** One entry in the relevance-ranked "Key papers" list (B4 + #42): the title, its most-weighty
 *  PubMed publication type (null for a plain journal article), and whether MeSH indexing has been
 *  applied yet -- `indexed: false` means "not yet indexed" (a recent paper), NOT low quality. The
 *  `relevant_titles` fact carries these; the `sample_titles` fallback carries plain strings. */
export interface KeyPaper {
  title: string
  pmid: string | null
  publication_type: string | null
  indexed: boolean
}

/** One source's stance in a disagreement (E1): its own value in its own words, plus where it came
 *  from -- so a reader can see and check each side. */
export interface DisagreementValue {
  source: string
  display: string
  source_url: string | null
}

/** A cross-source conflict (E1): two sources give a comparable fact (e.g. the clinical phase)
 *  different values. Names the conflict where today the reader had to notice it; every side stays
 *  visible, none silently wins. Links to the block it came from. */
export interface Disagreement {
  label: string
  block: string
  values: DisagreementValue[]
}

/** One pass/fail (or 'unknown') criterion behind a target's TDL verdict (C3). */
export interface TdlCriterion {
  label: string
  state: 'pass' | 'fail' | 'unknown'
}

/** A target's Pharos-style Target Development Level (C3): the level, a short reading, and the
 *  criteria that produced it. Surfaces the Tchem middle -- potent chemical matter, none approved. */
export interface TdlVerdict {
  level: 'Tclin' | 'Tchem' | 'Tbio' | 'Tdark'
  label: string
  criteria: TdlCriterion[]
}

/** One gene's mutation-frequency reading in a cancer's alteration_frequency fact (#43, cBioPortal).
 *  `state` keeps the honest cases apart: `measured` (a real %), `measured_zero` (profiled, never
 *  mutated — a real 0%, NOT missing), `gene_unmapped` (could not join this gene to an Entrez id —
 *  not measured, distinct from 0%). `pct`/`altered_n` are absent for gene_unmapped. */
export interface AlterationGene {
  symbol: string
  ensembl_id: string | null
  entrez_id: number | null
  state: 'measured' | 'measured_zero' | 'gene_unmapped'
  altered_n?: number
  pct?: number
}

/** The attribution the surface must carry (ODbL grant condition): the cBioPortal portal citations
 *  plus the specific source study cited by the cohort. */
export interface AlterationAttribution {
  portal: string[]
  study_citation: string | null
  study_pmid: string | null
}

/** A cancer's cBioPortal somatic-mutation frequency fact (#43). `state: 'unmapped'` is the honest
 *  "no matched cohort for this cancer" (most of the catalog) — distinct from source_failed and from
 *  a real 0%. `state: 'measured'` carries the cohort, the SCOPE (mutation-only) + denominator so the
 *  number is never bare, the per-gene readings, and the attribution. */
export interface AlterationFrequency {
  state: 'unmapped' | 'measured'
  study_id?: string
  study_label?: string
  study_name?: string | null
  alteration_scope?: string
  denominator_type?: string
  denominator_n?: number
  genes?: AlterationGene[]
  attribution?: AlterationAttribution
}

/** One cancer's reading in a TARGET's mutation-frequency reflection (#43, the transpose of the
 *  cancer block): how often this gene is mutated in that cancer's cohort. `measured_zero` = profiled
 *  never mutated (a real 0%); `source_failed` = that one cohort's fetch failed (amber, not a zero). */
export interface TargetAlterationCancer {
  disease_id: string
  name: string | null
  study_label: string
  state: 'measured' | 'measured_zero' | 'source_failed'
  pct?: number
  altered_n?: number
  denominator_n?: number
}

/** A target's somatic-mutation frequency across the cancers it drives (#43, cBioPortal). `no_cohort`
 *  = none of its cancers have a curated cohort; `gene_unmapped` = this gene could not be joined to a
 *  cBioPortal (Entrez) id. `n_more` cohorts beyond the shown cap are disclosed, not dropped. */
export interface TargetAlterationFrequency {
  state: 'measured' | 'no_cohort' | 'gene_unmapped'
  entrez_id?: number
  alteration_scope?: string
  cancers?: TargetAlterationCancer[]
  n_more?: number
  attribution?: { portal: string[] }
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
  /** The page-level "so what" (C1): derived threshold statements over the facts, each linking to
   *  its block. Empty when no rule's inputs are present. Optional: absent on pre-C1 payloads. */
  synthesis?: SynthesisStatement[]
  /** For each landscape target's Ensembl id, its Pharos-style Target Development Level (C3).
   *  Optional: absent on pre-C3 payloads (the card falls back to the drug-status badge). */
  target_tdl?: Record<string, TdlVerdict>
}

/** One cancer a target is associated with, in the target brief's associated_cancers fact.
 *  Every entry is in our catalog by construction, so disease_id is always a live link. */
export interface AssociatedCancer {
  disease_id: string
  name: string
  /** Open Targets association score, 0–1. */
  score: number
}

/** The associated_cancers fact value: the count of catalog cancers this target is associated
 *  with, plus the top displayed slice (by score). n_cancers may exceed cancers.length. */
export interface AssociatedCancers {
  n_cancers: number
  cancers: AssociatedCancer[]
}

/**
 * A target's evidence brief: the catalog row plus every fact we hold, with provenance. The
 * target-side twin of CancerDetail (the cancer page, run backwards). `name` and `n_cancers`
 * are null until enriched -- measured by the reverse query, never defaulted to 0.
 */
export interface TargetDetail {
  ensembl_id: string
  symbol: string
  name: string | null
  n_cancers: number | null
  last_enriched_at: string | null
  state: BriefState
  /** A ready brief being revalidated in the background (stale-while-revalidate). */
  refreshing: boolean
  /** Keyed by fact name, e.g. 'associated_cancers'. A list because sources disagree. */
  facts: Record<string, SourcedFact[]>
  /** Fact keys where every source failed -- an outage, not an absence. */
  unavailable: string[]
  /** ChEMBL ids of catalog drugs that act on this target (joined on the Ensembl id). Empty is
   *  "no such drug in our catalog", NOT "undruggable". */
  catalog_drugs: string[]
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

/** One phase bucket of a trial-reality fact. NB: a combined-design trial (e.g. Phase 1/2) counts
 *  in EACH of its phases, so by_phase is trials-PER-phase and need not sum to n_trials_scanned --
 *  render it as counts, never as shares. */
export interface TrialPhase {
  phase: string
  count: number
}

/** One overall-status bucket. overallStatus is single-valued, so by_status partitions the page. */
export interface TrialStatus {
  status: string
  count: number
}

/** One stated reason a trial stopped (whyStopped), with how many stopped trials gave it. */
export interface TrialStopReason {
  reason: string
  count: number
}

/**
 * The trial-reality fact's value: the real registered-trial landscape from ClinicalTrials.gov,
 * queried by CONDITION TEXT (a soft match — `condition` is the exact text queried, so the card
 * owns "trials mentioning this condition", not "trials of this cancer").
 *
 * `n_trials` is the TRUE total (countTotal); `by_phase`/`by_status`/`stopped` are distributions
 * over the scanned page — a SAMPLE of n_trials for a big cancer, so `n_trials_scanned` travels
 * beside it and the card labels the distribution as over a sample. The two nullables carry
 * their own honest sub-state, and neither ever means zero:
 *   n_trials null       — the count is unavailable (the source returned a page but no total).
 *                         A true zero is an EMPTY fact, never a value, so null is unambiguous.
 *   dach_recruiting null — the DACH sub-query failed (unknown), distinct from a real 0.
 */
/** One sponsor bucket in the trial-reality fact (#39). `sponsor` is the CANONICAL company name
 *  (subsidiaries merged); `count` is over the scanned page. */
export interface TrialSponsor {
  sponsor: string
  count: number
}

export interface TrialReality {
  condition: string
  n_trials: number | null
  n_trials_scanned: number
  by_phase: TrialPhase[]
  by_status: TrialStatus[]
  stopped: { count: number; reasons: TrialStopReason[] }
  dach_recruiting: number | null
  /** E3: the most-recent trial registration date (YYYY-MM-DD) for this condition, or null when
   *  unknown. Drives the "last new trial" line and the derived silent-stalling signal. Optional:
   *  absent on pre-E3 facts. */
  latest_registration?: string | null
  /** #39: the top lead sponsors over the scanned page, NORMALISED — a company's subsidiaries are
   *  merged onto its canonical name (raw display would fragment big pharma ~4:1). All optional:
   *  absent on a pre-#39 fact. `sponsors_normalised` says the counts merged subsidiaries. */
  by_sponsor?: TrialSponsor[]
  n_sponsors?: number
  sponsors_normalised?: boolean
}

/** One example trial in a drug's observed-combinations fact. `drugs` are the drugs the arm
 *  structure names -- the combination arm's members, or the single-drug arms being compared. */
export interface CombinationExample {
  nct_id: string
  drugs: string[]
}

/**
 * A drug's OBSERVED combinations vs comparisons, classified from ClinicalTrials.gov ARM
 * structure (a single arm with >=2 drugs = a combination; >=2 arms each a single drug = a
 * comparison). The multi-drug trials with no arm-level assignment are AMBIGUOUS and dropped,
 * never guessed -- `n_ambiguous` carries how many, for honesty, never acted on. Counts are over
 * `n_scanned` trials (a capped sample of the drug's `n_total`), matched by drug name (a soft
 * match the card owns in words).
 */
export interface Combinations {
  n_total: number | null
  n_scanned: number
  n_multi_drug: number
  n_combination: number
  n_comparison: number
  n_ambiguous: number
  combination_examples: CombinationExample[]
  comparison_examples: CombinationExample[]
}
