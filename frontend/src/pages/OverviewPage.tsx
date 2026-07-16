import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listDrugs } from '../api/client'
import type { DrugList } from '../api/types'
import { MaturityPill, PhasePill } from '../components/MaturityPill'
import { formatCount } from '../format'

const PAGE_SIZE = 25
// Long enough that typing a drug name is one query, not eight.
const SEARCH_DEBOUNCE_MS = 250

/**
 * The overview: a light, scannable index. Index columns only -- no molecular
 * detail, that is what the brief is for.
 *
 * Filters and paging go through the API's query params rather than filtering a
 * fetched page in the browser: the catalog is thousands of drugs, and `total` has
 * to mean the corpus, not the page. (The spike shipped exactly that bug once.)
 */
export function OverviewPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<DrugList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const q = params.get('q') ?? ''
  const maxPhase = params.get('max_phase') ?? ''
  const offset = Number(params.get('offset') ?? 0)

  // The input is uncontrolled-ish: it updates instantly while the URL (and the
  // query) lag behind by a debounce. Binding it straight to the URL made every
  // keystroke a request, and a search box that fires per character against an
  // exact match returns nothing until the very last letter -- which reads as
  // broken rather than strict.
  const [draft, setDraft] = useState(q)
  const firstRender = useRef(true)

  useEffect(() => {
    // Keep the box in step when the URL changes from outside (back button, a link).
    setDraft(q)
  }, [q])

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    if (draft === q) return
    const timer = setTimeout(() => {
      const merged = new URLSearchParams(params)
      if (draft) merged.set('q', draft)
      else merged.delete('q')
      merged.delete('offset') // a new search invalidates the page cursor
      setParams(merged, { replace: true })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listDrugs({
      q: q || undefined,
      max_phase: maxPhase ? Number(maxPhase) : undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((result) => !cancelled && setData(result))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [q, maxPhase, offset])

  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v)
      else merged.delete(k)
    }
    if (!('offset' in next)) merged.delete('offset')
    setParams(merged)
  }

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-ink">Drug programs</h1>
        {data && (
          <p className="text-xs text-ink-faint" data-testid="total-count">
            {formatCount(data.total)} {q || maxPhase ? 'match' : 'in catalog'}
          </p>
        )}
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search name, ChEMBL id or target"
          aria-label="Search drugs"
          className="w-72 rounded-md border border-line bg-card px-2.5 py-1.5 text-sm
                     placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
        <select
          value={maxPhase}
          onChange={(e) => update({ max_phase: e.target.value })}
          aria-label="Minimum phase"
          className="rounded-md border border-line bg-card px-2.5 py-1.5 text-sm text-ink
                     focus:border-accent focus:outline-none"
        >
          <option value="">Any phase</option>
          <option value="1">Phase 1+</option>
          <option value="2">Phase 2+</option>
          <option value="3">Phase 3+</option>
          <option value="4">Approved</option>
        </select>
        {(q || maxPhase) && (
          <button
            type="button"
            onClick={() => setParams(new URLSearchParams())}
            className="rounded-md border border-line px-2.5 py-1.5 text-sm text-ink-muted
                       hover:border-accent hover:text-accent"
          >
            Clear
          </button>
        )}
      </div>

      {error && (
        <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
          Could not load the catalog: {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full min-w-[46rem] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-ink-faint">
              <th className="px-3 py-2 font-medium">Drug</th>
              <th className="px-3 py-2 font-medium">Target</th>
              <th className="px-3 py-2 font-medium">Indication</th>
              <th className="px-3 py-2 font-medium">Modality</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Data</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            )}
            {!loading &&
              data?.items.map((drug) => (
                <tr
                  key={drug.chembl_id}
                  data-testid="drug-row"
                  onClick={() => navigate(`/drugs/${drug.chembl_id}`)}
                  className="cursor-pointer border-b border-line last:border-b-0 hover:bg-surface"
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-ink">{drug.pref_name ?? drug.chembl_id}</span>
                    <span className="ml-2 font-mono text-[11px] text-ink-faint">
                      {drug.chembl_id}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-ink-muted">{drug.primary_target ?? '—'}</td>
                  <td className="max-w-[16rem] truncate px-3 py-2 text-ink-muted">
                    {drug.primary_indication ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-ink-muted">{drug.drug_type ?? '—'}</td>
                  <td className="px-3 py-2">
                    <PhasePill phase={drug.max_phase} />
                  </td>
                  <td className="px-3 py-2">
                    <MaturityPill maturity={drug.maturity} />
                  </td>
                </tr>
              ))}
            {!loading && data?.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-ink-faint">
                  Nothing matches “{q}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {formatCount(data.total)}
          </span>
          <span className="flex gap-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => update({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
              className="rounded border border-line px-2 py-1 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= data.total}
              onClick={() => update({ offset: String(offset + PAGE_SIZE) })}
              className="rounded border border-line px-2 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </span>
        </div>
      )}
    </section>
  )
}
