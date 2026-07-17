import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Ask } from './Ask'
import type { Answer } from '../api/types'

/**
 * The five states, rendered distinctly. This is Fact.test.tsx's argument one layer
 * up: the backend spends real effort keeping "no model configured" apart from "the
 * model invented a citation", and a UI that renders both as a grey "something went
 * wrong" throws all of that away at the last inch.
 *
 * The client module is mocked here rather than the network, because these tests are
 * about rendering, not transport. The E2E suite asks the real API.
 */

vi.mock('../api/client', () => ({ askDrug: vi.fn() }))
const { askDrug } = await import('../api/client')
const mockAsk = vi.mocked(askDrug)

afterEach(() => vi.resetAllMocks())

function answer(over: Partial<Answer>): Answer {
  return { state: 'ok', text: '', citations: [], detail: null, ...over }
}

async function ask(question = 'Why does it stop working?') {
  render(<Ask chemblId="CHEMBL123" drugName="testinib" />)
  await userEvent.type(screen.getByTestId('ask-input'), question)
  await userEvent.click(screen.getByTestId('ask-submit'))
}

describe('a grounded answer', () => {
  it('shows the text and links every citation to PubMed', async () => {
    mockAsk.mockResolvedValue(
      answer({
        text: 'Resistance is driven by MUC1-C [PMID 37924972].',
        citations: [
          { pmid: '37924972', title: 'MUC1-C drives resistance', url: 'https://pubmed.ncbi.nlm.nih.gov/37924972/' },
        ],
      }),
    )

    await ask()

    expect(await screen.findByTestId('answer-ok')).toHaveTextContent('MUC1-C')
    const link = screen.getByTestId('answer-citation')
    expect(link).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/37924972/')
    // Opens out, never in: the citation's whole job is letting the reader check us.
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('shows no citation list when the answer cited nothing', async () => {
    // An answer drawn only from the structured facts cites no PMID, and inventing a
    // citation list for it would be the appearance of grounding rather than
    // grounding.
    mockAsk.mockResolvedValue(answer({ text: 'ChEMBL reports 383 trials.', citations: [] }))

    await ask()

    expect(await screen.findByTestId('answer-ok')).toBeVisible()
    expect(screen.queryByTestId('answer-citations')).not.toBeInTheDocument()
  })
})

describe('the states that are not an answer', () => {
  it('a withheld answer says so loudly, and never as a glitch', async () => {
    // The state this whole phase exists to be able to reach. If it renders as a
    // generic error the reader retries, gets a different answer, and never learns
    // the tool caught the model inventing a source -- which is the single most
    // useful thing it could have told them.
    mockAsk.mockResolvedValue(
      answer({
        state: 'ungrounded',
        detail: 'The answer was withheld: the model cited a source that was not in the retrieved evidence, which means it invented it.',
      }),
    )

    await ask()

    const notice = await screen.findByTestId('answer-ungrounded')
    expect(notice).toHaveTextContent(/withheld/i)
    expect(notice).toHaveTextContent(/invented/i)
    expect(screen.queryByTestId('answer-ok')).not.toBeInTheDocument()
  })

  it('an unconfigured model reads as a gap to close, not a failure', async () => {
    mockAsk.mockResolvedValue(
      answer({
        state: 'not_configured',
        detail: 'No language model is configured. Set ANTHROPIC_API_KEY, or point OLLAMA_URL at a local model.',
      }),
    )

    await ask()

    const notice = await screen.findByTestId('answer-not-configured')
    // Actionable, and specific enough to act on without reading the source.
    expect(notice).toHaveTextContent('ANTHROPIC_API_KEY')
  })

  it('a drug nobody has looked at says nothing was gathered, not "no answer"', async () => {
    mockAsk.mockResolvedValue(
      answer({ state: 'no_evidence', detail: 'Nothing has been gathered about testinib yet.' }),
    )

    await ask()

    expect(await screen.findByTestId('answer-no-evidence')).toHaveTextContent(/gathered/i)
  })

  it('a dead model reads as temporary', async () => {
    mockAsk.mockResolvedValue(answer({ state: 'unavailable', detail: 'the model API returned 503' }))

    await ask()

    expect(await screen.findByTestId('answer-unavailable')).toHaveTextContent(/try again/i)
  })

  it('the five states never render the same way as each other', async () => {
    // The guard against the whole file's premise quietly eroding: someone
    // consolidates two branches, both still pass their own test, and the
    // distinction is gone. Each state gets its own testid, and they must stay
    // distinct.
    const seen = new Set<string>()
    for (const state of ['ok', 'ungrounded', 'not_configured', 'no_evidence', 'unavailable'] as const) {
      mockAsk.mockResolvedValue(answer({ state, text: state === 'ok' ? 'An answer.' : '' }))
      const { unmount } = render(<Ask chemblId="CHEMBL123" drugName="t" />)
      await userEvent.type(screen.getByTestId('ask-input'), 'a question')
      await userEvent.click(screen.getByTestId('ask-submit'))
      const testId = `answer-${state.replace('_', '-')}`
      expect(await screen.findByTestId(testId)).toBeVisible()
      seen.add(testId)
      unmount()
      vi.resetAllMocks()
    }
    expect(seen.size).toBe(5)
  })
})

describe('the form itself', () => {
  it('refuses to ask nothing', async () => {
    render(<Ask chemblId="CHEMBL123" drugName="testinib" />)
    expect(screen.getByTestId('ask-submit')).toBeDisabled()

    await userEvent.type(screen.getByTestId('ask-input'), 'ab')
    expect(screen.getByTestId('ask-submit')).toBeDisabled()

    await userEvent.type(screen.getByTestId('ask-input'), 'c')
    expect(screen.getByTestId('ask-submit')).toBeEnabled()
  })

  it('says what it is doing while it waits', async () => {
    // Retrieval plus a model call is seconds, not milliseconds. A frozen button with
    // no explanation is how a working feature reads as broken.
    mockAsk.mockImplementation(() => new Promise(() => {}))

    await ask()

    expect(await screen.findByTestId('ask-pending')).toHaveTextContent(/literature/i)
  })

  it('a transport failure is kept apart from an API state', async () => {
    // The request never reached the server, so the API never got to have an opinion.
    // Faking this into `unavailable` would be inventing a state the backend never
    // reported.
    mockAsk.mockRejectedValue(new Error('network down'))

    await ask()

    expect(await screen.findByTestId('ask-transport-failed')).toBeVisible()
    expect(screen.queryByTestId('answer-unavailable')).not.toBeInTheDocument()
  })
})
