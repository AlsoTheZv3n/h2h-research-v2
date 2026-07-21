# Usability & comprehension report — 2026-07-21

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[extracted-not-curated]** `PubTator3 (NLM), NLP over the literature` → the reader assumed: _a specific database or tool that extracts and verifies facts from the literature_
- **[extracted-not-curated]** `co-mentions — how many papers mention both` → the reader assumed: _the number of studies that have found a link between this target and each disease/drug_

## Summary

- Tasks: 1 — completed **0** yes, 1 partially, 0 no, 0 unparseable
- Tasks with at least one misread label: **1**
- Harness errors (navigation/model): 0

## Per task

### extracted-not-curated — On this target (EGFR) page, read the "Extracted literature relations" block. Should you trust these relations the same way as the rest of the page (the associated cancers, the mutation frequency), or are they a different kind of thing? What does the count mean?

- **Completed:** partially
- **Reader's answer:** The 'Extracted literature relations' block appears to be a different kind of thing from the rest of the page. The count in this section refers to co-mentions, which is a measure of attention, not evidence.
- **Expected (known):** A DIFFERENT kind: these are machine-EXTRACTED (NLP) co-occurrences from the literature, NOT curated/verified facts like the rest of the page — the block says so, in a set-apart frame. So they should be trusted LESS / treated as leads, not settled facts. The count is CO-MENTIONS (how many papers mention both), a measure of attention/volume, NOT of evidence strength.
- **Terms misread:** `PubTator3 (NLM), NLP over the literature` → assumed _a specific database or tool that extracts and verifies facts from the literature_; `co-mentions — how many papers mention both` → assumed _the number of studies that have found a link between this target and each disease/drug_
- **Assumptions:** I assumed that 'machine-extracted, not curated' meant that these relations were automatically generated from the literature without human review.
- **Stuck at:** —
- **Labels this task stresses:** _"Extracted, not curated" = a different, lower-confidence kind of evidence than the curated cards_ · _the count is co-mentions (attention/volume), NOT curated evidence weight_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

### #44 gate — "extracted, not curated" (the reason this run exists)

The whole point of the PubTator card is that a reader must NOT read machine-extracted co-occurrences as curated facts. One task tests exactly that. It holds — DISMISS the flags:

- The reader's own answer is exactly right on BOTH load-bearing points: *"a **different** kind of thing from the rest of the page"* (extracted ≠ curated — the distinct frame + banner worked), and *"the count refers to **co-mentions, a measure of attention, not evidence**"* (volume, not weight). The reader's stated assumption — "machine-extracted, not curated" means "automatically generated from the literature without human review" — is the correct reading.
- The two flagged misreads are pedantic and contradicted by the reader's own answer: reading PubTator as a tool that *"extracts and verifies"* (it extracts; the reader nonetheless concluded "not curated/verified") and co-mentions as *"studies that found a link"* (the reader nonetheless said "attention, not evidence"). Secondary-phrasing over-reads, not a failure of the card.

**Verdict:** the "extracted, not curated" distinction and the co-mention framing read correctly — a reader treats these as leads, not settled facts. **#44 ships.**
