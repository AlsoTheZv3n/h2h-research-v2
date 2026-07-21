import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact, TrialReality } from '../api/types'
import { BriefStateProvider } from './Fact'
import { TrialRealityCard } from './TrialRealityCard'

/**
 * The trial-reality card's jobs: the honest count (a TRUE total, with the scanned sample beside it
 * so a distribution reads as a sample), phase/status distributions, stopped-with-reasons, the DACH
 * signal, and the four honest states -- with the two nullable sub-signals rendering as
 * "unavailable"/"unknown", NEVER as zero. Those last are the load-bearing guards.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'clinicaltrials',
    source_url: 'https://clinicaltrials.gov/search?cond=non-small+cell+lung+carcinoma',
    retrieved_at: '2026-07-19T18:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const trial: TrialReality = {
  condition: 'non-small cell lung carcinoma',
  n_trials: 8442,
  n_trials_scanned: 1000,
  by_phase: [
    { phase: 'PHASE1', count: 283 },
    { phase: 'PHASE2', count: 440 },
  ],
  by_status: [
    { status: 'RECRUITING', count: 153 },
    { status: 'TERMINATED', count: 143 },
  ],
  stopped: {
    count: 172,
    reasons: [
      { reason: 'Slow accrual', count: 12 },
      { reason: 'Business decision', count: 8 },
    ],
  },
  dach_recruiting: 122,
}

function renderCard(facts: SourcedFact[] | undefined, state = 'ready') {
  return render(
    <MemoryRouter>
      <BriefStateProvider value={state as 'ready' | 'enriching' | 'not_analyzed'}>
        <TrialRealityCard facts={facts} />
      </BriefStateProvider>
    </MemoryRouter>,
  )
}

describe('TrialRealityCard', () => {
  it('renders the true count, the soft-match + sample notes, distributions, DACH and stopped reasons', () => {
    renderCard([fact({ value: trial })])
    // The count reads as a TOTAL (8,442), never the scanned page (1,000).
    expect(screen.getByTestId('trial-count')).toHaveTextContent(/8,442 registered trials/)
    expect(screen.getByText(/Matched on condition text/i)).toBeInTheDocument()
    expect(screen.getByTestId('trial-sample-note')).toHaveTextContent(/1,000 most-relevant/)
    // Distributions render with human labels AND as counts, never shares -- the seeded 440
    // (Phase 2) is what a regression to percentages would drop.
    const phaseDist = screen.getByTestId('trial-phase-distribution')
    expect(within(phaseDist).getByText('Phase 2')).toBeInTheDocument()
    expect(within(phaseDist).getByText('440')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('trial-status-distribution')).getByText('Recruiting'),
    ).toBeInTheDocument()
    // DACH true count, and stopped count + a stated reason.
    expect(within(screen.getByTestId('trial-dach')).getByText('122')).toBeInTheDocument()
    expect(within(screen.getByTestId('trial-stopped')).getByText(/172/)).toBeInTheDocument()
    expect(screen.getByText('Slow accrual')).toBeInTheDocument()
  })

  it('shows the last-new-trial year when the registration date is known (E3)', () => {
    renderCard([fact({ value: { ...trial, latest_registration: '2019-05-14' } })])
    expect(screen.getByTestId('trial-latest-registration')).toHaveTextContent(
      /Last new trial registered:\s*2019/,
    )
  })

  it('omits the last-new-trial line when the date is unknown, never "never" or a zero (E3)', () => {
    // A pre-E3 fact (no latest_registration) shows no line rather than a fabricated date.
    renderCard([fact({ value: trial })])
    expect(screen.queryByTestId('trial-latest-registration')).not.toBeInTheDocument()
  })

  it('renders an outage as an unavailable chip, never "no trials"', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'boom' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByText(/no registered trials/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('trial-phase-distribution')).not.toBeInTheDocument()
  })

  it('renders a real empty as "no registered trials"', () => {
    renderCard([fact({ value: null, status: 'empty' })])
    expect(screen.getByText(/no registered trials/i)).toBeInTheDocument()
    expect(screen.queryByTestId('trial-phase-distribution')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    renderCard(undefined, 'enriching')
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })

  it('shows an unavailable count (never zero) when the total is missing, but keeps distributions', () => {
    renderCard([fact({ value: { ...trial, n_trials: null } })])
    expect(
      within(screen.getByTestId('trial-count')).getByText(/count unavailable/i),
    ).toBeInTheDocument()
    // No misleading sample note (there is no total to sample against), and no invented number.
    expect(screen.queryByTestId('trial-sample-note')).not.toBeInTheDocument()
    // The page we did get still renders its distributions.
    expect(screen.getByTestId('trial-phase-distribution')).toBeInTheDocument()
  })

  it('shows DACH as unknown (never zero) when the sub-query failed', () => {
    renderCard([fact({ value: { ...trial, dach_recruiting: null } })])
    const dach = screen.getByTestId('trial-dach')
    expect(within(dach).getByText(/unknown/i)).toBeInTheDocument()
    expect(within(dach).queryByText('0')).not.toBeInTheDocument()
  })

  it('distinguishes a real zero DACH from unknown', () => {
    renderCard([fact({ value: { ...trial, dach_recruiting: 0 } })])
    const dach = screen.getByTestId('trial-dach')
    expect(within(dach).getByText('0')).toBeInTheDocument()
    expect(within(dach).queryByText(/unknown/i)).not.toBeInTheDocument()
  })
})
