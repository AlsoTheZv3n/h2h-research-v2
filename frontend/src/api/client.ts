import type { DrugDetail, DrugList, DrugListParams } from './types'

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
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
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
    target: params.target,
    max_phase: params.max_phase,
    limit: params.limit ?? 25,
    offset: params.offset ?? 0,
  })
}

export function getDrug(chemblId: string): Promise<DrugDetail> {
  return get<DrugDetail>(`/drugs/${encodeURIComponent(chemblId)}`)
}

/** The structure SVG is rendered server-side by RDKit; the browser just shows it. */
export function structureUrl(chemblId: string): string {
  return `${BASE}/drugs/${encodeURIComponent(chemblId)}/structure.svg`
}
