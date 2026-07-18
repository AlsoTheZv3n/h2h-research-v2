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

  test('a target-class facet narrows the catalog, and its chip removes it', async ({
    page,
    request,
  }) => {
    // The facet's options come from the API, so the test uses whatever families the
    // catalog actually holds. An empty list is a real failure -- it means enrichment
    // stopped promoting target_class -- so this asserts rather than skips.
    const classes: string[] = await (await request.get('/api/drugs/target-classes')).json()
    expect(classes.length, 'no target classes present -- enrichment not promoting them').toBeGreaterThan(0)
    const cls = classes[0]

    const all = await (await request.get('/api/drugs?limit=1')).json()
    const filtered = await (
      await request.get(`/api/drugs?limit=1&target_class=${encodeURIComponent(cls)}`)
    ).json()
    expect(filtered.total, 'the class filter must remove something').toBeLessThan(all.total)

    await page.goto('/')
    await page.getByTestId('facet-target-class').selectOption(cls)

    await expect(page).toHaveURL(/target_class=/)
    // The UI's number is the API's number: the class filter runs in SQL, not the browser.
    await expect(page.getByTestId('total-count')).toContainText(
      filtered.total.toLocaleString('en-US'),
    )

    const chip = page.getByTestId('chip-target_class')
    await expect(chip).toBeVisible()
    await chip.click()
    await expect(page).not.toHaveURL(/target_class=/)
    await expect(page.getByTestId('total-count')).toContainText(all.total.toLocaleString('en-US'))
  })

  test('the non-oncology toggle reveals out-of-scope drugs', async ({ page, request }) => {
    // The premise: there must be drugs scoped out for the toggle to reveal. An empty
    // gap is a real failure -- scoping was never applied -- so this asserts, not skips.
    const inScope = await (await request.get('/api/drugs?limit=1')).json()
    const full = await (await request.get('/api/drugs?limit=1&include_out_of_scope=true')).json()
    expect(full.total, 'no out-of-scope drugs -- scoping not applied').toBeGreaterThan(
      inScope.total,
    )

    await page.goto('/')
    const count = page.getByTestId('total-count')
    const toggle = page.getByTestId('toggle-out-of-scope')
    // Default: a subset of the whole catalog, because the non-oncology tail is hidden.
    await expect(count).toContainText('shown')
    await expect(count).toContainText(inScope.total.toLocaleString('en-US'))

    // click(), not check(): the checkbox is controlled by URL state, so its DOM
    // `checked` settles a tick after the click -- and the real proof is the outcome,
    // not the box. The URL carries the param and the count widens to the whole catalog.
    await toggle.click()
    await expect(page).toHaveURL(/include_out_of_scope=true/)
    await expect(toggle).toBeChecked()
    // Now the whole catalog: the count reads "N in catalog", not "of N shown". That
    // transition is the proof the toggle widened the base set, not just added a param.
    await expect(count).toContainText(full.total.toLocaleString('en-US'))
    await expect(count).toContainText('in catalog')

    await toggle.click()
    await expect(page).not.toHaveURL(/include_out_of_scope/)
    await expect(toggle).not.toBeChecked()
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
    await expect(page).toHaveURL(/order=desc/)
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    const desc = (await page.getByTestId('drug-row').first().textContent()) ?? ''

    await page.getByTestId('sort-phase').click() // same column again -> flip to asc
    await expect(page).toHaveURL(/order=asc/)
    // A real sort: the two ends differ. Poll rather than read once -- the descending
    // rows linger on screen while the re-sorted page is still in flight, so reading the
    // first row immediately raced that fetch (and failed under CI load). If order were
    // ignored, the row never changes and this times out.
    await expect
      .poll(async () => (await page.getByTestId('drug-row').first().textContent()) ?? '')
      .not.toBe(desc)
  })

  test('the filtered count reads "X of Y shown"', async ({ page }) => {
    await page.goto('/?maturity=index_only')
    const count = page.getByTestId('total-count')
    await expect(count).toContainText('of')
    await expect(count).toContainText('shown')
  })
})
