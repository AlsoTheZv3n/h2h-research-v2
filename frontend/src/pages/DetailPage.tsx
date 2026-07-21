import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDrug, retryDrug, structureUrl } from '../api/client'
import type { DrugDetail, KeyPaper, SelectivityProfile, SourcedFact } from '../api/types'
import { ctgovPhaseLabel, otStageLabel } from '../phases'
import { Card, NotApplicable } from '../components/Card'
import { AnalyzingNotice } from '../components/AnalyzingNotice'
import { Ask } from '../components/Ask'
import { CombinationsCard } from '../components/CombinationsCard'
import { BriefStateProvider, Fact } from '../components/Fact'
import { MaturityPill } from '../components/MaturityPill'
import { MechanismsFact } from '../components/MechanismsFact'
import { PotencyCard } from '../components/PotencyCard'
import { SynthesisPanel } from '../components/SynthesisPanel'
import { DisagreementPanel } from '../components/DisagreementPanel'
import { SourceAdvisory } from '../components/SourceAdvisory'
import { lipinskiReading } from '../physchem'
import { orderTargetsByPotency } from '../targets'
import { chooseTitleFacts } from '../titles'
import { KeyPapersList } from '../components/KeyPapersList'

/** Facts for a key, from whichever source(s) asserted it. */
function pick(detail: DrugDetail, key: string): SourcedFact[] | undefined {
  return detail.facts[key]
}

/** The numeric value of a fact, or null when it was not measured. A source_failed fact is null
 *  (an outage, not a value); a measured 0 (status empty under this codebase's fact() classifier)
 *  is kept as 0 -- the showZero discipline -- so a real 0 violations reads as a 0, not as missing. */
function num(detail: DrugDetail, key: string): number | null {
  const f = pick(detail, key)?.[0]
  if (!f || f.status === 'source_failed') return null
  return typeof f.value === 'number' ? f.value : null
}

// The trial-phase enums read as jargon raw (the harness misread "EARLY_PHASE1", "APPROVAL"):
// humanise each through the shared labeller so the clinical block speaks English.
const phaseList = (v: unknown) =>
  Array.isArray(v) ? v.map((p) => ctgovPhaseLabel(String(p))).join(', ') : String(v)
const stage = (v: unknown) => otStageLabel(String(v))

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

        {/* C2: the page-level "so what" leads the evidence cards -- derived statements, each
            linking to the block it came from. Renders nothing when no rule's inputs are present. */}
        <SynthesisPanel synthesis={detail.synthesis} />

        {/* E1: cross-source conflicts (e.g. the clinical phase), named where the reader used to
            have to spot them. Renders nothing when sources agree. */}
        <DisagreementPanel disagreements={detail.disagreements} />

        <div className="grid gap-4 md:grid-cols-2">
          {/* Hero, first row: the molecule beside the distilled potency. Four cards, not
              eight -- physchem folded in under the structure it describes. */}
          <Card id="structure" title="Structure & chemistry">
            {isBiologic ? (
              <NotApplicable
                reason={`Not applicable — ${detail.drug_type ?? 'This drug'} is not a small molecule, so it has no structure or physicochemical profile; that data model is v2.`}
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

                <div className="mt-3 border-t border-line pt-2">
                  {/* B1: the block leads with a one-line reading of what the numbers imply (which
                      property drives the Lipinski violation), Open Targets' summary→detail shape.
                      Withheld when the count is missing; a caution reading is muted amber, never a
                      red/green verdict -- Ro5 is a rough heuristic, not a pass/fail on the drug. */}
                  {(() => {
                    const reading = lipinskiReading({
                      mw: num(detail, 'mw'),
                      alogp: num(detail, 'alogp'),
                      hbd: num(detail, 'hbd'),
                      hba: num(detail, 'hba'),
                      ro5_violations: num(detail, 'ro5_violations'),
                    })
                    return reading ? (
                      <p
                        data-testid="lipinski-reading"
                        className={`mb-2 text-xs ${reading.tone === 'caution' ? 'text-partial' : 'text-ink-muted'}`}
                      >
                        {reading.text}
                      </p>
                    ) : null
                  })()}
                  <dl>
                    <Fact label="Molecular weight" facts={pick(detail, 'mw')} render={(v) => `${v} Da`} />
                  {/* showZero: a measured 0 is the value for these properties (0 H-bond donors,
                      LogP 0, 0 Lipinski violations), never the "None found" that reads as no data. */}
                  <Fact label="LogP" facts={pick(detail, 'alogp')} showZero />
                  <Fact label="H-bond donors" facts={pick(detail, 'hbd')} showZero />
                  <Fact label="H-bond acceptors" facts={pick(detail, 'hba')} showZero />
                  <Fact
                    label="Polar surface area"
                    facts={pick(detail, 'psa')}
                    render={(v) => `${v} Å²`}
                    showZero
                  />
                    <Fact
                      label="Lipinski violations"
                      facts={pick(detail, 'ro5_violations')}
                      render={(v) => (Number(v) === 0 ? '0 — passes all four' : String(v))}
                      showZero
                    />
                  </dl>
                </div>
              </>
            )}
          </Card>

          <PotencyCard id="potency" facts={pick(detail, 'selectivity_profile')} isBiologic={isBiologic} />

          <Card id="mechanism" title="Mechanism & target">
            <dl>
              <Fact
                label="Mechanism of action"
                facts={[...(pick(detail, 'moa') ?? []), ...(pick(detail, 'ot_moa') ?? [])]}
                emptyLabel="No mechanism annotated"
              />
              <Fact label="Action type" facts={pick(detail, 'action_type')} />
              {/* Deduped across ChEMBL + Open Targets (B2): one set, each mechanism with its
                  source chips, instead of the same list repeated once per source. */}
              <MechanismsFact facts={pick(detail, 'all_moas')} />
              {/* Ordered by the selectivity profile's potency ranking (B3), so the target list
                  and the potency card tell the same story -- no target is "primary" here and
                  "off-target" there. Falls back to source order when the ranking is unavailable. */}
              <Fact
                label="Targets"
                facts={pick(detail, 'targets')}
                render={(v) => {
                  if (!Array.isArray(v)) return String(v)
                  const profile = pick(detail, 'selectivity_profile')?.[0]?.value as
                    | SelectivityProfile
                    | null
                  return orderTargetsByPotency(v as string[], profile?.targets ?? []).join(', ')
                }}
                emptyLabel="None annotated"
              />
              <Fact label="Target (ChEMBL)" facts={pick(detail, 'target_chembl_id')} />
              <Fact label="Modality" facts={pick(detail, 'drug_type')} />
            </dl>
          </Card>

          <Card id="clinical" title="Clinical & literature">
            <dl>
              <Fact label="Trials" facts={pick(detail, 'n_trials')} emptyLabel="None registered" />
              {/* showZero: ct_max_phase is an ordinal (0 = early phase 1), a real stage, not the
                  "None found" that would read as no phase on record. */}
              <Fact label="Highest phase" facts={pick(detail, 'ct_max_phase')} showZero />
              <Fact
                label="Phases seen"
                facts={pick(detail, 'phases')}
                render={phaseList}
                emptyLabel="None recorded"
              />
              <Fact label="Stage (Open Targets)" facts={pick(detail, 'max_stage')} render={stage} />
              <Fact
                label="Any terminated/withdrawn"
                facts={pick(detail, 'has_terminated')}
                render={(v) => (v ? 'Yes' : 'No')}
                emptyLabel="No"
              />
              <Fact
                label="Indications"
                facts={pick(detail, 'indications')}
                // A truncated list must say how many of how many, or the four shown read as all.
                render={(v) => {
                  if (!Array.isArray(v)) return String(v)
                  const shown = v.slice(0, 4).join(', ')
                  return v.length > 4 ? `${shown} — 4 of ${v.length}` : shown
                }}
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
              {/* B4: the shown titles are ranked by relevance to oncology (relevant_titles),
                  falling back to PubMed's recency order (sample_titles) if the rerank was
                  unavailable or stale -- so the sample is worth reading, not led by an off-topic
                  paper, and a source_failed outage is never masked by a leftover ranked list. */}
              {(() => {
                const { facts: titleFacts, ranked } = chooseTitleFacts(
                  pick(detail, 'sample_titles'),
                  pick(detail, 'relevant_titles'),
                )
                return (
                  <Fact
                    label="Key papers"
                    facts={titleFacts}
                    emptyLabel="None"
                    render={(v) => {
                      // Same guard as the targets/indications renders above: a title fact is
                      // an array of strings or KeyPaper objects, but a malformed value must
                      // degrade to its text rather than crash KeyPapersList's items.map.
                      if (!Array.isArray(v)) return String(v)
                      return (
                        <KeyPapersList
                          items={v as (string | KeyPaper)[]}
                          ranked={ranked}
                          total={num(detail, 'n_pubmed')}
                        />
                      )
                    }}
                  />
                )
              })()}
            </dl>
          </Card>
        </div>

        {/* Full width below the grid: the observed-combinations card carries example lists that
            want the room. Reads the `combinations` fact (ClinicalTrials.gov arm structure). */}
        <div className="mt-4">
          <CombinationsCard id="combinations" facts={pick(detail, 'combinations')} />
        </div>

        <p className="mt-4 text-[11px] text-ink-faint">
          Evidence aggregated from ChEMBL (CC BY-SA), ClinicalTrials.gov, Open Targets and PubMed.
          Every fact links its source. H2H surfaces evidence; it does not predict.
        </p>
      </article>
    </BriefStateProvider>
  )
}
