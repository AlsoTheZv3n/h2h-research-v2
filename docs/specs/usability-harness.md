# Spec — Usability & comprehension harness (Playwright + LLM evaluator)

**Status:** shipped — `frontend/eval/usability/`, first report `report-2026-07-19.md`. This file is the self-contained spec.

**Goal:** find out whether a domain reader **understands** the app — not whether it renders. The existing
~380 tests cover correctness (does the state render, does the filter filter, does the link resolve). None
covers comprehension: does a reader know what *ASR* means, that "1,036 drugs" includes an ontology
roll-up, or what *unexploited* actually claims? For a tool whose value is honest, precisely labelled
evidence, mislabelling is a real defect — and nothing currently tests for it.

Lives alongside the e2e setup (e.g. `frontend/eval/usability/`). Code in English.

## Design constraints (these decide whether it's useful or noise)

1. **A report, never a CI gate.** An LLM judgement is non-deterministic; as pass/fail it becomes flaky or
   vacuously green (a failure mode this project has shipped three times). Run on demand, write to a file,
   a human reads it. No green check.
2. **Task-based, not open-ended review.** "Evaluate this tool" yields plausible generalities. "Work out
   whether KRAS G12C is a crowded space" yields concrete failure points. Every task has an **expected
   answer you already know**, so success is checkable, not vibes.
3. **The evaluator sees only the rendered page.** No repo, README, NOTICE.md or source — otherwise it
   reads intent instead of experiencing the surface. Playwright drives a real browser; the evaluator
   receives page text/screenshots.
4. **Real model, real app.** Against the running stack with real data — a stub never misunderstands
   anything, so a stubbed run proves nothing.
5. **Findings need triage, not auto-fixing.** A model role-playing an oncologist produces confident
   criticism that can be wrong (e.g. "TNM stage is missing" when the page correctly states SEER summary
   stage). Generated critique ≠ validated defect. Every finding is **confirmed or dismissed by a human**
   before it becomes work; dismissed findings are recorded with the reason.

## The evaluator

System prompt, roughly: *"You are a professional oncology researcher evaluating this tool for real work.
At each step ask: does this matter to me? Is it incomplete? Am I missing information I would need? Do I
understand what this number actually means? Be specific about which wording confused you and what you
assumed instead. If you cannot complete a task, say exactly where you got stuck."*

Rules: judge only what is on screen; never speculate about implementation; when a term is unclear, say
what you *guessed* it meant — the wrong guess is the finding.

## Tasks (6–8; each with a known expected answer recorded in the harness)

1. **"Is KRAS G12C a crowded target?"** — reachable via target/pipeline views; several approved +
   clinical-stage programs.
2. **"On-target potency of osimertinib, and how reliable?"** — the distilled median + range over exact
   on-target measurements, not a raw activity count. Does the reader grasp off-target/censored exclusion?
3. **"For this cancer, which targets look promising but undrugged?"** — high association + `unexploited`.
   **Does the reader read `unexploited` as "no drug anywhere" or "not in this tool"?**
4. **"Where is this cancer most common?"** — distinguishes **burden share** from **ASR**; does not read
   the case-share doughnut as a risk map.
5. **"Survival odds for this cancer?"** — reads stages correctly, notices the diagnosis window and lag,
   does **not** treat it as an individual prognosis.
6. **"Why does this drug page show almost nothing?"** (source failed) — a pipeline gap, not a fact about
   the drug.
7. **"How many drugs in development for this cancer?"** — notices the count is an ontology **roll-up**
   (broader + narrower indications).
8. **Ask the chat something the evidence can't support** — an honest "not in the retrieved evidence",
   recognised as such, not as a broken feature.

## Output — `eval/usability/report-<date>.md`, comparable across releases

Per task: **Completed** (yes/no/partially) · **For the right reason** (expected answer via the intended
path?) · **Terms misread** (exact wording + what the reader assumed) · **Assumptions made** · **Stuck at**.
Plus a summary: tasks completed, and a **list of misread labels** — that list is the primary output.

## What to test hardest — the state labels

Nothing else in the project tests whether these are understood:
- `not available for this cancer` vs `source unavailable` vs `measured, none found` vs `not yet analysed`
- the roll-up note — *"statistics for lung cancer (C33–C34), broader than NSCLC"*
- **`drugged, no link`** vs `unexploited` — the highest-stakes distinction on the page
- the honest metric — *"322 · score ≥ 0.5 · 17,064 with any evidence"*
- the potency summary — median + range vs a raw activity count

If the evaluator misreads one, **the label failed**, not the reader.

## Implementation notes

- Playwright drives the real app (reuse the e2e config/base URL); evaluator gets page text/screenshots.
- Pre-warm the entities used so no task stalls on a cold enrichment (same discipline as the demo GIF).
- Model like the chat provider (`ANTHROPIC_API_KEY`, else a local model). **No key → say so and exit;**
  never silently degrade to a stub.
- Deterministic parts (navigation, task order, expected answers) in code; only the judgement is generated.
- Commit the harness and the reports so comprehension is tracked like any other quality signal.

## Non-goals

- Not a CI gate; no pass/fail, no branch protection, no red build from a model opinion.
- No auto-fixing; human triage first, dismissed findings recorded with the reason.
- No repo/README access for the evaluator; no fixtures/stub; a confident critique is not a defect until
  confirmed.

## Build order

Harness + one task end-to-end → verify the loop → then the remaining tasks. Report to the user in German,
leading with the misread-labels list.
