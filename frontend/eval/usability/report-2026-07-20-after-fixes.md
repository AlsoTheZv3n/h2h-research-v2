# Usability & comprehension report — 2026-07-20 (verification, after the label fixes)

**This is the acceptance re-run** of `report-2026-07-20.md` after the three confirmed findings were fixed (excerpt labels, the catalog link, and the `unexploited` → "no drug anywhere" wording). Compare against the findings report of the same date. Verdict summary at the end of the Triage section.

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Partial` → the reader assumed: _The drug is only partially effective_
- **[osimertinib-potency]** `On-target IC50, excluding off-target assays` → the reader assumed: _The potency is measured against all targets, not just the ones it's intended for_
- **[osimertinib-potency]** `nM median` → the reader assumed: _This means that 12.66 nM is the middle value of the measurements_
- **[unexploited-targets]** `score ≥ 0.5 · 12,475 with any evidence` → the reader assumed: _a score of 0.5 or higher indicates a target is associated with the cancer_
- **[unexploited-targets]** `Drug status: is there a drug against this target anywhere? (Open Targets, any indication)` → the reader assumed: _this refers to whether there is any kind of treatment or therapy targeting the specific gene_
- **[epidemiology-most-common]** `Age-standardised mortality rate — deaths, not incidence` → the reader assumed: _The number of new cases per year_
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _The total number of deaths in the EU_
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _A specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI` → the reader assumed: _A measure of confidence interval, but unclear what it means in this context_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from a database or source called 'ChEMBL'_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are phases of clinical trials, with 'NA' meaning not applicable_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note about how the data was collected_
- **[pipeline-rollup]** `score ≥ 0.5 · 12,475 with any evidence` → the reader assumed: _this line is unrelated to the pipeline count_
- **[chat-unsupported]** `the source was unavailable` → the reader assumed: _the website or database that stores the evidence is down_
- **[target-associated-cancers]** `Open Targets association score` → the reader assumed: _a measure of how strongly EGFR is associated with each cancer_
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _an identifier or code for non-small cell lung carcinoma_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the trials were matched based on the exact wording used in ClinicalTrials.gov to describe the interventions_

## Summary

- Tasks: 10 — completed **2** yes, 6 partially, 2 no, 0 unparseable
- Tasks with at least one misread label: **10**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Partial` → assumed _The drug is only partially effective_
- **Assumptions:** I assumed that 'Approved' means the program has been approved by regulatory agencies.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What is the on-target potency of osimertinib, and how reliable is that number? State the value and explain what it is measured over.

- **Completed:** partially
- **Reader's answer:** The on-target potency of osimertinib is measured as the median IC50 value of 12.66 nM over 62 exact on-target measurements, with a range of 0.9–480,000 nM.
- **Expected (known):** A median (12.66 nM) with a range over the EXACT on-target measurements (62), off-target and censored rows excluded -- a decision-grade summary, NOT a raw count of all activities.
- **Terms misread:** `On-target IC50, excluding off-target assays` → assumed _The potency is measured against all targets, not just the ones it's intended for_; `nM median` → assumed _This means that 12.66 nM is the middle value of the measurements_
- **Assumptions:** I assumed that 'on-target' refers to the drug's intended target, EGFR.
- **Stuck at:** —
- **Labels this task stresses:** _the potency summary: median + range over exact on-target measurements_ · _"N of M rows excluded" (off-target / censored)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `score ≥ 0.5 · 12,475 with any evidence` → assumed _a score of 0.5 or higher indicates a target is associated with the cancer_; `Drug status: is there a drug against this target anywhere? (Open Targets, any indication)` → assumed _this refers to whether there is any kind of treatment or therapy targeting the specific gene_
- **Assumptions:** I assumed that 'any evidence' in the score calculation means some level of association between the target and the cancer
- **Stuck at:** I am stuck because I don't understand how to identify a target that is biologically promising but not yet drugged anywhere in the world. The page lists targets with their associated scores, but it's unclear what 'score ≥ 0.5' means or how to interpret the presence of an approved drug for a given target.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures for mortality rate measure the number of deaths per 100,000 people in each country. The most deadly countries are Hungary and Croatia, with age-standardised mortality rates of 80.07 and 65.01 respectively.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate — deaths, not incidence` → assumed _The number of new cases per year_; `EU deaths` → assumed _The total number of deaths in the EU_
- **Assumptions:** I assumed that 'age-standardised' refers to a method of adjusting for differences in population age distribution.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% overall. However, the survival rates vary significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _A specific database or registry of cancer patients in the United States_; `95% CI` → assumed _A measure of confidence interval, but unclear what it means in this context_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of people who survive for at least 5 years after diagnosis, rather than a specific rate of survival.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from a database or source called 'ChEMBL'_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are phases of clinical trials, with 'NA' meaning not applicable_
- **Assumptions:** I assumed that the tool is trying to display data from various sources, but some sources are unavailable.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all phases and modalities.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note about how the data was collected_; `score ≥ 0.5 · 12,475 with any evidence` → assumed _this line is unrelated to the pipeline count_
- **Assumptions:** I assumed that 'in development' means all drugs listed in the pipeline, regardless of their current phase or status.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** yes
- **Reader's answer:** The tool does not have the US list price of osimertinib and could not retrieve it because its source was unavailable.
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `the source was unavailable` → assumed _the website or database that stores the evidence is down_
- **Assumptions:** I assumed that 'EVIDENCE' refers to a database or collection of information about drugs.
- **Stuck at:** —
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** partially
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. However, I'm unsure how the Open Targets association score is used to filter these associations or what it means for a cancer to have a higher score.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `Open Targets association score` → assumed _a measure of how strongly EGFR is associated with each cancer_; `MONDO_0005233` → assumed _an identifier or code for non-small cell lung carcinoma_
- **Assumptions:** I assumed that the 'Top 25' refers to the top 25 cancers out of a larger list, but I don't know what the total number of associated cancers (276) represents.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested against one other drug in 23 trials. The page does not provide information on what is excluded, only that two multi-drug trials were excluded because they had no arm-level drug assignment.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the trials were matched based on the exact wording used in ClinicalTrials.gov to describe the interventions_
- **Assumptions:** I assumed that 'arm structure' refers to how the drugs are grouped within each trial, rather than some other aspect of the trial design.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


## Triage (human)

Triaged 2026-07-20 as an acceptance check of the three fixes, against the same-date findings report. The evaluator is the same weak `llama3.1:8b`, so `completed` is noisy — the load-bearing evidence is the **answers and the misread list**, before vs after.

### Acceptance — the three fixes, before → after

| Fix | Acceptance bar | Before (findings run) | After (this run) | Verdict |
|---|---|---|---|---|
| **1 — excerpt labels** | combinations reports the **totals**, not the example count | reader answered "**5** combinations, **4** comparisons" (the example rows) | reader answered "**311** trials in combination, **23** in comparison" — the summary totals — and nailed the distinction ("combination = single arm with ≥2 drugs; comparison = separate single-drug arms") | **PASS.** The "Examples — N of TOTAL" headings closed the confusion. |
| **2 — the `℞` glyph** | the catalog link is not read as a status | the bare `℞` was read as "a symbol indicating approval/availability of a drug" (a status) | the `℞`-as-status misread is **gone** — no misread of the "in catalog ↗" link at all | **PASS.** |
| **3 — `unexploited` wording** | the twice-failed task is solvable | reader could not parse "unexploited"; stuck on "what it means / how the status is determined" | the `unexploited` misread is **gone** — the reader reads the drug status correctly ("whether there is any treatment targeting the gene"); the badge's "no drug anywhere" is understood | **Label PASS; task still `no`.** The specific defect is resolved, but the task's residual blocker **moved** (see below). |

### Fix 3 — where the residual blocker went

The `unexploited` label is no longer the problem: this run carries **no `unexploited` misread and no `℞` misread**. The reader now reads the drug-status column and its source correctly (the caption naming Open Targets landed). But the task is still `completed: no`, and the stuck-at moved to a different label:

> _"it's unclear what 'score ≥ 0.5' means or how to interpret the presence of an approved drug for a given target."_

The remaining blocker is the **Open Targets association score** — the same `score ≥ 0.5 · N with any evidence` terminology flagged on 2026-07-19 and again on the target page this run. That is the **carried-over terminology finding explicitly deferred** from this work ("noted but out of scope… if it recurs, one terminology pass — open an issue"). It has now recurred across two runs and three tasks (unexploited-targets, pipeline-rollup, target-associated-cancers), so it qualifies for that issue.

### Bottom line

Two fixes fully verified (combinations totals; the catalog link no longer a status). The third fixed its label — the `unexploited` misread is gone and the drug status now reads correctly — but the twice-failed task is not yet fully solvable by this weak evaluator, because its remaining blocker is the **association-score metric**, a separate, deferred terminology finding (not the drug-status wording, which is done). Recommended next step for that: a single **terminology pass** on the association score (`score ≥ 0.5 · N with any evidence`), opened as its own issue — iterating further on the drug-status wording will not move it.
