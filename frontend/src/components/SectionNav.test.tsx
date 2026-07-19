import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CancerSection } from '../pages/cancerSections'
import { SectionNav } from './SectionNav'

const SECTIONS: CancerSection[] = [
  { id: 'pipeline', label: 'Pipeline', render: () => null },
  { id: 'target-landscape', label: 'Target landscape', render: () => null },
]

// A capturing IntersectionObserver: keep the callback so a test can fire an intersection by
// hand (jsdom never fires real ones). Replaces the no-op stub from setup.ts for this file.
let ioCallback: IntersectionObserverCallback | null = null
class CapturingIO {
  constructor(cb: IntersectionObserverCallback) {
    ioCallback = cb
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return []
  }
}

function fireIntersection(id: string) {
  act(() => {
    ioCallback?.(
      [
        {
          target: { id } as Element,
          isIntersecting: true,
          boundingClientRect: { top: 10 } as DOMRectReadOnly,
        } as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    )
  })
}

describe('SectionNav', () => {
  beforeEach(() => {
    ioCallback = null
    vi.stubGlobal('IntersectionObserver', CapturingIO)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('links every section by its anchor id, straight from the registry', () => {
    render(<SectionNav sections={SECTIONS} />)
    expect(screen.getByTestId('section-nav-pipeline')).toHaveAttribute('href', '#pipeline')
    expect(screen.getByTestId('section-nav-target-landscape')).toHaveAttribute(
      'href',
      '#target-landscape',
    )
  })

  it('marks only the section currently in view as current', () => {
    // The nav observes section elements that exist in the DOM, so render the anchor targets
    // alongside it (as the page does: the nav is a sibling of the Card <section>s).
    render(
      <>
        <SectionNav sections={SECTIONS} />
        <section id="pipeline" />
        <section id="target-landscape" />
      </>,
    )
    // Nothing is current until the scroll-spy fires.
    expect(screen.getByTestId('section-nav-pipeline')).not.toHaveAttribute('aria-current')

    fireIntersection('target-landscape')

    // The in-view section is current...
    expect(screen.getByTestId('section-nav-target-landscape')).toHaveAttribute(
      'aria-current',
      'location',
    )
    // ...and ONLY it. Hard-code aria-current to the first item, or ignore activeId, and this
    // goes red -- the assertion that keeps the spy honest.
    expect(screen.getByTestId('section-nav-pipeline')).not.toHaveAttribute('aria-current')
  })

  it('keeps the topmost in-view section current when a lower one also enters the band', () => {
    render(
      <>
        <SectionNav sections={SECTIONS} />
        <section id="pipeline" />
        <section id="target-landscape" />
      </>,
    )
    // Pipeline (topmost) enters the band and is current.
    fireIntersection('pipeline')
    expect(screen.getByTestId('section-nav-pipeline')).toHaveAttribute('aria-current', 'location')

    // Now the lower section enters -- and the observer reports ONLY it (pipeline's state did
    // not change this tick). Pipeline is still in view, so it must stay current. Keying off a
    // single callback's entries (the pre-fix bug) would flip to target-landscape here -> red.
    fireIntersection('target-landscape')
    expect(screen.getByTestId('section-nav-pipeline')).toHaveAttribute('aria-current', 'location')
    expect(screen.getByTestId('section-nav-target-landscape')).not.toHaveAttribute('aria-current')
  })
})
