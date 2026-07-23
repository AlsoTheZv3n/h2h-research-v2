/**
 * A calm notice that some sources were unavailable when the brief was last built.
 *
 * It replaces a red wall that listed internal field names ("moa, ic50_summary, n_ic50")
 * -- alarming, and meaningless to a reader. This says the one true thing in plain
 * words: the picture is partial, not wrong, and here is a button to look again. Amber,
 * not red: a gap in our pipeline is not a failure of the drug, and the page should not
 * read like one.
 */
export function SourceAdvisory({ onRetry, retrying }: { onRetry: () => void; retrying: boolean }) {
  return (
    <div
      data-testid="source-advisory"
      className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-partial/30
                 bg-partial-bg px-3 py-2 text-xs text-partial"
    >
      <span className="min-w-[16rem] flex-1">
        Some sources couldn’t be reached when this brief was last refreshed. What’s shown below is
        what we could gather — a gap in our pipeline, not a finding about this drug.
      </span>
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        data-testid="retry-sources"
        className="rounded border border-partial/40 px-2 py-1 font-medium text-partial
                   transition-colors hover:bg-partial/10 disabled:opacity-50"
      >
        {retrying ? 'Retrying…' : 'Retry sources'}
      </button>
    </div>
  )
}
