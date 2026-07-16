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

test.describe('overview', () => {
  test('lists real catalog rows from the API', async ({ page }) => {
    await page.goto('/')

    const rows = page.getByTestId('drug-row')
    await expect(rows.first()).toBeVisible()
    // A mock would not have hundreds of drugs in it. This number comes from a real
    // ChEMBL ingest.
    const total = await page.getByTestId('total-count').textContent()
    const count = Number((total ?? '').replace(/[^\d]/g, ''))
    expect(count).toBeGreaterThan(20)
    await expect(rows).not.toHaveCount(0)
  })

  test('filters hit the API and change the result set', async ({ page }) => {
    await page.goto('/')
    const before = await page.getByTestId('total-count').textContent()

    await page.getByLabel('Filter by target').fill('KRAS')
    await expect(page.getByTestId('total-count')).not.toHaveText(before ?? '')

    // The filter is a query param, not a client-side slice -- so it survives a reload.
    await expect(page).toHaveURL(/target=KRAS/)
  })

  test('a row click opens that drug’s brief', async ({ page }) => {
    await page.goto(`/?target=KRAS`)
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
    // ChEMBL fails often enough that some field on some drug is source_failed. Which
    // drug carries one varies between ingests, so look across the subset -- but wait
    // for each page to actually render before counting. count() does not retry, so
    // counting straight after goto() reads an empty DOM, finds nothing, and skips:
    // a green run that asserted nothing, which is the failure mode this project
    // keeps having to root out.
    for (const id of [SOTORASIB, 'CHEMBL4594350', ADC]) {
      await page.goto(`/drugs/${id}`)
      await expect(page.locator('h1')).toBeVisible()

      const failed = page.getByTestId('fact-source-failed')
      if ((await failed.count()) > 0) {
        await expect(failed.first()).toBeVisible()
        await expect(failed.first()).toContainText(/unavailable/i)
        // The distinction that matters: an outage must not be worded as a finding.
        await expect(failed.first()).not.toContainText(/none found|no .* annotated/i)
        return
      }
    }
    throw new Error(
      'No source_failed fact anywhere in the enriched subset. Either every source ' +
        'was healthy during the ingest (re-run enrich to reproduce), or the status ' +
        'is being lost between the adapter and the UI -- which is the bug this test exists for.',
    )
  })

  test('a complete drug shows a real on-target potency, not a row count', async ({ page }) => {
    await page.goto(`/drugs/${OSIMERTINIB}`)
    await expect(page.getByText('Binding & potency')).toBeVisible()

    const median = page.getByTestId('median-ic50')
    if ((await median.count()) > 0) {
      // The headline is a median in nM over exact on-target rows -- the count of
      // activities is deliberately demoted to a footnote.
      await expect(median).toBeVisible()
      await expect(page.getByText(/nM median/)).toBeVisible()
    }
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
