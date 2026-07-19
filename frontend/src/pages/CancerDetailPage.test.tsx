import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import type { CancerDetail, SourcedFact } from '../api/types'
import { CancerDetailPage, TargetsStat } from './CancerDetailPage'

/**
 * The associated-targets stat is R3's whole point: the headline is the count of STRONG
 * associations, and that number must never be shown without the score threshold beside it
 * -- a bare "142 associated targets" is exactly the misleading whole-genome figure the
 * refinement replaced. The threshold-label test is load-bearing: it goes red the moment the
 * strong count is rendered without its threshold.
 */
describe('TargetsStat', () => {
  it('shows the strong count with its threshold and the total as a qualified sub-line', () => {
    render(<TargetsStat strong={142} threshold={0.5} total={17064} />)
    const stat = screen.getByTestId('targets-stat')
    // The strong count is the headline.
    expect(stat).toHaveTextContent('142')
    // ...and it never travels without the threshold: this is the assertion that fails if
    // the number is ever shown bare.
    expect(stat).toHaveTextContent(/score ≥ 0\.5/)
    // The raw total is present, but only ever framed as "with any evidence".
    expect(stat).toHaveTextContent(/17,064 with any evidence/)
  })

  it('never renders the raw total without a qualifier, even before the fact is ready', () => {
    // Enriching / outage: no threshold yet. The fallback shows the total, still labelled
    // "with any evidence" -- honest about what it is -- and never a bare "score ≥".
    render(<TargetsStat total={17064} />)
    const stat = screen.getByTestId('targets-stat')
    expect(stat).toHaveTextContent('17,064')
    expect(stat).toHaveTextContent(/with any evidence/)
    expect(stat).not.toHaveTextContent(/score ≥/)
  })
})

/**
 * Block C: the page is a stack of independently-loading, error-isolated, anchored sections.
 * The load-bearing behaviours -- one slow section never blanks the page, a section outage is
 * never rendered as an empty, and a URL hash scrolls to its section -- are tested here at the
 * page level, above the individual cards.
 */
vi.mock('../api/client', () => ({
  getCancer: vi.fn(),
  retryCancer: vi.fn(),
}))
const getCancer = vi.mocked(client.getCancer)

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'opentargets',
    source_url: null,
    retrieved_at: '2026-07-18T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

function detail(over: Partial<CancerDetail> = {}): CancerDetail {
  return {
    disease_id: 'MONDO_0005233',
    name: 'lung carcinoma',
    therapeutic_area: 'respiratory disease',
    n_drugs: 10,
    n_targets: 100,
    last_enriched_at: null,
    state: 'ready',
    refreshing: false,
    facts: {},
    unavailable: [],
    catalog_drug_ids: [],
    target_catalog_drug: {},
    ...over,
  }
}

function renderPage(entry = '/cancers/MONDO_0005233') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/cancers/:diseaseId" element={<CancerDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CancerDetailPage sections', () => {
  beforeEach(() => getCancer.mockReset())

  it('loads sections independently: one shows data while another is still pending', async () => {
    const landscape = {
      threshold: 0.5,
      n_strong: 1,
      targets: [
        {
          symbol: 'EGFR',
          ensembl_id: 'ENSG_E',
          score: 0.9,
          evidence_types: [],
          sm_tractable: true,
          ab_tractable: false,
          drug_status: 'approved',
        },
      ],
    }
    // Brief still enriching: target_landscape has landed, pipeline has NOT.
    getCancer.mockResolvedValue(
      detail({ state: 'enriching', facts: { target_landscape: [fact({ value: landscape })] } }),
    )
    renderPage()

    // The target section renders its body...
    expect(await screen.findByTestId('target-landscape')).toBeInTheDocument()
    // ...while the pipeline section, whose fact is absent mid-enrichment, shows its own
    // pending state (not "not collected", and not blanked)...
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
    // ...and the page shell is present throughout: one slow section never blanks the page.
    expect(
      screen.getByRole('heading', { level: 1, name: /lung carcinoma/i }),
    ).toBeInTheDocument()
  })

  it('renders a section outage as the amber chip, never as an empty section', async () => {
    getCancer.mockResolvedValue(
      detail({
        state: 'ready',
        facts: { pipeline: [fact({ status: 'source_failed', source: 'Open Targets', error: '503' })] },
      }),
    )
    renderPage()

    expect(await screen.findByTestId('fact-source-failed')).toBeInTheDocument()
    // The founding bug, guarded at the page level: an outage must not read as "no programmes".
    expect(screen.queryByText(/no drug programmes/i)).not.toBeInTheDocument()
  })

  it('scrolls to the section named in the URL hash once the page has loaded', async () => {
    const scrollIntoView = vi.fn()
    // jsdom has no scrollIntoView; install one so the deep-link effect is observable.
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      value: scrollIntoView,
      writable: true,
      configurable: true,
    })
    getCancer.mockResolvedValue(detail({ state: 'ready' }))
    renderPage('/cancers/MONDO_0005233#pipeline')

    await screen.findByRole('heading', { level: 1 })
    // The pipeline Card <section id="pipeline"> is the scroll target the hash effect resolves.
    // Drop the useLocation().hash effect and this is never called -> red.
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
      // Enriching -> the page polls every 2s. A FRESH object each call (mockImplementation, not
      // mockResolvedValue) is what a real poll returns; its new identity re-runs the effect --
      // exactly the condition the scrolled-hash ref must absorb without re-scrolling.
      getCancer.mockImplementation(async () => detail({ state: 'enriching' }))
      renderPage('/cancers/MONDO_0005233#pipeline')

      await act(async () => {}) // flush the initial getCancer promise + the scroll effect
      expect(scrollIntoView).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000) // one poll cycle -> a re-render with fresh detail
      })
      // The ref guard: the reader is scrolled once and then left where they are. Remove the
      // ref (scroll on every effect run) and this becomes 2+ -> red.
      expect(scrollIntoView).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
