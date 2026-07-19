import { chromium } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseJudgment, RESEARCHER_SYSTEM, resolveEvaluator, type Judgment } from './evaluator'
import { TASKS, type Task } from './tasks'

/**
 * Usability & comprehension harness (Playwright + an LLM evaluator).
 *
 * Drives the REAL running app, captures the rendered page text (and a screenshot) for each task,
 * and asks a model -- role-playing an oncology researcher who sees only that page -- to work the
 * task. The output is a REPORT, never a CI gate: an LLM judgement is non-deterministic, and as
 * pass/fail it would be flaky or vacuously green. A human triages the findings; a confident
 * critique is not a validated defect until confirmed.
 *
 * Run (from frontend/, with the stack up):  pnpm exec tsx eval/usability/run.ts
 * Base URL:   HARNESS_BASE_URL, else E2E_BASE_URL (the e2e convention), else
 *             http://localhost:${FRONTEND_PORT:-5173} -- the compose frontend's default port
 * Model:      ANTHROPIC_API_KEY -> Claude; else Ollama (OLLAMA_URL, llama3.1:8b). No model -> exit.
 */

const BASE =
  process.env.HARNESS_BASE_URL ??
  process.env.E2E_BASE_URL ??
  `http://localhost:${process.env.FRONTEND_PORT ?? 5173}`
const OUT_DIR = 'eval/usability'
const CAP_DIR = join(OUT_DIR, 'captures')

interface Result {
  task: Task
  url: string
  judgment: Judgment
  error?: string
}

function taskPrompt(task: Task, url: string, text: string): string {
  return `Your task: "${task.question}"

Here is the TEXT of the page you are looking at (URL: ${url}):
---
${text.slice(0, 8000)}
---

Work the task using ONLY the page text above -- you cannot see the code, the README, or anything else. Then reply with JSON ONLY (no prose outside the JSON):
{
  "completed": "yes" | "no" | "partially",
  "answer": "<your answer to the task, in your own words, 1-3 sentences>",
  "termsMisread": [{"term": "<exact wording from the page that confused you>", "assumed": "<what you GUESSED it meant>"}],
  "assumptions": ["<any assumption you had to make to proceed>"],
  "stuckAt": "<where you got stuck, or an empty string if you finished>"
}`
}

async function main(): Promise<void> {
  const evaluator = await resolveEvaluator() // throws (and exits) if no model -- never a stub
  console.log(`Evaluator: ${evaluator.name}\nBase: ${BASE}\nTasks: ${TASKS.length}\n`)
  mkdirSync(CAP_DIR, { recursive: true })

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } })
  const results: Result[] = []

  for (const task of TASKS) {
    console.log(`[${task.id}] ${task.question.slice(0, 68)}...`)
    try {
      const { url, text } = await task.capture(page, BASE)
      await page
        .screenshot({ path: join(CAP_DIR, `${task.id}.png`), fullPage: true })
        .catch(() => undefined)
      const raw = await evaluator.complete(RESEARCHER_SYSTEM, taskPrompt(task, url, text))
      const judgment = parseJudgment(raw)
      results.push({ task, url, judgment })
      console.log(`   -> completed=${judgment.completed}  misread=${judgment.termsMisread.length}`)
    } catch (e) {
      results.push({ task, url: '', judgment: parseJudgment(''), error: String(e) })
      console.log(`   -> ERROR ${String(e).slice(0, 140)}`)
    }
  }
  await browser.close()

  const date = new Date().toISOString().slice(0, 10)
  const path = join(OUT_DIR, `report-${date}.md`)
  writeFileSync(path, renderReport(evaluator.name, date, results))
  console.log(`\nWrote ${path} and ${CAP_DIR}/*.png`)
}

function renderReport(model: string, date: string, results: Result[]): string {
  const misreads = results.flatMap((r) =>
    r.judgment.termsMisread.map((m) => ({ task: r.task.id, ...m })),
  )
  const done = (v: string) => results.filter((r) => r.judgment.completed === v).length

  const lines: string[] = [
    `# Usability & comprehension report — ${date}`,
    '',
    `**Evaluator:** \`${model}\` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).`,
    '',
    `**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).`,
    '',
    '## Misread labels — the primary output',
    '',
    misreads.length === 0
      ? '_The evaluator reported no misread labels._'
      : misreads
          .map((m) => `- **[${m.task}]** \`${m.term}\` → the reader assumed: _${m.assumed}_`)
          .join('\n'),
    '',
    '## Summary',
    '',
    `- Tasks: ${results.length} — completed **${done('yes')}** yes, ${done('partially')} partially, ${done('no')} no, ${results.filter((r) => !r.error && r.judgment.completed === 'unknown').length} unparseable`,
    `- Tasks with at least one misread label: **${results.filter((r) => r.judgment.termsMisread.length > 0).length}**`,
    `- Harness errors (navigation/model): ${results.filter((r) => r.error).length}`,
    '',
    '## Per task',
    '',
  ]

  for (const r of results) {
    const j = r.judgment
    lines.push(
      `### ${r.task.id} — ${r.task.question}`,
      '',
      `- **Completed:** ${j.completed}`,
      `- **Reader's answer:** ${j.answer || '—'}`,
      `- **Expected (known):** ${r.task.expected}`,
      `- **Terms misread:** ${
        j.termsMisread.length
          ? j.termsMisread.map((m) => `\`${m.term}\` → assumed _${m.assumed}_`).join('; ')
          : '_none reported_'
      }`,
      `- **Assumptions:** ${j.assumptions.length ? j.assumptions.join('; ') : '_none_'}`,
      `- **Stuck at:** ${j.stuckAt ?? '—'}`,
      `- **Labels this task stresses:** ${r.task.labels.map((l) => `_${l}_`).join(' · ')}`,
      r.error ? `- **Harness error:** ${r.error}` : '',
      '',
    )
  }

  lines.push(
    '## Triage (human)',
    '',
    'For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.',
    '',
    '_Pending triage._',
    '',
  )
  return lines.join('\n')
}

main().catch((e) => {
  console.error(String(e))
  process.exit(1)
})
