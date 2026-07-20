import type { Page } from '@playwright/test'

/**
 * The comprehension tasks. Every task has an expected answer we ALREADY know, so success is
 * checkable rather than vibes, and a `labels` list naming the honest-state wording it stresses --
 * the labels a misreading would incriminate. Deterministic parts (navigation, order, expected
 * answers) live here in code; only the judgement is generated.
 */

export interface Capture {
  url: string
  text: string
}

export interface Task {
  id: string
  question: string
  /** The answer we already know -- for human triage, and to say whether the reader got the point. */
  expected: string
  /** The on-screen labels this task stresses; if the evaluator misreads one, the label failed. */
  labels: string[]
  /** Navigate to the relevant surface and return the visible text the evaluator will read. */
  capture: (page: Page, base: string) => Promise<Capture>
}

const OSIMERTINIB = 'CHEMBL3353410'
const AFATINIB = 'CHEMBL1173655' // seeded with a ChEMBL outage -> the calm amber advisory
const NSCLC = 'MONDO_0005233'
const EGFR_TARGET = 'ENSG00000146648' // the target page (#37): EGFR, the cancers it drives
// A high-volume drug for the observed-combinations card (#38): thousands of trials, so the
// scan caps (scanned < total) and a few are dropped-ambiguous -- the full honest card.
const PEMBROLIZUMAB = 'CHEMBL3137343'

/** The header (h1 + the stat cards) plus one named section of a cancer page -- what a reader
 *  focusing on that block actually sees. */
async function cancerSection(page: Page, base: string, section: string): Promise<Capture> {
  await page.goto(`${base}/cancers/${NSCLC}`, { waitUntil: 'networkidle' })
  const sec = page.locator(`#${section}`)
  await sec.waitFor({ timeout: 30_000 })
  await sec.scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  const header = await page
    .locator('article header')
    .first()
    .innerText()
    .catch(() => '')
  const stats = await page
    .locator('dl')
    .first()
    .innerText()
    .catch(() => '')
  const body = await sec.innerText().catch(() => '')
  return { url: `${base}/cancers/${NSCLC}#${section}`, text: `${header}\n\n${stats}\n\n${body}` }
}

async function drugPage(page: Page, base: string, id: string, waitText: RegExp): Promise<Capture> {
  await page.goto(`${base}/drugs/${id}`, { waitUntil: 'networkidle' })
  await page.getByText(waitText).first().waitFor({ timeout: 30_000 })
  await page.waitForTimeout(400)
  const text = await page
    .locator('article')
    .first()
    .innerText()
    .catch(() => '')
  return { url: `${base}/drugs/${id}`, text }
}

/** The header plus one named section of a DRUG page (e.g. the observed-combinations card),
 *  scoped to that block so the reader is judged on that surface, not the whole brief. */
async function drugSection(
  page: Page,
  base: string,
  id: string,
  section: string,
): Promise<Capture> {
  await page.goto(`${base}/drugs/${id}`, { waitUntil: 'networkidle' })
  const sec = page.locator(`#${section}`)
  await sec.waitFor({ timeout: 30_000 })
  await sec.scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  const header = await page
    .locator('article header, h1')
    .first()
    .innerText()
    .catch(() => '')
  const body = await sec.innerText().catch(() => '')
  return { url: `${base}/drugs/${id}#${section}`, text: `${header}\n\n${body}` }
}

/** The target detail page (#37): the header plus the associated-cancers and catalog-drugs
 *  sections -- what a reader focusing on "what does this gene do" actually sees. */
async function targetPage(page: Page, base: string, id: string): Promise<Capture> {
  await page.goto(`${base}/targets/${id}`, { waitUntil: 'networkidle' })
  const ac = page.locator('#associated-cancers')
  await ac.waitFor({ timeout: 30_000 })
  await page.waitForTimeout(400)
  const header = await page
    .locator('article header, h1')
    .first()
    .innerText()
    .catch(() => '')
  const cancers = await ac.innerText().catch(() => '')
  const drugs = await page
    .locator('#catalog-drugs')
    .innerText()
    .catch(() => '')
  return { url: `${base}/targets/${id}`, text: `${header}\n\n${cancers}\n\n${drugs}` }
}

export const TASKS: Task[] = [
  {
    id: 'kras-crowded',
    question:
      'You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?',
    expected:
      'Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.',
    labels: ['the drug table: approved vs clinical', 'the filtered total count'],
    capture: async (page, base) => {
      await page.goto(`${base}/?q=kras`, { waitUntil: 'networkidle' })
      await page.getByTestId('drug-row').first().waitFor({ timeout: 30_000 })
      const total = await page
        .getByTestId('total-count')
        .innerText()
        .catch(() => '')
      const table = await page
        .locator('table')
        .first()
        .innerText()
        .catch(() => '')
      return { url: `${base}/?q=kras`, text: `Result count: ${total}\n\n${table}` }
    },
  },
  {
    id: 'osimertinib-potency',
    question:
      'What is the on-target potency of osimertinib, and how reliable is that number? State the value and explain what it is measured over.',
    expected:
      'A median (12.66 nM) with a range over the EXACT on-target measurements (62), off-target and censored rows excluded -- a decision-grade summary, NOT a raw count of all activities.',
    labels: [
      'the potency summary: median + range over exact on-target measurements',
      '"N of M rows excluded" (off-target / censored)',
    ],
    capture: (page, base) => drugPage(page, base, OSIMERTINIB, /Binding & potency/),
  },
  {
    id: 'unexploited-targets',
    question:
      'For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.',
    expected:
      'A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.',
    labels: [
      '"unexploited" = no drug anywhere (the world) — the highest-stakes label',
      '"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"',
    ],
    capture: (page, base) => cancerSection(page, base, 'target-landscape'),
  },
  {
    id: 'epidemiology-most-common',
    question:
      'Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.',
    expected:
      'The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.',
    labels: [
      'ASR — age-standardised mortality rate, deaths per 100k, not incidence',
      'the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"',
    ],
    capture: (page, base) => cancerSection(page, base, 'epidemiology'),
  },
  {
    id: 'survival-odds',
    question:
      'What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.',
    expected:
      '5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.',
    labels: [
      '"5-year relative survival" (against a matched population), a population stat not a prognosis',
      'SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up',
    ],
    capture: (page, base) => cancerSection(page, base, 'survival'),
  },
  {
    id: 'source-failed',
    question:
      'This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?',
    expected:
      'A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool\'s pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".',
    labels: [
      'the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug',
      'source_failed vs "measured, none found"',
    ],
    capture: (page, base) => drugPage(page, base, AFATINIB, /couldn.t be reached|unavailable|gather/i),
  },
  {
    id: 'pipeline-rollup',
    question:
      'How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.',
    expected:
      'The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).',
    labels: [
      'the pipeline count = an ontology roll-up (broader + narrower indications)',
      '"N of M are in the catalog and open a brief" — a separate, weaker link signal',
    ],
    capture: (page, base) => cancerSection(page, base, 'pipeline'),
  },
  {
    id: 'chat-unsupported',
    question:
      'Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?',
    expected:
      'An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug\'s stored facts + abstracts, so a price question has no grounded answer.',
    labels: ['the chat\'s honest "not in the retrieved evidence" = working as designed, not broken'],
    capture: async (page, base) => {
      await page.goto(`${base}/drugs/${OSIMERTINIB}`, { waitUntil: 'networkidle' })
      await page.getByTestId('ask-input').waitFor({ timeout: 30_000 })
      await page.getByTestId('ask-input').fill('What is the US list price of osimertinib in dollars?')
      await page.getByTestId('ask-submit').click()
      // The ask box runs the REAL chat model (Ollama here) and can be slow: wait for the pending
      // state to appear then clear, then read the whole ask section (question + answer / no-answer).
      await page
        .getByTestId('ask-pending')
        .waitFor({ state: 'visible', timeout: 8000 })
        .catch(() => undefined)
      await page
        .getByTestId('ask-pending')
        .waitFor({ state: 'detached', timeout: 180_000 })
        .catch(() => undefined)
      await page.waitForTimeout(600)
      const text = await page
        .getByTestId('ask')
        .innerText()
        .catch(() => '')
      return { url: `${base}/drugs/${OSIMERTINIB} (ask box)`, text }
    },
  },
  {
    id: 'target-associated-cancers',
    question:
      'You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?',
    expected:
      "The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.",
    labels: [
      'associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)',
      '"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"',
    ],
    capture: (page, base) => targetPage(page, base, EGFR_TARGET),
  },
  {
    id: 'observed-combinations',
    question:
      'Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?',
    expected:
      'Two DISTINCT counts from the trials\' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug\'s trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.',
    labels: [
      'combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct',
      'the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample',
    ],
    capture: (page, base) => drugSection(page, base, PEMBROLIZUMAB, 'combinations'),
  },
]
