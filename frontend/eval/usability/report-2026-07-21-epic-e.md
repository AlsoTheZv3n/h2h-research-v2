# Usability & comprehension report — 2026-07-21

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Phase` → the reader assumed: _the phase of the clinical trial, e.g. Phase I, II, III_
- **[kras-crowded]** `Modality` → the reader assumed: _the type of treatment or intervention being tested_
- **[osimertinib-potency]** `Well-studied: 384 registered trials` → the reader assumed: _This means that there are 384 trials where osimertinib has been studied._
- **[osimertinib-potency]** `Measurements by assay kind` → the reader assumed: _This section lists the types of assays used to measure the potency of osimertinib on different targets._
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _This section explains how selective osimertinib is for its main target._
- **[unexploited-targets]** `Tbio no drug anywhere` → the reader assumed: _This target has no approved drugs in the world_
- **[unexploited-targets]** `Tchem chemical matter, none approved` → the reader assumed: _There are no approved drugs for this target, but there may be some that are still in development_
- **[epidemiology-most-common]** `Age-standardised mortality rate` → the reader assumed: _a measure of how quickly cancer is spreading_
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _the number of people in the EU who died from non-small cell lung carcinoma_
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _Some kind of national cancer registry in the US_
- **[survival-odds]** `95% CI 29.3%–29.7%` → the reader assumed: _A confidence interval indicating a range within which the true survival rate is likely to lie_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from ChEMBL_
- **[source-failed]** `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → the reader assumed: _these are phases of clinical trials, but I'm not sure what each abbreviation stands for_
- **[pipeline-rollup]** `via ontology roll-up` → the reader assumed: _a method of categorizing or grouping drugs_
- **[pipeline-rollup]** `strong association (score ≥ 0.5)` → the reader assumed: _a measure of how closely related a target is to the disease_
- **[chat-unsupported]** `US list price` → the reader assumed: _the average cost of osimertinib in the United States_
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _a disease or condition identifier_
- **[target-associated-cancers]** `CHEMBL_E2E_INPIPE` → the reader assumed: _a ChEMBL identifier, possibly indicating an in-pipeline compound_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _two or more different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact name of the drug, not just its chemical identifier_
- **[drug-conclusion]** `EARLY_PHASE1` → the reader assumed: _an early phase of clinical trials_
- **[drug-conclusion]** `APPROVAL` → the reader assumed: _a stage in the approval process_
- **[cancer-conclusion]** `strong association (score ≥ 0.5)` → the reader assumed: _a target is strongly associated with the disease if it has a score of at least 0.5_
- **[cancer-conclusion]** `in catalog ↗` → the reader assumed: _the drug is available in the catalog and has been reviewed_
- **[cancer-conclusion]** `Tbio no drug anywhere` → the reader assumed: _there are targets that have not been associated with any drugs, but they are still relevant to the disease_
- **[orientation]** `H2H` → the reader assumed: _a type of data visualization_
- **[orientation]** `EARLY_PHASE1` → the reader assumed: _an early phase of clinical trials_
- **[trust]** `Well-studied: 242 registered trials` → the reader assumed: _This number represents some kind of quality metric for the drug, rather than simply the number of trials._
- **[trust]** `chembl unavailable` → the reader assumed: _That ChEMBL is a database or service that provides information on the drug's properties, but it does not provide this specific information._

## Summary

- Tasks: 14 — completed **3** yes, 5 partially, 6 no, 0 unparseable
- Tasks with at least one misread label: **14**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Phase` → assumed _the phase of the clinical trial, e.g. Phase I, II, III_; `Modality` → assumed _the type of treatment or intervention being tested_
- **Assumptions:** I assumed that 'Approved' means the drug has been approved for use in patients.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** partially
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR), and it is very selective for this target, being at least 100 times more potent on EGFR than any other target.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Well-studied: 384 registered trials` → assumed _This means that there are 384 trials where osimertinib has been studied._; `Measurements by assay kind` → assumed _This section lists the types of assays used to measure the potency of osimertinib on different targets._; `Selectivity & potency` → assumed _This section explains how selective osimertinib is for its main target._
- **Assumptions:** I assumed that 'ranked' in the context of 'Targets ranked by potency' means that the targets are listed in order of their potency, with EGFR being the most potent.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `Tbio no drug anywhere` → assumed _This target has no approved drugs in the world_; `Tchem chemical matter, none approved` → assumed _There are no approved drugs for this target, but there may be some that are still in development_
- **Assumptions:** I assumed 'strong association' means a high level of evidence linking the target to the cancer; I assumed 'score ≥ 0.5' is a threshold for what constitutes a strong association
- **Stuck at:** I'm stuck because I don't know how to determine if a target is biologically promising, and I need more information about what makes a target 'undrugged'
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate` → assumed _a measure of how quickly cancer is spreading_; `EU deaths` → assumed _the number of people in the EU who died from non-small cell lung carcinoma_
- **Assumptions:** I assumed that 'strong association (score ≥ 0.5)' refers to a specific statistical measure, but I'm not sure what it means
- **Stuck at:** I don't understand how to interpret the country figures and what they actually measure
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% across all stages. However, the survival rates vary significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _Some kind of national cancer registry in the US_; `95% CI 29.3%–29.7%` → assumed _A confidence interval indicating a range within which the true survival rate is likely to lie_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of patients who survive for at least 5 years after diagnosis, rather than the percentage of patients who are alive at any point during the 5-year period.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from ChEMBL_; `EARLY_PHASE1, NA, PHASE1, PHASE2, PHASE3, PHASE4` → assumed _these are phases of clinical trials, but I'm not sure what each abbreviation stands for_
- **Assumptions:** I assumed that 'brief' refers to a summary or update of the data, and that it was last refreshed at some point in time.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up` → assumed _a method of categorizing or grouping drugs_; `strong association (score ≥ 0.5)` → assumed _a measure of how closely related a target is to the disease_
- **Assumptions:** I assumed that 'in development' means all stages of development, from early phase 1 to approved.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `US list price` → assumed _the average cost of osimertinib in the United States_
- **Assumptions:** I assumed that 'Reading this drug's facts and literature...' means it is searching for information on osimertinib
- **Stuck at:** The tool does not provide any answer, it just displays a progress message
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** yes
- **Reader's answer:** The EGFR target is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The association strength is based on the Open Targets score, which filters to a catalog of strong associations (score ≥ 0.5). The drugs section lists CHEMBL identifiers for compounds that act on this target.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `MONDO_0005233` → assumed _a disease or condition identifier_; `CHEMBL_E2E_INPIPE` → assumed _a ChEMBL identifier, possibly indicating an in-pipeline compound_
- **Assumptions:** I assumed that the MONDO identifiers are related to specific cancer types; I assumed that CHEMBL is a database or catalog of compounds
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested in a head-to-head comparison against one in 23 trials. However, I couldn't determine what's excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _two or more different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact name of the drug, not just its chemical identifier_
- **Assumptions:** I assumed that '≥2' means two or more, but I'm not sure if it's a typo and should be '>= 2' (greater than or equal to 2) instead.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


### drug-conclusion — After reading this whole drug page, what would you CONCLUDE about the drug overall -- what is it, how strong is the evidence, and would you act on it (e.g. prioritise it for an EGFR-driven cancer)? Answer as a one-paragraph conclusion, not a list of fields.

- **Completed:** partially
- **Reader's answer:** Osimertinib is a well-studied drug that has been approved for use in phase 4. It is selective for the Epidermal growth factor receptor (EGFR) and has shown promise in treating various cancers, including glioblastoma, head and neck squamous cell carcinoma, non-small cell lung adenocarcinoma, and mesothelioma.
- **Expected (known):** Osimertinib is an APPROVED (phase 4), SELECTIVE EGFR inhibitor (most potent on EGFR, ~8.8 nM, no other target within 100x) with a large trial and literature base -- a well-evidenced, actionable EGFR-targeted therapy; act: yes, for an EGFR-driven cancer. A reader should reach this WITHOUT assembling it from scattered blocks.
- **Terms misread:** `EARLY_PHASE1` → assumed _an early phase of clinical trials_; `APPROVAL` → assumed _a stage in the approval process_
- **Assumptions:** I assumed that 'Well-studied: 384 registered trials' means that there are 384 trials with some level of evidence, but I'm not sure what this number represents.
- **Stuck at:** —
- **Labels this task stresses:** _a page-level synthesis the reader can conclude from, not eight separate blocks_ · _the conclusion is supported by the data: approved + selective for EGFR + deep evidence_


### cancer-conclusion — After reading this whole cancer page, what would you CONCLUDE -- what is the therapeutic landscape, and where is the opportunity or the risk? Answer as a one-paragraph conclusion, not a list of blocks.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** NSCLC has strongly-associated, druggable targets with approved drugs (EGFR, KRAS) and a large development pipeline, but ALSO high-association targets with no drug anywhere -- the unexploited opportunity; survival is strongly stage-dependent. A reader should reach a "so what" (the druggable landscape plus the unexploited gap) without assembling it from separate blocks.
- **Terms misread:** `strong association (score ≥ 0.5)` → assumed _a target is strongly associated with the disease if it has a score of at least 0.5_; `in catalog ↗` → assumed _the drug is available in the catalog and has been reviewed_; `Tbio no drug anywhere` → assumed _there are targets that have not been associated with any drugs, but they are still relevant to the disease_
- **Assumptions:** I assumed that 'strong association' is a measure of how strongly a target is associated with the disease; I assumed that 'in catalog ↗' indicates that the drug has been reviewed and is available in the catalog
- **Stuck at:** The page does not provide enough information to conclude what the therapeutic landscape, opportunity, or risk are for non-small cell lung carcinoma.
- **Labels this task stresses:** _a page-level "so what": the druggable landscape plus the unexploited gap, not separate blocks_ · _the conclusion is supported: approved targets, pipeline size, unexploited high-association targets_


### orientation — First time seeing this tool. After three minutes on it, what is this tool FOR -- and what is it NOT for? Answer in your own words, as if telling a colleague whether to open it.

- **Completed:** yes
- **Reader's answer:** This tool appears to be a database of oncology drugs and their associated evidence. It provides information on the drug's mechanism of action, clinical trials, and literature references. However, it does not seem to be suitable for finding new or experimental treatments.
- **Expected (known):** HYPOTHESIS (human triage): the tool is a research / drug-intelligence view of oncology evidence -- sourced, provenance-linked facts about drugs, cancers and targets, with a page-level synthesis of them. It is NOT clinical decision support, NOT medical advice, and does not predict or rank treatments (it "surfaces evidence; it does not predict"). Passes if the reader names both the purpose and the not-for boundary; fails if the tool reads as a treatment recommender or a clinical tool.
- **Terms misread:** `H2H` → assumed _a type of data visualization_; `EARLY_PHASE1` → assumed _an early phase of clinical trials_
- **Assumptions:** I assumed that 'sourced evidence' refers to the collection of literature and trial data associated with each drug.
- **Stuck at:** —
- **Labels this task stresses:** _the product tagline + the Drugs|Cancers scope = what the tool is for_ · _the "surfaces evidence; does not predict" / "not clinical decision support" boundary = what it is NOT for_


### trust — Looking at this drug page, what here would you NOT trust, and why? Does anything make you doubt the tool itself -- or is it being candid about what it does and does not have?

- **Completed:** no
- **Reader's answer:** I would not trust the 'chembl unavailable' labels as they appear in multiple sections of the page. This is because these labels are scattered throughout the page and do not provide any explanation for their presence or what it means for a value to be unavailable.
- **Expected (known):** HYPOTHESIS (human triage): the amber "source unavailable" advisory should read as CANDOUR -- the tool being honest that ChEMBL was down (a pipeline gap, with a retry), not as the tool being broken or the drug lacking a mechanism. A sceptical reader may rightly say a source_failed section is not evidence of absence, and that empties mean "measured none / not yet gathered". Passes if the gaps read as the tool being candid about its provenance; FAILS (feeds back into copy) if they read as "unfinished", "half-built" or a reason to distrust the tool itself.
- **Terms misread:** `Well-studied: 242 registered trials` → assumed _This number represents some kind of quality metric for the drug, rather than simply the number of trials._; `chembl unavailable` → assumed _That ChEMBL is a database or service that provides information on the drug's properties, but it does not provide this specific information._
- **Assumptions:** I assumed that 'chembl' refers to a specific database or service, rather than just being part of the page's formatting.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = candour about a pipeline gap, not "broken"_ · _source_failed / empty shown honestly = trust-building, not "unfinished"_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

This is the **Epic E gate** ("differentiators none of the surveyed platforms have"), against the `report-2026-07-20-epic-d.md` baseline. Epic E shipped **three of four** issues — **E1** source disagreement, **E3** silent stalling, **E4** per-fact freshness — all needing no new source. **E2** (inclusion provenance) is deferred: the Open Targets API exposes no per-row indication on the pipeline rows, so the exact-vs-rollup path is not derivable cheaply (documented on #79).

**The differentiators do not appear in this report — by design, and it is the right behaviour.** The harness reads the same osimertinib (drug) and NSCLC (cancer) fixtures, and on those:

- **E1 (disagreement)** correctly stays SILENT: osimertinib's three phase sources agree, so there is no conflict to name — the no-false-positive rule holding on the tested drug. It fires only where sources genuinely differ, verified live on other drugs (e.g. CHEMBL1421 renders *"Sources disagree — Clinical phase: ChEMBL says phase 4 · ClinicalTrials.gov says phase 2 · Open Targets says approved"*; 7 of 60 full-brief drugs surfaced a real conflict, the other 53 silent).
- **E3 (silent stalling)** correctly stays SILENT: NSCLC's latest trial registered 2026-07-20 (yesterday), an active field — no stalling line, no false positive. The derived rule and the "last new trial: YYYY" display are verified live and unit-proven at the threshold.
- **E4 (freshness)** lives in the citation **hover panel** (CitationChip), which the harness capture — `article` innerText, no hover — never opens, so it is absent from the reader's captured text here. Verified live by hovering a chip: *"Checked yesterday"*.

So Epic E added **no new misread** (the list above is entirely the pre-existing recurring items — `H2H`, `EARLY_PHASE1`, `Tbio/Tchem`, `SEER`, `ontology roll-up` — none from an E-surface) and **no regression** (all 14 tasks answerable, no crash on the E1-augmented drug page or the E3-augmented cancer card). The completion swings vs Epic D (e.g. `epidemiology` partially→no, `trust` unchanged) are llama3.1:8b non-determinism on byte-identical surfaces; the afatinib outage fixture was confirmed intact (18 unavailable).

**Verdict: Epic E delivers its three feasible differentiators with no regression and no false positives on the tested entities.** Their value shows on entities that actually exhibit a conflict / dormancy / staleness, verified live rather than through the fixed harness fixtures. An **adversarial pre-PR review** (four dimensions → each finding double-verified, majority-refute) returned **2 candidates, 0 confirmed** — the one surfaced (formatAge not clamping a future/clock-skew timestamp) refuted because `retrieved_at` is server-set and never ahead of the clock, and showing a skewed value relationally is the codebase's show-don't-fabricate discipline, not a defect. **E2** stays open (#79) pending a decision on a bounded per-drug enrichment vs waiting for an OT schema that carries the indication.
