import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDrug, structureUrl } from '../api/client'
import type { DrugDetail, SourcedFact } from '../api/types'
import { Card, NotApplicable } from '../components/Card'
import { Fact } from '../components/Fact'
import { MaturityPill } from '../components/MaturityPill'
import { PotencyCard } from '../components/PotencyCard'

/** Facts for a key, from whichever source(s) asserted it. */
function pick(detail: DrugDetail, key: string): SourcedFact[] | undefined {
  return detail.facts[key]
}

function firstOkValue<T>(facts: SourcedFact[] | undefined): T | null {
  const ok = facts?.find((f) => f.status === 'ok')
  return (ok?.value as T) ?? null
}

const list = (v: unknown) => (Array.isArray(v) ? v.join(', ') : String(v))

export function DetailPage() {
  const { chemblId = '' } = useParams()
  const [detail, setDetail] = useState<DrugDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [structureFailed, setStructureFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    setError(null)
    setStructureFailed(false)
    getDrug(chemblId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [chemblId])

  if (error) {
    return (
      <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
        Could not load {chemblId}: {error}
      </p>
    )
  }
  if (!detail) return <p className="text-sm text-ink-faint">Loading…</p>

  const smiles = firstOkValue<string>(pick(detail, 'smiles'))
  // Modality decides what we can show, not the presence of a structure -- the same
  // rule the backend's maturity classifier applies.
  const drugType = firstOkValue<string>(pick(detail, 'drug_type'))
  const isBiologic = detail.maturity === 'index_only' && !smiles

  return (
    <article>
      <nav className="mb-3 text-xs">
        <Link to="/" className="text-accent hover:underline">
          ← All programs
        </Link>
      </nav>

      <header className="mb-4 flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          {detail.pref_name ?? detail.chembl_id}
        </h1>
        <span className="font-mono text-xs text-ink-faint">{detail.chembl_id}</span>
        <MaturityPill maturity={detail.maturity} />
      </header>

      {detail.unavailable.length > 0 && (
        <p
          data-testid="unavailable-banner"
          className="mb-4 rounded-md border border-unavailable/30 bg-unavailable-bg px-3 py-2 text-xs
                     text-unavailable"
        >
          Every source failed for: {detail.unavailable.join(', ')}. These are gaps in our pipeline,
          not findings about this drug.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Structure" note={smiles ? undefined : 'No small-molecule structure'}>
          {isBiologic ? (
            <NotApplicable reason="Not applicable — this is a biologic. Antibodies and ADCs have no small-molecule structure to draw; their data model is v2." />
          ) : smiles && !structureFailed ? (
            <>
              <img
                src={structureUrl(detail.chembl_id)}
                alt={`Structure of ${detail.pref_name ?? detail.chembl_id}`}
                data-testid="structure-svg"
                onError={() => setStructureFailed(true)}
                className="mx-auto block h-auto max-w-full"
              />
              <p className="mt-2 truncate font-mono text-[10px] text-ink-faint" title={smiles}>
                {smiles}
              </p>
            </>
          ) : (
            <NotApplicable reason="No renderable structure for this drug." />
          )}
        </Card>

        <PotencyCard facts={pick(detail, 'ic50_summary')} isBiologic={isBiologic} />

        <Card title="Chemical properties">
          {isBiologic ? (
            <NotApplicable reason="Not applicable — physchem descriptors describe small molecules." />
          ) : (
            <dl>
              <Fact label="Molecular weight" facts={pick(detail, 'mw')} render={(v) => `${v} Da`} />
              <Fact label="LogP" facts={pick(detail, 'alogp')} />
              <Fact label="H-bond donors" facts={pick(detail, 'hbd')} />
              <Fact label="H-bond acceptors" facts={pick(detail, 'hba')} />
              <Fact label="Polar surface area" facts={pick(detail, 'psa')} render={(v) => `${v} Å²`} />
              <Fact
                label="Lipinski violations"
                facts={pick(detail, 'ro5_violations')}
                emptyLabel="0 — passes all four"
              />
            </dl>
          )}
        </Card>

        <Card title="Mechanism">
          <dl>
            <Fact
              label="Mechanism of action"
              facts={[...(pick(detail, 'moa') ?? []), ...(pick(detail, 'ot_moa') ?? [])]}
              emptyLabel="No mechanism annotated"
            />
            <Fact label="Action type" facts={pick(detail, 'action_type')} />
            <Fact
              label="All mechanisms"
              facts={pick(detail, 'all_moas')}
              render={list}
              emptyLabel="None annotated"
            />
          </dl>
        </Card>

        <Card title="Target & pathway">
          <dl>
            <Fact label="Targets" facts={pick(detail, 'targets')} render={list} emptyLabel="None annotated" />
            <Fact label="Target (ChEMBL)" facts={pick(detail, 'target_chembl_id')} />
            <Fact label="Modality" facts={pick(detail, 'drug_type')} />
          </dl>
        </Card>

        <Card title="Selectivity" note="What the potency summary had to exclude">
          <dl>
            <Fact
              label="IC50 activities on record"
              facts={pick(detail, 'n_ic50')}
              emptyLabel="None"
              render={(v) => `${v}`}
            />
            <Fact
              label="Off-target assays"
              facts={pick(detail, 'ic50_summary')}
              emptyLabel="None"
              render={(v) => {
                const s = v as { off_target?: Record<string, number> }
                const n = Object.values(s.off_target ?? {}).reduce((a, b) => a + b, 0)
                return n === 0 ? 'None' : `${n} rows against other targets`
              }}
            />
          </dl>
        </Card>

        <Card title="Clinical status">
          <dl>
            <Fact label="Trials" facts={pick(detail, 'n_trials')} emptyLabel="None registered" />
            <Fact label="Highest phase" facts={pick(detail, 'ct_max_phase')} />
            <Fact label="Stage (Open Targets)" facts={pick(detail, 'max_stage')} />
            <Fact label="Phases seen" facts={pick(detail, 'phases')} render={list} />
            <Fact
              label="Any terminated/withdrawn"
              facts={pick(detail, 'has_terminated')}
              render={(v) => (v ? 'Yes' : 'No')}
              emptyLabel="No"
            />
            <Fact
              label="Indications"
              facts={pick(detail, 'indications')}
              render={(v) => (Array.isArray(v) ? v.slice(0, 4).join(', ') : String(v))}
              emptyLabel="None annotated"
            />
          </dl>
        </Card>

        <Card title="Key literature">
          <dl>
            <Fact
              label="PubMed hits"
              facts={pick(detail, 'n_pubmed')}
              emptyLabel="No publications found"
            />
            <Fact
              label="Recent titles"
              facts={pick(detail, 'sample_titles')}
              emptyLabel="None"
              render={(v) => (
                <ul className="mt-0.5 space-y-0.5">
                  {(v as string[]).map((t) => (
                    <li key={t} className="text-xs text-ink-muted">
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            />
          </dl>
        </Card>
      </div>

      <div className="mt-4 rounded-lg border border-line bg-card p-4">
        <label htmlFor="followup" className="text-xs text-ink-faint">
          Follow-up
        </label>
        <input
          id="followup"
          disabled
          placeholder="Ask a follow-up about this drug — coming in a later phase"
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm
                     text-ink-faint placeholder:text-ink-faint disabled:cursor-not-allowed"
        />
      </div>

      <p className="mt-4 text-[11px] text-ink-faint">
        Evidence aggregated from ChEMBL (CC BY-SA), ClinicalTrials.gov, Open Targets and PubMed.
        Every fact links its source. H2H surfaces evidence; it does not predict.
      </p>
    </article>
  )
}
