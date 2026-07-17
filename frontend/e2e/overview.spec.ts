import { expect, test } from '@playwright/test'

/**
 * The overview's facets, chips, sort and URL state, against the real API and its real
 * ~3,900-row catalog. No mock layer: the numbers are read back from the API itself,
 * so the assertions hold at any catalog size and prove the filtering happens in the
 * database, not in the browser.
 */

test.describe('overview filters', () => {
  test('a modality facet narrows the catalog, and its chip removes it', async ({
    page,
    request,
  }) => {
    // The premise, checked rather than assumed: there must be non-small-molecule rows
    // for the filter to remove, or "narrows" means nothing.
    const all = await (await request.get('/api/drugs?limit=1')).json()
    const sm = await (await request.get('/api/drugs?limit=1&modality=Small%20molecule')).json()
    expect(sm.total, 'the catalog has only small molecules to filter').toBeLessThan(all.total)

    await page.goto('/')
    await page.getByTestId('facet-modality').selectOption('Small molecule')

    await expect(page).toHaveURL(/modality=Small/)
    // The UI's number is the API's number: filtering is a query param, not a slice.
    await expect(page.getByTestId('total-count')).toContainText(sm.total.toLocaleString('en-US'))

    const chip = page.getByTestId('chip-modality')
    await expect(chip).toBeVisible()
    await chip.click()
    await expect(page).not.toHaveURL(/modality=/)
    await expect(page.getByTestId('total-count')).toContainText(all.total.toLocaleString('en-US'))
  })

  test('clicking a column header sorts, and the URL carries it across a reload', async ({
    page,
  }) => {
    await page.goto('/')
    await expect(page.getByTestId('drug-row').first()).toBeVisible()

    await page.getByTestId('sort-name').click()
    await expect(page).toHaveURL(/sort=name/)
    const firstAfterSort = await page.getByTestId('drug-row').first().textContent()

    await page.reload()
    // The sort survives the reload from the URL alone -- shareable, refresh-proof.
    await expect(page).toHaveURL(/sort=name/)
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    expect(await page.getByTestId('drug-row').first().textContent()).toEqual(firstAfterSort)
  })

  test('reversing the sort order actually reorders the table', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('sort-phase').click() // phase, its default direction (desc)
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    const desc = await page.getByTestId('drug-row').first().textContent()

    await page.getByTestId('sort-phase').click() // same column again -> flip to asc
    await expect(page).toHaveURL(/order=asc/)
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    const asc = await page.getByTestId('drug-row').first().textContent()

    // A real sort: the two ends differ. If order were ignored these would match.
    expect(asc).not.toEqual(desc)
  })

  test('the filtered count reads "X of Y shown"', async ({ page }) => {
    await page.goto('/?maturity=index_only')
    const count = page.getByTestId('total-count')
    await expect(count).toContainText('of')
    await expect(count).toContainText('shown')
  })
})
