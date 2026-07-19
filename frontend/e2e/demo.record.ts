import { chromium } from '@playwright/test'

/**
 * Records the README's hero GIF from the real, running app.
 *
 * Committed so the GIF is reproducible: when the UI changes, re-run this rather
 * than hand-capturing something that quietly stops matching the product. It was
 * last re-run for the cancer entity -- the demo now threads from a drug brief to
 * the disease it treats, where the same target (EGFR) leads the landscape.
 *
 * The arc, in two acts joined by a visible nav click:
 *   1. osimertinib's brief -- real science, distilled, four calm cards
 *   2. the provenance behind a quiet "i" -- the differentiator vs a chat assistant
 *   3. honest when a source is down -- the calm amber advisory
 *   4. honest when there is nothing to show -- a biologic's "not applicable"
 *   5. click the Cancers tab -- the second entity, the hinge between the acts
 *   6. NSCLC: the honest targets metric (strong count above a threshold, not the
 *      whole-genome total), EGFR leading the landscape, and the pipeline as a
 *      phase distribution + a table that links only the drugs we actually hold
 *   7. the sourced evidence blocks below -- the registered-trial landscape
 *      (ClinicalTrials.gov), European mortality by country (Eurostat) and 5-year
 *      survival by stage (SEER), each honest about a roll-up or a gap
 *
 * Not a test. There are no assertions and the pauses are deliberately generous --
 * this is paced for a human reading a loop, not for a machine checking a condition.
 *
 * Prerequisites (both matter):
 *   - `docker compose up`, with the current UI reachable at BASE
 *   - osimertinib, afatinib, the ADC, and NSCLC (MONDO_0005233) already enriched
 *     and fresh. A cold entity would put a lazy-enrichment spinner in the shot, at
 *     the mercy of a source's mood.
 *
 * Run:  pnpm exec tsx e2e/demo.record.ts
 * Then convert the webm to docs/demo.gif with:  pnpm exec tsx e2e/demo.convert.ts
 */

const BASE = process.env.DEMO_BASE_URL ?? 'http://localhost:5175'
const OUT = process.env.DEMO_OUT ?? 'demo-recording'

// osimertinib: a complete brief -- the product working. An EGFR inhibitor for NSCLC,
// which is why it is the thread into the cancer act.
const OSIMERTINIB = 'CHEMBL3353410'
// afatinib: a real drug whose last refresh hit a source outage -- the calm advisory.
const AFATINIB = 'CHEMBL1173655'
// trastuzumab deruxtecan: a biologic -- the product being honest about what it lacks.
const ADC = 'CHEMBL4297844'
// non-small cell lung carcinoma: the disease osimertinib treats, where EGFR is the
// first associated target -- the drug->cancer thread paying off.
const NSCLC = 'MONDO_0005233'

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: { width: 1000, height: 720 },
  recordVideo: { dir: OUT, size: { width: 1000, height: 720 } },
  deviceScaleFactor: 1,
})
const page = await context.newPage()

// 1. Open straight on the brief: the molecule beside the distilled potency, four
//    calm cards -- "real science, distilled". This is the hero thumbnail.
await page.goto(`${BASE}/drugs/${OSIMERTINIB}`)
await page.getByTestId('structure-svg').waitFor()
await page.waitForTimeout(2000)

// 2. The money shot. The source is a quiet "i" now; hovering it opens the provenance
//    popover -- source, retrieval date, a link. This is the whole differentiator
//    against a chat assistant, and it is invisible in a screenshot, so the loop has
//    to trigger it.
const info = page.getByTestId('source-info').first()
await info.scrollIntoViewIfNeeded()
await info.hover()
await page.getByRole('tooltip').first().waitFor()
await page.waitForTimeout(2600)
await page.mouse.move(0, 0)
await page.waitForTimeout(300)

// 3. Honest when a source is down. A real drug whose last refresh hit a ChEMBL outage:
//    a calm amber advisory says the picture is partial, not wrong -- a gap in our
//    pipeline, with a button to look again.
await page.goto(`${BASE}/drugs/${AFATINIB}`)
await page.getByTestId('source-advisory').waitFor()
await page.waitForTimeout(2400)

// 4. Honest when it does not have something at all. The ADC is a biologic -- no
//    small-molecule structure or binding curve to show -- and the page says so calmly,
//    never a broken card.
await page.goto(`${BASE}/drugs/${ADC}`)
await page.getByTestId('not-applicable').first().waitFor()
await page.waitForTimeout(2400)

// 5. The hinge. Click the Cancers tab: the same product, a second entity. This is the
//    one navigation the loop shows, so the two acts read as one tool, not two.
await page.getByTestId('nav-cancers').click()
await page.getByTestId('cancer-row').first().waitFor()
// The dev DB may hold the e2e fixture cancers (MONDO_E2E_*), which the Playwright
// global-setup reseeds on every run -- so "record then convert regenerates the GIF" must
// not depend on someone having deleted them by hand. Strip them from the recorded catalog
// here: a view-only filter, no DB edit, so the recording is clean on any machine.
await page.evaluate(() => {
  for (const row of document.querySelectorAll('[data-testid="cancer-row"]')) {
    if (row.textContent?.includes('MONDO_E2E_')) row.remove()
  }
})
// Guard the one leak point. The cancer list is the only view that renders every catalog row,
// so it is the only place a fixture can enter the shot; every other step navigates to a pinned
// real id. If a future change ever lets an MONDO_E2E_* row survive the strip above, fail the
// recording loudly rather than publish a GIF with a synthetic fixture in it.
const leaked = await page
  .locator('[data-testid="cancer-row"]', { hasText: 'MONDO_E2E_' })
  .count()
if (leaked > 0) throw new Error(`demo recording leaked ${leaked} E2E fixture row(s) into the shot`)
await page.waitForTimeout(1800)

// 6. NSCLC -- the disease osimertinib treats. Land on the honest targets metric: the
//    count of STRONG associations above a documented score threshold, with the raw
//    whole-genome-sized total kept only as a qualified sub-line. The same honest-states
//    discipline as the drug cards, now on a number that would otherwise mislead.
await page.goto(`${BASE}/cancers/${NSCLC}`)
await page.getByTestId('targets-stat').waitFor()
await page.getByTestId('targets-stat').scrollIntoViewIfNeeded()
await page.waitForTimeout(2600)

// EGFR leads the target landscape -- the same target osimertinib inhibits, closing the
// thread -- beside the pipeline as a phase distribution rather than a wall of names.
await page.getByTestId('pipeline-distribution').scrollIntoViewIfNeeded()
await page.waitForTimeout(2200)

// The pipeline table links only the drugs we actually hold (matched by exact ChEMBL id,
// never by name). Narrow it to those with "in catalog only": every remaining row is a
// live link into its brief -- osimertinib among them.
await page.getByTestId('pipeline-filter-catalog').check()
await page.getByTestId('pipeline-table').scrollIntoViewIfNeeded()
await page.waitForTimeout(2600)

// 7. The blocks that make this a cancer-intelligence view, not just a drug list -- and every one
//    sourced and honest about a roll-up or a gap:
//    - the real registered-trial landscape (ClinicalTrials.gov, by condition): a true count with
//      the scanned sample beside it, a phase/status split, stopped-with-reasons, DACH recruiting;
await page.locator('#trial-reality').scrollIntoViewIfNeeded()
await page.getByTestId('trial-count').waitFor()
await page.waitForTimeout(2600)
//    - European mortality by country (Eurostat), labelled as the broader ICD-10 rollup it is;
await page.locator('#epidemiology').scrollIntoViewIfNeeded()
await page.waitForTimeout(2600)
//    - and 5-year relative survival by stage (SEER), the same honest-rollup discipline.
await page.locator('#survival').scrollIntoViewIfNeeded()
await page.waitForTimeout(2600)

await context.close()
await browser.close()
console.log(`recorded to ${OUT}/`)
