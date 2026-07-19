import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { BriefState, SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { FactGate } from './FactGate'

/**
 * FactGate is where the founding bug is now caught for every card at once: a failed source
 * must never reach the card body (which would render it as a measured empty), and an absent
 * fact must read as "waiting" while enriching, "not collected" once ready -- never the wrong
 * one. Prove each branch, and prove the body is NOT called on the two states the gate owns.
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: 1,
    status: 'ok',
    source: 'opentargets',
    source_url: null,
    retrieved_at: '2026-07-18T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

function renderGate(
  facts: SourcedFact[] | undefined,
  state: BriefState,
  children: (f: SourcedFact) => ReactNode = (f) => (
    <span data-testid="body">{String(f.value)}</span>
  ),
) {
  return render(
    <BriefStateProvider value={state}>
      <FactGate facts={facts}>{children}</FactGate>
    </BriefStateProvider>,
  )
}

describe('FactGate', () => {
  it('reads an absent fact as "waiting" while the brief is still enriching', () => {
    renderGate(undefined, 'enriching')
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
    expect(screen.queryByTestId('body')).not.toBeInTheDocument()
  })

  it('reads the same absence as "not collected" once the brief is ready', () => {
    renderGate(undefined, 'ready')
    expect(screen.getByTestId('fact-not-collected')).toBeInTheDocument()
    expect(screen.queryByTestId('fact-pending')).not.toBeInTheDocument()
  })

  it('renders a source_failed fact as the amber chip and never calls the body', () => {
    const body = vi.fn(() => <span data-testid="body" />)
    renderGate([fact({ status: 'source_failed', value: null, error: 'boom' })], 'ready', body)
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    // The load-bearing line: a failed source must not reach the card body, or it would be
    // rendered as an empty ("none found") -- the exact lie. Let it through and this goes red.
    expect(body).not.toHaveBeenCalled()
  })

  it('hands an ok fact to the body', () => {
    renderGate([fact({ value: 42 })], 'ready')
    expect(screen.getByTestId('body')).toHaveTextContent('42')
  })

  it('hands an empty fact to the body, which decides what empty means here', () => {
    const body = vi.fn((f: SourcedFact) => <span data-testid="body">{f.status}</span>)
    renderGate([fact({ value: null, status: 'empty' })], 'ready', body)
    expect(body).toHaveBeenCalled()
    expect(screen.getByTestId('body')).toHaveTextContent('empty')
  })
})
