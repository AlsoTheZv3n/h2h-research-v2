# Usability & comprehension report — 2026-07-21

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[sponsor-normalisation]** `Counts are normalised — a company's subsidiaries are merged onto one name` → the reader assumed: _The count is the total number of trials sponsored by each company, including all its subsidiaries._

## Summary

- Tasks: 1 — completed **0** yes, 1 partially, 0 no, 0 unparseable
- Tasks with at least one misread label: **1**
- Harness errors (navigation/model): 0

## Per task

### sponsor-normalisation — Read the "Top sponsors" list in the trial-reality block. Are these the raw sponsor names exactly as ClinicalTrials.gov records them, or something else -- and what does that mean for the counts?

- **Completed:** partially
- **Reader's answer:** The 'Top sponsors' list appears to be a normalized list of company names, with subsidiaries merged onto one name. However, I'm unsure whether the counts (e.g., 24 for AstraZeneca) represent the exact number of trials sponsored by each company or some other metric.
- **Expected (known):** Something else: the counts are NORMALISED -- a company's subsidiaries are merged onto one canonical name (Pfizer absorbs Seagen/Wyeth/Array; the counts therefore differ from, and are larger than, any single raw string). The card says so. The reader should NOT read the list as the literal raw ClinicalTrials.gov strings.
- **Terms misread:** `Counts are normalised — a company's subsidiaries are merged onto one name` → assumed _The count is the total number of trials sponsored by each company, including all its subsidiaries._
- **Assumptions:** I assumed that 'normalised' means the counts are adjusted to account for subsidiaries being merged into their parent companies.
- **Stuck at:** —
- **Labels this task stresses:** _the counts are NORMALISED (subsidiaries merged), not raw leadSponsor strings_ · _a canonical company name stands for several raw strings -> its count is larger than any one_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

### #39 gate — the normalised sponsor counts (a focused, single-task run)

One task pointed the reader at the new "Top sponsors" list; the question is whether the reader reads the counts as RAW leadSponsor strings (wrong) or understands they are NORMALISED (subsidiaries merged). It holds — DISMISS:

- The reader's own answer is correct: *"a normalized list of company names, with subsidiaries merged onto one name."* It got the point exactly.
- The flagged misread — `Counts are normalised … merged onto one name` → *"the count is the total number of trials sponsored by each company, including all its subsidiaries"* — is ALSO correct: that is precisely what a normalised count is. Not a defect.
- "partially" reflects only a hedge (*"unsure whether the counts represent the exact number of trials or some other metric"*), not a misreading of the normalisation.

**Verdict:** the "normalised — subsidiaries merged" label reads correctly; a reader does not mistake the merged counts for raw leadSponsor strings. **#39 ships.**
