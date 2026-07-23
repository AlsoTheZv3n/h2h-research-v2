import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Epidemiology, SourcedFact } from '../../api/types'
import { ResolvedSection } from './ResolvedSection'

/**
 * The match-type layer is where the Gate-1 distinction reaches the reader: unmapped is its own
 * "not available" answer (never rendered as empty), and a rollup must NAME the broader entity so
 * its figures are never passed off as the specific cancer's.
 */

function fact(value: unknown, status: SourcedFact['status'] = 'ok'): SourcedFact {
  return {
    value,
    status,
    source: 'eurostat',
    source_url: null,
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
  }
}

function renderSection(f: SourcedFact, body = (v: Epidemiology) => <div data-testid="data">{v.year}</div>) {
  return render(
    <ResolvedSection<Epidemiology> fact={f} cancerName="NSCLC" emptyLabel="no figures">
      {body}
    </ResolvedSection>,
  )
}

describe('ResolvedSection', () => {
  it('renders unmapped as "not available for this cancer", never the data', () => {
    const body = vi.fn(() => <div data-testid="data" />)
    renderSection(fact({ match_type: 'unmapped' }), body)
    expect(screen.getByTestId('not-applicable')).toHaveTextContent(/not available for NSCLC/i)
    // The data body is never invoked for an unmapped fact.
    expect(body).not.toHaveBeenCalled()
  })

  it('names the broader entity for a rollup, then renders the data', () => {
    renderSection(fact({ match_type: 'rollup', source_label: 'lung cancer', year: 2023 }))
    const note = screen.getByTestId('rollup-note')
    // The load-bearing line: the broader entity is named AND framed as broader than the cancer.
    expect(note).toHaveTextContent(/lung cancer/)
    expect(note).toHaveTextContent(/broader than NSCLC/)
    expect(screen.getByTestId('data')).toBeInTheDocument()
  })

  it('renders an exact match as just the data, with no broader-than banner', () => {
    renderSection(fact({ match_type: 'exact', year: 2023 }))
    expect(screen.queryByTestId('rollup-note')).not.toBeInTheDocument()
    expect(screen.getByTestId('data')).toHaveTextContent('2023')
  })

  it('renders a measured empty as the empty label', () => {
    renderSection(fact(null, 'empty'))
    expect(screen.getByTestId('fact-empty')).toHaveTextContent('no figures')
    expect(screen.queryByTestId('data')).not.toBeInTheDocument()
  })
})
