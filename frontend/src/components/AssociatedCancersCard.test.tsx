import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { AssociatedCancersCard } from './AssociatedCancersCard'

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'opentargets',
    source_url: 'https://platform.opentargets.org/target/ENSG_E',
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

function renderCard(facts?: SourcedFact[]) {
  return render(
    <MemoryRouter>
      <AssociatedCancersCard facts={facts} />
    </MemoryRouter>,
  )
}

describe('AssociatedCancersCard', () => {
  it('is honest that the displayed list is a top slice when the count exceeds it', () => {
    // n_cancers (30) is over the displayed slice (2): the card must say "Top 2 of 30", so the
    // count is never read as the number of rows shown.
    const value = {
      n_cancers: 30,
      cancers: [
        { disease_id: 'MONDO_A', name: 'cancer A', score: 0.9 },
        { disease_id: 'MONDO_B', name: 'cancer B', score: 0.8 },
      ],
    }
    renderCard([fact({ value })])
    expect(screen.getByText(/Top 2 of 30 associated cancers/i)).toBeInTheDocument()
    expect(screen.getAllByTestId('associated-cancer-row')).toHaveLength(2)
  })

  it('does not show the "top N of M" note when the list is the whole set', () => {
    const value = {
      n_cancers: 1,
      cancers: [{ disease_id: 'MONDO_A', name: 'cancer A', score: 0.9 }],
    }
    renderCard([fact({ value })])
    expect(screen.queryByText(/Top 1 of/i)).not.toBeInTheDocument()
  })

  it('renders a measured empty as "no associated cancers in the catalog"', () => {
    renderCard([fact({ value: {}, status: 'empty' })])
    expect(screen.getByText(/no associated cancers in the catalog/i)).toBeInTheDocument()
  })

  it('renders an outage as the amber chip, never as an empty', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'boom' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByText(/no associated cancers/i)).not.toBeInTheDocument()
  })
})
