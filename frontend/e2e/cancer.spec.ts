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

  test('the therapeutic-area facet shows per-option counts from the API', async ({ page }) => {
    // The counts flow DB -> API -> UI on the cancer overview too: at least one area option carries
    // a "(N)". A count-less list would mean the page never fetched /cancers/facets.
    await page.goto('/cancers')
    await expect(page.getByTestId('cancer-row').first()).toBeVisible()
    const counted = page
      .getByTestId('facet-therapeutic-area')
      .locator('option')
      .filter({ hasText: /\(\d+\)/ })
    // Web-first + auto-retrying: the counts and the area options both come from SEPARATE fetches
    // than the rows, so a one-shot count() could read 0 before they land. not.toHaveCount(0) waits.
    await expect(counted).not.toHaveCount(0)
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
    // The associated-targets stat leads with the STRONG count (118), always beside its
    // threshold, with the raw total framed as "with any evidence" -- never a bare figure.
    const stat = page.getByTestId('targets-stat')
    await expect(stat).toContainText('118')
    await expect(stat).toContainText('score ≥ 0.5')
    await expect(stat).toContainText('8,000 with any evidence')
  })

  test('the target landscape shows the drugged flag, the target link and the in-catalog drug link', async ({
    page,
  }) => {
    // Fixture: EGFR is `approved` and we hold a drug against it (drug_target, by Ensembl id)
    // -> a badge AND an "in catalog" link to that drug; KRAS has no drug anywhere -> a badge, no
    // link. Every target's symbol also drills into its own page. This checks the R4 flag and both
    // catalog links (target page + drug) end to end.
    await page.goto('/cancers/MONDO_E2E_NSCLC')
    await expect(page.getByTestId('drug-status-approved')).toBeVisible()
    await expect(page.getByTestId('drug-status-unexploited')).toBeVisible()
    // The finding's badge writes out the claim ("no drug anywhere"), not the term of art.
    await expect(page.getByTestId('drug-status-unexploited')).toContainText(/no drug anywhere/i)
    // EGFR's symbol drills into its own target page, matched by Ensembl id.
    const targetLink = page.getByTestId('landscape-target-link').filter({ hasText: 'EGFR' })
    await expect(targetLink).toHaveAttribute('href', '/targets/ENSG_E2E_EGFR')
    // The separate, weaker signal: a WORDED "in catalog" link to the drug we hold against EGFR --
    // an action, set apart from the status badges, not the old bare ℞ glyph read as a status.
    const drugLink = page.getByTestId('landscape-catalog-link')
    await expect(drugLink).toHaveAttribute('href', '/drugs/CHEMBL_E2E_INPIPE')
    await expect(drugLink).toContainText(/in catalog/i)
    // Exactly one: KRAS (no drug anywhere) stays plain, not a dead link.
    await expect(drugLink).toHaveCount(1)

    // The status filter narrows to the unexploited finding (KRAS), the decision-useful cell.
    await page.getByTestId('landscape-filter-status').selectOption('unexploited')
    const rows = page.getByTestId('landscape-row')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('KRAS')
  })

  test('the pipeline shows a distribution + filterable table, linking only catalog drugs', async ({
    page,
  }) => {
    await page.goto('/cancers/MONDO_E2E_NSCLC')
    await expect(page.getByTestId('pipeline-distribution')).toBeVisible()
    const table = page.getByTestId('pipeline-table')
    await expect(table).toBeVisible()
    // Modality + mechanism columns carry values (the spec gap R2 filled).
    await expect(table).toContainText('Small molecule')
    await expect(table).toContainText('E2E kinase inhibitor')
    // In the catalog -> a link by exact ChEMBL id; not in the catalog -> plain, never a dead link.
    await expect(page.getByRole('link', { name: 'E2E APPROVED DRUG' })).toHaveAttribute(
      'href',
      /\/drugs\/CHEMBL_E2E_INPIPE/,
    )
    await expect(table).toContainText('E2E EXTERNAL DRUG')
    await expect(page.getByRole('link', { name: 'E2E EXTERNAL DRUG' })).toHaveCount(0)
    // The modality filter narrows the table to just the Antibody (the external drug).
    await page.getByTestId('pipeline-filter-modality').selectOption('Antibody')
    await expect(page.getByTestId('pipeline-row')).toHaveCount(1)
    await expect(table).toContainText('E2E EXTERNAL DRUG')
  })

  test('the trial-reality block shows the honest count, distributions and the DACH signal', async ({
    page,
  }) => {
    // MONDO_E2E_NSCLC carries a seeded trial_reality fact (global-setup), so the block renders
    // the real card from DB -> API -> UI without a live ClinicalTrials.gov fetch.
    await page.goto('/cancers/MONDO_E2E_NSCLC')
    const count = page.getByTestId('trial-count')
    await expect(count).toBeVisible()
    // The count reads as the TRUE total (8,442), never the scanned page -- with the sample noted.
    await expect(count).toContainText('8,442')
    await expect(page.getByTestId('trial-sample-note')).toContainText('1,000')
    // Phase and status distributions render as COUNTS, not shares -- the seeded 440 (Phase 2) is
    // exactly what a regression to percentages would drop.
    const phaseDist = page.getByTestId('trial-phase-distribution')
    await expect(phaseDist).toContainText('Phase 2')
    await expect(phaseDist).toContainText('440')
    await expect(page.getByTestId('trial-status-distribution')).toContainText('Recruiting')
    // The query-side DACH count and the stopped-with-reasons honesty angle.
    await expect(page.getByTestId('trial-dach')).toContainText('122')
    const stopped = page.getByTestId('trial-stopped')
    await expect(stopped).toContainText('172')
    await expect(stopped).toContainText('Slow accrual')
  })

  test('the drug catalog still works, and its tab is active there', async ({ page }) => {
    // The expansion must not have broken the drug side.
    await page.goto('/')
    await expect(page.getByTestId('drug-row').first()).toBeVisible()
    await expect(page.getByTestId('nav-drugs')).toHaveAttribute('aria-current', 'page')
  })
})
