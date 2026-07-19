import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// jsdom ships no IntersectionObserver, and the section scroll-spy (SectionNav) constructs one
// on mount. This no-op stub keeps any page that renders the nav from crashing; a test that
// wants to drive the spy replaces the global with its own capturing stub (see
// SectionNav.test.tsx). Kept deliberately loose -- it only needs the shape SectionNav calls.
class IntersectionObserverStub {
  constructor(_cb: IntersectionObserverCallback) {}
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return []
  }
}
vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
