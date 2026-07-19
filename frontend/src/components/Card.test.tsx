import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Card } from './Card'

/**
 * Card gained one Block-C responsibility: be an anchor target. The id must land on the real
 * <section> -- that element is what the section nav links to (#pipeline) and what the page's
 * hash effect scrolls to. If the id does not reach the section, the whole anchor mechanism is
 * silently dead, so this is the test that guards it.
 */
describe('Card', () => {
  it('puts the anchor id on its section element', () => {
    const { container } = render(
      <Card id="pipeline" title="Pipeline">
        body
      </Card>,
    )
    // Drop id={id} from the <section> in Card and this query returns null -> red.
    expect(container.querySelector('section#pipeline')).not.toBeNull()
  })

  it('emits no id when none is given, so non-section cards stay anchor-free', () => {
    const { container } = render(<Card title="Structure">body</Card>)
    expect(container.querySelector('section')?.id).toBe('')
  })
})
