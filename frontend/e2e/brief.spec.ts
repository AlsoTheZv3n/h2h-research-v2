import { expect, test } from '@playwright/test'

/**
 * Against the real API, serving really-enriched facts. No mocks anywhere in here.
 *
 * This suite is the guard against this project's most expensive defect, one level
 * up: a backend whose adapters were only ever called by its own tests, so every
 * test was green while production would have served `facts: {}`. A frontend that
 * mocked the facts endpoint would look just as finished and be just as empty.
 * If the backend stops serving real facts, these fail. That is the whole point.
 */

const SOTORASIB = 'CHEMBL4535757'
const OSIMERTINIB = 'CHEMBL3353410'
const ADC = 'CHEMBL4297844' // trastuzumab deruxtecan -- a biologic, no SMILES
// Seeded by global-setup.ts: a drug whose ChEMBL mechanism fetch failed.
const E2E_FIXTURE = 'CHEMBL_E2E_FAILURE'

test.describe('overview', () => {
  test('lists what the API actually holds', async ({ page, request }) => {
    // Checked against the API rather than against a row count. "More than 20 drugs"
    // was a poor proxy for "not mocked": it says nothing about where the rows came
    // from, and it breaks the moment the catalog is smaller -- as it is on a fresh
    // checkout. Comparing the table to the API's own answer is the real claim, and
    // it holds at any size.
    const api = await (await request.get('/api/drugs?limit=25&offset=0')).json()

    await page.goto('/')
    const rows = page.getByTestId('drug-row')
    await expect(rows.first()).toBeVisible()

    await expect(rows).toHaveCount(api.items.length)
    await expect(page.getByTestId('total-count')).toContainText(
      api.total.toLocaleString('en-US'),
    )
    // And the first row is the drug the API put first -- not something invented.
    await expect(rows.first()).toContainText(api.items[0].chembl_id)
  })

  test('search narrows the result set through the API', async ({ page }) => {
    await page.goto('/')
    const before = await page.getByTestId('total-count').textContent()

    await page.getByLabel('Search drugs').fill('sotorasib')
    await expect(page.getByTestId('total-count')).not.toHaveText(before ?? '')

    // A query param, not a client-side slice of one page -- so it survives a reload
    // and `total` keeps meaning the corpus.
    await expect(page).toHaveURL(/q=sotorasib/)
    await expect(page.getByTestId('drug-row').first()).toContainText(/sotorasib/i)
  })

  test('search is partial and case-insensitive', async ({ page }) => {
    // The first cut matched exactly and case-sensitively. Since people type one
    // character at a time, every keystroke but the last returned nothing -- a field
    // that reads as broken rather than strict.
    await page.goto('/')
    await page.getByLabel('Search drugs').fill('sotor')

    await expect(page.getByTestId('drug-row').first()).toContainText(/sotorasib/i)
  })

  test('the phase filter narrows the corpus', async ({ page, request }) => {
    // The premise, checked rather than assumed: there has to be something below
    // phase 4 for the filter to remove. The first cut took that for granted, and
    // against a demo fixture of nothing but approved drugs it failed with "expected
    // < 5, received 5" -- a green filter reported as a bug.
    const all = await (await request.get('/api/drugs?limit=1')).json()
    const approved = await (await request.get('/api/drugs?limit=1&max_phase=4')).json()
    expect(approved.total, 'the catalog has nothing below phase 4 to filter out').toBeLessThan(
      all.total,
    )

    await page.goto('/')
    await expect(page.getByTestId('total-count')).toContainText(all.total.toLocaleString('en-US'))

    await page.getByLabel('Minimum phase').selectOption('4')

    await expect(page).toHaveURL(/max_phase=4/)
    // The UI's number has to be the API's number -- filtering is a query param, not
    // a slice of the page the browser already had.
    await expect(page.getByTestId('total-count')).toContainText(
      approved.total.toLocaleString('en-US'),
    )
  })

  test('a row click opens that drug’s brief', async ({ page }) => {
    await page.goto(`/?q=kras`)
    const row = page.getByTestId('drug-row').first()
    await expect(row).toBeVisible()
    await row.click()

    await expect(page).toHaveURL(/\/drugs\/CHEMBL\d+/)
    await expect(page.locator('h1')).toBeVisible()
  })
})

test.describe('detail brief', () => {
  test('renders a real brief with real facts and working citations', async ({ page }) => {
    await page.goto(`/drugs/${SOTORASIB}`)

    await expect(page.locator('h1')).toContainText(/sotorasib/i)

    // Real facts, not an empty shell: if enrichment never ran, this page would be
    // all "Not collected" and this assertion is what catches it.
    const okFacts = page.getByTestId('fact-ok')
    await expect(okFacts.first()).toBeVisible()
    expect(await okFacts.count()).toBeGreaterThan(3)

    // Provenance is the signature interaction.
    const chip = page.getByRole('button', { name: /source:/i }).first()
    await chip.hover()
    const tip = page.getByRole('tooltip').first()
    await expect(tip).toBeVisible()
    await expect(tip).toContainText(/retrieved/i)
    await expect(tip.getByRole('link')).toHaveAttribute('href', /^https?:\/\//)
  })

  test('the structure renders from the backend’s RDKit SVG', async ({ page }) => {
    const response = page.waitForResponse((r) => r.url().includes('/structure.svg'))
    await page.goto(`/drugs/${SOTORASIB}`)

    const svg = await response
    expect(svg.status()).toBe(200)
    expect(svg.headers()['content-type']).toContain('image/svg+xml')
    await expect(page.getByTestId('structure-svg')).toBeVisible()
  })

  test('a failed source reads as unavailable, never as empty', async ({ page }) => {
    // Against a seeded fixture (see global-setup.ts), not against whatever ChEMBL
    // happens to be doing. Looking for an organic failure made this a coin flip:
    // green while the source was sick, red while it was healthy, and neither reading
    // said anything about our code. The row is real, in the real database, served by
    // the real API -- only *which* drug is broken is controlled.
    await page.goto(`/drugs/${E2E_FIXTURE}`)
    await expect(page.locator('h1')).toBeVisible()

    const failed = page.getByTestId('fact-source-failed')
    await expect(failed.first()).toBeVisible()
    await expect(failed.first()).toContainText(/unavailable/i)
    // The distinction that matters: an outage must never be worded as a finding.
    await expect(failed.first()).not.toContainText(/none found|no .* annotated/i)

    // And the contrast, on the same page: a measured zero reads differently.
    const empty = page.getByTestId('fact-empty')
    await expect(empty.first()).toBeVisible()
    expect(await failed.first().textContent()).not.toEqual(await empty.first().textContent())
  })

  test('a complete drug shows a real on-target potency, not a row count', async ({ page }) => {
    // Unconditional. This sat behind `if ((await median.count()) > 0)`, which made
    // both assertions optional -- so the project's marquee claim had no enforced
    // coverage anywhere, ninety lines below two guards written to kill exactly that.
    // The fixture pins osimertinib at 12.66 nM over 62 exact rows, so there is
    // nothing to be defensive about.
    await page.goto(`/drugs/${OSIMERTINIB}`)
    await expect(page.getByText('Binding & potency')).toBeVisible()

    await expect(page.getByTestId('median-ic50')).toBeVisible()
    await expect(page.getByText(/nM median/)).toBeVisible()
    // The count is demoted to a footnote on purpose: 701 activities exist, and the
    // median over 62 exact on-target rows is the only one of the two that is an answer.
    await expect(page.getByText(/exact on-target measurements/)).toBeVisible()
  })
})

test.describe('the biologic case', () => {
  test('the ADC shows "not applicable", not a broken structure card', async ({ page }) => {
    await page.goto(`/drugs/${ADC}`)

    await expect(page.locator('h1')).toContainText(/trastuzumab deruxtecan/i)

    // Present in the catalog, honestly labelled -- the §8 requirement.
    await expect(page.getByText('Index only')).toBeVisible()

    const na = page.getByTestId('not-applicable')
    await expect(na.first()).toBeVisible()
    await expect(na.first()).toContainText(/biologic/i)
    // Never a blank image standing in for a molecule.
    await expect(page.getByTestId('structure-svg')).toHaveCount(0)
  })
})
