import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { MechanismsFact } from './MechanismsFact'

function fact(source: string, value: unknown, status: SourcedFact['status'] = 'ok'): SourcedFact {
  return {
    value,
    status,
    source,
    source_url: `https://example/${source}`,
    retrieved_at: '2026-07-20T00:00:00Z',
    error: null,
    confidence: null,
  }
}

const CHEMBL = ['Stem cell growth factor receptor inhibitor', 'PDGFR inhibitor', 'VEGFR inhibitor']
const OT = ['VEGFR inhibitor', 'PDGFR inhibitor', 'Stem cell growth factor receptor inhibitor']

describe('MechanismsFact', () => {
  it('renders one deduped row per mechanism, not the list repeated per source', () => {
    render(<MechanismsFact facts={[fact('chembl', CHEMBL), fact('opentargets', OT)]} />)
    const rows = within(screen.getByTestId('mechanisms')).getAllByRole('listitem')
    expect(rows).toHaveLength(3) // three distinct mechanisms, not six
    // Each mechanism keeps both sources' provenance chips (the sources agree).
    for (const row of rows) {
      expect(within(row).getAllByTestId('source-info')).toHaveLength(2)
    }
  })

  it('renders an outage as an amber chip, never "none annotated"', () => {
    render(<MechanismsFact facts={[fact('chembl', null, 'source_failed')]} />)
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('mechanisms')).not.toBeInTheDocument()
    expect(screen.queryByText(/none annotated/i)).not.toBeInTheDocument()
  })

  it('still shows the mechanisms when one source failed and another answered', () => {
    render(<MechanismsFact facts={[fact('chembl', null, 'source_failed'), fact('opentargets', OT)]} />)
    const rows = within(screen.getByTestId('mechanisms')).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
  })

  it('renders a real empty as "None annotated", with a citation', () => {
    render(<MechanismsFact facts={[fact('chembl', [], 'empty')]} />)
    expect(screen.getByTestId('fact-empty')).toHaveTextContent(/none annotated/i)
    expect(screen.queryByTestId('mechanisms')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    render(
      <BriefStateProvider value="enriching">
        <MechanismsFact facts={undefined} />
      </BriefStateProvider>,
    )
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
