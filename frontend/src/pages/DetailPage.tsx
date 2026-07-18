import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDrug, retryDrug, structureUrl } from '../api/client'
import type { DrugDetail, SourcedFact } from '../api/types'
import { Card, NotApplicable } from '../components/Card'
import { AnalyzingNotice } from '../components/AnalyzingNotice'
import { Ask } from '../components/Ask'
import { BriefStateProvider, Fact } from '../components/Fact'
import { MaturityPill } from '../components/MaturityPill'
import { PotencyCard } from '../components/PotencyCard'
import { SourceAdvisory } from '../components/SourceAdvisory'

/** Facts for a key, from whichever source(s) asserted it. */
function pick(detail: DrugDetail, key: string): SourcedFact[] | undefined {
  return detail.facts[key]
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
  const [retrying, setRetrying] = useState(false)
  // Bumped by a retry to re-run the load effect: the retry re-fetches server-side, and
  // this re-starts the poll that watches for the fresh brief.
  const [reloadNonce, setReloadNonce] = useState(0)

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
        // Keep polling while a brief is being built (not ready) OR revalidated in the
        // background (ready but stale): in both the next poll swaps in fresher facts.
        if (d.state !== 'ready' || d.refreshing) timer = setTimeout(load, POLL_MS)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    void load()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [chemblId, reloadNonce])

  const retry = useCallback(async () => {
    setRetrying(true)
    try {
      await retryDrug(chemblId)
      setReloadNonce((n) => n + 1) // re-poll for the fresh attempt
    } catch {
      // Leave the advisory in place; the reader can try again.
    } finally {
      setRetrying(false)
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

  // One source of truth for the structure: the SMILES the server draws from. Deriving
  // "has a structure" from one place while reading the formula text from a separately
  // fetched ChEMBL fact let the two disagree the moment ChEMBL failed on a re-fetch --
  // a drawn molecule with no formula under it, or the reverse.
  const smiles = detail.smiles
  const isBiologic = !detail.is_small_molecule
  // A small molecule with nothing to draw. A measured absence, not a class of drug.
  const structureMissing = detail.is_small_molecule && smiles === null
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
          {detail.refreshing && (
            <span data-testid="refreshing" className="text-xs text-ink-faint italic">
              refreshing…
            </span>
          )}
        </header>

        <AnalyzingNotice state={detail.state} />

        {detail.unavailable.length > 0 && <SourceAdvisory onRetry={retry} retrying={retrying} />}

        {/* Ask moved to the top: it is the thing a reader came to do, and burying it
            under eight cards made it feel like a footnote. */}
        <div className="mb-5 rounded-lg border border-line bg-card p-4">
          <h2 className="mb-2 text-xs text-ink-faint">
            Ask about this drug
            <span className="ml-2 normal-case">
              — answered only from this drug’s sourced facts and its PubMed abstracts, never from
              what a model happens to remember
            </span>
          </h2>
          <Ask
            key={detail.chembl_id}
            chemblId={detail.chembl_id}
            drugName={detail.pref_name ?? detail.chembl_id}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {/* Hero, first row: the molecule beside the distilled potency. Four cards, not
              eight -- physchem folded in under the structure it describes. */}
          <Card title="Structure & chemistry">
            {isBiologic ? (
              <NotApplicable
                reason={`Not applicable — ${detail.drug_type ?? 'this'} is a biologic. Antibodies and ADCs have no small-molecule structure or physchem profile; their data model is v2.`}
              />
            ) : (
              <>
                {pending && smiles === null ? (
                  <p
                    data-testid="fact-pending"
                    className="py-4 text-center text-xs text-ink-faint italic"
                  >
                    Waiting for sources…
                  </p>
                ) : structureMissing ? (
                  <NotApplicable reason="ChEMBL has no structure on record for this small molecule. The structure is missing, not inapplicable." />
                ) : structureFailed ? (
                  <p data-testid="fact-source-failed" className="text-center text-xs text-ink-muted">
                    The structure could not be rendered.
                  </p>
                ) : smiles !== null ? (
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
                ) : null}

                <dl className="mt-3 border-t border-line pt-2">
                  <Fact label="Molecular weight" facts={pick(detail, 'mw')} render={(v) => `${v} Da`} />
                  <Fact label="LogP" facts={pick(detail, 'alogp')} />
                  <Fact label="H-bond donors" facts={pick(detail, 'hbd')} />
                  <Fact label="H-bond acceptors" facts={pick(detail, 'hba')} />
                  <Fact
                    label="Polar surface area"
                    facts={pick(detail, 'psa')}
                    render={(v) => `${v} Å²`}
                  />
                  <Fact
                    label="Lipinski violations"
                    facts={pick(detail, 'ro5_violations')}
                    emptyLabel="0 — passes all four"
                  />
                </dl>
              </>
            )}
          </Card>

          <PotencyCard facts={pick(detail, 'ic50_summary')} isBiologic={isBiologic} />

          <Card title="Mechanism & target">
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
              <Fact
                label="Targets"
                facts={pick(detail, 'targets')}
                render={list}
                emptyLabel="None annotated"
              />
              <Fact label="Target (ChEMBL)" facts={pick(detail, 'target_chembl_id')} />
              <Fact label="Modality" facts={pick(detail, 'drug_type')} />
            </dl>
          </Card>

          <Card title="Clinical & literature">
            <dl>
              <Fact label="Trials" facts={pick(detail, 'n_trials')} emptyLabel="None registered" />
              <Fact label="Highest phase" facts={pick(detail, 'ct_max_phase')} />
              <Fact
                label="Phases seen"
                facts={pick(detail, 'phases')}
                render={list}
                emptyLabel="None recorded"
              />
              <Fact label="Stage (Open Targets)" facts={pick(detail, 'max_stage')} />
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
              <Fact
                label="IC50 activities on record"
                facts={pick(detail, 'n_ic50')}
                emptyLabel="None"
                render={(v) => `${v}`}
              />
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

        <p className="mt-4 text-[11px] text-ink-faint">
          Evidence aggregated from ChEMBL (CC BY-SA), ClinicalTrials.gov, Open Targets and PubMed.
          Every fact links its source. H2H surfaces evidence; it does not predict.
        </p>
      </article>
    </BriefStateProvider>
  )
}
