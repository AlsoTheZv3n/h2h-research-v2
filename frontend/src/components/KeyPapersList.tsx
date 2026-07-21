import { formatCount } from '../format'
import type { KeyPaper } from '../api/types'

/**
 * The drug page's "Key papers" list (B4 + #42). `items` are the relevance-ranked KeyPaper objects
 * (relevant_titles) OR the plain-string fallback (sample_titles) -- normalised here to one shape.
 *
 * #42 adds two per-paper signals without touching the RANKING (which stays oncology-embedding
 * relevance): the publication type, a free evidence hierarchy that draws the eye to the
 * higher-evidence papers (a plain journal article gets no badge, so the badge is signal not noise);
 * and "not yet indexed" for a recent paper PubMed has not MeSH-indexed -- a label, never a
 * down-ranking, so a fresh trial is not sunk for lacking MeSH.
 */
export function KeyPapersList({
  items,
  ranked,
  total,
}: {
  items: (string | KeyPaper)[]
  ranked: boolean
  total: number | null
}) {
  const papers: KeyPaper[] = items.map((it) =>
    typeof it === 'string'
      ? { title: it, pmid: null, publication_type: null, indexed: true }
      : it,
  )
  // A sample, labelled: the N most relevant OF the M PubMed hits above.
  const ofTotal = total !== null && total > papers.length ? ` of ${formatCount(total)}` : ''
  return (
    <>
      <span className="text-[11px] text-ink-faint">
        the {papers.length} {ranked ? 'most relevant' : 'most recent'}
        {ofTotal}
      </span>
      <ul className="mt-0.5 space-y-0.5">
        {/* keyed by index+title: two records can share a title (errata, duplicate deposits) and a
            title-only key would drop one row. */}
        {papers.map((p, i) => (
          <li key={`${i}-${p.title}`} className="text-xs text-ink-muted">
            {p.title}
            {p.publication_type && (
              <span
                data-testid="paper-pubtype"
                className="ml-1.5 rounded bg-accent-bg px-1 text-[10px] font-medium text-accent"
              >
                {p.publication_type}
              </span>
            )}
            {!p.indexed && (
              <span
                data-testid="paper-unindexed"
                title="MeSH indexing not applied yet — recent, not low quality"
                className="ml-1.5 text-[10px] italic text-ink-faint"
              >
                not yet indexed
              </span>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}
