import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { BriefState, SourcedFact } from '../api/types'
import { BriefStateProvider, Fact } from './Fact'

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
    expect(screen.getByTestId('fact-not-collected')).toBeInTheDocument()
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

describe('the four states', () => {
  /**
   * The distinction this whole project keeps having to re-establish at each new
   * layer. Four absences that mean four different things:
   *
   *   not_analyzed / enriching  we have not looked
   *   source_failed             we looked, the source fell over
   *   empty                     we looked, there is nothing
   *   ok                        here it is
   *
   * Any two of these rendering identically is a defect, not a style choice.
   */
  it('an absent fact reads as "waiting" while the brief is still enriching', () => {
    render(
      <BriefStateProvider value="enriching">
        <Fact label="Mechanism" facts={undefined} emptyLabel="No mechanism annotated" />
      </BriefStateProvider>,
    )

    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
    // Not a finding about the drug -- we have not asked yet.
    expect(screen.queryByText('No mechanism annotated')).not.toBeInTheDocument()
    expect(screen.queryByTestId('fact-not-collected')).not.toBeInTheDocument()
  })

  it('the same absence reads as "not collected" once the brief is ready', () => {
    render(
      <BriefStateProvider value="ready">
        <Fact label="Mechanism" facts={undefined} />
      </BriefStateProvider>,
    )

    expect(screen.getByTestId('fact-not-collected')).toBeInTheDocument()
    expect(screen.queryByTestId('fact-pending')).not.toBeInTheDocument()
  })

  it('a not-yet-analyzed brief never renders as source_failed', () => {
    render(
      <BriefStateProvider value="not_analyzed">
        <Fact label="Mechanism" facts={undefined} />
      </BriefStateProvider>,
    )

    // "We have not looked" must not be dressed up as "the source is broken".
    expect(screen.queryByTestId('fact-source-failed')).not.toBeInTheDocument()
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })

  it('all four render distinctly', () => {
    const rendered = new Set<string>()

    const cases: Array<[BriefState, SourcedFact[] | undefined]> = [
      ['enriching', undefined],
      ['ready', undefined],
      ['ready', [fact({ value: 0, status: 'empty' })]],
      ['ready', [fact({ value: null, status: 'source_failed' })]],
      ['ready', [fact({ value: 42 })]],
    ]

    for (const [state, facts] of cases) {
      const { container, unmount } = render(
        <BriefStateProvider value={state}>
          <Fact label="X" facts={facts} emptyLabel="None found" />
        </BriefStateProvider>,
      )
      rendered.add(container.textContent ?? '')
      unmount()
    }

    // Five renders, five different sentences. A collision here means two different
    // truths look the same to a reader.
    expect(rendered.size).toBe(5)
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
