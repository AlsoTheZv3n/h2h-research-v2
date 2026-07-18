import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { PipelineCard } from './PipelineCard'

/**
 * The load-bearing behaviour: a pipeline drug links to its brief only when the catalog
 * holds it, matched by exact ChEMBL id -- never by name (the weave's hard rule). And an
 * outage is never rendered as an empty pipeline.
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

const pipeline = {
  total: 2,
  by_phase: [
    {
      stage: 'APPROVAL',
      count: 2,
      drugs: [
        { chembl_id: 'CHEMBL_IN', name: 'Osimertinib' },
        { chembl_id: 'CHEMBL_OUT', name: 'External Drug' },
      ],
    },
  ],
}

function renderCard(facts: SourcedFact[] | undefined, catalogDrugIds: string[] = [], state = 'ready') {
  return render(
    <MemoryRouter>
      <BriefStateProvider value={state as 'ready' | 'enriching' | 'not_analyzed'}>
        <PipelineCard facts={facts} catalogDrugIds={catalogDrugIds} />
      </BriefStateProvider>
    </MemoryRouter>,
  )
}

describe('PipelineCard', () => {
  it('links only the drugs the catalog holds, and shows the rest as plain text', () => {
    renderCard([fact({ value: pipeline })], ['CHEMBL_IN'])
    expect(screen.getByTestId('pipeline')).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
    // In the catalog: a link to the brief, by exact ChEMBL id.
    expect(screen.getByRole('link', { name: 'Osimertinib' })).toHaveAttribute(
      'href',
      '/drugs/CHEMBL_IN',
    )
    // Not in the catalog: shown, but never a (dead) link.
    expect(screen.getByText('External Drug')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'External Drug' })).not.toBeInTheDocument()
  })

  it('renders an outage as an unavailable chip, never "no programmes"', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'boom' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByText(/no drug programmes/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('pipeline')).not.toBeInTheDocument()
  })

  it('renders a real empty as "no drug programmes"', () => {
    renderCard([fact({ value: {}, status: 'empty' })])
    expect(screen.getByText(/no drug programmes/i)).toBeInTheDocument()
    expect(screen.queryByTestId('pipeline')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    renderCard(undefined, [], 'enriching')
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
