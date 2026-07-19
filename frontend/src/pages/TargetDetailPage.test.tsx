import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import type { SourcedFact, TargetDetail } from '../api/types'
import { TargetDetailPage } from './TargetDetailPage'

/**
 * The target page is the cancer page run backwards: a stack of independently-loading,
 * error-isolated, anchored sections. The load-bearing behaviours -- a section outage is never
 * rendered as an empty, the associated cancers are live links into their briefs, and the
 * headline count is hidden (not shown as 0) until the target is enriched -- are tested here.
 */
vi.mock('../api/client', () => ({
  getTarget: vi.fn(),
  retryTarget: vi.fn(),
}))
const getTarget = vi.mocked(client.getTarget)

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'opentargets',
    source_url: null,
    retrieved_at: '2026-07-19T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

function detail(over: Partial<TargetDetail> = {}): TargetDetail {
  return {
    ensembl_id: 'ENSG00000146648',
    symbol: 'EGFR',
    name: 'epidermal growth factor receptor',
    n_cancers: 2,
    last_enriched_at: null,
    state: 'ready',
    refreshing: false,
    facts: {},
    unavailable: [],
    catalog_drugs: [],
    ...over,
  }
}

const associatedCancers = {
  n_cancers: 2,
  cancers: [
    { disease_id: 'MONDO_0005233', name: 'non-small cell lung carcinoma', score: 0.85 },
    { disease_id: 'MONDO_0007254', name: 'breast carcinoma', score: 0.7 },
  ],
}

function renderPage(entry = '/targets/ENSG00000146648') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/targets/:ensemblId" element={<TargetDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('TargetDetailPage', () => {
  beforeEach(() => getTarget.mockReset())

  it('renders the target header and the associated cancers as live links into their briefs', async () => {
    getTarget.mockResolvedValue(
      detail({ facts: { associated_cancers: [fact({ value: associatedCancers })] } }),
    )
    renderPage()

    expect(await screen.findByRole('heading', { level: 1, name: 'EGFR' })).toBeInTheDocument()
    expect(screen.getByText(/epidermal growth factor receptor/)).toBeInTheDocument()

    const link = screen.getByRole('link', { name: /non-small cell lung carcinoma/i })
    expect(link).toHaveAttribute('href', '/cancers/MONDO_0005233')
    expect(screen.getByTestId('associated-cancers')).toBeInTheDocument()
    // The headline count is shown once enriched.
    expect(screen.getByTestId('target-stats')).toHaveTextContent('2')
  })

  it('renders a source outage as the amber chip, never as "no associated cancers"', async () => {
    getTarget.mockResolvedValue(
      detail({
        state: 'ready',
        unavailable: ['associated_cancers'],
        facts: {
          associated_cancers: [fact({ status: 'source_failed', source: 'Open Targets', error: '503' })],
        },
      }),
    )
    renderPage()

    expect(await screen.findByTestId('fact-source-failed')).toBeInTheDocument()
    // The founding bug, guarded: an outage must not read as "this target drives no cancers".
    expect(screen.queryByText(/no associated cancers/i)).not.toBeInTheDocument()
  })

  it('renders a measured empty as "no associated cancers in the catalog"', async () => {
    getTarget.mockResolvedValue(
      detail({ facts: { associated_cancers: [fact({ value: {}, status: 'empty' })] } }),
    )
    renderPage()
    expect(await screen.findByText(/no associated cancers in the catalog/i)).toBeInTheDocument()
  })

  it('hides the associated-cancers count until the target is enriched (null, not 0)', async () => {
    // A never-enriched target: n_cancers is null. The headline stat must be absent, not "0" --
    // "not yet measured" is not "measured, zero".
    getTarget.mockResolvedValue(detail({ state: 'enriching', n_cancers: null, facts: {} }))
    renderPage()
    await screen.findByRole('heading', { level: 1, name: 'EGFR' })
    expect(screen.queryByTestId('target-stats')).not.toBeInTheDocument()
  })

  it('links the catalog drugs against the target into their briefs', async () => {
    getTarget.mockResolvedValue(
      detail({ catalog_drugs: ['CHEMBL3353410'], facts: { associated_cancers: [fact({ value: associatedCancers })] } }),
    )
    renderPage()
    const drugLink = await screen.findByTestId('catalog-drug-link')
    expect(drugLink).toHaveAttribute('href', '/drugs/CHEMBL3353410')
  })

  it('says a missing catalog drug is a gap, not "undruggable"', async () => {
    // catalog_drugs is empty: the honest message is "a gap in our catalog", never a claim that
    // the target cannot be drugged (the world's answer is not ours to give here).
    getTarget.mockResolvedValue(detail({ catalog_drugs: [] }))
    renderPage()
    await screen.findByRole('heading', { level: 1, name: 'EGFR' })
    expect(screen.getByText(/No drug in our catalog acts on this target/i)).toBeInTheDocument()
    expect(screen.queryByTestId('catalog-drug-link')).not.toBeInTheDocument()
  })

  it('scrolls to the section named in the URL hash once the page has loaded', async () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      value: scrollIntoView,
      writable: true,
      configurable: true,
    })
    getTarget.mockResolvedValue(
      detail({ facts: { associated_cancers: [fact({ value: associatedCancers })] } }),
    )
    renderPage('/targets/ENSG00000146648#associated-cancers')

    await screen.findByRole('heading', { level: 1 })
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled())
  })

  it('honours the hash once, not again on every poll re-render', async () => {
    vi.useFakeTimers()
    try {
      const scrollIntoView = vi.fn()
      Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
        value: scrollIntoView,
        writable: true,
        configurable: true,
      })
      // Enriching -> the page polls every 2s. A FRESH object each call (mockImplementation) is
      // what a real poll returns; its new identity re-runs the [hash, detail] effect -- exactly
      // the condition the scrolledForHash ref must absorb without re-scrolling.
      getTarget.mockImplementation(async () =>
        detail({
          state: 'enriching',
          n_cancers: null,
          facts: { associated_cancers: [fact({ value: associatedCancers })] },
        }),
      )
      renderPage('/targets/ENSG00000146648#associated-cancers')

      await act(async () => {}) // flush the initial getTarget + the scroll effect
      expect(scrollIntoView).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000) // one poll cycle -> a re-render with fresh detail
      })
      // The ref guard: the reader is scrolled once and then left where they are. Remove the ref
      // (scroll on every effect run) and this becomes 2+ -> red.
      expect(scrollIntoView).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
