import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../../api/types'
import { BriefStateProvider } from '../ui/Fact'
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

  it('shows the outage, not "None annotated", when one source FAILED and another was empty', () => {
    // The founding-bug trap: ChEMBL (the primary MoA source) is down, Open Targets measured empty.
    // Rendering "None annotated" would tell the reader mechanisms are definitively absent when the
    // main source was never asked. The failed source must still surface its amber chip.
    render(
      <MechanismsFact
        facts={[fact('chembl', null, 'source_failed'), fact('opentargets', [], 'empty')]}
      />,
    )
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByText(/none annotated/i)).not.toBeInTheDocument()
  })

  it('surfaces a partial outage: mechanisms from the source that answered PLUS the failed chip', () => {
    render(
      <MechanismsFact
        facts={[fact('chembl', null, 'source_failed'), fact('opentargets', ['EGFR inhibitor'])]}
      />,
    )
    // The mechanism the answering source gave is shown...
    expect(screen.getByTestId('mechanisms')).toHaveTextContent('EGFR inhibitor')
    // ...and the outage is not hidden by it.
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
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
