# Usability & comprehension report — 2026-07-20

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `↕` → the reader assumed: _a separator between columns_
- **[kras-crowded]** `▼` → the reader assumed: _an icon indicating a dropdown menu_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section title that will explain how selectively osimertinib acts_
- **[osimertinib-potency]** `Targets ranked by potency · fold vs the most potent (log scale)` → the reader assumed: _a table or list showing the targets and their potencies relative to EGFR_
- **[unexploited-targets]** `Tbio no drug anywhere` → the reader assumed: _This target is not associated with any biological processes in the body._
- **[unexploited-targets]** `Tchem chemical matter, none approved` → the reader assumed: _There are no approved drugs targeting this protein's chemical properties._
- **[epidemiology-most-common]** `Age-standardised mortality rate — deaths, not incidence` → the reader assumed: _This is a measure of how many people die from non-small cell lung carcinoma per year._
- **[epidemiology-most-common]** `EU deaths 229,920 in 2023` → the reader assumed: _This refers to the total number of deaths from non-small cell lung carcinoma in the EU in 2023._
- **[survival-odds]** `SEER summary stage` → the reader assumed: _a specific type of cancer staging system_
- **[survival-odds]** `TNM` → the reader assumed: _another type of cancer staging system_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from ChEMBL_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are phases of clinical trials, but I'm not sure what 'NA' stands for_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note about how the data is aggregated_
- **[pipeline-rollup]** `strong association (score ≥ 0.5) · 12,475 with any evidence` → the reader assumed: _this is a separate count of drugs or targets that have some level of association_
- **[chat-unsupported]** `average sales price (ASP)` → the reader assumed: _the actual cost to the patient_
- **[target-associated-cancers]** `Open Targets association strength` → the reader assumed: _a measure of how strongly the target is associated with each cancer_
- **[target-associated-cancers]** `filtered to the catalog (strong = score ≥ 0.5)` → the reader assumed: _the list only includes cancers that are strong associations, where 'strong' means a score of at least 0.5_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact names of the drugs mentioned in the trial_
- **[drug-conclusion]** `EARLY_PHASE1` → the reader assumed: _an early phase of clinical trials_
- **[drug-conclusion]** `APPROVAL` → the reader assumed: _a stage in the approval process_
- **[cancer-conclusion]** `SEER (U.S.)` → the reader assumed: _a database of cancer patients in the United States_
- **[cancer-conclusion]** `H2H surfaces evidence; it does not predict or advise.` → the reader assumed: _the tool is a data visualization platform that presents information without making recommendations_
- **[orientation]** `H2H` → the reader assumed: _a type of data visualization_
- **[orientation]** `Phase 1+` → the reader assumed: _the drug has been tested in at least one human trial_
- **[trust]** `chembl unavailable` → the reader assumed: _that the ChEMBL database was not available or had issues with the API_
- **[trust]** `Partial` → the reader assumed: _that some data is missing, but it's unclear what percentage of data is complete_

## Summary

- Tasks: 14 — completed **2** yes, 6 partially, 6 no, 0 unparseable
- Tasks with at least one misread label: **14**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `↕` → assumed _a separator between columns_; `▼` → assumed _an icon indicating a dropdown menu_
- **Assumptions:** I assumed that the 'Approved' label indicates that the drug is currently approved for use, rather than in development.
- **Stuck at:** I'm stuck because I don't have enough information to determine if KRAS is a crowded or sparse target. The page only shows two drugs targeting KRAS, but it claims there are 3,923 results total. I need more context or data to make an informed decision.
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** partially
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR) and is selective for it, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section title that will explain how selectively osimertinib acts_; `Targets ranked by potency · fold vs the most potent (log scale)` → assumed _a table or list showing the targets and their potencies relative to EGFR_
- **Assumptions:** I assumed that 'fold' in the Targets ranked by potency section refers to a logarithmic scale, as it is often used in scientific contexts.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `Tbio no drug anywhere` → assumed _This target is not associated with any biological processes in the body._; `Tchem chemical matter, none approved` → assumed _There are no approved drugs targeting this protein's chemical properties._
- **Assumptions:** I assumed that 'strong association (score ≥ 0.5)' means a score of at least 0.5 is required for a target to be considered associated with the cancer.
- **Stuck at:** I am stuck because I need to identify one target that has no drug anywhere in the world, but I'm not sure how to determine this from the information provided.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures for mortality rates measure the number of deaths per 100k people in each country. The most common and deadliest countries for non-small cell lung carcinoma are not explicitly stated, but based on the provided data, it appears that Hungary has one of the highest age-standardised mortality rates.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate — deaths, not incidence` → assumed _This is a measure of how many people die from non-small cell lung carcinoma per year._; `EU deaths 229,920 in 2023` → assumed _This refers to the total number of deaths from non-small cell lung carcinoma in the EU in 2023._
- **Assumptions:** I assumed that the country figures are for non-small cell lung carcinoma specifically, as it is not explicitly stated.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% for all stages. However, the survival rates vary significantly depending on the stage at diagnosis: localized (65.5%), regional (38.2%), and distant (10.5%).
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER summary stage` → assumed _a specific type of cancer staging system_; `TNM` → assumed _another type of cancer staging system_
- **Assumptions:** I assumed that 'relative survival' means the percentage of people who survive for at least 5 years after diagnosis, compared to a matched general population.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from ChEMBL_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are phases of clinical trials, but I'm not sure what 'NA' stands for_
- **Assumptions:** I assumed that the tool is trying to aggregate data from multiple sources and display it on this page.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note about how the data is aggregated_; `strong association (score ≥ 0.5) · 12,475 with any evidence` → assumed _this is a separate count of drugs or targets that have some level of association_
- **Assumptions:** I assumed that 'in development' means all stages of development, from pre-registration to approved.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `average sales price (ASP)` → assumed _the actual cost to the patient_
- **Assumptions:** I assumed that ASP is a common term in this context, but I'm not sure what it specifically means.
- **Stuck at:** The tool does not provide an answer to my question about the US list price of osimertinib.
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** partially
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The association strength is indicated by a score (strong or moderate) and a numerical value (e.g., 0.85). However, I'm unsure what the 'catalog' refers to in the context of filtering associated cancers.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `Open Targets association strength` → assumed _a measure of how strongly the target is associated with each cancer_; `filtered to the catalog (strong = score ≥ 0.5)` → assumed _the list only includes cancers that are strong associations, where 'strong' means a score of at least 0.5_
- **Assumptions:** I assumed that the numerical values (e.g., 0.85) represent some kind of statistical measure or confidence level.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested against one other drug in 23 trials. However, I couldn't determine what's excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact names of the drugs mentioned in the trial_
- **Assumptions:** I assumed that '≥2 drugs' refers to two or more different types of drugs, not just multiple instances of the same drug.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


### drug-conclusion — After reading this whole drug page, what would you CONCLUDE about the drug overall -- what is it, how strong is the evidence, and would you act on it (e.g. prioritise it for an EGFR-driven cancer)? Answer as a one-paragraph conclusion, not a list of fields.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** Osimertinib is an APPROVED (phase 4), SELECTIVE EGFR inhibitor (most potent on EGFR, ~8.8 nM, no other target within 100x) with a large trial and literature base -- a well-evidenced, actionable EGFR-targeted therapy; act: yes, for an EGFR-driven cancer. A reader should reach this WITHOUT assembling it from scattered blocks.
- **Terms misread:** `EARLY_PHASE1` → assumed _an early phase of clinical trials_; `APPROVAL` → assumed _a stage in the approval process_
- **Assumptions:** I assumed that 'Well-studied: 384 registered trials' means that there are 384 trials with some level of evidence, but I'm not sure what 'registered' implies.
- **Stuck at:** I got stuck trying to understand the implications of the information on this page and how it relates to my task. The page provides a lot of data, but I'm having trouble synthesizing it into a conclusion about the drug overall.
- **Labels this task stresses:** _a page-level synthesis the reader can conclude from, not eight separate blocks_ · _the conclusion is supported by the data: approved + selective for EGFR + deep evidence_


### cancer-conclusion — After reading this whole cancer page, what would you CONCLUDE -- what is the therapeutic landscape, and where is the opportunity or the risk? Answer as a one-paragraph conclusion, not a list of blocks.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** NSCLC has strongly-associated, druggable targets with approved drugs (EGFR, KRAS) and a large development pipeline, but ALSO high-association targets with no drug anywhere -- the unexploited opportunity; survival is strongly stage-dependent. A reader should reach a "so what" (the druggable landscape plus the unexploited gap) without assembling it from separate blocks.
- **Terms misread:** `SEER (U.S.)` → assumed _a database of cancer patients in the United States_; `H2H surfaces evidence; it does not predict or advise.` → assumed _the tool is a data visualization platform that presents information without making recommendations_
- **Assumptions:** I assumed that 'non-small cell lung carcinoma' refers to a specific type of cancer, and the statistics provided are relevant to this disease.
- **Stuck at:** The page does not provide enough information to conclude the therapeutic landscape, opportunities, or risks for non-small cell lung carcinoma. The data on targets, pipeline, survival rates, and trial reality is presented, but it is unclear how these pieces fit together to form a comprehensive picture of the disease.
- **Labels this task stresses:** _a page-level "so what": the druggable landscape plus the unexploited gap, not separate blocks_ · _the conclusion is supported: approved targets, pipeline size, unexploited high-association targets_


### orientation — First time seeing this tool. After three minutes on it, what is this tool FOR -- and what is it NOT for? Answer in your own words, as if telling a colleague whether to open it.

- **Completed:** yes
- **Reader's answer:** This tool appears to be a database of oncology drugs and their associated cancers. It provides information on the drug's mechanism of action, clinical trials, and literature references. However, it does not seem to be suitable for finding new treatments or making predictions about cancer biology.
- **Expected (known):** HYPOTHESIS (human triage): the tool is a research / drug-intelligence view of oncology evidence -- sourced, provenance-linked facts about drugs, cancers and targets, with a page-level synthesis of them. It is NOT clinical decision support, NOT medical advice, and does not predict or rank treatments (it "surfaces evidence; it does not predict"). Passes if the reader names both the purpose and the not-for boundary; fails if the tool reads as a treatment recommender or a clinical tool.
- **Terms misread:** `H2H` → assumed _a type of data visualization_; `Phase 1+` → assumed _the drug has been tested in at least one human trial_
- **Assumptions:** I assumed that the 'Full brief' option on the detail page would provide a comprehensive summary of the drug's information.
- **Stuck at:** —
- **Labels this task stresses:** _the product tagline + the Drugs|Cancers scope = what the tool is for_ · _the "surfaces evidence; does not predict" / "not clinical decision support" boundary = what it is NOT for_


### trust — Looking at this drug page, what here would you NOT trust, and why? Does anything make you doubt the tool itself -- or is it being candid about what it does and does not have?

- **Completed:** partially
- **Reader's answer:** I would not trust the 'chembl unavailable' labels, as they indicate that some information is missing, but I'm unsure what this means in terms of data quality or completeness. The tool seems to be candid about its limitations and sources.
- **Expected (known):** HYPOTHESIS (human triage): the amber "source unavailable" advisory should read as CANDOUR -- the tool being honest that ChEMBL was down (a pipeline gap, with a retry), not as the tool being broken or the drug lacking a mechanism. A sceptical reader may rightly say a source_failed section is not evidence of absence, and that empties mean "measured none / not yet gathered". Passes if the gaps read as the tool being candid about its provenance; FAILS (feeds back into copy) if they read as "unfinished", "half-built" or a reason to distrust the tool itself.
- **Terms misread:** `chembl unavailable` → assumed _that the ChEMBL database was not available or had issues with the API_; `Partial` → assumed _that some data is missing, but it's unclear what percentage of data is complete_
- **Assumptions:** I assumed that 'chembl unavailable' means that the ChEMBL database was not able to provide the requested information, rather than a technical issue with the tool itself.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = candour about a pipeline gap, not "broken"_ · _source_failed / empty shown honestly = trust-building, not "unfinished"_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

This is the **Epic D gate** ("verify usefulness, not just labels"), against the prior baseline `report-2026-07-20-epic-c.md`. Epic D added **no app code** — only two harness tasks: **D2 orientation** ("what is this tool for, and NOT for?") and **D3 trust** ("what here would you not trust, and why?"). Their answers are **hypotheses for human triage**, not checkable expected answers. The 12 shared tasks run against byte-identical surfaces, so every completion swing below is llama3.1:8b non-determinism, not a regression.

**The two new usefulness dimensions:**

| Task | Verdict | Triage |
| --- | --- | --- |
| **orientation** (D2) | yes | **PASS — the orientation surface communicates its own purpose.** In three minutes the reader named BOTH halves: the purpose (*"a database of oncology drugs and their associated cancers… mechanism, clinical trials, literature"*) AND the not-for boundary (*"it does not seem to be suitable for finding new treatments or making predictions"*) — exactly the "surfaces evidence; does not predict" line. Misreads: `Phase 1+` → *"tested in ≥1 human trial"* is a **correct** reading (dismiss); `H2H` → *"a data visualization"* is the one genuine nit — the product **name** alone does not orient, but the tagline + nav did the work, so orientation still succeeded. A tagline that expands "H2H" is an optional, low-priority polish. |
| **trust** (D3) | partially | **PASS — the project's core bet holds: the honest gap read as candour, not "unfinished".** The reader said *"the tool seems to be candid about its limitations and sources"* and, load-bearingly, attributed the gap to the **source, not the tool**: *"'chembl unavailable' means ChEMBL was not able to provide the information, rather than a technical issue with the tool itself."* That is the whole differentiator confirmed on a real page. Residual: the reader was *"unsure what this means in terms of data quality or completeness."* The `SourceAdvisory` copy already answers this directly (*"a gap in our pipeline, not a finding about this drug… what's shown below is what we could gather"*), and the reader read candour — so **no copy change is forced** (chasing a single weak model's mild uncertainty against copy that already addresses it would be over-fixing a passing result). Optional, human-decidable micro-idea: surface the count of affected sources on the advisory. Misreads `chembl unavailable` and `Partial` are correct/near-correct readings (dismiss). |

**The 12 shared tasks (unchanged surfaces) — every swing is model noise:**

| Task | Epic C → Epic D | Read |
| --- | --- | --- |
| kras-crowded | partially → no | Overview untouched; reader still describes a crowded KRAS field. |
| osimertinib-potency | yes → partially | Potency card untouched; answer still correct, model narrated titles. |
| chat-unsupported | yes → no | The ask box hits Ollama — the **same** model as the evaluator, so the two contend during a run (documented since Epic A). Untouched grounding guard. |
| target-associated-cancers | yes → partially | Target page untouched. |
| drug-conclusion | partially → no | Drug synthesis panel still renders (verified live); model did not compose a paragraph. |
| unexploited / epidemiology / survival / source-failed / pipeline / observed-combinations / cancer-conclusion | unchanged | Untouched surfaces; afatinib outage fixture confirmed intact (18 unavailable). |

**Verdict: Epic D delivers its goal.** The harness now measures usefulness across three axes — conclude (D1), orient (D2), trust (D3) — and on the real app both new dimensions pass: a first-time reader orients in three minutes and reads the honest gaps as candour, not as a half-built tool. No app regression; no copy change warranted. **D4** (twenty minutes with a real oncologist) remains open (#77) — human user research, out of scope for the harness and for me to execute.
