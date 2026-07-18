import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { App } from './App'

/**
 * The nav's one job with two entities: mark the catalog you are in -- including on a
 * detail page, where the active tab is the only thing telling you which catalog a
 * drug or cancer belongs to. Computed from the path, not NavLink's exact match, so
 * these assert that a detail route keeps its parent tab lit.
 */

function at(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App nav', () => {
  it('marks Drugs active on the drug overview', () => {
    at('/')
    expect(screen.getByTestId('nav-drugs')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('nav-cancers')).not.toHaveAttribute('aria-current')
  })

  it('keeps Drugs active on a drug detail page', () => {
    at('/drugs/CHEMBL123')
    expect(screen.getByTestId('nav-drugs')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('nav-cancers')).not.toHaveAttribute('aria-current')
  })

  it('marks Cancers active on the cancer catalog', () => {
    at('/cancers')
    expect(screen.getByTestId('nav-cancers')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('nav-drugs')).not.toHaveAttribute('aria-current')
  })

  it('keeps Cancers active on a cancer detail page', () => {
    at('/cancers/MONDO_0005233')
    expect(screen.getByTestId('nav-cancers')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('nav-drugs')).not.toHaveAttribute('aria-current')
  })
})
