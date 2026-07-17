import type { Answer, DrugDetail, DrugList, DrugListParams } from './types'

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

export function getDrug(chemblId: string): Promise<DrugDetail> {
  return get<DrugDetail>(`/drugs/${encodeURIComponent(chemblId)}`)
}

/** The structure SVG is rendered server-side by RDKit; the browser just shows it. */
export function structureUrl(chemblId: string): string {
  return `${BASE}/drugs/${encodeURIComponent(chemblId)}/structure.svg`
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
