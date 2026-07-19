import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SectionErrorBoundary } from './SectionErrorBoundary'

/**
 * The boundary's whole job: a render throw in one section must not blank the page. Without it
 * (the app has no other error boundary) a single malformed fact shape takes down every
 * section. It must degrade to the neutral NotApplicable box -- not alarm like a source outage.
 */

function Boom(): never {
  throw new Error('render exploded')
}

describe('SectionErrorBoundary', () => {
  // React re-throws a caught render error to console.error; silence it so the run stays clean.
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}))
  afterEach(() => vi.restoreAllMocks())

  it('degrades a throwing section to a NotApplicable box instead of propagating the throw', () => {
    // If getDerivedStateFromError is neutered (returns failed:false), the throw escapes and
    // this render() itself throws -> the test errors out -> red.
    render(
      <SectionErrorBoundary title="Pipeline">
        <Boom />
      </SectionErrorBoundary>,
    )
    expect(screen.getByTestId('not-applicable')).toBeInTheDocument()
    // Degraded, not alarming, and still labelled with the section it stood in for.
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
  })

  it('keeps the section anchor id on the degraded box, so a crashed section stays reachable', () => {
    // The whole feature promises sections are anchor targets. A degrade must not silently drop
    // the anchor, or the nav link and deep-link to that section jump nowhere. Drop id={id} from
    // the fallback Card and this query is null -> red.
    const { container } = render(
      <SectionErrorBoundary id="pipeline" title="Pipeline">
        <Boom />
      </SectionErrorBoundary>,
    )
    expect(container.querySelector('section#pipeline')).not.toBeNull()
  })

  it('renders children untouched when they do not throw', () => {
    render(
      <SectionErrorBoundary title="Pipeline">
        <p data-testid="ok">fine</p>
      </SectionErrorBoundary>,
    )
    expect(screen.getByTestId('ok')).toBeInTheDocument()
    expect(screen.queryByTestId('not-applicable')).not.toBeInTheDocument()
  })
})
