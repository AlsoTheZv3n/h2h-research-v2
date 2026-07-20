import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Combinations, SourcedFact } from '../api/types'
import { CombinationsCard } from './CombinationsCard'
import { BriefStateProvider } from './Fact'

/**
 * The card must never render a ClinicalTrials.gov outage as "no combinations" (the founding bug),
 * must keep combination and comparison visibly distinct (opposite meanings), and must footnote the
 * dropped-ambiguous count honestly rather than folding it into either bucket.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'clinicaltrials',
    source_url: 'https://clinicaltrials.gov/search?intr=focus',
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const combinations: Combinations = {
  n_total: 999,
  n_scanned: 300,
  n_multi_drug: 120,
  n_combination: 90,
  n_comparison: 22,
  n_ambiguous: 8,
  combination_examples: [{ nct_id: 'NCT_COMBO', drugs: ['focus', 'partner'] }],
  comparison_examples: [{ nct_id: 'NCT_COMPARE', drugs: ['focus', 'rival'] }],
}

describe('CombinationsCard', () => {
  it('shows the combination and comparison counts and both example lists, distinctly', () => {
    render(<CombinationsCard facts={[fact({ value: combinations })]} />)
    const summary = screen.getByTestId('combinations-summary')
    expect(summary).toHaveTextContent('90 combinations')
    expect(summary).toHaveTextContent('22 comparisons')

    // Combinations are drugs GIVEN TOGETHER (+), comparisons are drugs tested AGAINST (vs) --
    // the two must never render alike.
    const combo = screen.getByTestId('combination-examples')
    expect(combo).toHaveTextContent('NCT_COMBO')
    expect(combo).toHaveTextContent('focus + partner')
    const compare = screen.getByTestId('comparison-examples')
    expect(compare).toHaveTextContent('focus vs rival')
    // The NCT id links out to the trial record.
    expect(screen.getByText('NCT_COMBO')).toHaveAttribute(
      'href',
      'https://clinicaltrials.gov/study/NCT_COMBO',
    )
  })

  it('marks each example list as an excerpt of the total, so the sample is not read as the count', () => {
    // The harness finding: a reader answered "5 combinations" (the example rows) instead of the
    // summary total. Each list heading must state "N of TOTAL", tied to the summary count.
    render(<CombinationsCard facts={[fact({ value: combinations })]} />)
    // one example shown, 90 total combinations.
    expect(screen.getByTestId('combination-examples-heading')).toHaveTextContent(
      /Examples — 1 of 90 combinations/,
    )
    expect(screen.getByTestId('comparison-examples-heading')).toHaveTextContent(
      /Examples — 1 of 22 comparisons/,
    )
  })

  it('does not show an "of N" excerpt marker when all examples are shown (no "N of N")', () => {
    // The backend caps examples at 5; when the total is <= that, the list IS the count. The
    // heading must not read the silly "2 of 2 combinations" (a truncation marker with nothing
    // truncated), only when there are genuinely more than shown.
    const value = {
      ...combinations,
      n_combination: 2,
      combination_examples: [
        { nct_id: 'NCT_A', drugs: ['x', 'y'] },
        { nct_id: 'NCT_B', drugs: ['x', 'z'] },
      ],
    }
    render(<CombinationsCard facts={[fact({ value })]} />)
    const heading = screen.getByTestId('combination-examples-heading')
    expect(heading).not.toHaveTextContent(/of 2/)
    expect(heading).not.toHaveTextContent(/Examples/)
  })

  it('is honest about the scanned sample and the dropped-ambiguous count', () => {
    render(<CombinationsCard facts={[fact({ value: combinations })]} />)
    expect(screen.getByTestId('combinations-summary')).toHaveTextContent(/300 trials scanned/)
    expect(screen.getByTestId('combinations-summary')).toHaveTextContent(/of 999 total/)
    // The ~4% dropped are footnoted as excluded, not guessed -- never folded into a bucket.
    expect(screen.getByTestId('combinations-ambiguous')).toHaveTextContent(/8 further multi-drug/)
    expect(screen.getByTestId('combinations-ambiguous')).toHaveTextContent(/excluded — not guessed/)
  })

  it('does not footnote ambiguous when none were dropped', () => {
    render(<CombinationsCard facts={[fact({ value: { ...combinations, n_ambiguous: 0 } })]} />)
    expect(screen.queryByTestId('combinations-ambiguous')).not.toBeInTheDocument()
  })

  it('renders an outage as a calm unavailable chip, never "no combinations"', () => {
    render(<CombinationsCard facts={[fact({ value: null, status: 'source_failed', error: 'boom' })]} />)
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('combinations-summary')).not.toBeInTheDocument()
    expect(screen.queryByText(/No combination or comparison/i)).not.toBeInTheDocument()
  })

  it('renders a real empty as "none classified"', () => {
    render(<CombinationsCard facts={[fact({ value: null, status: 'empty' })]} />)
    expect(screen.getByText(/No combination or comparison could be classified/i)).toBeInTheDocument()
    expect(screen.queryByTestId('combinations-summary')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    render(
      <BriefStateProvider value="enriching">
        <CombinationsCard facts={undefined} />
      </BriefStateProvider>,
    )
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
