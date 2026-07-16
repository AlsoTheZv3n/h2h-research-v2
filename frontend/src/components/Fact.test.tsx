import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { Fact } from './Fact'

/**
 * The three states are the product. These tests are the last guard against the
 * defect this whole codebase is built to refuse: an outage rendered as "nothing
 * found", telling a reader a drug has no mechanism when the truth is ChEMBL was
 * down.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: 42,
    status: 'ok',
    source: 'chembl',
    source_url: 'https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL4535757/',
    retrieved_at: '2026-07-16T18:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

describe('Fact', () => {
  it('renders an ok value with its citation', () => {
    render(<Fact label="Molecular weight" facts={[fact({ value: 560.61 })]} />)

    expect(screen.getByText('560.61')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /source: chembl/i })).toBeInTheDocument()
  })

  it('renders empty as a measured negative, not a failure', () => {
    render(<Fact label="Trials" facts={[fact({ value: 0, status: 'empty' })]} emptyLabel="None registered" />)

    expect(screen.getByTestId('fact-empty')).toHaveTextContent('None registered')
    expect(screen.queryByTestId('fact-source-failed')).not.toBeInTheDocument()
  })

  it('renders source_failed as unavailable, never as empty', () => {
    render(
      <Fact
        label="Mechanism"
        facts={[fact({ value: null, status: 'source_failed', error: 'mechanism: 500' })]}
        emptyLabel="No mechanism annotated"
      />,
    )

    const failed = screen.getByTestId('fact-source-failed')
    expect(failed).toHaveTextContent(/chembl unavailable/i)
    // The whole point: an outage must not be worded as a finding about the drug.
    expect(screen.queryByText('No mechanism annotated')).not.toBeInTheDocument()
    expect(screen.queryByTestId('fact-empty')).not.toBeInTheDocument()
  })

  it('keeps the reason for a failure available', () => {
    render(<Fact label="Mechanism" facts={[fact({ value: null, status: 'source_failed', error: 'mechanism: 500 Internal Server Error' })]} />)

    expect(screen.getByTestId('fact-source-failed')).toHaveAttribute(
      'title',
      'mechanism: 500 Internal Server Error',
    )
  })

  it('distinguishes a zero from a failure', () => {
    // Both are "null-ish" on the wire. Only status tells them apart, and the reader
    // must see two different things.
    const { rerender } = render(<Fact label="Trials" facts={[fact({ value: 0, status: 'empty' })]} />)
    const zero = screen.getByTestId('fact-empty').textContent

    rerender(<Fact label="Trials" facts={[fact({ value: null, status: 'source_failed' })]} />)
    const failure = screen.getByTestId('fact-source-failed').textContent

    expect(zero).not.toEqual(failure)
  })

  it('says "not collected" when no source asserted the key at all', () => {
    render(<Fact label="Mechanism" facts={[]} />)
    expect(screen.getByText(/not collected/i)).toBeInTheDocument()
  })

  it('renders every source when they disagree', () => {
    render(
      <Fact
        label="Mechanism"
        facts={[
          fact({ value: 'KRas inhibitor', source: 'chembl' }),
          fact({ value: 'GTPase KRas inhibitor', source: 'opentargets' }),
        ]}
      />,
    )

    // Keeping both IS the evidence; picking one would be us deciding silently.
    expect(screen.getByText('KRas inhibitor')).toBeInTheDocument()
    expect(screen.getByText('GTPase KRas inhibitor')).toBeInTheDocument()
  })

  it('applies a custom renderer to ok values only', () => {
    render(
      <Fact
        label="Terminated"
        facts={[fact({ value: true })]}
        render={(v) => (v ? 'Yes' : 'No')}
      />,
    )
    expect(screen.getByText('Yes')).toBeInTheDocument()
  })
})

describe('CitationChip', () => {
  it('reveals provenance on hover', async () => {
    const user = userEvent.setup()
    render(<Fact label="MW" facts={[fact({ value: 560.61, confidence: 0.9 })]} />)

    const chip = screen.getByRole('button', { name: /source: chembl/i })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    await user.hover(chip)

    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent('Retrieved 2026-07-16')
    expect(tip).toHaveTextContent('Confidence 90%')
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      'https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL4535757/',
    )
  })

  it('opens on click too, for touch and keyboard', async () => {
    const user = userEvent.setup()
    render(<Fact label="MW" facts={[fact()]} />)

    await user.click(screen.getByRole('button', { name: /source: chembl/i }))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
  })

  it('omits confidence when the backend did not supply one', async () => {
    const user = userEvent.setup()
    render(<Fact label="MW" facts={[fact({ confidence: null })]} />)

    await user.hover(screen.getByRole('button', { name: /source: chembl/i }))
    expect(screen.getByRole('tooltip')).not.toHaveTextContent(/confidence/i)
  })
})
