import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../../api/types'
import { EpidemiologyCard } from './EpidemiologyCard'
import { BriefStateProvider } from '../ui/Fact'

/**
 * Block A shows age-standardised mortality (a rate, never a doughnut) as sorted per-country
 * bars with Switzerland highlighted, plus EU/CH headlines. An outage is amber, never an empty.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'eurostat',
    source_url: null,
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const EPI = {
  match_type: 'exact',
  source_code: 'C33_C34',
  source_label: 'Trachea, bronchus & lung (C33-C34)',
  year: 2023,
  unit: 'per 100 000, age-standardised',
  eu_asr: 46.65,
  ch_asr: 34.77,
  total_deaths: 229920,
  by_country: [
    { geo: 'HU', country: 'Hungary', asr: 80.07 },
    { geo: 'DE', country: 'Germany', asr: 40.0 },
    { geo: 'CH', country: 'Switzerland', asr: 34.77 },
  ],
}

function renderCard(facts: SourcedFact[] | undefined, state = 'ready') {
  return render(
    <BriefStateProvider value={state as 'ready' | 'enriching' | 'not_analyzed'}>
      <EpidemiologyCard facts={facts} cancerName="lung cancer" />
    </BriefStateProvider>,
  )
}

describe('EpidemiologyCard', () => {
  it('renders sorted per-country ASR bars, the EU/CH headlines and the deaths figure', () => {
    renderCard([fact({ value: EPI })])
    const barsEl = screen.getByTestId('epi-bars')
    const bars = screen.getAllByTestId('epi-bar')
    expect(bars).toHaveLength(3)
    // Sorted highest first (Hungary 80 > Germany 40 > Switzerland 34.77).
    expect(within(bars[0]).getByText('Hungary')).toBeInTheDocument()
    // Headlines carry the EU ASR and the en-US-formatted EU deaths (both unique to the header).
    expect(screen.getByText('46.65')).toBeInTheDocument()
    expect(screen.getByText('229,920')).toBeInTheDocument()
    // Switzerland is highlighted (accent) in the bars, the others are not -- the Swiss angle.
    expect(within(barsEl).getByText('Switzerland').className).toMatch(/text-accent/)
    expect(within(barsEl).getByText('Germany').className).not.toMatch(/text-accent/)
  })

  it('renders an Open Targets/Eurostat outage as an amber chip, never an empty', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'down' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('epi-bars')).not.toBeInTheDocument()
  })

  it('renders unmapped as "not available for this cancer"', () => {
    renderCard([fact({ value: { match_type: 'unmapped' } })])
    expect(screen.getByTestId('not-applicable')).toHaveTextContent(/not available for lung cancer/i)
    expect(screen.queryByTestId('epi-bars')).not.toBeInTheDocument()
  })

  it('names the broader entity when the figures are a rollup', () => {
    renderCard([fact({ value: { ...EPI, match_type: 'rollup' } })])
    expect(screen.getByTestId('rollup-note')).toHaveTextContent(/broader than lung cancer/)
    expect(screen.getByTestId('epi-bars')).toBeInTheDocument()
  })
})
