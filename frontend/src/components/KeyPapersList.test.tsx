import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { KeyPaper } from '../api/types'
import { KeyPapersList } from './KeyPapersList'

describe('KeyPapersList', () => {
  it('badges the publication type and labels an un-indexed paper, ranked not sunk (#42)', () => {
    const papers: KeyPaper[] = [
      {
        title: 'A pivotal trial',
        pmid: '1',
        publication_type: 'Randomized Controlled Trial',
        indexed: true,
      },
      { title: 'A fresh paper', pmid: '2', publication_type: null, indexed: false },
    ]
    render(<KeyPapersList items={papers} ranked total={40} />)
    const rows = screen.getAllByRole('listitem')
    // The RCT carries its evidence-type badge; the un-indexed paper carries none.
    expect(within(rows[0]).getByTestId('paper-pubtype')).toHaveTextContent(
      'Randomized Controlled Trial',
    )
    expect(within(rows[0]).queryByTestId('paper-unindexed')).not.toBeInTheDocument()
    // The un-indexed paper is LABELLED (not sunk: it is still shown, in the leader's list).
    expect(within(rows[1]).getByTestId('paper-unindexed')).toHaveTextContent('not yet indexed')
    expect(within(rows[1]).queryByTestId('paper-pubtype')).not.toBeInTheDocument()
    expect(screen.getByText(/most relevant/)).toHaveTextContent('of 40')
  })

  it('renders the plain-string fallback (sample_titles) with no badges, and "most recent"', () => {
    render(<KeyPapersList items={['Recent paper one', 'Recent paper two']} ranked={false} total={2} />)
    expect(screen.getByText('Recent paper one')).toBeInTheDocument()
    expect(screen.queryByTestId('paper-pubtype')).not.toBeInTheDocument()
    expect(screen.queryByTestId('paper-unindexed')).not.toBeInTheDocument()
    expect(screen.getByText(/most recent/)).toBeInTheDocument()
  })
})
