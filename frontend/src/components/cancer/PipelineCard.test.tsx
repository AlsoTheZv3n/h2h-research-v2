import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../../api/types'
import { BriefStateProvider } from '../ui/Fact'
import { PipelineCard } from './PipelineCard'

/**
 * The pipeline card's jobs: a distribution + a filterable table (not a name wall), drugs
 * linked only when the catalog holds them (by exact ChEMBL id, never by name), and honest
 * states. The filter tests are load-bearing -- they go red if a filter becomes a no-op.
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
  total: 3,
  by_phase: [
    { stage: 'APPROVAL', count: 1 },
    { stage: 'PHASE_2', count: 2 },
  ],
  drugs: [
    { chembl_id: 'CHEMBL_IN', name: 'Osimertinib', stage: 'APPROVAL', modality: 'Small molecule', mechanism: 'EGFR inhibitor' },
    { chembl_id: 'CHEMBL_OUT', name: 'External Drug', stage: 'PHASE_2', modality: 'Antibody', mechanism: null },
    { chembl_id: 'CHEMBL_P2', name: 'Candidate X', stage: 'PHASE_2', modality: 'Small molecule', mechanism: 'KRAS inhibitor' },
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
  it('renders the distribution and a table with modality + mechanism, linking catalog drugs', () => {
    renderCard([fact({ value: pipeline })], ['CHEMBL_IN'])
    expect(screen.getByTestId('pipeline-distribution')).toBeInTheDocument()
    expect(screen.getByTestId('pipeline-table')).toBeInTheDocument()
    // The mechanism column carries the value, and a missing one renders honestly.
    expect(screen.getByText('EGFR inhibitor')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0) // External Drug has no mechanism
    // In the catalog -> a link by exact id; not in the catalog -> plain text.
    expect(screen.getByRole('link', { name: 'Osimertinib' })).toHaveAttribute('href', '/drugs/CHEMBL_IN')
    expect(screen.queryByRole('link', { name: 'External Drug' })).not.toBeInTheDocument()
    // The catalog ratio and the roll-up honesty note are both present.
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument()
    expect(screen.getByText(/roll-up/i)).toBeInTheDocument()
  })

  it('carries the modality census caveat, so a modality filter is not read as complete (#40)', () => {
    renderCard([fact({ value: pipeline })], ['CHEMBL_IN'])
    const note = screen.getByTestId('pipeline-modality-note')
    // The load-bearing honesty: the filter reflects the catalog, and mRNA vaccines are absent/mistyped.
    expect(note.textContent).toMatch(/not a complete census/i)
    expect(note.textContent).toMatch(/mRNA/i)
  })

  it('the modality filter narrows the table', async () => {
    const user = userEvent.setup()
    renderCard([fact({ value: pipeline })], ['CHEMBL_IN'])
    expect(screen.getAllByTestId('pipeline-row')).toHaveLength(3)
    await user.selectOptions(screen.getByTestId('pipeline-filter-modality'), 'Antibody')
    const rows = screen.getAllByTestId('pipeline-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('External Drug')).toBeInTheDocument()
  })

  it('the "in catalog only" filter shows only drugs with a brief', async () => {
    const user = userEvent.setup()
    renderCard([fact({ value: pipeline })], ['CHEMBL_IN'])
    await user.click(screen.getByTestId('pipeline-filter-catalog'))
    const rows = screen.getAllByTestId('pipeline-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByRole('link', { name: 'Osimertinib' })).toBeInTheDocument()
  })

  it('renders an outage as an unavailable chip, never "no programmes"', () => {
    renderCard([fact({ value: null, status: 'source_failed', error: 'boom' })])
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByText(/no drug programmes/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('pipeline-table')).not.toBeInTheDocument()
  })

  it('renders a real empty as "no drug programmes"', () => {
    renderCard([fact({ value: {}, status: 'empty' })])
    expect(screen.getByText(/no drug programmes/i)).toBeInTheDocument()
    expect(screen.queryByTestId('pipeline-table')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    renderCard(undefined, [], 'enriching')
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
