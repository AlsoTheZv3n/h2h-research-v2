# Usability & comprehension report — 2026-07-20

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `↕` → the reader assumed: _a separator between columns_
- **[kras-crowded]** `Modality` → the reader assumed: _the type of treatment or therapy being used_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section about how selective the drug is_
- **[osimertinib-potency]** `Measurements by assay kind` → the reader assumed: _a table or list of different types of measurements_
- **[unexploited-targets]** `strong association (score ≥ 0.5)` → the reader assumed: _a high score indicating a strong biological relationship between the target and cancer_
- **[unexploited-targets]** `Drug status: is there a drug against this target anywhere?` → the reader assumed: _whether any drug has been developed or approved for use with this target, regardless of its effectiveness or specificity to NSCLC_
- **[epidemiology-most-common]** `strong association (score ≥ 0.5)` → the reader assumed: _a measure of how strongly associated a target is with the cancer_
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _the number of deaths in Europe due to non-small cell lung carcinoma_
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _a specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI 29.3%–29.7%` → the reader assumed: _the confidence interval for the 5-year relative survival rate, indicating a range within which the true value is likely to lie_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to retrieve data from a database or source named 'ChEMBL'_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are different stages of clinical trials_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note about how the data is aggregated_
- **[pipeline-rollup]** `strong association (score ≥ 0.5) · 12,475 with any evidence` → the reader assumed: _this is unrelated to the pipeline count_
- **[chat-unsupported]** `US list price` → the reader assumed: _the average wholesale price in the United States_
- **[target-associated-cancers]** `Open Targets association score` → the reader assumed: _a measure of the strength of the association between the target and each cancer type_
- **[target-associated-cancers]** `strong` → the reader assumed: _a label indicating a high association score, but it's unclear what threshold defines 'strong' vs. 'moderate'_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact name of the drug, rather than its generic or chemical name_

## Summary

- Tasks: 10 — completed **2** yes, 5 partially, 3 no, 0 unparseable
- Tasks with at least one misread label: **10**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `↕` → assumed _a separator between columns_; `Modality` → assumed _the type of treatment or therapy being used_
- **Assumptions:** I assumed that 'Approved' means the drug has been approved for use in patients, and 'Clinical-stage programs' refers to drugs that are currently being tested in clinical trials.
- **Stuck at:** I'm stuck at trying to determine if KRAS is a crowded target or not. The page shows two approved drugs targeting KRAS, but I don't know how many more there might be in total.
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** partially
- **Reader's answer:** Osimertinib mainly targets Epidermal growth factor receptor (EGFR) and is highly selective for this target, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section about how selective the drug is_; `Measurements by assay kind` → assumed _a table or list of different types of measurements_
- **Assumptions:** I assumed that 'potency' refers to the strength of the drug's action on its target.; I assumed that the numbers in the 'Targets ranked by potency' section are in nanomolar (nM) units.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `strong association (score ≥ 0.5)` → assumed _a high score indicating a strong biological relationship between the target and cancer_; `Drug status: is there a drug against this target anywhere?` → assumed _whether any drug has been developed or approved for use with this target, regardless of its effectiveness or specificity to NSCLC_
- **Assumptions:** I assumed that 'strong association' refers to the strength of biological relationship between the target and cancer, rather than a score indicating how many targets are associated with the cancer.
- **Stuck at:** I am stuck because I need to identify one target that is biologically promising but has no drug anywhere in the world. The page lists several targets with 'no drug anywhere' status, but I don't know what this means or how it was determined.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures measure age-standardised mortality rate per 100,000 for non-small cell lung carcinoma. However, the text also mentions that these figures describe a wider category (Trachea, bronchus & lung) and not specifically non-small cell lung carcinoma.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `strong association (score ≥ 0.5)` → assumed _a measure of how strongly associated a target is with the cancer_; `EU deaths` → assumed _the number of deaths in Europe due to non-small cell lung carcinoma_
- **Assumptions:** I assumed that 'strong association' refers to a statistical measure, but I'm not sure what it means or how it's calculated.; I assumed that 'EU deaths' refers specifically to deaths from non-small cell lung carcinoma in Europe, but the text also mentions European mortality and age-standardised mortality rate.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% for all stages. However, the survival rates vary significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _a specific database or registry of cancer patients in the United States_; `95% CI 29.3%–29.7%` → assumed _the confidence interval for the 5-year relative survival rate, indicating a range within which the true value is likely to lie_
- **Assumptions:** I assumed that 'SEER (U.S.)' refers to a specific database or registry of cancer patients in the United States, as it is not clear what SEER stands for without additional context.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to retrieve data from a database or source named 'ChEMBL'_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are different stages of clinical trials_
- **Assumptions:** I assumed that the term 'chembl unavailable' is a standard error message in this tool.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all phases and modalities.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note about how the data is aggregated_; `strong association (score ≥ 0.5) · 12,475 with any evidence` → assumed _this is unrelated to the pipeline count_
- **Assumptions:** I assumed that 'in development' means all drugs listed in the pipeline, regardless of their approval status.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** yes
- **Reader's answer:** The tool answered honestly that it cannot verify the current US list price of osimertinib.
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `US list price` → assumed _the average wholesale price in the United States_
- **Assumptions:** I assumed 'list price' refers to a publicly available or official pricing information.
- **Stuck at:** —
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** partially
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The relevance of these associations is based on the Open Targets association score, but it's unclear what this score represents or how it was calculated. The drugs section lists several compounds that act on this target, but their names are in a format (CHEMBL...) that I don't recognize.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `Open Targets association score` → assumed _a measure of the strength of the association between the target and each cancer type_; `strong` → assumed _a label indicating a high association score, but it's unclear what threshold defines 'strong' vs. 'moderate'_
- **Assumptions:** I assume that the Open Targets association score is a measure of the strength of the association between the target and each cancer type.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested head-to-head against one in 23 trials. However, I'm missing information on what's excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact name of the drug, rather than its generic or chemical name_
- **Assumptions:** I assumed that '≥2 drugs' refers to at least two different types of drugs being given together, not just multiple instances of the same drug.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

This is the **Epic B gate** ("every card interprets"), against the prior baseline `report-2026-07-20-epic-a.md`. Epic B touched the drug page (B1 physchem reading, B2 mechanism dedupe, B3 target order, B4 literature relevance) and the association-score surfaces (B5). The most-affected tasks by design are `unexploited-targets` and `target-associated-cancers` (B5's self-explaining score).

**The completion verdicts this run are dominated by llama3.1:8b non-determinism** — every verdict change is on a surface where the reader's answer is unchanged or still correct:

| Task | Epic A → Epic B | Read |
| --- | --- | --- |
| **unexploited-targets** | no → no | **B5 win in the misread list:** the score misread went from *"unclear what 'score ≥ 0.5' means"* (Epic A) to *"a high score indicating a strong biological relationship between the target and cancer"* (correct). The task's residual block is the drug-status label, not the score. |
| **target-associated-cancers** | partially → partially | **B5 win + one residual, now fixed:** "strong" is read correctly as "a high association score", but the reader found it *"unclear what threshold defines strong vs moderate"* — the ≥0.5 cut was disclosed only on the cancer stat. Iterated post-run: both the target-landscape and associated-cancers **card notes now state "strong = score ≥ 0.5"**. |
| osimertinib-potency | yes → partially | Grading noise — the reader's answer is still exactly correct (*"osimertinib mainly targets EGFR and is highly selective, potency 8.81 nM"*); the "misreads" are the model narrating the section titles. B1–B4's drug-page additions did not regress it. |
| kras-crowded | partially → no | Model non-determinism — the overview surface is untouched by Epic B; the reader still answered "crowded, ≥2 approved". |
| survival-odds | yes → partially | Model non-determinism — SurvivalCard untouched. |
| chat-unsupported | no → yes | The live-Ollama capture flake (Epic A) recovered this run — untouched surface. |
| epidemiology / pipeline / observed-combinations | unchanged | Untouched surfaces. |
| source-failed | no → no | Known small-model limit; **afatinib's outage fixture confirmed intact** (it had been re-seeded to source_failed after an accidental enrichment). |

**Verdict: Epic B improved the association-score interpretability (its stated goal), with no real regression** — every completion-verdict swing is noise on an unchanged surface, and B1–B4's drug-page changes left the potency reader's answer correct. The one genuine harness-surfaced gap (the strong/moderate threshold on the target page) was fixed in the same branch.

Separately, an **adversarial pre-PR code review** caught three confirmed findings (two honest-state collapses: `MechanismsFact` rendering "None annotated" on a source_failed+empty mix, and a stale `relevant_titles` masking a PubMed outage) — all fixed with tests before this gate closed.
