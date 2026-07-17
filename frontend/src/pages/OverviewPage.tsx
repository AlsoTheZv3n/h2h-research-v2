import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listDrugs } from '../api/client'
import type { DataMaturity, DrugList, SortField, SortOrder } from '../api/types'
import { MaturityPill, PhasePill } from '../components/MaturityPill'
import { formatCount } from '../format'

const PAGE_SIZE = 25
// Long enough that typing a drug name is one query, not eight.
const SEARCH_DEBOUNCE_MS = 250

// The drug types the catalog actually holds, most common first. Exact values, so the
// modality filter (an exact, case-insensitive match) has something to match.
const MODALITIES = [
  'Small molecule',
  'Antibody',
  'Antibody drug conjugate',
  'Protein',
  'Oligonucleotide',
  'Gene',
  'Cell',
  'Enzyme',
]

const MATURITY_LABELS: Record<string, string> = {
  full: 'Full brief',
  partial: 'Partial',
  index_only: 'Index only',
}

// A new column sorts in the direction a reader expects first: names A→Z, but the
// most complete data and the highest phase at the top.
const DEFAULT_ORDER: Record<SortField, SortOrder> = {
  data: 'desc',
  phase: 'desc',
  name: 'asc',
  target: 'asc',
  indication: 'asc',
}

/**
 * The overview: a light, scannable index. Index columns only -- no molecular detail,
 * that is what the brief is for.
 *
 * Everything -- search, facets, sort, paging -- goes through the API's query params
 * and is reflected in the URL, so a filtered view survives a refresh and is
 * shareable. Nothing is filtered or sorted in the browser: the catalog is thousands
 * of drugs and `total` has to mean the filtered corpus, not the page. (The spike
 * shipped exactly that bug once.)
 */
export function OverviewPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<DrugList | null>(null)
  const [catalogTotal, setCatalogTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const q = params.get('q') ?? ''
  const target = params.get('target') ?? ''
  const maxPhase = params.get('max_phase') ?? ''
  const modality = params.get('modality') ?? ''
  const maturity = params.get('maturity') ?? ''
  const hasTarget = params.get('has_target') ?? '' // '', 'true', 'false'
  const sort = (params.get('sort') as SortField | null) ?? 'data'
  const order = (params.get('order') as SortOrder | null) ?? 'desc'
  const offset = Number(params.get('offset') ?? 0)

  const filtersActive = Boolean(q || target || maxPhase || modality || maturity || hasTarget)

  // The search box updates instantly while the URL (and query) lag by a debounce.
  // Binding it straight to the URL made every keystroke a request against a partial
  // match -- readable, but a request per character.
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
      const merged = new URLSearchParams(params)
      if (draft) merged.set('q', draft)
      else merged.delete('q')
      merged.delete('offset')
      setParams(merged, { replace: true })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  // The catalog total, once, so the count can read "612 of 3,923 shown" -- the second
  // number is the whole corpus, not this filtered slice.
  useEffect(() => {
    listDrugs({ limit: 1 })
      .then((r) => setCatalogTotal(r.total))
      .catch(() => setCatalogTotal(null))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listDrugs({
      q: q || undefined,
      target: target || undefined,
      max_phase: maxPhase ? Number(maxPhase) : undefined,
      modality: modality || undefined,
      maturity: (maturity || undefined) as DataMaturity | undefined,
      has_target: hasTarget === '' ? undefined : hasTarget === 'true',
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
  }, [q, target, maxPhase, modality, maturity, hasTarget, sort, order, offset])

  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v)
      else merged.delete(k)
    }
    if (!('offset' in next)) merged.delete('offset') // any filter change resets the page
    setParams(merged)
  }

  function toggleSort(field: SortField) {
    // Same column: flip direction. New column: its natural first direction.
    const nextOrder = sort === field ? (order === 'asc' ? 'desc' : 'asc') : DEFAULT_ORDER[field]
    update({ sort: field, order: nextOrder })
  }

  // One removable chip per active filter, in the order they read.
  const chips: { key: string; label: string; clear: Record<string, string> }[] = []
  if (q) chips.push({ key: 'q', label: `“${q}”`, clear: { q: '' } })
  if (modality) chips.push({ key: 'modality', label: modality, clear: { modality: '' } })
  if (maturity)
    chips.push({ key: 'maturity', label: MATURITY_LABELS[maturity] ?? maturity, clear: { maturity: '' } })
  if (maxPhase)
    chips.push({
      key: 'phase',
      label: maxPhase === '4' ? 'Approved' : `Phase ${maxPhase}+`,
      clear: { max_phase: '' },
    })
  if (target) chips.push({ key: 'target', label: `Target: ${target}`, clear: { target: '' } })
  if (hasTarget)
    chips.push({
      key: 'has_target',
      label: hasTarget === 'true' ? 'Has target' : 'No target',
      clear: { has_target: '' },
    })

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-ink">Drug programs</h1>
        {data && (
          <p className="text-xs text-ink-faint" data-testid="total-count">
            {filtersActive && catalogTotal !== null ? (
              <>
                {formatCount(data.total)} of {formatCount(catalogTotal)} shown
              </>
            ) : (
              <>{formatCount(data.total)} in catalog</>
            )}
          </p>
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search name, ChEMBL id or target"
          aria-label="Search drugs"
          className="w-72 rounded-md border border-line bg-card px-2.5 py-1.5 text-sm
                     placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
        <Facet
          name="Modality"
          placeholder="Modality"
          value={modality}
          onChange={(v) => update({ modality: v })}
          options={MODALITIES.map((m) => [m, m])}
        />
        <Facet
          name="Data completeness"
          placeholder="Data"
          value={maturity}
          onChange={(v) => update({ maturity: v })}
          options={[
            ['full', 'Full brief'],
            ['partial', 'Partial'],
            ['index_only', 'Index only'],
          ]}
        />
        <Facet
          name="Minimum phase"
          placeholder="Any phase"
          value={maxPhase}
          onChange={(v) => update({ max_phase: v })}
          options={[
            ['1', 'Phase 1+'],
            ['2', 'Phase 2+'],
            ['3', 'Phase 3+'],
            ['4', 'Approved'],
          ]}
        />
        <Facet
          name="Target presence"
          placeholder="Target"
          value={hasTarget}
          onChange={(v) => update({ has_target: v })}
          options={[
            ['true', 'Has target'],
            ['false', 'No target'],
          ]}
        />
      </div>

      {chips.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="active-filters">
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
        <table className="w-full min-w-[46rem] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-ink-faint">
              <SortableTh label="Drug" field="name" sort={sort} order={order} onSort={toggleSort} />
              <SortableTh label="Target" field="target" sort={sort} order={order} onSort={toggleSort} />
              <SortableTh
                label="Indication"
                field="indication"
                sort={sort}
                order={order}
                onSort={toggleSort}
              />
              <th className="px-3 py-2 font-medium">Modality</th>
              <SortableTh label="Phase" field="phase" sort={sort} order={order} onSort={toggleSort} />
              <SortableTh label="Data" field="data" sort={sort} order={order} onSort={toggleSort} />
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
                  Nothing matches these filters.
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

/**
 * A facet dropdown whose first option clears it.
 *
 * `name` is the accessible name and the testid basis; `placeholder` is the empty
 * option's text. They are separate on purpose: the phase facet reads "Any phase" but
 * is named "Minimum phase" (what it does), and conflating the two renamed the
 * accessible label out from under an existing E2E.
 */
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
  field: SortField
  sort: SortField
  order: SortOrder
  onSort: (f: SortField) => void
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
