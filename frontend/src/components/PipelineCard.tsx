import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { PipelineData, SourcedFact } from '../api/types'
import { formatCount } from '../format'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'

// Open Targets' maxClinicalStage enum, in human words. Most advanced first is the order
// the backend already sorts by.
const PHASE_LABELS: Record<string, string> = {
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

const phaseLabel = (stage: string) => PHASE_LABELS[stage] ?? stage

// How many table rows to reveal at a time. The table pages rather than truncating, so
// the whole pipeline is reachable without a wall of names.
const PAGE_STEP = 25

/**
 * The cancer's pipeline: a phase distribution (where development is concentrated) above a
 * filterable Drug · Phase · Modality · Mechanism table, sorted by stage not alphabet.
 * Drugs the catalog holds link to their brief (matched by exact ChEMBL id, never by
 * name); the rest are plain. Honest states are handled here -- an outage is an amber
 * chip, never an empty pipeline.
 */
export function PipelineCard({
  id,
  facts,
  catalogDrugIds,
}: {
  id?: string
  facts?: SourcedFact[]
  catalogDrugIds: string[]
}) {
  return (
    <Card id={id} title="Pipeline">
      <FactGate facts={facts}>
        {(fact) => {
          const data = fact.value as PipelineData | null
          // An outage never reaches here (FactGate renders the amber chip); this is the
          // real empty -- the source looked and there is no programme -- carrying its chip.
          if (fact.status === 'empty' || !data || !data.drugs?.length) {
            return (
              <p className="text-sm text-ink-faint">
                No drug programmes indicated for this cancer
                <CitationChip fact={fact} />
              </p>
            )
          }
          return <PipelineBody data={data} catalogDrugIds={catalogDrugIds} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

function PipelineBody({
  data,
  catalogDrugIds,
  fact,
}: {
  data: PipelineData
  catalogDrugIds: string[]
  fact: SourcedFact
}) {
  const inCatalog = useMemo(() => new Set(catalogDrugIds), [catalogDrugIds])
  const [phase, setPhase] = useState('')
  const [modality, setModality] = useState('')
  const [catalogOnly, setCatalogOnly] = useState(false)
  const [query, setQuery] = useState('')
  const [shown, setShown] = useState(PAGE_STEP)

  const resetPaging = () => setShown(PAGE_STEP)

  const modalities = useMemo(() => {
    const set = new Set<string>()
    for (const d of data.drugs) if (d.modality) set.add(d.modality)
    return [...set].sort()
  }, [data.drugs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return data.drugs.filter(
      (d) =>
        (!phase || d.stage === phase) &&
        (!modality || d.modality === modality) &&
        (!catalogOnly || inCatalog.has(d.chembl_id)) &&
        (!q || d.name.toLowerCase().includes(q) || (d.mechanism ?? '').toLowerCase().includes(q)),
    )
  }, [data.drugs, phase, modality, catalogOnly, query, inCatalog])

  const maxCount = Math.max(...data.by_phase.map((p) => p.count), 1)

  return (
    <>
      <p className="text-xs text-ink-muted">
        <span className="font-medium text-ink">{formatCount(data.total)}</span> drugs &amp; clinical
        candidates
        {/* Honesty: the count is a roll-up, not an exact-node match, and that is why it
            is right (and larger than a naive match). */}
        <span className="mt-0.5 block text-ink-faint">
          via ontology roll-up — broader and narrower indications are included, which is why
          an exact-node match would undercount.
        </span>
        <span className="mt-0.5 block">
          <span className="font-medium text-ink">
            {formatCount(catalogDrugIds.length)} of {formatCount(data.total)}
          </span>{' '}
          are in the catalog and open a brief.
        </span>
      </p>

      <div className="mt-3 space-y-1" data-testid="pipeline-distribution">
        {data.by_phase.map((p) => (
          <div key={p.stage} className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0 text-ink-muted">{phaseLabel(p.stage)}</span>
            <div className="h-2 flex-1 rounded bg-surface">
              <div
                className="h-2 rounded bg-accent"
                style={{ width: `${(p.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right tabular-nums text-ink-muted">
              {formatCount(p.count)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          aria-label="Filter by phase"
          data-testid="pipeline-filter-phase"
          value={phase}
          onChange={(e) => {
            setPhase(e.target.value)
            resetPaging()
          }}
          className="rounded-md border border-line bg-card px-2 py-1 text-xs text-ink focus:outline-none"
        >
          <option value="">All phases</option>
          {data.by_phase.map((p) => (
            <option key={p.stage} value={p.stage}>
              {phaseLabel(p.stage)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by modality"
          data-testid="pipeline-filter-modality"
          value={modality}
          onChange={(e) => {
            setModality(e.target.value)
            resetPaging()
          }}
          className="rounded-md border border-line bg-card px-2 py-1 text-xs text-ink focus:outline-none"
        >
          <option value="">All modalities</option>
          {modalities.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            resetPaging()
          }}
          placeholder="Search drug or mechanism"
          aria-label="Search the pipeline"
          className="w-44 rounded-md border border-line bg-card px-2 py-1 text-xs
                     placeholder:text-ink-faint focus:outline-none"
        />
        <label className="flex items-center gap-1.5 text-xs text-ink-muted">
          <input
            type="checkbox"
            data-testid="pipeline-filter-catalog"
            checked={catalogOnly}
            onChange={(e) => {
              setCatalogOnly(e.target.checked)
              resetPaging()
            }}
            className="accent-accent"
          />
          In catalog only
        </label>
      </div>

      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-xs" data-testid="pipeline-table">
          <thead>
            <tr className="border-b border-line text-ink-faint">
              <th className="py-1 pr-2 font-medium">Drug</th>
              <th className="py-1 pr-2 font-medium">Phase</th>
              <th className="py-1 pr-2 font-medium">Modality</th>
              <th className="py-1 font-medium">Mechanism</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, shown).map((d) => (
              <tr
                key={d.chembl_id}
                data-testid="pipeline-row"
                className="border-b border-line last:border-b-0"
              >
                <td className="py-1 pr-2">
                  {inCatalog.has(d.chembl_id) ? (
                    <Link to={`/drugs/${d.chembl_id}`} className="text-accent hover:underline">
                      {d.name}
                    </Link>
                  ) : (
                    <span className="text-ink-muted">
                      {d.name}
                      <span
                        aria-hidden="true"
                        title="Not in the catalog — no brief"
                        className="ml-1 text-ink-faint"
                      >
                        ·
                      </span>
                    </span>
                  )}
                </td>
                <td className="py-1 pr-2 text-ink-muted">{phaseLabel(d.stage)}</td>
                <td className="py-1 pr-2 text-ink-muted">{d.modality ?? '—'}</td>
                <td className="py-1 text-ink-muted">{d.mechanism ?? '—'}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="py-3 text-center text-ink-faint">
                  No drugs match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex items-center justify-between text-[11px] text-ink-faint">
        <span>
          Showing {formatCount(Math.min(shown, filtered.length))} of {formatCount(filtered.length)}
        </span>
        <span className="flex items-center gap-2">
          {shown < filtered.length && (
            <button
              type="button"
              onClick={() => setShown((s) => s + PAGE_STEP)}
              className="text-accent hover:underline"
            >
              Show more
            </button>
          )}
          {shown < filtered.length && (
            <button
              type="button"
              onClick={() => setShown(filtered.length)}
              className="text-accent hover:underline"
            >
              Show all
            </button>
          )}
          <CitationChip fact={fact} />
        </span>
      </div>
    </>
  )
}
