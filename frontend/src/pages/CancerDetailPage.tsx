import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCancer, retryCancer } from '../api/client'
import type { CancerDetail, TargetLandscape } from '../api/types'
import { AnalyzingNotice } from '../components/AnalyzingNotice'
import { BriefStateProvider } from '../components/Fact'
import { PipelineCard } from '../components/PipelineCard'
import { SourceAdvisory } from '../components/SourceAdvisory'
import { TargetLandscapeCard } from '../components/TargetLandscapeCard'
import { formatCount } from '../format'

// Long enough not to hammer the API, short enough that a finished enrichment shows up
// while the reader is still looking. Same cadence as the drug page.
const POLL_MS = 2000

/**
 * A cancer's evidence brief. It enriches on first open and serves from Postgres after,
 * so a never-seen cancer arrives `enriching` and this polls until the target landscape
 * lands -- the disease-side twin of the drug detail page.
 */
export function CancerDetailPage() {
  const { diseaseId = '' } = useParams()
  const [detail, setDetail] = useState<CancerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [reloadNonce, setReloadNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    setDetail(null)
    setError(null)

    async function load() {
      try {
        const d = await getCancer(diseaseId)
        if (cancelled) return
        setDetail(d)
        // Keep polling while the brief is being built (not ready) or revalidated behind
        // the scenes (ready but refreshing): the next poll swaps in fresher facts.
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
  }, [diseaseId, reloadNonce])

  const retry = useCallback(async () => {
    setRetrying(true)
    try {
      await retryCancer(diseaseId)
      setReloadNonce((n) => n + 1) // re-poll for the fresh attempt
    } catch {
      // Leave the advisory in place; the reader can try again.
    } finally {
      setRetrying(false)
    }
  }, [diseaseId])

  if (error) {
    return (
      <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
        Could not load this cancer: {error}
      </p>
    )
  }
  if (!detail) return <p className="text-sm text-ink-faint">Loading…</p>

  // The strong-association metric lives in the target_landscape fact, computed once from the
  // real score distribution (see enrich_cancer). n_targets is the raw "any evidence" total --
  // a threshold artifact near whole-genome size -- so the strong count is the headline and the
  // total is only ever shown beside its threshold, never bare.
  // Array.isArray guards the pre-reshape fact shape (a bare target array): it has no strong
  // count, so the stat falls back to the raw total until revalidation upgrades the fact.
  const tlFact = detail.facts['target_landscape']?.[0]
  const tl =
    tlFact?.status === 'ok' && !Array.isArray(tlFact.value)
      ? (tlFact.value as TargetLandscape | null)
      : null

  return (
    <BriefStateProvider value={detail.state}>
      <article>
        <nav className="mb-3 text-xs">
          <Link to="/cancers" className="text-accent hover:underline">
            ← All cancers
          </Link>
        </nav>

        <header className="mb-1 flex flex-wrap items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-ink">{detail.name}</h1>
          <span className="font-mono text-xs text-ink-faint">{detail.disease_id}</span>
          {detail.therapeutic_area && (
            <span className="text-xs text-ink-faint">{detail.therapeutic_area}</span>
          )}
          {detail.refreshing && (
            <span data-testid="refreshing" className="text-xs text-ink-faint italic">
              refreshing…
            </span>
          )}
        </header>

        {/* Non-clinical disclaimer: this shows treatment evidence, not treatment advice. */}
        <p className="mb-4 text-[11px] text-ink-faint" data-testid="non-clinical-disclaimer">
          A research and drug-intelligence view of the evidence and trial record — not clinical
          decision support, and not medical advice.
        </p>

        <AnalyzingNotice state={detail.state} />

        {detail.unavailable.length > 0 && <SourceAdvisory onRetry={retry} retrying={retrying} />}

        <dl className="mb-4 grid grid-cols-2 gap-3 sm:max-w-md">
          <Stat label="Drugs & clinical candidates" value={formatCount(detail.n_drugs)} />
          <TargetsStat strong={tl?.n_strong} threshold={tl?.threshold} total={detail.n_targets} />
        </dl>

        <div className="grid gap-4 md:grid-cols-2">
          <PipelineCard
            facts={detail.facts['pipeline']}
            catalogDrugIds={detail.catalog_drug_ids}
          />
          <TargetLandscapeCard facts={detail.facts['target_landscape']} />
        </div>

        <p className="mt-4 text-[11px] text-ink-faint">
          Target landscape from Open Targets (CC0). Pipeline, trial reality and biomarker evidence
          are the next blocks. H2H surfaces evidence; it does not predict or advise.
        </p>
      </article>
    </BriefStateProvider>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-2">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  )
}

/**
 * The associated-targets stat. The headline is the count of *strong* associations (score above
 * the documented threshold); the raw total is a threshold artifact near whole-genome size, so it
 * only appears as a sub-line qualified by the threshold -- the number is never shown bare.
 * Before the fact is ready (enriching, or an outage) there is no threshold yet, so we fall back
 * to the raw total, still labelled "with any evidence" -- honest about what it is.
 */
export function TargetsStat({
  strong,
  threshold,
  total,
}: {
  strong?: number
  threshold?: number
  total: number
}) {
  const hasStrong = strong !== undefined && threshold !== undefined
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-2" data-testid="targets-stat">
      <dt className="text-xs text-ink-faint">Associated targets</dt>
      <dd className="text-lg font-semibold tabular-nums text-ink">
        {formatCount(hasStrong ? strong : total)}
      </dd>
      <dd className="mt-0.5 text-[11px] text-ink-faint">
        {hasStrong ? (
          <>
            score ≥ {threshold} · {formatCount(total)} with any evidence
          </>
        ) : (
          'with any evidence'
        )}
      </dd>
    </div>
  )
}
