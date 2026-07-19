import { useEffect, useState } from 'react'
import type { CancerSection } from '../pages/cancerSections'

/**
 * In-page navigation for the detail sections.
 *
 * Each link is a native `#anchor` jump (the Card carries the id + a scroll-mt so the title
 * clears the nav); an IntersectionObserver lights the section currently in view. The active
 * section is reflected ONLY through aria-current + styling -- it is never written back into
 * the URL, which would spam history and fight the router's own hash handling. Deep-linking
 * (arriving at /cancers/x#pipeline) is the page's job, not this component's.
 */
export function SectionNav({ sections }: { sections: CancerSection[] }) {
  const [activeId, setActiveId] = useState('')

  useEffect(() => {
    const els = sections
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => el !== null)
    if (els.length === 0) return

    // An IntersectionObserver reports only the sections whose state CHANGED in a tick, so
    // keying the active section off a single callback's entries forgets sections still in view.
    // This map keeps every observed section's intersecting state for the observer's lifetime;
    // the active section is derived from the whole set each tick: the topmost (first in
    // registry / document order) section currently in the band.
    const inBand = new Map<string, boolean>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) inBand.set(e.target.id, e.isIntersecting)
        const topmost = sections.find((s) => inBand.get(s.id))
        if (topmost) setActiveId(topmost.id)
      },
      // "Active" = a section whose top sits in the upper fifth of the viewport, so the nav
      // tracks reading position rather than flipping on the slightest edge.
      { rootMargin: '-20% 0px -70% 0px' },
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [sections])

  return (
    <nav aria-label="Sections" className="mb-4 lg:sticky lg:top-4 lg:mb-0 lg:self-start">
      <ul className="flex flex-wrap gap-1 lg:flex-col lg:gap-0.5">
        {sections.map((s) => {
          const active = s.id === activeId
          return (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                aria-current={active ? 'location' : undefined}
                data-testid={`section-nav-${s.id}`}
                className={`block rounded-md px-2 py-1 text-xs transition-colors ${
                  active
                    ? 'bg-accent-bg font-medium text-accent'
                    : 'text-ink-muted hover:text-accent'
                }`}
              >
                {s.label}
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
