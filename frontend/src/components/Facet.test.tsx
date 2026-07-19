import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FacetCount } from '../api/types'
import { Facet } from './Facet'

function renderFacet(counts?: FacetCount[]) {
  return render(
    <Facet
      name="Modality"
      placeholder="Modality"
      value=""
      onChange={() => {}}
      options={[
        ['Small molecule', 'Small molecule'],
        ['Antibody', 'Antibody'],
      ]}
      counts={counts}
    />,
  )
}

describe('Facet', () => {
  it('shows a per-option count when the server returned one', () => {
    renderFacet([
      { value: 'Small molecule', count: 2190 },
      { value: 'Antibody', count: 519 },
    ])
    expect(screen.getByRole('option', { name: 'Small molecule (2190)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Antibody (519)' })).toBeInTheDocument()
  })

  it('shows a plain label for an option with no count (0 under the current filters)', () => {
    // The facets endpoint omits options that match nothing given the other filters, so an
    // absent count reads as a plain label -- not "(0)" invented on the client.
    renderFacet([{ value: 'Small molecule', count: 3 }])
    expect(screen.getByRole('option', { name: 'Small molecule (3)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Antibody' })).toBeInTheDocument()
  })

  it('shows plain labels when no counts are provided at all', () => {
    renderFacet(undefined)
    expect(screen.getByRole('option', { name: 'Small molecule' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Antibody' })).toBeInTheDocument()
  })

  it('keeps the placeholder option (which clears the facet) count-less', () => {
    renderFacet([{ value: 'Small molecule', count: 2 }])
    expect(screen.getByRole('option', { name: 'Modality' })).toHaveValue('')
  })
})
