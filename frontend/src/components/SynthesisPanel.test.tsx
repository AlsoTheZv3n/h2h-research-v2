import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SynthesisPanel } from './SynthesisPanel'

describe('SynthesisPanel', () => {
  it('renders each statement as a link to the block it came from', () => {
    render(
      <SynthesisPanel
        synthesis={[
          { text: '117 strongly-associated targets', block: 'target-landscape' },
          { text: 'Crowded field: 1,072 drugs in development', block: 'pipeline' },
        ]}
      />,
    )
    const links = screen.getAllByTestId('synthesis-statement')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveTextContent('117 strongly-associated targets')
    expect(links[0]).toHaveAttribute('href', '#target-landscape')
    expect(links[1]).toHaveAttribute('href', '#pipeline')
  })

  it('renders nothing when there is no synthesis (no panel of confident nothings)', () => {
    const { container } = render(<SynthesisPanel synthesis={[]} />)
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByTestId('synthesis')).not.toBeInTheDocument()
  })

  it('renders nothing when synthesis is absent (pre-C1 payload)', () => {
    const { container } = render(<SynthesisPanel synthesis={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })
})
