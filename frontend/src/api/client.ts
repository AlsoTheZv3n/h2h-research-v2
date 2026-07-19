import type {
  Answer,
  BriefState,
  CancerDetail,
  CancerList,
  CancerListParams,
  DrugDetail,
  DrugList,
  DrugListParams,
  FacetCounts,
  TargetDetail,
} from './types'

/**
 * Same-origin /api by default, which Vite's proxy forwards to the backend with the
 * prefix stripped -- so dev needs no CORS.
 *
 * The prefix is not cosmetic: the SPA owns /drugs/:id as a route, so proxying bare
 * /drugs would make a direct load or a refresh of a detail page return JSON instead
 * of the app. Two namespaces, kept apart.
 */
const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  // Declared and assigned rather than a constructor parameter property: the app's
  // tsconfig sets erasableSyntaxOnly, which bans the TS-only shorthand because it
  // has no meaning once the types are stripped.
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
  }

  const response = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new ApiError(`${response.status} ${response.statusText} for ${path}`, response.status)
  }
  return response.json() as Promise<T>
}

export function listDrugs(params: DrugListParams = {}): Promise<DrugList> {
  return get<DrugList>('/drugs', {
    q: params.q,
    target: params.target,
    max_phase: params.max_phase,
    modality: params.modality,
    maturity: params.maturity,
    // Only send has_target when set: a bare key would filter to "false".
    has_target: params.has_target === undefined ? undefined : String(params.has_target),
    target_class: params.target_class,
    // Only send when opting in; the default (oncology-only) needs no param.
    include_out_of_scope: params.include_out_of_scope ? 'true' : undefined,
    sort: params.sort,
    order: params.order,
    limit: params.limit ?? 25,
    offset: params.offset ?? 0,
  })
}

/**
 * The target-class facet's options: families actually present in the catalog, most
 * common first. The overview appends its own "Unclassified" (target_class IS NULL),
 * which this list never includes.
 */
export function listTargetClasses(): Promise<string[]> {
  return get<string[]>('/drugs/target-classes')
}

/**
 * Per-facet option counts for the drug overview, given the current FILTERS. Only the filter
 * params matter -- sort/order/offset do not change what matches, so they are omitted. Each
 * facet's counts exclude its own selection (server-side), so an option's "(N)" reads as what
 * picking it would give.
 */
export function listDrugFacets(params: DrugListParams = {}): Promise<FacetCounts> {
  return get<FacetCounts>('/drugs/facets', {
    q: params.q,
    target: params.target,
    max_phase: params.max_phase,
    modality: params.modality,
    maturity: params.maturity,
    has_target: params.has_target === undefined ? undefined : String(params.has_target),
    target_class: params.target_class,
    include_out_of_scope: params.include_out_of_scope ? 'true' : undefined,
  })
}

export function getDrug(chemblId: string): Promise<DrugDetail> {
  return get<DrugDetail>(`/drugs/${encodeURIComponent(chemblId)}`)
}

export function listCancers(params: CancerListParams = {}): Promise<CancerList> {
  return get<CancerList>('/cancers', {
    q: params.q,
    therapeutic_area: params.therapeutic_area,
    // Only send has_drugs when set: a bare key would filter to "false".
    has_drugs: params.has_drugs === undefined ? undefined : String(params.has_drugs),
    sort: params.sort,
    order: params.order,
    limit: params.limit ?? 25,
    offset: params.offset ?? 0,
  })
}

/** The therapeutic-area facet's options: areas present in the catalog, most common first. */
export function listTherapeuticAreas(): Promise<string[]> {
  return get<string[]>('/cancers/therapeutic-areas')
}

/** Per-facet option counts for the cancer overview, given the current filters. See listDrugFacets. */
export function listCancerFacets(params: CancerListParams = {}): Promise<FacetCounts> {
  return get<FacetCounts>('/cancers/facets', {
    q: params.q,
    therapeutic_area: params.therapeutic_area,
    has_drugs: params.has_drugs === undefined ? undefined : String(params.has_drugs),
  })
}

export function getCancer(diseaseId: string): Promise<CancerDetail> {
  return get<CancerDetail>(`/cancers/${encodeURIComponent(diseaseId)}`)
}

/** Re-fetch every source for a cancer whose brief has failures. Returns the new state;
 *  the caller polls getCancer until it is `ready`, as on the drug side. */
export async function retryCancer(diseaseId: string): Promise<{ state: BriefState }> {
  const response = await fetch(`${BASE}/cancers/${encodeURIComponent(diseaseId)}/retry`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(`${response.status} ${response.statusText}`, response.status)
  }
  return response.json() as Promise<{ state: BriefState }>
}

export function getTarget(ensemblId: string): Promise<TargetDetail> {
  return get<TargetDetail>(`/targets/${encodeURIComponent(ensemblId)}`)
}

/** Re-fetch Open Targets for a target whose brief has failures. Returns the new state; the
 *  caller polls getTarget until it is `ready`, as on the drug and cancer sides. */
export async function retryTarget(ensemblId: string): Promise<{ state: BriefState }> {
  const response = await fetch(`${BASE}/targets/${encodeURIComponent(ensemblId)}/retry`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(`${response.status} ${response.statusText}`, response.status)
  }
  return response.json() as Promise<{ state: BriefState }>
}

/** The structure SVG is rendered server-side by RDKit; the browser just shows it. */
export function structureUrl(chemblId: string): string {
  return `${BASE}/drugs/${encodeURIComponent(chemblId)}/structure.svg`
}

/**
 * Ask the sources again for a drug whose brief has failures. Returns the new brief
 * state; the caller then polls getDrug as usual until it is `ready`. The server
 * invalidates its cache, so the poll sees the fresh attempt, not the stale one.
 */
export async function retryDrug(chemblId: string): Promise<{ state: BriefState }> {
  const response = await fetch(`${BASE}/drugs/${encodeURIComponent(chemblId)}/retry`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(`${response.status} ${response.statusText}`, response.status)
  }
  return response.json() as Promise<{ state: BriefState }>
}

/**
 * Ask about one drug. Scoped by URL, because a question is always about a molecule.
 *
 * A non-ok `state` is not an error and must not be thrown: "no model is configured"
 * and "the model cited a source we never gave it" are answers the reader needs to
 * see, and throwing here would collapse both into a generic failure toast. The
 * distinction the backend works to preserve dies at this line if it is written
 * carelessly.
 */
export async function askDrug(chemblId: string, question: string): Promise<Answer> {
  const response = await fetch(`${BASE}/drugs/${encodeURIComponent(chemblId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!response.ok) {
    throw new ApiError(`${response.status} ${response.statusText}`, response.status)
  }
  return response.json() as Promise<Answer>
}
