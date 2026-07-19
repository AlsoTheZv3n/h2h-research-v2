import type { BriefState } from '../api/types'

/**
 * The fourth state, said out loud.
 *
 * A drug nobody has opened before has no facts -- and that is a statement about
 * us, not about the drug. Rendering it as an empty brief would say "we looked and
 * there is nothing", which is the exact lie this project keeps having to refuse,
 * arriving here in its newest disguise. So the page says what is true: we are
 * looking right now, this takes a moment, ChEMBL is slow.
 */
export function AnalyzingNotice({
  state,
  noun = 'drug',
  sources = 'ChEMBL, ClinicalTrials.gov, Open Targets and PubMed',
}: {
  state: BriefState
  /** The entity being analyzed, for the not-analyzed line. Defaults to the drug page's wording. */
  noun?: string
  /** The sources actually queried, named honestly -- a target brief only touches Open Targets,
   *  so it must not claim to be gathering from ChEMBL or PubMed it never asks. */
  sources?: string
}) {
  if (state === 'ready') return null

  return (
    <p
      data-testid="analyzing-notice"
      className="mb-4 flex items-center gap-2 rounded-md border border-accent/30 bg-accent-bg px-3
                 py-2 text-xs text-accent"
    >
      <span
        aria-hidden="true"
        className="size-1.5 animate-pulse rounded-full bg-accent"
      />
      {state === 'enriching'
        ? `Gathering evidence from ${sources}. This takes a few seconds — the page fills in as facts arrive.`
        : `This ${noun} has not been analyzed yet. Fetching its evidence now.`}
    </p>
  )
}
