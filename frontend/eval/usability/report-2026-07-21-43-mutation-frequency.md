# Usability & comprehension report — 2026-07-21

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Full brief` → the reader assumed: _a detailed summary or description of the drug's mechanism and efficacy_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section title indicating where to find information on selectivity and potency_
- **[osimertinib-potency]** `Targets ranked by potency · fold vs the most potent (log scale)` → the reader assumed: _a table or list showing the targets ranked by their potency compared to the most potent target_
- **[unexploited-targets]** `Tbio no drug anywhere` → the reader assumed: _This target is not associated with any drugs in the treatment of non-small cell lung carcinoma, but there may be some other type of therapy or treatment that targets this gene._
- **[unexploited-targets]** `Tchem chemical matter, none approved` → the reader assumed: _There are no approved chemical compounds targeting this gene, but it's possible that there are experimental or investigational treatments being developed._
- **[mutation-frequency-coverage]** `strong association (score ≥ 0.5)` → the reader assumed: _a score of at least 50%_
- **[mutation-frequency-coverage]** `How often each landscape gene is mutated in a matched tumour cohort` → the reader assumed: _the frequency of mutations in genes that are associated with this cancer_
- **[mutation-frequency-target]** `somatic mutation (SNV/indel); excludes copy-number & fusions` → the reader assumed: _a type of genetic alteration that is not a deletion or duplication of the gene_
- **[mutation-frequency-target]** `Cohorts: TCGA PanCancer Atlas` → the reader assumed: _the specific dataset used to calculate the mutation frequency_
- **[epidemiology-most-common]** `Age-standardised mortality rate — deaths, not incidence` → the reader assumed: _I assumed this meant that the mortality rate is adjusted for age, but I'm not sure what 'deaths' and 'incidence' refer to in this context._
- **[epidemiology-most-common]** `EU deaths 229,920 in 2023` → the reader assumed: _I assumed this was a total number of deaths in the EU, but it's unclear how this relates to the mortality rates listed below._
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _a specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI 29.3%–29.7%` → the reader assumed: _the range within which the actual survival rate lies with 95% confidence_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from ChEMBL_
- **[source-failed]** `Partial` → the reader assumed: _the page only displays partial information about the drug_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note about how the data is aggregated_
- **[pipeline-rollup]** `strong association (score ≥ 0.5) · 12,475 with any evidence` → the reader assumed: _this is a separate count of associated targets_
- **[chat-unsupported]** `Unfortunately` → the reader assumed: _This is an error message, and the tool is not functioning properly._
- **[chat-unsupported]** `Is there anything else I can help you with?` → the reader assumed: _The tool is asking for further clarification or another question._
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _a unique identifier for non-small cell lung carcinoma_
- **[target-associated-cancers]** `CHEMBL1079742` → the reader assumed: _a unique identifier for a drug that acts on the EGFR target_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact name of the drug, not just its chemical identifier_
- **[drug-conclusion]** `Well-studied: 384 registered trials` → the reader assumed: _The drug has been tested in 384 clinical trials with unknown results_
- **[drug-conclusion]** `Passed all four Lipinski rules — MW ≤ 500 Da, LogP ≤ 5, ≤ 5 H-bond donors, ≤ 10 acceptors.` → the reader assumed: _The molecular weight of the drug is less than or equal to 500 Da and it has a certain number of hydrogen bond donors and acceptors_
- **[drug-conclusion]** `Selective — most potent on Epidermal growth factor receptor (8.81 nM); no other target within 100× of it` → the reader assumed: _The drug is selective for EGFR with an IC50 value of 8.81 nM, meaning that it is more than 100 times more potent against EGFR than any other target_
- **[cancer-conclusion]** `Not measured — which is not zero.` → the reader assumed: _The mutation frequency is unknown for this cancer._
- **[cancer-conclusion]** `Showing Lung and Bronchus — broader than non-small cell lung carcinoma.` → the reader assumed: _The survival rates provided are for a broader category, but the exact numbers for NSCLC are not available._
- **[cancer-conclusion]** `EU deaths` → the reader assumed: _European mortality rate for NSCLC._
- **[orientation]** `H2H surfaces evidence; it does not predict.` → the reader assumed: _H2H stands for 'Human to Human' and the sentence implies that the tool provides a way for humans to interact with the evidence, but I'm not sure what this means in practice._
- **[orientation]** `Stage (Open Targets)` → the reader assumed: _I assumed this refers to some kind of classification or categorization system within Open Targets, but I don't know what it specifically represents._
- **[trust]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from ChEMBL_
- **[trust]** `Partial` → the reader assumed: _this drug has incomplete information, but it's unclear what this means in practice_

## Summary

- Tasks: 16 — completed **5** yes, 6 partially, 5 no, 0 unparseable
- Tasks with at least one misread label: **16**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs, but I'm missing information on the number of clinical-stage programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Full brief` → assumed _a detailed summary or description of the drug's mechanism and efficacy_
- **Assumptions:** I assumed that 'Approved' means the program has already received regulatory approval, but I'm not sure what 'clinical-stage' means in this context.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** yes
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR) and is highly selective for this target, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section title indicating where to find information on selectivity and potency_; `Targets ranked by potency · fold vs the most potent (log scale)` → assumed _a table or list showing the targets ranked by their potency compared to the most potent target_
- **Assumptions:** I assumed that 'fold' in the context of 'targets ranked by potency · fold vs the most potent (log scale)' meant a ratio or multiplier, rather than an actual unit of measurement.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `Tbio no drug anywhere` → assumed _This target is not associated with any drugs in the treatment of non-small cell lung carcinoma, but there may be some other type of therapy or treatment that targets this gene._; `Tchem chemical matter, none approved` → assumed _There are no approved chemical compounds targeting this gene, but it's possible that there are experimental or investigational treatments being developed._
- **Assumptions:** I assumed that 'strong association' means a high level of evidence supporting the link between the target and non-small cell lung carcinoma.
- **Stuck at:** I'm stuck because I need to identify one target that is not yet drugged anywhere in the world, but I don't see any clear indication of which targets meet this criterion.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### mutation-frequency-coverage — Read the "Mutation frequency" block on this cancer page. Does it tell you these genes are RARELY mutated in this cancer, or is it saying something else? What is the honest reading?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** Something else: this cancer (broad NSCLC) has NO matched cBioPortal cohort, so mutation frequency is NOT MEASURED here -- explicitly "not measured, which is not zero". It is a coverage gap (only ~two dozen tumour types have a curated cohort), NOT a finding that the genes are rarely mutated. Reading "no cohort" as "low/zero mutation" is the exact None-vs-0 error the block is worded to prevent.
- **Terms misread:** `strong association (score ≥ 0.5)` → assumed _a score of at least 50%_; `How often each landscape gene is mutated in a matched tumour cohort` → assumed _the frequency of mutations in genes that are associated with this cancer_
- **Assumptions:** I assumed 'landscape gene' refers to a specific set of genes related to the cancer, but I'm not sure what it means.
- **Stuck at:** The text does not clearly state whether the mutation frequency is high or low for these genes. It mentions that there is no matched cBioPortal cohort for this cancer, which suggests that the data may be incomplete or unavailable.
- **Labels this task stresses:** _"No matched cBioPortal cohort" = a coverage gap, NOT a low frequency_ · _"not measured — which is not zero" (the None-vs-0 distinction)_


### mutation-frequency-target — On this target (EGFR) page, read the "Mutation frequency by cancer" block. In which cancer is this gene most mutated, and what does the percentage COUNT (and not count)?

- **Completed:** partially
- **Reader's answer:** The gene EGFR is most mutated in lung adenocarcinoma, with a mutation frequency of 12.4%. The percentage count refers to the proportion of samples from the TCGA PanCancer Atlas that have somatic mutations (SNV/indel) in this gene.
- **Expected (known):** EGFR is most mutated in lung adenocarcinoma (~12%), lower in the others shown. The percentage counts SOMATIC MUTATIONS ONLY (SNV/indel) in a matched cohort -- it excludes copy-number and fusions, so it is a floor on the true alteration frequency, and the block says so. A measured 0% (profiled, never mutated) is distinct from "not measured".
- **Terms misread:** `somatic mutation (SNV/indel); excludes copy-number & fusions` → assumed _a type of genetic alteration that is not a deletion or duplication of the gene_; `Cohorts: TCGA PanCancer Atlas` → assumed _the specific dataset used to calculate the mutation frequency_
- **Assumptions:** I assumed that 'somatic mutation' refers to mutations that occur in non-tumor cells, and that 'SNV/indel' is a type of genetic alteration.
- **Stuck at:** —
- **Labels this task stresses:** _the per-cancer frequency, ranked (lung adenocarcinoma highest)_ · _scope: "somatic mutation (SNV/indel)" — a floor, excludes copy-number & fusions_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures measure age-standardised mortality rate per 100,000 for non-small cell lung carcinoma. The most common countries are not explicitly stated in the provided text, but it can be inferred that they are part of the European Union (EU) based on the 'European mortality' label. However, I am unable to determine which country has the highest mortality rate.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate — deaths, not incidence` → assumed _I assumed this meant that the mortality rate is adjusted for age, but I'm not sure what 'deaths' and 'incidence' refer to in this context._; `EU deaths 229,920 in 2023` → assumed _I assumed this was a total number of deaths in the EU, but it's unclear how this relates to the mortality rates listed below._
- **Assumptions:** I assumed that 'non-small cell lung carcinoma' is the specific type of cancer being referred to, and not just a broader category as mentioned earlier on the page.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _a specific database or registry of cancer patients in the United States_; `95% CI 29.3%–29.7%` → assumed _the range within which the actual survival rate lies with 95% confidence_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of patients who survive for at least 5 years after diagnosis, compared to a matched general population.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from ChEMBL_; `Partial` → assumed _the page only displays partial information about the drug_
- **Assumptions:** I assumed that 'brief' refers to a summary of the available data, and not an external document.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note about how the data is aggregated_; `strong association (score ≥ 0.5) · 12,475 with any evidence` → assumed _this is a separate count of associated targets_
- **Assumptions:** I assumed that 'drugs & clinical candidates' refers to the total number of drugs in development, rather than just those in the catalog.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** yes
- **Reader's answer:** The tool answered honestly that it cannot provide the US list price of osimertinib. It provided a clear message stating its inability to answer the question.
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `Unfortunately` → assumed _This is an error message, and the tool is not functioning properly._; `Is there anything else I can help you with?` → assumed _The tool is asking for further clarification or another question._
- **Assumptions:** I assumed that 'Unfortunately' was a standard phrase used in error messages, and the tool was indicating it couldn't find the information.
- **Stuck at:** —
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** yes
- **Reader's answer:** The target EGFR is associated with various cancers, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The association strength is based on the Open Targets score, which filters to a catalog of strong associations (score ≥ 0.5).
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `MONDO_0005233` → assumed _a unique identifier for non-small cell lung carcinoma_; `CHEMBL1079742` → assumed _a unique identifier for a drug that acts on the EGFR target_
- **Assumptions:** I assumed that MONDO and CHEMBL are standard identifiers for cancer types and drugs, respectively.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested against one other drug in 23 trials. However, I couldn't determine what's excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact name of the drug, not just its chemical identifier_
- **Assumptions:** I assumed that 'combination' refers to two or more drugs being given together in a single arm, and 'comparison' refers to multiple arms with different treatments.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


### drug-conclusion — After reading this whole drug page, what would you CONCLUDE about the drug overall -- what is it, how strong is the evidence, and would you act on it (e.g. prioritise it for an EGFR-driven cancer)? Answer as a one-paragraph conclusion, not a list of fields.

- **Completed:** partially
- **Reader's answer:** Osimertinib is a selective inhibitor of the Epidermal growth factor receptor (EGFR) with strong evidence from numerous clinical trials. It has been approved for use in several types of cancer, including glioblastoma, head and neck squamous cell carcinoma, non-small cell lung adenocarcinoma, and mesothelioma. However, I am unable to conclude the overall strength of the evidence due to incomplete information on trial outcomes.
- **Expected (known):** Osimertinib is an APPROVED (phase 4), SELECTIVE EGFR inhibitor (most potent on EGFR, ~8.8 nM, no other target within 100x) with a large trial and literature base -- a well-evidenced, actionable EGFR-targeted therapy; act: yes, for an EGFR-driven cancer. A reader should reach this WITHOUT assembling it from scattered blocks.
- **Terms misread:** `Well-studied: 384 registered trials` → assumed _The drug has been tested in 384 clinical trials with unknown results_; `Passed all four Lipinski rules — MW ≤ 500 Da, LogP ≤ 5, ≤ 5 H-bond donors, ≤ 10 acceptors.` → assumed _The molecular weight of the drug is less than or equal to 500 Da and it has a certain number of hydrogen bond donors and acceptors_; `Selective — most potent on Epidermal growth factor receptor (8.81 nM); no other target within 100× of it` → assumed _The drug is selective for EGFR with an IC50 value of 8.81 nM, meaning that it is more than 100 times more potent against EGFR than any other target_
- **Assumptions:** [object Object]
- **Stuck at:** —
- **Labels this task stresses:** _a page-level synthesis the reader can conclude from, not eight separate blocks_ · _the conclusion is supported by the data: approved + selective for EGFR + deep evidence_


### cancer-conclusion — After reading this whole cancer page, what would you CONCLUDE -- what is the therapeutic landscape, and where is the opportunity or the risk? Answer as a one-paragraph conclusion, not a list of blocks.

- **Completed:** partially
- **Reader's answer:** The therapeutic landscape for non-small cell lung carcinoma (NSCLC) appears to be crowded with 1,072 drugs in development, but there are opportunities for unexploited targets. The survival rates vary significantly depending on the stage of diagnosis, with localized NSCLC having a 5-year relative survival rate of 65.5%.
- **Expected (known):** NSCLC has strongly-associated, druggable targets with approved drugs (EGFR, KRAS) and a large development pipeline, but ALSO high-association targets with no drug anywhere -- the unexploited opportunity; survival is strongly stage-dependent. A reader should reach a "so what" (the druggable landscape plus the unexploited gap) without assembling it from separate blocks.
- **Terms misread:** `Not measured — which is not zero.` → assumed _The mutation frequency is unknown for this cancer._; `Showing Lung and Bronchus — broader than non-small cell lung carcinoma.` → assumed _The survival rates provided are for a broader category, but the exact numbers for NSCLC are not available._; `EU deaths` → assumed _European mortality rate for NSCLC._
- **Assumptions:** I assumed that 'strong association' in the target landscape table means a high level of evidence supporting the association between the target and the cancer.
- **Stuck at:** —
- **Labels this task stresses:** _a page-level "so what": the druggable landscape plus the unexploited gap, not separate blocks_ · _the conclusion is supported: approved targets, pipeline size, unexploited high-association targets_


### orientation — First time seeing this tool. After three minutes on it, what is this tool FOR -- and what is it NOT for? Answer in your own words, as if telling a colleague whether to open it.

- **Completed:** yes
- **Reader's answer:** This tool appears to be a database of oncology drugs and cancers, providing information on drug programs, modality, phase, target, class, and more. It seems to aggregate evidence from various sources such as ChEMBL, ClinicalTrials.gov, Open Targets, and PubMed. However, it's not clear what specific use cases or applications this tool is intended for.
- **Expected (known):** HYPOTHESIS (human triage): the tool is a research / drug-intelligence view of oncology evidence -- sourced, provenance-linked facts about drugs, cancers and targets, with a page-level synthesis of them. It is NOT clinical decision support, NOT medical advice, and does not predict or rank treatments (it "surfaces evidence; it does not predict"). Passes if the reader names both the purpose and the not-for boundary; fails if the tool reads as a treatment recommender or a clinical tool.
- **Terms misread:** `H2H surfaces evidence; it does not predict.` → assumed _H2H stands for 'Human to Human' and the sentence implies that the tool provides a way for humans to interact with the evidence, but I'm not sure what this means in practice._; `Stage (Open Targets)` → assumed _I assumed this refers to some kind of classification or categorization system within Open Targets, but I don't know what it specifically represents._
- **Assumptions:** I had to assume that the 'Modality' section refers to the type of drug (e.g. small molecule, antibody, etc.) and not something else entirely.; I assumed that the 'Phase' section refers to the clinical trial phase, but I'm not sure what the specific numbers or labels mean.
- **Stuck at:** —
- **Labels this task stresses:** _the product tagline + the Drugs|Cancers scope = what the tool is for_ · _the "surfaces evidence; does not predict" / "not clinical decision support" boundary = what it is NOT for_


### trust — Looking at this drug page, what here would you NOT trust, and why? Does anything make you doubt the tool itself -- or is it being candid about what it does and does not have?

- **Completed:** no
- **Reader's answer:** I would not trust the 'chembl unavailable' labels as they indicate a lack of data from ChEMBL, but it's unclear what other sources are used to fill in the gaps.
- **Expected (known):** HYPOTHESIS (human triage): the amber "source unavailable" advisory should read as CANDOUR -- the tool being honest that ChEMBL was down (a pipeline gap, with a retry), not as the tool being broken or the drug lacking a mechanism. A sceptical reader may rightly say a source_failed section is not evidence of absence, and that empties mean "measured none / not yet gathered". Passes if the gaps read as the tool being candid about its provenance; FAILS (feeds back into copy) if they read as "unfinished", "half-built" or a reason to distrust the tool itself.
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from ChEMBL_; `Partial` → assumed _this drug has incomplete information, but it's unclear what this means in practice_
- **Assumptions:** I assumed that 'chembl unavailable' labels indicate a lack of data from ChEMBL and not necessarily an error or issue with the tool itself.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = candour about a pipeline gap, not "broken"_ · _source_failed / empty shown honestly = trust-building, not "unfinished"_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

### #43 gate — the mutation-frequency block (the reason this run exists)

Two tasks were added to point the reader at the new cBioPortal mutation-frequency cards; the load-bearing question is whether the **None-vs-0 discipline holds** — does a reader read "no cohort" / "not measured" as "rarely/never mutated"? It holds:

- **[mutation-frequency-target]** (EGFR, a MEASURED card) — DISMISS. The reader's own answer is correct: *"EGFR is most mutated in lung adenocarcinoma, 12.4%… the proportion of TCGA PanCancer Atlas samples with somatic mutations (SNV/indel)."* It got the ranking AND the scope. `Cohorts: TCGA PanCancer Atlas` "misread" as "the dataset used" is the RIGHT reading, not a defect. "partially" is the weak evaluator wanting the word "floor" said back verbatim.
- **[mutation-frequency-coverage]** (NSCLC, an UNMAPPED card) — DISMISS as a card defect. The reader wrote *"no matched cBioPortal cohort … data may be incomplete or unavailable"* — the CORRECT reading (a coverage gap), NOT "these genes are rarely mutated." The None-vs-0 trap did not catch them. `strong association (score ≥ 0.5)` → "at least 50%" is the association STAT in the page header, not this card (a pre-existing target-landscape label, unrelated to #43).
- **[cancer-conclusion]** `Not measured — which is not zero.` → read as *"the mutation frequency is unknown for this cancer"* — CORRECT. The label did exactly its job. DISMISS.

**The one genuine gap:** `somatic mutation` was misread as "mutations in non-tumor cells" (somatic-vs-germline). This is inherent domain jargon, correct for the tool's oncology-researcher audience — the same class as the SEER / MONDO / 95%-CI misreads dismissed in earlier runs. The term is right; the evaluator is a lay proxy. Kept.

**Verdict:** the honest-state wording (no cohort / not measured / a mutation-only floor) reads correctly; no reader fell into the None-vs-0 error the block is worded to prevent, and no new confusion was introduced elsewhere (16-task spread 6 yes / 5 partially / 5 no is in line with the prior baselines). **#43 ships.**
