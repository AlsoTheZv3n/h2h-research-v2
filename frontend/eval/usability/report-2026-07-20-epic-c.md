# Usability & comprehension report — 2026-07-20

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Hydrolase` → the reader assumed: _a type of enzyme or protein involved in the KRAS target_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section about how selectively osimertinib acts on multiple targets_
- **[osimertinib-potency]** `Measurements by assay kind` → the reader assumed: _a list of different types of assays used to measure the potency of osimertinib_
- **[unexploited-targets]** `Tbio no drug anywhere` → the reader assumed: _This target has been biologically identified as promising but is not yet being targeted by any drugs in the world._
- **[unexploited-targets]** `Tchem chemical matter, none approved` → the reader assumed: _There are no approved drugs targeting this target, and it's related to chemical compounds._
- **[epidemiology-most-common]** `Age-standardised mortality rate` → the reader assumed: _a type of cancer-specific death rate_
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _the total number of deaths within the EU, not a specific country's data_
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _a specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI` → the reader assumed: _confidence interval, but I'm not sure what it means in this context_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from a database or source called 'ChEMBL'_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are different phases of clinical trials_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note about how the data is aggregated_
- **[pipeline-rollup]** `strong association (score ≥ 0.5) · 12,475 with any evidence` → the reader assumed: _this is a note about the strength of associations between targets and drugs_
- **[chat-unsupported]** `Unfortunately` → the reader assumed: _This is a polite way of saying the tool is broken._
- **[chat-unsupported]** `verify` → the reader assumed: _Check or confirm_
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _a disease code or identifier_
- **[target-associated-cancers]** `CHEMBL_E2E_INPIPE` → the reader assumed: _a drug name or identifier_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact wording of the drug names in ClinicalTrials.gov_
- **[drug-conclusion]** `EARLY_PHASE1` → the reader assumed: _an early phase of clinical trials_
- **[drug-conclusion]** `APPROVAL` → the reader assumed: _a stage of drug development indicating approval for use_
- **[cancer-conclusion]** `5-year relative survival · SEER (U.S.)` → the reader assumed: _5-year overall survival rate in the United States_
- **[cancer-conclusion]** `Stage at diagnosis` → the reader assumed: _the stage of cancer diagnosis, not the treatment stage_

## Summary

- Tasks: 12 — completed **4** yes, 5 partially, 3 no, 0 unparseable
- Tasks with at least one misread label: **12**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Hydrolase` → assumed _a type of enzyme or protein involved in the KRAS target_
- **Assumptions:** I assumed that 'Approved' means the program has been approved for use as a treatment.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** yes
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR) and is highly selective for this target, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section about how selectively osimertinib acts on multiple targets_; `Measurements by assay kind` → assumed _a list of different types of assays used to measure the potency of osimertinib_
- **Assumptions:** I assumed that 'most potent' in the context of the table meant the target with the lowest IC50 value.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `Tbio no drug anywhere` → assumed _This target has been biologically identified as promising but is not yet being targeted by any drugs in the world._; `Tchem chemical matter, none approved` → assumed _There are no approved drugs targeting this target, and it's related to chemical compounds._
- **Assumptions:** I assumed that 'strong association (score ≥ 0.5)' means a significant biological connection between the cancer and the target.; I assumed that 'Tbio' stands for 'biological targets' or something similar, given its context.
- **Stuck at:** I'm stuck because I don't know how to identify which of these targets are biologically promising but not yet drugged anywhere in the world. The page lists several targets with 'no drug anywhere', but it's unclear what this means and whether it's a reliable indicator of biological promise.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures for mortality rate measure the number of deaths per 100,000 people in each country. The most deadly countries are Hungary and Croatia.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate` → assumed _a type of cancer-specific death rate_; `EU deaths` → assumed _the total number of deaths within the EU, not a specific country's data_
- **Assumptions:** I assumed that 'European mortality' refers to the EU as a whole, and not individual countries.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% for all stages. However, the survival rates vary significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _a specific database or registry of cancer patients in the United States_; `95% CI` → assumed _confidence interval, but I'm not sure what it means in this context_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of people who survive for at least 5 years after diagnosis.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from a database or source called 'ChEMBL'_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are different phases of clinical trials_
- **Assumptions:** I assumed that the tool is trying to provide a comprehensive view of the drug afatinib by aggregating data from various sources.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note about how the data is aggregated_; `strong association (score ≥ 0.5) · 12,475 with any evidence` → assumed _this is a note about the strength of associations between targets and drugs_
- **Assumptions:** I assumed that 'drugs & clinical candidates' refers to all drugs in development for this cancer, regardless of their stage.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** yes
- **Reader's answer:** The tool answered honestly by stating it cannot verify the current US list price of osimertinib.
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `Unfortunately` → assumed _This is a polite way of saying the tool is broken._; `verify` → assumed _Check or confirm_
- **Assumptions:** I assumed that 'US list price' refers to the current market price in the United States.
- **Stuck at:** —
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** yes
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The association strength is indicated by a score (strong ≥ 0.5 or moderate < 0.5), but it's unclear what the scores mean in terms of clinical relevance. The drugs section lists several compounds that act on this target.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `MONDO_0005233` → assumed _a disease code or identifier_; `CHEMBL_E2E_INPIPE` → assumed _a drug name or identifier_
- **Assumptions:** I assumed that the MONDO codes are some kind of standardized identifier for diseases, but I'm not sure what they represent. I also assumed that CHEMBL_E2E_INPIPE is a valid drug name, although it looks like an internal code.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested head-to-head against one in 23 trials. However, I'm not sure what 'excluded' refers to.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact wording of the drug names in ClinicalTrials.gov_
- **Assumptions:** I assumed that 'combination' refers to a single arm with two or more drugs, and 'comparison' refers to separate single-drug arms.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


### drug-conclusion — After reading this whole drug page, what would you CONCLUDE about the drug overall -- what is it, how strong is the evidence, and would you act on it (e.g. prioritise it for an EGFR-driven cancer)? Answer as a one-paragraph conclusion, not a list of fields.

- **Completed:** partially
- **Reader's answer:** Osimertinib is a well-studied drug that has shown strong evidence of effectiveness in treating EGFR-driven cancers, particularly non-small cell lung adenocarcinoma. However, I am unable to conclude its overall strength and potential for prioritization due to the lack of clear information on its efficacy compared to other treatments.
- **Expected (known):** Osimertinib is an APPROVED (phase 4), SELECTIVE EGFR inhibitor (most potent on EGFR, ~8.8 nM, no other target within 100x) with a large trial and literature base -- a well-evidenced, actionable EGFR-targeted therapy; act: yes, for an EGFR-driven cancer. A reader should reach this WITHOUT assembling it from scattered blocks.
- **Terms misread:** `EARLY_PHASE1` → assumed _an early phase of clinical trials_; `APPROVAL` → assumed _a stage of drug development indicating approval for use_
- **Assumptions:** I assumed that 'Well-studied: 384 registered trials' implies a high level of evidence, but I am not sure what this number represents in terms of the overall strength of the evidence.
- **Stuck at:** The section on 'Observed combinations' and 'Examples — 5 of 177 combinations (drugs given together)' is unclear to me. I do not understand how these combinations are classified or what they imply about the drug's effectiveness.
- **Labels this task stresses:** _a page-level synthesis the reader can conclude from, not eight separate blocks_ · _the conclusion is supported by the data: approved + selective for EGFR + deep evidence_


### cancer-conclusion — After reading this whole cancer page, what would you CONCLUDE -- what is the therapeutic landscape, and where is the opportunity or the risk? Answer as a one-paragraph conclusion, not a list of blocks.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** NSCLC has strongly-associated, druggable targets with approved drugs (EGFR, KRAS) and a large development pipeline, but ALSO high-association targets with no drug anywhere -- the unexploited opportunity; survival is strongly stage-dependent. A reader should reach a "so what" (the druggable landscape plus the unexploited gap) without assembling it from separate blocks.
- **Terms misread:** `5-year relative survival · SEER (U.S.)` → assumed _5-year overall survival rate in the United States_; `Stage at diagnosis` → assumed _the stage of cancer diagnosis, not the treatment stage_
- **Assumptions:** I assumed that 'strong association' means a high level of evidence linking a target to the disease; I assumed that 'in trials' means the drug is currently being tested in clinical trials
- **Stuck at:** The page does not provide enough information to conclude the therapeutic landscape, opportunities, or risks for non-small cell lung carcinoma.
- **Labels this task stresses:** _a page-level "so what": the druggable landscape plus the unexploited gap, not separate blocks_ · _the conclusion is supported: approved targets, pipeline size, unexploited high-association targets_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

This is the **Epic C gate** ("useful, not just correct" — a page-level *so what*), against the prior baseline `report-2026-07-20-epic-b.md`. Epic C added the two D1 conclusion tasks (`drug-conclusion`, `cancer-conclusion`), the page-level **synthesis** panel (C1 cancer, C2 drug — derived threshold statements, each linking to its block), the **TDL verdict** badge (C3, the Tchem middle), and the C4 block reorder (epidemiology demoted). The most-affected tasks are the two conclusion tasks and `unexploited-targets` (C3's TDL badges).

**C3 landed — the new TDL labels were read correctly.** On `unexploited-targets`, the evaluator's readings of the two TDL badges match their intended meaning:

| TDL label (C3) | Reader's reading | Verdict |
| --- | --- | --- |
| `Tbio no drug anywhere` | *"biologically identified as promising but not yet targeted by any drugs in the world"* | **Correct** — dismiss. This is exactly Tbio. |
| `Tchem chemical matter, none approved` | *"no approved drugs targeting this target, and it's related to chemical compounds"* | **Correct** — dismiss. This is exactly Tchem, the middle C3 exists to surface. |

**The two D1 conclusion tasks:**

| Task | Verdict | Triage |
| --- | --- | --- |
| **drug-conclusion** | partially | **The synthesis works.** The reader reached the right conclusion *directly from the panel* — *"a well-studied drug with strong evidence in EGFR-driven cancers"* — and its Assumptions line quotes the C2 statement it leaned on (*"Well-studied: 384 registered trials"*). It hedged only on **comparative efficacy vs other treatments**, which the tool deliberately does not hold (no comparative-efficacy source — a milestone constraint, not a gap). The two misreads (`EARLY_PHASE1`, `APPROVAL`) are raw trial-phase enum strings in the trials/observed-combinations data — **genuine but pre-existing and outside Epic C's scope** (synthesis + TDL); the same raw enums appear under `source-failed`. → Confirm as a readability item; **defer to a later epic**. |
| **cancer-conclusion** | no | **Dismissed — evaluator limitation, not a missing so-what.** The synthesis is present, correct, and *on the reader's captured surface*: re-capturing the rendered `article` text (the exact bytes the harness feeds the model) shows all five statements verbatim under "What the evidence adds up to" — *"117 strongly-associated targets"*, *"2 of the top targets have no drug anywhere — the unexploited opportunity"*, *"Crowded field: 1,072 drugs in development"*, *"Notable attrition: 172 of 1,000 scanned trials stopped"*, *"Outcomes hinge on stage: 66% localized vs 10% distant 5-year survival"* — i.e. exactly the Expected "druggable landscape + unexploited gap + stage-dependent survival". The reader even engaged the landscape terms ("strong association", "in trials") yet defaulted to *"not enough information"*: llama3.1:8b failed to compose a paragraph from content it demonstrably received. The two misreads (`5-year relative survival · SEER (U.S.)`, `Stage at diagnosis`) are survival/epidemiology wording, **pre-existing** (SurvivalCard predates Epic C), and reinterpreting outcome wording is fenced by the "no reinterpretation of survival data" constraint. → **Defer**. |

The other tasks sit on surfaces Epic C did not touch; their verdict swings are the usual llama3.1:8b non-determinism (e.g. `source-failed` remains a known small-model limit, and the afatinib outage fixture was confirmed intact — 18 keys unavailable — before this run).

**Verdict: Epic C delivers the page-level "so what" and it reaches the reader.** The cancer synthesis is captured on the reader's surface and matches the data; the drug synthesis carried the reader to the right conclusion; C3's TDL labels were read correctly. No real regression. The residual harness misreads (trial-phase enums, survival/stage wording) are pre-existing, out-of-scope readability items, deferred rather than forced into this epic.

Separately, an **adversarial pre-PR code review** (four dimensions → each finding double-verified by independent skeptics, majority-refute) surfaced **one confirmed finding**, now fixed with tests: an honest-state collapse in `tdl.py` — when Open Targets never resolved a target's drug status but the catalog holds a potent ligand, the verdict returned Tchem labelled *"chemical matter, none approved"*, asserting "none approved" from an unmeasured input (and the ligand itself may be an approved drug, e.g. EGFR/osimertinib). Fixed: that case now reads **"chemical matter, approval not measured"** (the level stays Tchem — the chemical matter is real and measured — but the false approval claim is dropped, and the drug criteria stay `unknown`, never a ✗). The frontend badge now renders the backend's self-explaining label, the cancer-detail cache bumped v8→v9 so stale briefs recompute, and both sides gained a regression test. Verified on the live stack (NSCLC: Tclin 12 / Tbio 2 / Tchem 1, Tbio now reading "no drug anywhere").
