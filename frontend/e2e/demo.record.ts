import { chromium } from '@playwright/test'

/**
 * Records the README's hero GIF from the real, running app.
 *
 * Committed so the GIF is reproducible: when the UI changes, re-run this rather
 * than hand-capturing something that quietly stops matching the product.
 *
 * Not a test. There are no assertions and the pauses are deliberately generous --
 * this is paced for a human reading a loop, not for a machine checking a condition.
 *
 * Prerequisites (both matter):
 *   - `docker compose up`, with the UI reachable at BASE
 *   - osimertinib and the ADC already enriched. A cold drug would put a lazy
 *     enrichment spinner in the hero shot, at the mercy of ChEMBL's mood.
 *
 * Run:  pnpm exec tsx e2e/demo.record.ts   (see docs/README of the repo)
 */

const BASE = process.env.DEMO_BASE_URL ?? 'http://localhost:5175'
const OUT = process.env.DEMO_OUT ?? 'demo-recording'

// osimertinib: a complete brief -- the product working.
const OSIMERTINIB = 'CHEMBL3353410'
// trastuzumab deruxtecan: a biologic -- the product being honest.
const ADC = 'CHEMBL4297844'

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: { width: 1000, height: 720 },
  recordVideo: { dir: OUT, size: { width: 1000, height: 720 } },
  deviceScaleFactor: 1,
})
const page = await context.newPage()

// 1. The overview, briefly: this is a real catalog, not a toy. Kept short -- a
//    generic table eats the seconds the brief needs.
await page.goto(`${BASE}/`)
await page.getByTestId('drug-row').first().waitFor()
await page.waitForTimeout(1200)

// 2. The brief. The molecule beside the distilled potency: "real science, distilled".
await page.goto(`${BASE}/drugs/${OSIMERTINIB}`)
await page.getByTestId('structure-svg').waitFor()
await page.waitForTimeout(1800)

// 3. The money shot. A citation chip revealing source, retrieval date and a link.
//    This is the whole differentiator against a chat assistant, and it is invisible
//    in a screenshot -- if the GIF misses this, it undersells the product.
const chip = page.getByRole('button', { name: /source: chembl/i }).first()
await chip.scrollIntoViewIfNeeded()
await chip.hover()
await page.getByRole('tooltip').first().waitFor()
await page.waitForTimeout(2600)
await page.mouse.move(0, 0)
await page.waitForTimeout(400)

// 4. The kicker: and it is honest when it does not have something.
await page.goto(`${BASE}/drugs/${ADC}`)
await page.getByTestId('not-applicable').first().waitFor()
await page.waitForTimeout(2600)

await context.close()
await browser.close()
console.log(`recorded to ${OUT}/`)
