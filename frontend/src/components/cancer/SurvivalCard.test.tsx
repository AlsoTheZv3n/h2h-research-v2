import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../../api/types'
import { BriefStateProvider } from '../ui/Fact'
import { SurvivalCard } from './SurvivalCard'

/**
 * Block B is a TABLE of 5-year RELATIVE survival by SEER summary stage -- not a Kaplan-Meier
 * curve, no traffic-light. Leukemias are not stage-decomposed, so only the all-stages figure
 * shows (a real gap, never a zero). The wording caveats (relative, not TNM, not KM) are
 * load-bearing: they keep the reader from reading more into the number than it holds.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'seer',
    source_url: null,
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const STAGED = {
  match_type: 'exact',
  source_label: 'Lung and Bronchus',
  metric: '5-year relative survival',
  staged: true,
  all_stages: { rate: 29.47, ci_low: 29.28, ci_high: 29.65, n: 390184 },
  by_stage: [
    { stage: 'Localized', rate: 65.5, ci_low: 65.0, ci_high: 66.0, n: 92662, share: 0.2375 },
    { stage: 'Regional', rate: 38.2, ci_low: 37.8, ci_high: 38.6, n: 80220, share: 0.2056 },
    { stage: 'Distant', rate: 10.5, ci_low: 10.3, ci_high: 10.7, n: 200434, share: 0.5137 },
  ],
}

const NON_STAGED = {
  match_type: 'exact',
  source_label: 'Leukemia',
  metric: '5-year relative survival',
  staged: false,
  all_stages: { rate: 68.6, ci_low: 68.2, ci_high: 69.0, n: 118580 },
  by_stage: [],
}

function renderCard(facts: SourcedFact[] | undefined, state = 'ready') {
  return render(
    <BriefStateProvider value={state as 'ready' | 'enriching' | 'not_analyzed'}>
      <SurvivalCard facts={facts} cancerName="lung cancer" />
    </BriefStateProvider>,
  )
}

describe('SurvivalCard', () => {
  it('renders the staged table with rate, CI, cases and share, plus the all-stages headline', () => {
    renderCard([fact({ value: STAGED })])
    expect(screen.getByTestId('survival-all')).toHaveTextContent('29.5%')
    expect(screen.getByTestId('survival-table')).toBeInTheDocument()
    expect(screen.getAllByTestId('survival-row')).toHaveLength(3)
    // A stage row carries its rate, CI and case share.
    expect(screen.getByText('Localized')).toBeInTheDocument()
    expect(screen.getByText('65.5%')).toBeInTheDocument()
    expect(screen.getByText(/65\.0%–66\.0%/)).toBeInTheDocument()
    // The wording caveats that keep the number honest (phrases unique to the caveat line).
    expect(screen.getByText(/against a matched general population/i)).toBeInTheDocument()
    expect(screen.getByText(/not TNM/)).toBeInTheDocument()
    expect(screen.getByText(/not a Kaplan–Meier curve/)).toBeInTheDocument()
  })

  it('keeps the all-stages case count even when the CI is suppressed (capped rate)', () => {
    // A ~100% rate suppresses the CI bounds, but the total N is still meaningful and must not
    // vanish with the CI. Re-couple N to the CI conditional and this goes red.
    const capped = { ...NON_STAGED, all_stages: { rate: 99.9, ci_low: null, ci_high: null, n: 50000 } }
    renderCard([fact({ value: capped })])
    expect(screen.getByText(/50,000 cases/)).toBeInTheDocument()
  })

  it('shows only the all-stages figure for a non-staged cancer, with an honest note', () => {
    renderCard([fact({ value: NON_STAGED })])
    expect(screen.getByTestId('survival-all')).toHaveTextContent('68.6%')
    // The stage block is a real gap for leukemias, stated -- never rendered as a zero table.
    expect(screen.getByTestId('survival-not-staged')).toBeInTheDocument()
    expect(screen.queryByTestId('survival-table')).not.toBeInTheDocument()
  })

  it('renders a SEER outage as an amber chip, never an empty', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'down' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('survival-all')).not.toBeInTheDocument()
  })

  it('renders unmapped as "not available for this cancer"', () => {
    renderCard([fact({ value: { match_type: 'unmapped' } })])
    expect(screen.getByTestId('not-applicable')).toHaveTextContent(/not available for lung cancer/i)
  })
})
