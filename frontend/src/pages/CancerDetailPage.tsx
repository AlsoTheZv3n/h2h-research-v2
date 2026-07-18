import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCancer } from '../api/client'
import type { CancerDetail } from '../api/types'
import { formatCount } from '../format'

/**
 * A cancer's page. Deliberately thin for P1-T1: it shows the catalog facts and says,
 * honestly, that the evidence brief has not been built yet -- because enrich_cancer
 * (the target landscape, pipeline and trial-reality blocks) is P1-T2. The pending
 * notice is the not_analyzed state, never "no evidence exists".
 */
export function CancerDetailPage() {
  const { diseaseId = '' } = useParams()
  const [cancer, setCancer] = useState<CancerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getCancer(diseaseId)
      .then((c) => !cancelled && setCancer(c))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [diseaseId])

  return (
    <div>
      <Link to="/cancers" className="text-sm text-accent hover:underline">
        ← All cancers
      </Link>

      {loading && <p className="mt-4 text-sm text-ink-faint">Loading…</p>}

      {error && (
        <p className="mt-4 rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable">
          Could not load this cancer: {error}
        </p>
      )}

      {cancer && (
        <>
          <header className="mt-3">
            <h1 className="text-xl font-semibold tracking-tight text-ink">{cancer.name}</h1>
            <p className="mt-0.5 text-xs text-ink-faint">
              <span className="font-mono">{cancer.disease_id}</span>
              {cancer.therapeutic_area && <> · {cancer.therapeutic_area}</>}
            </p>
          </header>

          <dl className="mt-4 grid grid-cols-2 gap-3 sm:max-w-md">
            <Stat label="Drugs & clinical candidates" value={formatCount(cancer.n_drugs)} />
            <Stat label="Associated targets" value={formatCount(cancer.n_targets)} />
          </dl>

          <div
            className="mt-6 rounded-lg border border-line bg-card p-4"
            data-testid="cancer-brief-pending"
          >
            <p className="text-sm font-medium text-ink">The evidence brief is not built yet</p>
            <p className="mt-1 text-sm text-ink-muted">
              This cancer is in the catalog, but its target landscape, pipeline and trial
              reality have not been assembled. That is the next step — enrichment — not a
              finding that no evidence exists.
            </p>
          </div>
        </>
      )}
    </div>
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
