import { chromium } from '@playwright/test'

/**
 * Records the README's hero GIF from the real, running app.
 *
 * Committed so the GIF is reproducible: when the UI changes, re-run this rather
 * than hand-capturing something that quietly stops matching the product. It was
 * last re-run for the detail redesign -- four cards, the source behind an "i" icon,
 * the calm advisory replacing the red field-name wall.
 *
 * Not a test. There are no assertions and the pauses are deliberately generous --
 * this is paced for a human reading a loop, not for a machine checking a condition.
 *
 * Prerequisites (both matter):
 *   - `docker compose up`, with the redesigned UI reachable at BASE
 *   - osimertinib and the ADC already enriched. A cold drug would put a lazy
 *     enrichment spinner in the hero shot, at the mercy of ChEMBL's mood.
 *
 * Run:  pnpm exec tsx e2e/demo.record.ts
 */

const BASE = process.env.DEMO_BASE_URL ?? 'http://localhost:5175'
const OUT = process.env.DEMO_OUT ?? 'demo-recording'

// osimertinib: a complete brief -- the product working.
const OSIMERTINIB = 'CHEMBL3353410'
// afatinib: a real drug whose last refresh hit a source outage -- the calm advisory.
const AFATINIB = 'CHEMBL1173655'
// trastuzumab deruxtecan: a biologic -- the product being honest.
const ADC = 'CHEMBL4297844'

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: { width: 1000, height: 720 },
  recordVideo: { dir: OUT, size: { width: 1000, height: 720 } },
  deviceScaleFactor: 1,
})
const page = await context.newPage()

// 1. Open straight on the brief: the molecule beside the distilled potency, four
//    calm cards -- "real science, distilled". No toy table in the way.
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
await page.waitForTimeout(2800)
await page.mouse.move(0, 0)
await page.waitForTimeout(400)

// 3. Honest when a source is down. A real drug whose last refresh hit a ChEMBL outage:
//    the structure still draws, and a calm amber advisory says the picture is partial,
//    not wrong -- a gap in our pipeline, with a button to look again. This is the red
//    field-name wall the old GIF showed, redesigned into something that does not alarm.
await page.goto(`${BASE}/drugs/${AFATINIB}`)
await page.getByTestId('source-advisory').waitFor()
await page.waitForTimeout(2600)

// 4. Honest when it does not have something at all. The ADC is a biologic -- no
//    small-molecule structure or binding curve to show -- and the page says so calmly,
//    never a broken card.
await page.goto(`${BASE}/drugs/${ADC}`)
await page.getByTestId('not-applicable').first().waitFor()
await page.waitForTimeout(2600)

await context.close()
await browser.close()
console.log(`recorded to ${OUT}/`)
