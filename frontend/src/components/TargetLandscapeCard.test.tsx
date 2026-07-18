import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { TargetLandscapeCard } from './TargetLandscapeCard'

/**
 * The one thing this card must never do is render an Open Targets outage as "no
 * associated targets" -- that would tell a reader a cancer has no druggable biology
 * when the truth is the source was down. So the states are tested apart, and the
 * outage case is the load-bearing one.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'opentargets',
    source_url: 'https://platform.opentargets.org/disease/MONDO_0005233',
    retrieved_at: '2026-07-18T18:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

// The fact value is the {threshold, n_strong, targets} wrapper -- the card reads
// value.targets, and the strong count/threshold live beside the displayed rows.
const landscape = {
  threshold: 0.5,
  n_strong: 2,
  targets: [
    { symbol: 'EGFR', score: 0.89, evidence_types: ['clinical', 'somatic_mutation'], sm_tractable: true, ab_tractable: true },
    { symbol: 'KRAS', score: 0.83, evidence_types: ['clinical'], sm_tractable: true, ab_tractable: false },
  ],
}

describe('TargetLandscapeCard', () => {
  it('renders the targets with their provenance chip', () => {
    render(<TargetLandscapeCard facts={[fact({ value: landscape })]} />)
    expect(screen.getByTestId('target-landscape')).toBeInTheDocument()
    expect(screen.getByText('EGFR')).toBeInTheDocument()
    expect(screen.getByText('KRAS')).toBeInTheDocument()
    // Provenance behind the info icon, the same chip the drug page uses.
    expect(screen.getByTestId('source-info')).toBeInTheDocument()
  })

  it('still renders targets from a pre-reshape (bare array) fact value', () => {
    // A fact stored before the {threshold, n_strong, targets} reshape is a bare array.
    // The card must keep rendering its targets from it -- an already-enriched cancer's
    // landscape must not collapse to "no targets" between the deploy and revalidation.
    render(<TargetLandscapeCard facts={[fact({ value: landscape.targets })]} />)
    expect(screen.getByTestId('target-landscape')).toBeInTheDocument()
    expect(screen.getByText('EGFR')).toBeInTheDocument()
    expect(screen.getByText('KRAS')).toBeInTheDocument()
  })

  it('renders an outage as a calm unavailable chip, never "no targets"', () => {
    render(<TargetLandscapeCard facts={[fact({ value: null, status: 'source_failed', error: 'boom' })]} />)
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    // The founding lie, refused: an outage is not an empty landscape.
    expect(screen.queryByTestId('target-landscape')).not.toBeInTheDocument()
    expect(screen.queryByText(/no associated targets/i)).not.toBeInTheDocument()
  })

  it('renders a real empty as "no associated targets"', () => {
    // The backend emits an empty dict for a resolved-but-no-targets landscape (EMPTY),
    // the same shape the pipeline uses; the card reads no targets out of it.
    render(<TargetLandscapeCard facts={[fact({ value: {}, status: 'empty' })]} />)
    expect(screen.getByText(/no associated targets/i)).toBeInTheDocument()
    expect(screen.queryByTestId('target-landscape')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    render(
      <BriefStateProvider value="enriching">
        <TargetLandscapeCard facts={undefined} />
      </BriefStateProvider>,
    )
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
