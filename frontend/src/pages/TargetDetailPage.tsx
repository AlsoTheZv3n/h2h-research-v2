import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getTarget, retryTarget } from '../api/client'
import type { TargetDetail } from '../api/types'
import { AnalyzingNotice } from '../components/AnalyzingNotice'
import { BriefStateProvider } from '../components/Fact'
import { SectionErrorBoundary } from '../components/SectionErrorBoundary'
import { SectionNav } from '../components/SectionNav'
import { SourceAdvisory } from '../components/SourceAdvisory'
import { formatCount } from '../format'
import { TARGET_SECTIONS } from './targetSections'

// Same cadence as the drug and cancer pages: long enough not to hammer the API, short enough
// that a finished enrichment shows up while the reader is still looking.
const POLL_MS = 2000

/**
 * A target's evidence brief -- the cancer page run backwards. It enriches on first open (the
 * Open Targets reverse query: the cancers this target is associated with, filtered to our
 * catalog) and serves from Postgres after, so a never-seen target arrives `enriching` and this
 * polls until its associated cancers land.
 */
export function TargetDetailPage() {
  const { ensemblId = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<TargetDetail | null>(null)
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
        const d = await getTarget(ensemblId)
        if (cancelled) return
        setDetail(d)
        // Keep polling while the brief is being built or revalidated behind the scenes.
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
  }, [ensemblId, reloadNonce])

  const retry = useCallback(async () => {
    setRetrying(true)
    try {
      await retryTarget(ensemblId)
      setReloadNonce((n) => n + 1) // re-poll for the fresh attempt
    } catch {
      // Leave the advisory in place; the reader can try again.
    } finally {
      setRetrying(false)
    }
  }, [ensemblId])

  // Deep-link to a section: /targets/ENSG_x#associated-cancers. Scroll only ONCE per hash, and
  // only once the anchor is in the DOM (which is after `detail` renders); the ref records the
  // hash already honoured so later poll re-renders do not yank a reader who scrolled away.
  const { hash } = useLocation()
  const scrolledForHash = useRef<string | null>(null)
  useEffect(() => {
    if (!hash || scrolledForHash.current === hash) return
    const target = document.getElementById(hash.slice(1))
    if (!target) return
    target.scrollIntoView()
    scrolledForHash.current = hash
  }, [hash, detail])

  if (error) {
    return (
      <p className="rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
        Could not load this target: {error}
      </p>
    )
  }
  if (!detail) return <p className="text-sm text-ink-faint">Loading…</p>

  return (
    <BriefStateProvider value={detail.state}>
      <article className="lg:grid lg:grid-cols-[11rem_1fr] lg:gap-8">
        <SectionNav sections={TARGET_SECTIONS} />

        <div>
          <nav className="mb-3 text-xs">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="text-accent hover:underline"
            >
              ← Back
            </button>
          </nav>

          <header className="mb-1 flex flex-wrap items-baseline gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-ink">{detail.symbol}</h1>
            {detail.name && <span className="text-sm text-ink-muted">{detail.name}</span>}
            <span className="font-mono text-xs text-ink-faint">{detail.ensembl_id}</span>
            {detail.refreshing && (
              <span data-testid="refreshing" className="text-xs text-ink-faint italic">
                refreshing…
              </span>
            )}
          </header>

          {/* Non-clinical disclaimer: this shows treatment evidence, not treatment advice. */}
          <p className="mb-4 text-[11px] text-ink-faint" data-testid="non-clinical-disclaimer">
            A research and drug-intelligence view of a target's evidence — not clinical decision
            support, and not medical advice.
          </p>

          <AnalyzingNotice state={detail.state} noun="target" sources="Open Targets" />

          {detail.unavailable.length > 0 && <SourceAdvisory onRetry={retry} retrying={retrying} />}

          {detail.n_cancers !== null && (
            <dl data-testid="target-stats" className="mb-4 grid grid-cols-2 gap-3 sm:max-w-md">
              <Stat label="Associated cancers" value={formatCount(detail.n_cancers)} />
            </dl>
          )}

          {/* Each section renders its own honest state from its slice, inside its own error
              boundary. Order, labels and anchors come from the TARGET_SECTIONS registry. */}
          <div className="space-y-4">
            {TARGET_SECTIONS.map((s) => (
              <SectionErrorBoundary key={s.id} id={s.id} title={s.label}>
                {s.render(detail)}
              </SectionErrorBoundary>
            ))}
          </div>

          <p className="mt-4 text-[11px] text-ink-faint">
            Associated cancers from Open Targets (CC0), filtered to the diseases our catalog lists.
            H2H surfaces evidence; it does not predict or advise.
          </p>
        </div>
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
