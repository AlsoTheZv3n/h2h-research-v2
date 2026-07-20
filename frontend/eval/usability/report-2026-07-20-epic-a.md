# Usability & comprehension report — 2026-07-20

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Hydrolase` → the reader assumed: _a type of enzyme_
- **[kras-crowded]** `Modality Phase` → the reader assumed: _the stage of development for the drug, but unclear what 'Phase' refers to_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section title indicating where to find information about selectivity and potency_
- **[osimertinib-potency]** `Targets ranked by potency · fold vs the most potent (log scale)` → the reader assumed: _a table or list showing the targets in order of potency, with a log scale used for comparison_
- **[unexploited-targets]** `score ≥ 0.5 · 12,475 with any evidence` → the reader assumed: _a score of at least 0.5 is required to be considered associated with the target_
- **[unexploited-targets]** `Drug status: is there a drug against this target anywhere? (Open Targets, any indication)` → the reader assumed: _this refers to whether there is any drug available for treatment, regardless of its effectiveness or stage of development_
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _the number of deaths in Europe due to non-small cell lung carcinoma_
- **[epidemiology-most-common]** `Age-standardised mortality rate — deaths, not incidence — per 100 000` → the reader assumed: _a measure of the number of deaths from non-small cell lung carcinoma per 100,000 people, adjusted for age_
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _a specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI 29.3%–29.7%` → the reader assumed: _a statistical measure indicating that the true survival rate is likely between 29.3% and 29.7%_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the value of this field is not available or has been removed_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are phases of clinical trials, but I'm not sure what each abbreviation stands for_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a technical term that means the count might be inflated due to some kind of data aggregation_
- **[pipeline-rollup]** `score ≥ 0.5 · 12,475 with any evidence` → the reader assumed: _this line is irrelevant to the task at hand and can be ignored_
- **[chat-unsupported]** `US list price` → the reader assumed: _the current market price of osimertinib in the United States_
- **[target-associated-cancers]** `Open Targets association score` → the reader assumed: _a measure of how strongly EGFR is associated with each cancer_
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _an identifier for non-small cell lung carcinoma_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact name of the drug, rather than its chemical structure or other characteristics_

## Summary

- Tasks: 10 — completed **3** yes, 4 partially, 3 no, 0 unparseable
- Tasks with at least one misread label: **10**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Hydrolase` → assumed _a type of enzyme_; `Modality Phase` → assumed _the stage of development for the drug, but unclear what 'Phase' refers to_
- **Assumptions:** I assumed that 'Approved' means the program is in a late stage of development and has been approved by regulatory agencies.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** yes
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR) and is highly selective for this target, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section title indicating where to find information about selectivity and potency_; `Targets ranked by potency · fold vs the most potent (log scale)` → assumed _a table or list showing the targets in order of potency, with a log scale used for comparison_
- **Assumptions:** I assumed that 'fold' meant a multiplier or ratio, rather than a specific unit of measurement.; I assumed that 'log scale' referred to a logarithmic scale, which is commonly used in scientific measurements.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `score ≥ 0.5 · 12,475 with any evidence` → assumed _a score of at least 0.5 is required to be considered associated with the target_; `Drug status: is there a drug against this target anywhere? (Open Targets, any indication)` → assumed _this refers to whether there is any drug available for treatment, regardless of its effectiveness or stage of development_
- **Assumptions:** I assumed that 'associated targets' means targets that are biologically associated with the cancer; I assumed that 'undrugged' means no approved drugs or clinical candidates targeting this specific target
- **Stuck at:** I am stuck because I need to identify one target that is not yet drugged anywhere in the world, but I don't see any clear indication of which targets meet this criterion.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures measure age-standardised mortality rate per 100,000 for non-small cell lung carcinoma. The most common countries are not explicitly stated in the provided text, but it can be inferred that they are likely those with higher rates. The most deadly countries are also not explicitly stated, but based on the highest rates, some of the top contenders include Hungary, Croatia, and Serbia.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `EU deaths` → assumed _the number of deaths in Europe due to non-small cell lung carcinoma_; `Age-standardised mortality rate — deaths, not incidence — per 100 000` → assumed _a measure of the number of deaths from non-small cell lung carcinoma per 100,000 people, adjusted for age_
- **Assumptions:** I assumed that 'EU' refers to Europe as a whole, and not a specific country or region.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** yes
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of around 29.5% across all stages. However, this rate varies significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _a specific database or registry of cancer patients in the United States_; `95% CI 29.3%–29.7%` → assumed _a statistical measure indicating that the true survival rate is likely between 29.3% and 29.7%_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of patients who survive for at least 5 years after diagnosis, compared to a matched general population.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the information was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the value of this field is not available or has been removed_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are phases of clinical trials, but I'm not sure what each abbreviation stands for_
- **Assumptions:** I assumed that 'chembl' refers to the ChEMBL database, which is mentioned at the bottom of the page.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a technical term that means the count might be inflated due to some kind of data aggregation_; `score ≥ 0.5 · 12,475 with any evidence` → assumed _this line is irrelevant to the task at hand and can be ignored_
- **Assumptions:** I assumed that 'drugs & clinical candidates' refers specifically to drugs in development for non-small cell lung carcinoma, rather than a broader category of compounds.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `US list price` → assumed _the current market price of osimertinib in the United States_
- **Assumptions:** I assumed that 'Reading this drug's facts and literature...' means the tool is attempting to retrieve information from a database or external source.
- **Stuck at:** The page does not provide any answer to my question, it only displays a progress message.
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** partially
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. However, I'm unsure how the Open Targets association score is used to filter the catalog or what makes these cancers relevant.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `Open Targets association score` → assumed _a measure of how strongly EGFR is associated with each cancer_; `MONDO_0005233` → assumed _an identifier for non-small cell lung carcinoma_
- **Assumptions:** I assumed that the Open Targets association score is a measure of relevance, but I'm not sure what it represents or how it's calculated.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested head-to-head against one in 23 trials. However, I couldn't determine what is excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact name of the drug, rather than its chemical structure or other characteristics_
- **Assumptions:** I assumed that 'combination' refers to two or more drugs being given together in a single trial arm.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

This run is the **Epic A gate**: it re-runs the harness over the rebuilt drug potency surface (the `osimertinib-potency` task) and confirms the other nine surfaces — which Epic A did not touch — did not regress. Each task's before→after delta was triaged independently (one verifier per task, each reading the actual source), against the prior baseline `report-2026-07-20-after-fixes.md`.

**Verdict: gate passes. 0 of 10 findings are actionable label defects.**

| Task | before → after | Triage | Actionable? |
| --- | --- | --- | --- |
| **osimertinib-potency** | partially → **yes** | **Epic A improvement** — the reader now reads "EGFR, 8.81 nM, highly selective" off the rebuilt card. The two "misreads" are the small model narrating the self-explanatory card title/subtitle, and its glosses ("fold" = ratio, "log scale" = logarithmic) are correct. | no |
| survival-odds | partially → yes | Model non-determinism — SurvivalCard untouched; both misreads ("SEER (U.S.)", "95% CI") are correct readings. | no |
| chat-unsupported | yes → no | Harness flake — the capture snapshot landed on the live-Ollama loading state before the grounded refusal rendered (the task waits on the real chat model). Surface untouched. The `US list price` "misread" is the question text the harness itself typed, not a page label. | no |
| kras-crowded | partially → partially | Model non-determinism — OverviewPage untouched; "Hydrolase"/"Modality Phase" are correct glosses of self-explanatory column headers. | no |
| epidemiology-most-common | partially → partially | Model non-determinism — "EU deaths" and the ASR label read correctly; residual "partially" is a question-comprehension gap (omitted the C33–C34 roll-up), not a label. | no |
| pipeline-rollup | yes → yes | Model non-determinism — the roll-up label already preempts the "inflated?" concern; the score-≥0.5 string belongs to a different card. | no |
| unexploited-targets | no → no | Known small-model limit — both terms read correctly (the R4 "no drug anywhere" wording landed); the task just never completes for this model. | no |
| source-failed | no → no | Known small-model limit — afatinib's outage advisory read correctly ("a pipeline gap"); the model is unsure of ChEMBL/trial-phase domain terms. **Fixture confirmed intact** (it had been accidentally enriched, then reseeded to `source_failed`). | no |
| target-associated-cancers | partially → partially | Model non-determinism — "association score"/"MONDO_0005233" read correctly; AssociatedCancersCard untouched. | no |
| observed-combinations | partially → partially | Model non-determinism — "≥2 drugs"/"matched by drug name" read correctly with the soft-match caveat; CombinationsCard untouched. | no |

The epic-gate acceptance ("golden set green + no headline contradicts the mechanism card") was verified separately against the real stack: vatalanib → VEGFR2 (54 nM), imatinib → PDGFRα (agreeing with its Bcr/Abl mechanism targets), osimertinib → EGFR — each headline now agreeing with its mechanism card.
