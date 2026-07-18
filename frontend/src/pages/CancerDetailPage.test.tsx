import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TargetsStat } from './CancerDetailPage'

/**
 * The associated-targets stat is R3's whole point: the headline is the count of STRONG
 * associations, and that number must never be shown without the score threshold beside it
 * -- a bare "142 associated targets" is exactly the misleading whole-genome figure the
 * refinement replaced. The threshold-label test is load-bearing: it goes red the moment the
 * strong count is rendered without its threshold.
 */
describe('TargetsStat', () => {
  it('shows the strong count with its threshold and the total as a qualified sub-line', () => {
    render(<TargetsStat strong={142} threshold={0.5} total={17064} />)
    const stat = screen.getByTestId('targets-stat')
    // The strong count is the headline.
    expect(stat).toHaveTextContent('142')
    // ...and it never travels without the threshold: this is the assertion that fails if
    // the number is ever shown bare.
    expect(stat).toHaveTextContent(/score ≥ 0\.5/)
    // The raw total is present, but only ever framed as "with any evidence".
    expect(stat).toHaveTextContent(/17,064 with any evidence/)
  })

  it('never renders the raw total without a qualifier, even before the fact is ready', () => {
    // Enriching / outage: no threshold yet. The fallback shows the total, still labelled
    // "with any evidence" -- honest about what it is -- and never a bare "score ≥".
    render(<TargetsStat total={17064} />)
    const stat = screen.getByTestId('targets-stat')
    expect(stat).toHaveTextContent('17,064')
    expect(stat).toHaveTextContent(/with any evidence/)
    expect(stat).not.toHaveTextContent(/score ≥/)
  })
})
