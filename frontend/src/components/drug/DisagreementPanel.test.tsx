import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Disagreement } from '../../api/types'
import { DisagreementPanel } from './DisagreementPanel'

const phase: Disagreement = {
  label: 'Clinical phase',
  block: 'clinical',
  values: [
    { source: 'clinicaltrials', display: 'phase 3', source_url: 'https://clinicaltrials.gov' },
    { source: 'opentargets', display: 'phase 2', source_url: 'https://platform.opentargets.org' },
  ],
}

describe('DisagreementPanel', () => {
  it('renders nothing when there is no conflict (agreement is silent)', () => {
    const { container } = render(<DisagreementPanel disagreements={[]} />)
    expect(container).toBeEmptyDOMElement()
    const { container: c2 } = render(<DisagreementPanel disagreements={undefined} />)
    expect(c2).toBeEmptyDOMElement()
  })

  it('names the conflict and keeps every source and its value visible', () => {
    render(<DisagreementPanel disagreements={[phase]} />)
    const row = screen.getByTestId('disagreement')
    // Both sources, in their reader-facing names, each with its own value -- none silently wins.
    expect(row).toHaveTextContent('ClinicalTrials.gov says phase 3')
    expect(row).toHaveTextContent('Open Targets says phase 2')
  })

  it('links the label to its block and each source to its url', () => {
    render(<DisagreementPanel disagreements={[phase]} />)
    const row = screen.getByTestId('disagreement')
    expect(within(row).getByRole('link', { name: 'Clinical phase' })).toHaveAttribute(
      'href',
      '#clinical',
    )
    expect(within(row).getByRole('link', { name: 'ClinicalTrials.gov' })).toHaveAttribute(
      'href',
      'https://clinicaltrials.gov',
    )
  })

  it('shows a source without a url as plain text, never a dead link', () => {
    const noUrl: Disagreement = {
      label: 'Clinical phase',
      block: 'clinical',
      values: [
        { source: 'chembl', display: 'phase 4', source_url: null },
        { source: 'opentargets', display: 'phase 2', source_url: 'https://platform.opentargets.org' },
      ],
    }
    render(<DisagreementPanel disagreements={[noUrl]} />)
    const row = screen.getByTestId('disagreement')
    expect(row).toHaveTextContent('ChEMBL says phase 4')
    expect(within(row).queryByRole('link', { name: 'ChEMBL' })).not.toBeInTheDocument()
  })
})
