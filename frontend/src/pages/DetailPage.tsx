import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDrug, structureUrl } from '../api/client'
import type { DrugDetail, SourcedFact } from '../api/types'
import { Card, NotApplicable } from '../components/Card'
import { AnalyzingNotice } from '../components/AnalyzingNotice'
import { Ask } from '../components/Ask'
import { BriefStateProvider, Fact } from '../components/Fact'
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

// Long enough not to hammer the API, short enough that a finished enrichment shows
// up while the reader is still looking at the page.
const POLL_MS = 2000

export function DetailPage() {
  const { chemblId = '' } = useParams()
  const [detail, setDetail] = useState<DrugDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [structureFailed, setStructureFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    setDetail(null)
    setError(null)
    setStructureFailed(false)

    // Opening a never-analyzed drug starts its enrichment server-side and returns
    // immediately, so poll until the facts land. The alternative -- holding the
    // request open -- would mean a 60s spinner against a source that often takes
    // that long, with nothing on screen explaining why.
    async function load() {
      try {
        const d = await getDrug(chemblId)
        if (cancelled) return
        setDetail(d)
        if (d.state !== 'ready') timer = setTimeout(load, POLL_MS)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    void load()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
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
  // Straight from the server. Deriving it here as "index_only and no SMILES" looked
  // right and was wrong for 87 catalog drugs -- auranofin, aroplatin, cisplatin: small
  // molecules ChEMBL simply has no structure for. The page told the reader they were
  // biologics, next to a Modality card reading "Small molecule".
  const isBiologic = !detail.is_small_molecule
  // A small molecule with nothing to draw. A measured absence, not a class of drug.
  const structureMissing = detail.is_small_molecule && !detail.has_structure
  const pending = detail.state !== 'ready'

  return (
    <BriefStateProvider value={detail.state}>
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

      <AnalyzingNotice state={detail.state} />

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
        {/* Four different sentences, because there are four different reasons this
            card might be empty. Collapsing them into "no renderable structure" told
            the reader a lie in three of the four cases. */}
        <Card title="Structure">
          {isBiologic ? (
            <NotApplicable reason={`Not applicable — ${detail.drug_type ?? 'this'} is a biologic. Antibodies and ADCs have no small-molecule structure to draw; their data model is v2.`} />
          ) : pending && !detail.has_structure ? (
            <p data-testid="fact-pending" className="py-4 text-center text-xs text-ink-faint italic">
              Waiting for sources…
            </p>
          ) : structureMissing ? (
            <NotApplicable reason="ChEMBL has no structure on record for this drug. It is a small molecule — the structure is missing, not inapplicable." />
          ) : structureFailed ? (
            <p
              data-testid="fact-source-failed"
              className="inline-flex items-center gap-1.5 rounded bg-unavailable-bg px-1.5 py-0.5
                         text-xs font-medium text-unavailable"
            >
              <span aria-hidden="true" className="size-1.5 rounded-full bg-unavailable" />
              structure could not be rendered
            </p>
          ) : (
            <>
              <img
                src={structureUrl(detail.chembl_id)}
                alt={`Structure of ${detail.pref_name ?? detail.chembl_id}`}
                data-testid="structure-svg"
                onError={() => setStructureFailed(true)}
                className="mx-auto block h-auto max-w-full"
              />
              {smiles && (
                <p className="mt-2 truncate font-mono text-[10px] text-ink-faint" title={smiles}>
                  {smiles}
                </p>
              )}
            </>
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

      {/* This was a disabled input promising "coming in a later phase" since v0.1.0.
          It now works. The answer is composed only from the facts and abstracts above
          it -- when it cannot be, the box says which of the five reasons applies
          rather than shrugging. */}
      <div className="mt-4 rounded-lg border border-line bg-card p-4">
        <h2 className="mb-2 text-xs text-ink-faint">
          Ask about this drug
          <span className="ml-2 normal-case">
            — answered only from the sourced evidence on this page
          </span>
        </h2>
        <Ask chemblId={detail.chembl_id} drugName={detail.pref_name ?? detail.chembl_id} />
      </div>

      <p className="mt-4 text-[11px] text-ink-faint">
        Evidence aggregated from ChEMBL (CC BY-SA), ClinicalTrials.gov, Open Targets and PubMed.
        Every fact links its source. H2H surfaces evidence; it does not predict.
      </p>
    </article>
    </BriefStateProvider>
  )
}
