import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Card, NotApplicable } from './Card'

/**
 * Isolates one section so a render throw in it cannot blank the whole page.
 *
 * There is no other error boundary in the app, so today a single malformed fact shape --
 * a persisted value the wrong shape, an unexpected null -- would take down every section on
 * the page. Each registry section renders inside one of these; a throw degrades that section
 * to a NotApplicable box and leaves the rest intact.
 *
 * It degrades, it does not alarm: a render bug in our code is not a source outage, so this
 * uses the neutral NotApplicable box, never the amber/red an outage would earn. (Only a class
 * component can catch a render error -- hooks cannot -- so this is the app's one class.)
 */
export class SectionErrorBoundary extends Component<
  { id?: string; title: string; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the detail for the console; the reader sees only the degraded box.
    console.error(`Section "${this.props.title}" failed to render`, error, info)
  }

  render(): ReactNode {
    if (this.state.failed) {
      // Keep the section's anchor id on the degraded box: without it a crashed section drops
      // out of the DOM as an anchor target, so its nav link jumps nowhere, a deep-link never
      // scrolls to it, and the scroll-spy observes a detached node. A degrade must stay an
      // anchor, so the section a reader jumps to still exists even when it could not render.
      return (
        <Card id={this.props.id} title={this.props.title}>
          <NotApplicable reason="This section could not be displayed." />
        </Card>
      )
    }
    return this.props.children
  }
}
