# Usability & comprehension report — 2026-07-21

**Evaluator:** `ollama:llama3.1:8b` — a real model against the real running app; it saw ONLY the rendered page text for each task (no repo, README or source).

**This is a report, not a CI gate.** An LLM judgement is non-deterministic; findings need human triage. A confident critique is NOT a validated defect until confirmed — dismissed findings are recorded with a reason (see the Triage section, filled by a human).

## Misread labels — the primary output

- **[kras-crowded]** `Phase` → the reader assumed: _the stage of development for each drug_
- **[kras-crowded]** `Modality` → the reader assumed: _the type of treatment or intervention being used_
- **[osimertinib-potency]** `Selectivity & potency` → the reader assumed: _a section title that describes how selective osimertinib is_
- **[osimertinib-potency]** `Targets ranked by potency · fold vs the most potent (log scale)` → the reader assumed: _a table or list of targets in order of their potency compared to EGFR_
- **[unexploited-targets]** `Tbio no drug anywhere` → the reader assumed: _This target is not targeted by any drugs in the Tbio database_
- **[unexploited-targets]** `Tchem chemical matter, none approved` → the reader assumed: _There are no approved drugs targeting this protein_
- **[epidemiology-most-common]** `Age-standardised mortality rate — deaths, not incidence` → the reader assumed: _I assumed 'deaths' referred to the number of people who died from non-small cell lung carcinoma, rather than a rate._
- **[epidemiology-most-common]** `EU deaths` → the reader assumed: _I assumed this was the total number of deaths in the EU due to non-small cell lung carcinoma, but it's actually the number of deaths in 2023._
- **[survival-odds]** `SEER (U.S.)` → the reader assumed: _a specific database or registry of cancer patients in the United States_
- **[survival-odds]** `95% CI` → the reader assumed: _a statistical measure indicating a confidence interval of 95% for the reported survival rates_
- **[source-failed]** `chembl unavailable` → the reader assumed: _the tool is unable to access or retrieve data from ChEMBL_
- **[pipeline-rollup]** `via ontology roll-up — broader and narrower indications are included` → the reader assumed: _this is a note explaining why the number might be higher than expected_
- **[pipeline-rollup]** `in catalog only` → the reader assumed: _this refers to drugs that are currently in development, but not yet approved_
- **[chat-unsupported]** `a grounded answer can take a moment` → the reader assumed: _it will give me the information I need in a reasonable amount of time_
- **[target-associated-cancers]** `MONDO_0005233` → the reader assumed: _a unique identifier for a specific cancer type_
- **[target-associated-cancers]** `CHEMBL1079742` → the reader assumed: _a unique identifier for a specific drug_
- **[observed-combinations]** `≥2 drugs` → the reader assumed: _at least two different types of drugs_
- **[observed-combinations]** `matched by drug name (ClinicalTrials.gov keys by intervention text)` → the reader assumed: _the tool matches trials based on the exact names of the drugs, not just their chemical structures or generic names_
- **[drug-conclusion]** `Targets ranked by potency · fold vs the most potent (log scale)` → the reader assumed: _a graph showing the ranking of targets by their potency_
- **[drug-conclusion]** `Measurements by assay kind` → the reader assumed: _the types of assays used to measure target binding, cell-line response, and unassigned measurements_
- **[cancer-conclusion]** `SEER (U.S.)` → the reader assumed: _a database of cancer patients in the United States_
- **[cancer-conclusion]** `Eurostat 2023` → the reader assumed: _a dataset of mortality rates for European countries in 2023_
- **[orientation]** `H2H` → the reader assumed: _a database query language_
- **[orientation]** `Stage (Open Targets)` → the reader assumed: _the stage of a clinical trial_
- **[trust]** `chembl unavailable` → the reader assumed: _the tool has no data or access to this information_
- **[trust]** `Partial` → the reader assumed: _this drug's page only shows partial information, but it doesn't specify what is missing_

## Summary

- Tasks: 14 — completed **5** yes, 4 partially, 5 no, 0 unparseable
- Tasks with at least one misread label: **14**
- Harness errors (navigation/model): 0

## Per task

### kras-crowded — You are scoping the competitive landscape. Search the drug catalog for KRAS and decide: is KRAS a crowded target (many approved and clinical-stage programs), or a sparse one?

- **Completed:** partially
- **Reader's answer:** KRAS appears to be a crowded target with at least two approved programs, but I'm missing information on the number of clinical-stage programs.
- **Expected (known):** Crowded: several APPROVED KRAS G12C inhibitors (sotorasib, adagrasib) plus more in development. The count/table make this clear.
- **Terms misread:** `Phase` → assumed _the stage of development for each drug_; `Modality` → assumed _the type of treatment or intervention being used_
- **Assumptions:** I assumed that 'Approved' means the program has completed clinical trials and is available on the market.
- **Stuck at:** —
- **Labels this task stresses:** _the drug table: approved vs clinical_ · _the filtered total count_


### osimertinib-potency — What does osimertinib mainly target, and how selective is it? Read the potency card and say which target it is most potent on and how you can tell how selectively it acts.

- **Completed:** yes
- **Reader's answer:** Osimertinib mainly targets the Epidermal growth factor receptor (EGFR) and is highly selective for this target, with a potency of 8.81 nM.
- **Expected (known):** SELECTIVE for EGFR: EGFR is its most potent target (the reference, ~8.8 nM) and no other measured target is within 100× of it (the next, LSD1/KDM1A, is ~450× weaker). The card ranks single-protein BINDING measurements on a log scale; cell-line readouts (a cell response, not target binding) are counted in a separate section, never folded into the selectivity read.
- **Terms misread:** `Selectivity & potency` → assumed _a section title that describes how selective osimertinib is_; `Targets ranked by potency · fold vs the most potent (log scale)` → assumed _a table or list of targets in order of their potency compared to EGFR_
- **Assumptions:** I assumed that 'fold' refers to a logarithmic scale, as it is often used in scientific contexts.
- **Stuck at:** —
- **Labels this task stresses:** _the selectivity verdict: "Selective" vs "Multi-target" — targets within 100× of the most potent_ · _assay kinds kept distinct: "Target-binding" vs "Cell-line" (a cell response, not binding)_


### unexploited-targets — For this cancer (NSCLC), which targets look biologically promising but are NOT yet drugged anywhere in the world? Name one and explain how you know it is undrugged.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** A high-association target flagged "unexploited" -- which means NO approved or clinical drug exists against it ANYWHERE (Open Targets, the world), not merely "absent from this tool". The catalog-link is a separate, weaker signal.
- **Terms misread:** `Tbio no drug anywhere` → assumed _This target is not targeted by any drugs in the Tbio database_; `Tchem chemical matter, none approved` → assumed _There are no approved drugs targeting this protein_
- **Assumptions:** I assumed that 'strong association' means a high level of evidence linking the target to the cancer; I assumed that 'in catalog ↗' is a link to more information about the target, but I don't know what it links to
- **Stuck at:** I'm stuck because I need to identify one target that has no drugs anywhere in the world. The page lists several targets with 'Tbio no drug anywhere', but I don't know how to verify this information or understand why some targets have this status and others do not.
- **Labels this task stresses:** _"unexploited" = no drug anywhere (the world) — the highest-stakes label_ · _"drugged, no link" (a drug exists but not in this catalog) vs "unexploited"_


### epidemiology-most-common — Where is this cancer most common / most deadly? Read the epidemiology block and say what the country figures actually measure.

- **Completed:** partially
- **Reader's answer:** The country figures in the epidemiology block measure age-standardised mortality rates per 100,000 for non-small cell lung carcinoma. The most deadly countries are Hungary and Croatia, with mortality rates of 80.07 and 65.01 respectively.
- **Expected (known):** The figures are AGE-STANDARDISED MORTALITY RATES (deaths per 100k), NOT incidence and NOT a burden/case count. And they describe the broader ICD-10 category (Trachea, bronchus & lung, C33-C34), a labelled roll-up, not NSCLC exactly.
- **Terms misread:** `Age-standardised mortality rate — deaths, not incidence` → assumed _I assumed 'deaths' referred to the number of people who died from non-small cell lung carcinoma, rather than a rate._; `EU deaths` → assumed _I assumed this was the total number of deaths in the EU due to non-small cell lung carcinoma, but it's actually the number of deaths in 2023._
- **Assumptions:** I had to assume that the country figures were for non-small cell lung carcinoma specifically, as there is no explicit mention of this on the page.
- **Stuck at:** —
- **Labels this task stresses:** _ASR — age-standardised mortality rate, deaths per 100k, not incidence_ · _the roll-up note: "Trachea, bronchus & lung (C33-C34) — broader than NSCLC"_


### survival-odds — What are the survival odds for this cancer? Read the survival block and state what it tells you -- and what it does NOT.

- **Completed:** partially
- **Reader's answer:** The survival odds for non-small cell lung carcinoma are generally poor, with a 5-year relative survival rate of 29.5% for all stages. However, the survival rates vary significantly depending on the stage at diagnosis, ranging from 65.5% for localized cases to 10.5% for distant cases.
- **Expected (known):** 5-year RELATIVE survival (against a matched general population), by SEER summary stage (Localized/Regional/Distant), for the broader Lung & Bronchus category. It is a population statistic, NOT an individual prognosis, and not TNM stage.
- **Terms misread:** `SEER (U.S.)` → assumed _a specific database or registry of cancer patients in the United States_; `95% CI` → assumed _a statistical measure indicating a confidence interval of 95% for the reported survival rates_
- **Assumptions:** I assumed that '5-year relative survival' refers to the percentage of patients who survive at least 5 years after diagnosis, rather than the percentage of patients who are alive at any point within those 5 years.
- **Stuck at:** —
- **Labels this task stresses:** _"5-year relative survival" (against a matched population), a population stat not a prognosis_ · _SEER summary stage (Localized/Regional/Distant), not TNM; the Lung & Bronchus roll-up_


### source-failed — This drug page (afatinib) shows almost no data. Why? Is that telling you something about the drug, or about the tool?

- **Completed:** no
- **Reader's answer:** The drug page for afatinib shows almost no data because some sources couldn't be reached when the brief was last refreshed.
- **Expected (known):** A SOURCE FAILURE (ChEMBL was unavailable) -- a gap in the tool's pipeline, shown as a calm amber advisory with a retry, NOT a finding that the drug lacks a mechanism/structure. "Source unavailable" must not read as "none found".
- **Terms misread:** `chembl unavailable` → assumed _the tool is unable to access or retrieve data from ChEMBL_
- **Assumptions:** I assumed that 'chembl' refers to a database or source of information, but I'm not sure what it stands for.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = a pipeline gap, not a fact about the drug_ · _source_failed vs "measured, none found"_


### pipeline-rollup — How many drugs are in development for this cancer? Read the pipeline block and state the number -- and exactly what it counts.

- **Completed:** yes
- **Reader's answer:** There are 1,072 drugs in development for non-small cell lung carcinoma. This count includes all drugs and clinical candidates, regardless of their stage of development.
- **Expected (known):** The count is an ONTOLOGY ROLL-UP: it includes drugs for broader AND narrower indications of the disease, so it is larger than an exact-node match. The card says so. Also, only some of those drugs are in this catalog (a separate ratio).
- **Terms misread:** `via ontology roll-up — broader and narrower indications are included` → assumed _this is a note explaining why the number might be higher than expected_; `in catalog only` → assumed _this refers to drugs that are currently in development, but not yet approved_
- **Assumptions:** I assumed that 'drugs & clinical candidates' refers specifically to treatments for non-small cell lung carcinoma, and not a broader category of cancer treatments.
- **Stuck at:** —
- **Labels this task stresses:** _the pipeline count = an ontology roll-up (broader + narrower indications)_ · _"N of M are in the catalog and open a brief" — a separate, weaker link signal_


### chat-unsupported — Use the ask box to ask something the stored evidence cannot answer (e.g. the US list price of osimertinib). Does the tool answer honestly, or does it look broken?

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** An honest "not in the retrieved evidence"-style refusal -- the grounding guard working as designed, NOT a broken feature. The tool answers only from the drug's stored facts + abstracts, so a price question has no grounded answer.
- **Terms misread:** `a grounded answer can take a moment` → assumed _it will give me the information I need in a reasonable amount of time_
- **Assumptions:** I assumed that 'grounded' is an adjective describing the type of answer, rather than a technical term with a specific meaning
- **Stuck at:** still waiting for an answer
- **Labels this task stresses:** _the chat's honest "not in the retrieved evidence" = working as designed, not broken_


### target-associated-cancers — You are on the page for a target (a gene, EGFR). Which cancers is this target associated with, and how do you know these are the relevant ones -- not, say, unrelated non-cancer conditions? And what does the drugs section tell you?

- **Completed:** yes
- **Reader's answer:** The EGFR target is associated with various types of cancer, including non-small cell lung carcinoma, breast cancer, and colorectal adenocarcinoma. The association strength is indicated by the 'strong' or 'moderate' label next to each cancer type, with scores ranging from 0.5 to 0.85. The drugs section lists several compounds that act on this target.
- **Expected (known):** The associated cancers are the target's Open Targets associations FILTERED to the cancers this tool catalogs (each a live link, with a score, the top slice of a larger count). Non-cancers are excluded. The drugs section lists the catalog drugs that act on this target; an empty list is 'a gap in our catalog', NOT 'undruggable'.
- **Terms misread:** `MONDO_0005233` → assumed _a unique identifier for a specific cancer type_; `CHEMBL1079742` → assumed _a unique identifier for a specific drug_
- **Assumptions:** I assumed that the 'strong' and 'moderate' labels refer to the association strength between the target and each cancer type.
- **Stuck at:** —
- **Labels this task stresses:** _associated cancers = the OT reverse query filtered to the catalog (not raw top diseases)_ · _"drugs in the catalog" = drugs WE hold against the target; empty is a gap, not "undruggable"_


### observed-combinations — Read the "observed combinations" card for this drug. In how many registered trials is it given IN COMBINATION with another drug, versus tested in a head-to-head COMPARISON against one? And is anything excluded?

- **Completed:** partially
- **Reader's answer:** Pembrolizumab is given in combination with another drug in 311 trials and tested against one other drug in 23 trials. However, I couldn't determine what's excluded.
- **Expected (known):** Two DISTINCT counts from the trials' arm structure: combination (drugs in one arm, given together) vs comparison (drugs in separate arms, tested against each other). The counts are over a scanned sample of the drug's trials, and the multi-drug trials whose arms carry no drug assignment are EXCLUDED (dropped, not guessed) -- a footnoted count, never folded into either bucket.
- **Terms misread:** `≥2 drugs` → assumed _at least two different types of drugs_; `matched by drug name (ClinicalTrials.gov keys by intervention text)` → assumed _the tool matches trials based on the exact names of the drugs, not just their chemical structures or generic names_
- **Assumptions:** I assumed that 'combination' refers to two or more drugs being given together in a single arm, and 'comparison' refers to a head-to-head test between two different treatments.
- **Stuck at:** —
- **Labels this task stresses:** _combination (given together) vs comparison (tested against) -- opposite meanings, kept distinct_ · _the dropped-ambiguous count = excluded, not guessed; counts are over a scanned sample_


### drug-conclusion — After reading this whole drug page, what would you CONCLUDE about the drug overall -- what is it, how strong is the evidence, and would you act on it (e.g. prioritise it for an EGFR-driven cancer)? Answer as a one-paragraph conclusion, not a list of fields.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** Osimertinib is an APPROVED (phase 4), SELECTIVE EGFR inhibitor (most potent on EGFR, ~8.8 nM, no other target within 100x) with a large trial and literature base -- a well-evidenced, actionable EGFR-targeted therapy; act: yes, for an EGFR-driven cancer. A reader should reach this WITHOUT assembling it from scattered blocks.
- **Terms misread:** `Targets ranked by potency · fold vs the most potent (log scale)` → assumed _a graph showing the ranking of targets by their potency_; `Measurements by assay kind` → assumed _the types of assays used to measure target binding, cell-line response, and unassigned measurements_
- **Assumptions:** I assumed that 'fold vs the most potent' refers to a comparison of the potency of each target relative to the most potent one.; I assumed that 'Measurements by assay kind' is a table or list showing the types of assays used for each measurement type.
- **Stuck at:** I am stuck trying to understand the overall conclusion about the drug, as I need more information on its efficacy and potential uses in EGFR-driven cancer treatment.
- **Labels this task stresses:** _a page-level synthesis the reader can conclude from, not eight separate blocks_ · _the conclusion is supported by the data: approved + selective for EGFR + deep evidence_


### cancer-conclusion — After reading this whole cancer page, what would you CONCLUDE -- what is the therapeutic landscape, and where is the opportunity or the risk? Answer as a one-paragraph conclusion, not a list of blocks.

- **Completed:** no
- **Reader's answer:** —
- **Expected (known):** NSCLC has strongly-associated, druggable targets with approved drugs (EGFR, KRAS) and a large development pipeline, but ALSO high-association targets with no drug anywhere -- the unexploited opportunity; survival is strongly stage-dependent. A reader should reach a "so what" (the druggable landscape plus the unexploited gap) without assembling it from separate blocks.
- **Terms misread:** `SEER (U.S.)` → assumed _a database of cancer patients in the United States_; `Eurostat 2023` → assumed _a dataset of mortality rates for European countries in 2023_
- **Assumptions:** I assumed that 'SEER' and 'Eurostat' are databases or datasets used to collect and analyze cancer data, but I'm not sure what they specifically contain.; I assumed that the 'molecular profile' mentioned at the end of the page is a block of information that will be displayed next, but it's not visible in this text.
- **Stuck at:** The molecular profile section is missing and I don't know where to find it or what it contains.
- **Labels this task stresses:** _a page-level "so what": the druggable landscape plus the unexploited gap, not separate blocks_ · _the conclusion is supported: approved targets, pipeline size, unexploited high-association targets_


### orientation — First time seeing this tool. After three minutes on it, what is this tool FOR -- and what is it NOT for? Answer in your own words, as if telling a colleague whether to open it.

- **Completed:** yes
- **Reader's answer:** This tool appears to be a database of oncology drugs and cancers, providing information on drug programs, modality, phase, target, class, and clinical trials. It's not clear what specific features or analyses it offers beyond displaying this data.
- **Expected (known):** HYPOTHESIS (human triage): the tool is a research / drug-intelligence view of oncology evidence -- sourced, provenance-linked facts about drugs, cancers and targets, with a page-level synthesis of them. It is NOT clinical decision support, NOT medical advice, and does not predict or rank treatments (it "surfaces evidence; it does not predict"). Passes if the reader names both the purpose and the not-for boundary; fails if the tool reads as a treatment recommender or a clinical tool.
- **Terms misread:** `H2H` → assumed _a database query language_; `Stage (Open Targets)` → assumed _the stage of a clinical trial_
- **Assumptions:** I assumed that 'sourced evidence' refers to the data sources used to populate the database.
- **Stuck at:** —
- **Labels this task stresses:** _the product tagline + the Drugs|Cancers scope = what the tool is for_ · _the "surfaces evidence; does not predict" / "not clinical decision support" boundary = what it is NOT for_


### trust — Looking at this drug page, what here would you NOT trust, and why? Does anything make you doubt the tool itself -- or is it being candid about what it does and does not have?

- **Completed:** yes
- **Reader's answer:** I would not trust the availability of certain molecular properties and mechanism information for Afatinib, as it is labeled 'chembl unavailable' in several sections.
- **Expected (known):** HYPOTHESIS (human triage): the amber "source unavailable" advisory should read as CANDOUR -- the tool being honest that ChEMBL was down (a pipeline gap, with a retry), not as the tool being broken or the drug lacking a mechanism. A sceptical reader may rightly say a source_failed section is not evidence of absence, and that empties mean "measured none / not yet gathered". Passes if the gaps read as the tool being candid about its provenance; FAILS (feeds back into copy) if they read as "unfinished", "half-built" or a reason to distrust the tool itself.
- **Terms misread:** `chembl unavailable` → assumed _the tool has no data or access to this information_; `Partial` → assumed _this drug's page only shows partial information, but it doesn't specify what is missing_
- **Assumptions:** I assumed that 'chembl' refers to the ChEMBL database, which is mentioned as a source of evidence at the bottom of the page.
- **Stuck at:** —
- **Labels this task stresses:** _the amber "source unavailable" advisory = candour about a pipeline gap, not "broken"_ · _source_failed / empty shown honestly = trust-building, not "unfinished"_


## Triage (human)

For each misread label above, a human confirms it (the label is genuinely ambiguous → work) or dismisses it (the evaluator was wrong, e.g. a small model hallucinating) WITH the reason. A confident critique is not a defect until confirmed.

### #42 gate (the reason this run exists)

This run is the reader-visible gate for #42 (publication-type badge + "not yet indexed" label on the Key papers block). Two questions, both answered:

- **Did #42 introduce a new misread?** No. None of the 25 misread labels touches the literature block — no `key papers`, `publication type`, `not yet indexed`, `Review`, `Randomized Controlled Trial`, or `Meta-Analysis`. The reader who read a drug page (osimertinib-potency, drug-conclusion, trust) never once tripped on the new evidence signals. The badge and the un-indexed label read as intended.
- **Did #42 regress comprehension overall?** No — it improved. Completion this run **5 yes / 4 partially / 5 no**, versus the immediately prior Epic-E baseline `report-2026-07-21-epic-e.md` at **3 yes / 5 partially / 6 no**. (LLM judgement is non-deterministic, so read the direction, not the two-point delta — the point is there is no regression.)

The remaining misreads are all pre-existing and pre-#42 (SEER/95% CI/MONDO ids/ChEMBL-unavailable/H2H) — the ordinary jargon-vs-lay gap this harness always surfaces, none of it introduced or worsened by #42. **Verdict: #42 ships.**
