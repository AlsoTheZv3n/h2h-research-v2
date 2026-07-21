import { expect, test } from '@playwright/test'

/**
 * The target detail page against the real stack, and the thread it completes: a cancer's target
 * landscape now links each target to its own page, that page lists the cancers the target drives
 * (filtered to our catalog, from the Open Targets reverse query), and each is a live link back
 * into its brief. The whole cancer -> target -> cancer loop, DB -> API -> UI, no mock layer.
 *
 * Uses the ENSG_E2E_EGFR fixture: the same EGFR that leads the MONDO_E2E_NSCLC landscape,
 * seeded as an enriched target so the page renders without a live source fetch.
 */

test.describe('target detail', () => {
  test('the cancer landscape links a target to its page, which links back to the cancer', async ({
    page,
  }) => {
    // Start on the enriched cancer fixture and open its target landscape.
    await page.goto('/cancers/MONDO_E2E_NSCLC#target-landscape')
    const egfr = page.getByTestId('landscape-target-link').filter({ hasText: 'EGFR' })
    await expect(egfr).toBeVisible()

    // Click the target symbol -> its own page.
    await egfr.click()
    await expect(page).toHaveURL(/\/targets\/ENSG_E2E_EGFR/)
    await expect(page.getByRole('heading', { level: 1, name: 'EGFR' })).toBeVisible()

    // The associated cancer, from the reverse query, filtered to our catalog -> a live link.
    const cancerLink = page
      .getByTestId('associated-cancers')
      .getByRole('link', { name: /E2E lung carcinoma/i })
    await expect(cancerLink).toBeVisible()

    // #43: the target-side mutation-frequency reflection -- this gene's frequency across the cancers
    // it drives (seeded). The card renders the cancer row with its measured %, DB -> API -> UI.
    const altCard = page.getByTestId('target-alt-cancers')
    await expect(altCard).toBeVisible()
    await expect(altCard).toContainText('E2E lung carcinoma')
    await expect(page.getByTestId('target-alt-measured').first()).toContainText('12.4%')

    // #44: the PubTator extracted-relations block. The load-bearing thing: the "extracted, not
    // curated" banner reads at a glance, and a bridged disease links into the catalog, DB -> API -> UI.
    await expect(page.getByTestId('extracted-banner')).toContainText(/extracted, not curated/i)
    await expect(
      page.getByTestId('extracted-diseases').getByRole('link', { name: /E2E lung carcinoma/i }),
    ).toBeVisible()
    await expect(page.getByTestId('extracted-chemicals')).toContainText('E2E Gefitinib')

    // A target page belongs to neither catalog: no primary tab is lit.
    await expect(page.getByTestId('nav-drugs')).not.toHaveAttribute('aria-current', 'page')
    await expect(page.getByTestId('nav-cancers')).not.toHaveAttribute('aria-current', 'page')

    // Follow it back to the cancer brief -- the loop closes.
    await cancerLink.click()
    await expect(page).toHaveURL(/\/cancers\/MONDO_E2E_NSCLC/)
    await expect(page.getByRole('heading', { level: 1, name: /E2E lung carcinoma/i })).toBeVisible()
  })

  test('the target page links the drugs in our catalog that act on it', async ({ page }) => {
    await page.goto('/targets/ENSG_E2E_EGFR')
    // CHEMBL_E2E_INPIPE acts on ENSG_E2E_EGFR (a drug_target row) -> a live link into its brief.
    const drugLink = page.getByTestId('catalog-drug-link').filter({ hasText: 'CHEMBL_E2E_INPIPE' })
    await expect(drugLink).toBeVisible()
    await drugLink.click()
    await expect(page).toHaveURL(/\/drugs\/CHEMBL_E2E_INPIPE/)
  })
})
