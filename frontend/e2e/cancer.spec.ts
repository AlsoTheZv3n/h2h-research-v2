import { expect, test } from '@playwright/test'

/**
 * The cancer catalog against the real API and its real ~1,300-row disease spine. No
 * mock layer: the counts are read back from the API itself, so the assertions hold at
 * any catalog size and prove the filtering happens in the database, not the browser.
 */

test.describe('cancer catalog', () => {
  test('the nav opens the cancer catalog and lists the real catalog', async ({ page, request }) => {
    const all = await (await request.get('/api/cancers?limit=1')).json()
    // A non-empty catalog is the premise (global-setup seeds fixtures; dev has the real
    // ~1,300). The count assertion below is what proves the number is the API's, not a
    // hardcoded one, so this only guards against a totally empty table.
    expect(all.total, 'the cancer catalog is empty -- seed/loader never ran').toBeGreaterThan(0)

    await page.goto('/')
    await page.getByTestId('nav-cancers').click()
    await expect(page).toHaveURL(/\/cancers/)
    await expect(page.getByTestId('cancer-row').first()).toBeVisible()
    // The UI's number is the API's number.
    await expect(page.getByTestId('cancer-total-count')).toContainText(
      all.total.toLocaleString('en-US'),
    )
    // The tab that owns this route is lit.
    await expect(page.getByTestId('nav-cancers')).toHaveAttribute('aria-current', 'page')
  })

  test('the drug-programme facet narrows the catalog to its API count', async ({ page, request }) => {
    const all = await (await request.get('/api/cancers?limit=1')).json()
    const drugged = await (await request.get('/api/cancers?limit=1&has_drugs=true')).json()
    // The premise: fewer cancers have a drug programme than exist, or the filter is a
    // no-op and this proves nothing.
    expect(drugged.total, 'every cancer has drugs -- filter would be a no-op').toBeLessThan(
      all.total,
    )

    await page.goto('/cancers')
    await page.getByTestId('facet-drug-programme').selectOption('true')
    await expect(page).toHaveURL(/has_drugs=true/)
    // The filtered count is the API's filtered count: the filter ran in SQL.
    await expect(page.getByTestId('cancer-total-count')).toContainText(
      drugged.total.toLocaleString('en-US'),
    )
  })

  test('a row opens the cancer page, with the non-clinical disclaimer', async ({ page }) => {
    await page.goto('/cancers?sort=drugs&order=desc')
    const first = page.getByTestId('cancer-row').first()
    await expect(first).toBeVisible()

    await first.click()
    // A real disease id in the URL (MONDO_ or the residual EFO_).
    await expect(page).toHaveURL(/\/cancers\/(MONDO|EFO)_/)
    // This is a research view, not clinical advice -- the disclaimer is always present.
    await expect(page.getByTestId('non-clinical-disclaimer')).toBeVisible()
    // The detail page keeps the Cancers tab lit.
    await expect(page.getByTestId('nav-cancers')).toHaveAttribute('aria-current', 'page')
  })

  test('an enriched cancer shows its target landscape with provenance', async ({ page }) => {
    // MONDO_E2E_NSCLC is seeded with a target-landscape brief (global-setup), so it is
    // READY on open and renders the real card -- no live Open Targets fetch.
    await page.goto('/cancers/MONDO_E2E_NSCLC')
    const card = page.getByTestId('target-landscape')
    await expect(card).toBeVisible()
    await expect(card).toContainText('EGFR')
    await expect(card).toContainText('KRAS')
    // Provenance behind the info icon, the same chip the drug page uses.
    await expect(page.getByTestId('source-info').first()).toBeVisible()
  })

  test('the pipeline groups drugs by phase, linking only catalog drugs', async ({ page }) => {
    await page.goto('/cancers/MONDO_E2E_NSCLC')
    const pipeline = page.getByTestId('pipeline')
    await expect(pipeline).toBeVisible()
    await expect(pipeline).toContainText('Approved')
    await expect(pipeline).toContainText('Phase 2')
    // In the catalog -> a link to its brief (matched by exact ChEMBL id).
    await expect(page.getByRole('link', { name: 'E2E APPROVED DRUG' })).toHaveAttribute(
      'href',
      /\/drugs\/CHEMBL_E2E_INPIPE/,
    )
    // Not in the catalog -> shown, but never a dead link.
    await expect(pipeline).toContainText('E2E EXTERNAL DRUG')
    await expect(page.getByRole('link', { name: 'E2E EXTERNAL DRUG' })).toHaveCount(0)
  })

  test('the drug catalog still works, and its tab is active there', async ({ page }) => {
    // The expansion must not have broken the drug side.
    await page.goto('/')
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    await expect(page.getByTestId('nav-drugs')).toHaveAttribute('aria-current', 'page')
  })
})
