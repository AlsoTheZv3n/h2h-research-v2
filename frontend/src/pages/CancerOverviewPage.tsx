import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listCancers, listTherapeuticAreas } from '../api/client'
import type { CancerList, CancerSortField, SortOrder } from '../api/types'
import { Pagination } from '../components/Pagination'
import { formatCount } from '../format'

const PAGE_SIZE = 25
const SEARCH_DEBOUNCE_MS = 250

// A new column sorts in the direction a reader expects first: the most drugs and
// targets at the top, but names A->Z.
const DEFAULT_ORDER: Record<CancerSortField, SortOrder> = {
  drugs: 'desc',
  targets: 'desc',
  name: 'asc',
  area: 'asc',
}

/**
 * The cancer overview: a scannable index of cancer types, mirroring the drug overview.
 * Search, facets, sort and paging all go through the API's query params and the URL, so
 * a filtered view survives a refresh and is shareable; nothing is filtered in the
 * browser, so `total` means the filtered corpus and not the page.
 */
export function CancerOverviewPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<CancerList | null>(null)
  const [catalogTotal, setCatalogTotal] = useState<number | null>(null)
  const [areas, setAreas] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const q = params.get('q') ?? ''
  const area = params.get('therapeutic_area') ?? ''
  const hasDrugs = params.get('has_drugs') ?? '' // '', 'true', 'false'
  const sort = (params.get('sort') as CancerSortField | null) ?? 'drugs'
  const order = (params.get('order') as SortOrder | null) ?? 'desc'
  const offset = Number(params.get('offset') ?? 0)

  const hasFilter = Boolean(q || area || hasDrugs)

  const [draft, setDraft] = useState(q)
  const firstRender = useRef(true)

  useEffect(() => {
    setDraft(q) // keep the box in step with the URL (back button, a shared link)
  }, [q])

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    if (draft === q) return
    const timer = setTimeout(() => {
      // Functional updater, not a captured `params` snapshot: a facet chosen during the
      // debounce window changes params but not draft, so this effect never re-ran and a
      // snapshot would clobber that facet. Reading the live params at fire time keeps it.
      setParams(
        (prev) => {
          const merged = new URLSearchParams(prev)
          if (draft) merged.set('q', draft)
          else merged.delete('q')
          merged.delete('offset')
          return merged
        },
        { replace: true },
      )
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  // The whole-catalog total, once, so the count can read "470 of 1,321 shown".
  useEffect(() => {
    listCancers({ limit: 1 })
      .then((r) => setCatalogTotal(r.total))
      .catch(() => setCatalogTotal(null))
  }, [])

  // The area facet's options, once. A failure just leaves the facet empty rather than
  // breaking the page.
  useEffect(() => {
    listTherapeuticAreas()
      .then(setAreas)
      .catch(() => setAreas([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listCancers({
      q: q || undefined,
      therapeutic_area: area || undefined,
      has_drugs: hasDrugs === '' ? undefined : hasDrugs === 'true',
      sort,
      order,
      limit: PAGE_SIZE,
      offset,
    })
      .then((result) => !cancelled && setData(result))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [q, area, hasDrugs, sort, order, offset])

  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v)
      else merged.delete(k)
    }
    if (!('offset' in next)) merged.delete('offset') // any filter change resets the page
    setParams(merged)
  }

  function toggleSort(field: CancerSortField) {
    const nextOrder = sort === field ? (order === 'asc' ? 'desc' : 'asc') : DEFAULT_ORDER[field]
    update({ sort: field, order: nextOrder })
  }

  const chips: { key: string; label: string; clear: Record<string, string> }[] = []
  if (q) chips.push({ key: 'q', label: `“${q}”`, clear: { q: '' } })
  if (area) chips.push({ key: 'therapeutic_area', label: area, clear: { therapeutic_area: '' } })
  if (hasDrugs)
    chips.push({
      key: 'has_drugs',
      label: hasDrugs === 'true' ? 'Has drug programme' : 'No drug programme',
      clear: { has_drugs: '' },
    })

  const countText = data
    ? hasFilter
      ? `${formatCount(data.total)}${catalogTotal !== null ? ` of ${formatCount(catalogTotal)}` : ''} shown`
      : `${formatCount(data.total)} cancers`
    : ''

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-ink">Cancer types</h1>
        {data && (
          <p className="text-xs text-ink-faint" data-testid="cancer-total-count">
            {countText}
          </p>
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search cancer name or disease id"
          aria-label="Search cancers"
          className="w-72 rounded-md border border-line bg-card px-2.5 py-1.5 text-sm
                     placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
        <Facet
          name="Therapeutic area"
          placeholder="Therapeutic area"
          value={area}
          onChange={(v) => update({ therapeutic_area: v })}
          options={areas.map((a): [string, string] => [a, a])}
        />
        <Facet
          name="Drug programme"
          placeholder="Drug programme"
          value={hasDrugs}
          onChange={(v) => update({ has_drugs: v })}
          options={[
            ['true', 'Has drug programme'],
            ['false', 'No drug programme'],
          ]}
        />
      </div>

      {chips.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="cancer-active-filters">
          {chips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              data-testid={`chip-${chip.key}`}
              onClick={() => update(chip.clear)}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-surface
                         px-2.5 py-1 text-xs text-ink-muted hover:border-accent hover:text-accent"
            >
              {chip.label}
              <span aria-hidden="true">✕</span>
              <span className="sr-only">remove filter</span>
            </button>
          ))}
          <button
            type="button"
            data-testid="clear-all"
            onClick={() => setParams(new URLSearchParams())}
            className="text-xs text-ink-faint underline hover:text-accent"
          >
            Clear all
          </button>
        </div>
      )}

      {error && (
        <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
          Could not load the catalog: {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full min-w-[42rem] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-ink-faint">
              <SortableTh label="Cancer" field="name" sort={sort} order={order} onSort={toggleSort} />
              <SortableTh
                label="Therapeutic area"
                field="area"
                sort={sort}
                order={order}
                onSort={toggleSort}
              />
              <SortableTh label="Drugs" field="drugs" sort={sort} order={order} onSort={toggleSort} />
              <SortableTh
                label="Targets"
                field="targets"
                sort={sort}
                order={order}
                onSort={toggleSort}
              />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            )}
            {!loading &&
              data?.items.map((cancer) => (
                <tr
                  key={cancer.disease_id}
                  data-testid="cancer-row"
                  onClick={() => navigate(`/cancers/${cancer.disease_id}`)}
                  className="cursor-pointer border-b border-line last:border-b-0 hover:bg-surface"
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-ink">{cancer.name}</span>
                    <span className="ml-2 font-mono text-[11px] text-ink-faint">
                      {cancer.disease_id}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-ink-muted">{cancer.therapeutic_area ?? '—'}</td>
                  <td className="px-3 py-2 tabular-nums text-ink-muted">
                    {formatCount(cancer.n_drugs)}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-ink-muted">
                    {formatCount(cancer.n_targets)}
                  </td>
                </tr>
              ))}
            {!loading && data?.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-ink-faint">
                  Nothing matches these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {formatCount(data.total)}
            {' · '}
            {formatCount(Math.ceil(data.total / PAGE_SIZE))} pages
          </span>
          <Pagination
            page={Math.floor(offset / PAGE_SIZE) + 1}
            totalPages={Math.ceil(data.total / PAGE_SIZE)}
            onPage={(p) => update({ offset: p > 1 ? String((p - 1) * PAGE_SIZE) : '' })}
          />
        </div>
      )}
    </section>
  )
}

function Facet({
  name,
  placeholder,
  value,
  onChange,
  options,
}: {
  name: string
  placeholder: string
  value: string
  onChange: (v: string) => void
  options: [string, string][]
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={name}
      data-testid={`facet-${name.toLowerCase().replace(/\s+/g, '-')}`}
      className="rounded-md border border-line bg-card px-2.5 py-1.5 text-sm text-ink
                 focus:border-accent focus:outline-none"
    >
      <option value="">{placeholder}</option>
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  )
}

/** A column header that sorts on click and shows a caret when it is the active sort. */
function SortableTh({
  label,
  field,
  sort,
  order,
  onSort,
}: {
  label: string
  field: CancerSortField
  sort: CancerSortField
  order: SortOrder
  onSort: (f: CancerSortField) => void
}) {
  const active = sort === field
  return (
    <th className="px-3 py-2 font-medium">
      <button
        type="button"
        onClick={() => onSort(field)}
        data-testid={`sort-${field}`}
        aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}
        className={`inline-flex items-center gap-1 hover:text-accent ${active ? 'text-ink' : ''}`}
      >
        {label}
        <span aria-hidden="true" className="text-[9px]">
          {active ? (order === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}
