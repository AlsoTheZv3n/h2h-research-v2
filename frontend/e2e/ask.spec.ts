import { expect, test } from '@playwright/test'

/**
 * The ask box, against the real API. No mocked facts endpoint, no mocked answer.
 *
 * What this can and cannot assert is worth being precise about, because getting it
 * wrong is how the suite ends up green and meaningless -- the mistake this project
 * has now made twice.
 *
 * A real model's *prose* is not testable: it is different every run, so any
 * assertion on it is either vacuous or flaky. What IS testable, and is the whole
 * product, is the contract around it: the request reaches the real backend, the
 * state that comes back is one the UI renders distinctly, and whichever state it is,
 * the reader is told which. That holds with or without a model configured -- and CI
 * has none, which makes not_configured the honest, deterministic path rather than a
 * reason to skip.
 */

const OSIMERTINIB = 'CHEMBL3353410'

/**
 * Playwright's 30s default is for pages, and a page is not what these wait on.
 * Answering means an embedding, a vector search and a model generating tokens --
 * with a cold local model that is comfortably over a minute, and the first request
 * after a restart also pays to load the weights off disk. Measured against a real
 * Ollama, every model-calling test here timed out at 30s.
 *
 * Raised rather than mocked, because the mock is what would make the suite
 * meaningless. Slow is the correct behaviour: the alternative is a test that only
 * ever exercises the not_configured path and reports it as full coverage.
 */
test.describe.configure({ timeout: 180_000 })

test.describe('ask', () => {
  test('the box is live, not the disabled placeholder it used to be', async ({ page }) => {
    // v0.1.0 shipped a greyed-out input reading "coming in a later phase". This is
    // the assertion that the promise was kept.
    await page.goto(`/drugs/${OSIMERTINIB}`)

    const input = page.getByTestId('ask-input')
    await expect(input).toBeVisible()
    await expect(input).toBeEnabled()
  })

  test('a question reaches the real API and comes back as a state the UI names', async ({
    page,
  }) => {
    await page.goto(`/drugs/${OSIMERTINIB}`)

    const response = page.waitForResponse(
      (r) => r.url().includes('/ask') && r.request().method() === 'POST',
    )
    await page.getByTestId('ask-input').fill('What drives resistance to this drug?')
    await page.getByTestId('ask-submit').click()

    // The real backend answered. Not a mock, not a fixture.
    const res = await response
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(['ok', 'not_configured', 'no_evidence', 'unavailable', 'ungrounded']).toContain(
      body.state,
    )

    // And whatever it was, the reader can see which. This is the assertion that
    // matters: every state has a rendering, so none of them can silently become a
    // blank box.
    const rendered = page.getByTestId(`answer-${String(body.state).replace('_', '-')}`)
    await expect(rendered).toBeVisible({ timeout: 60_000 })
    await expect(rendered).not.toBeEmpty()
  })

  test('with no model configured, it says so and says what to do', async ({ page, request }) => {
    // CI has no ANTHROPIC_API_KEY and no OLLAMA_URL, which makes this the state a
    // stranger cloning the repo actually hits. It has to be useful to them, not a
    // dead end -- so it names the variable to set. Skipped when a model IS
    // configured, asking the API rather than the environment, because the API is
    // what decides.
    //
    // The probe goes at the evidence-less fixture, and that is the trick: with no
    // evidence the backend never calls the model, so both possible answers come back
    // instantly -- not_configured if there is no model, no_evidence if there is.
    // Probing a real drug instead asked a real question, cost 114s of model time to
    // learn one bit, and blew the test budget when a second worker queued behind it
    // on the same serialised Ollama.
    const probe = await request.post('/api/drugs/CHEMBL_E2E_UNSEEN/ask', {
      data: { question: 'probe' },
    })
    const state = (await probe.json()).state
    test.skip(state !== 'not_configured', `a model is configured (state=${state})`)

    await page.goto(`/drugs/${OSIMERTINIB}`)
    await page.getByTestId('ask-input').fill('What drives resistance to this drug?')
    await page.getByTestId('ask-submit').click()

    const notice = page.getByTestId('answer-not-configured')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText('ANTHROPIC_API_KEY')
    // Never worded as a fault: nothing is broken, something is unset.
    await expect(notice).not.toContainText(/error|failed|went wrong/i)
  })

  test('the API never returns abstract text to the browser', async ({ request }) => {
    // The output boundary, checked from where it actually matters -- over the wire,
    // in the response the browser receives, rather than in a unit test that trusts
    // the same code it is testing. NOTICE.md's promise, end to end.
    const brief = await request.get(`/api/drugs/${OSIMERTINIB}`)
    const body = await brief.text()

    expect(body).not.toContain('CONCLUSIONS:')
    expect(body).not.toContain('INTRODUCTION:')
    // sample_titles is metadata and is served -- so this test is not passing merely
    // because the drug has no literature. That would make it vacuous.
    expect(body).toContain('n_pubmed')
  })

  test('a drug with no facts at all never reaches the model', async ({ request }) => {
    // The founding distinction at the chat layer: with nothing gathered, a model
    // would answer from training -- fluently, and indistinguishably from a grounded
    // answer. So it is not called, and the reader is told why.
    //
    // Two wrong versions preceded this one, and both were wrong the same way: they
    // pinned a state that only holds under a configuration I had assumed rather
    // than checked.
    //
    // First it pointed at CHEMBL_E2E_FAILURE and asserted `state != 'ok'`, assuming
    // no model. That fixture HAS facts, so with a model it correctly answers `ok`.
    // Then it asserted `no_evidence` -- which only holds WITH a model, because the
    // provider is checked before the evidence, so a keyless instance answers
    // `not_configured` first.
    //
    // The invariant that holds either way is the one actually worth defending: for a
    // drug with nothing gathered, the reader never gets an answer. Which reason they
    // are given depends on configuration, and both are true.
    const r = await request.post('/api/drugs/CHEMBL_E2E_UNSEEN/ask', {
      data: { question: 'What is its mechanism?' },
    })

    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(['no_evidence', 'not_configured']).toContain(body.state)
    expect(body.text).toBe('')
    // And always a reason, never a silent blank.
    expect(body.detail).toBeTruthy()
  })
})
