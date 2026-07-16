# Data sources and attribution

H2H aggregates evidence from four open databases. None requires a login or an API
key. Every fact stored carries its `source_url` and `retrieved_at`, and the UI shows
both on the citation chip beside the value — attribution is per fact, not just per
project.

## ChEMBL — **CC BY-SA 3.0**

<https://www.ebi.ac.uk/chembl/>

Structures, physicochemical properties, IC50 activities, mechanisms of action.

> ChEMBL data is licensed under a Creative Commons Attribution-ShareAlike 3.0
> Unported licence.

**Share-alike matters here.** ChEMBL-derived data redistributed from this project
carries the same obligation. If you fork H2H and publish its database, or a derived
dataset, that derivative is CC BY-SA too. The code in this repository is separately
licensed (see `LICENSE`); the *data* is not the code's to relicense.

Cite: Zdrazil B, et al. *The ChEMBL Database in 2023.* Nucleic Acids Res.

## ClinicalTrials.gov — public domain

<https://clinicaltrials.gov/>

Trial counts, phases, recruitment status. A U.S. government work; no restriction on
reuse. We use the v2 REST API.

## Open Targets — CC0 1.0

<https://platform.opentargets.org/>

Drug modality, maximum clinical stage, mechanisms, targets, indications. Released
into the public domain, attribution requested as good practice.

Cite: Ochoa D, et al. *The Open Targets Platform.* Nucleic Acids Res.

## PubMed / NCBI E-utilities — metadata only

<https://pubmed.ncbi.nlm.nih.gov/>

Literature counts, PMIDs and titles. **Deliberately metadata only.** Abstracts and
full text are not stored, cached or redistributed; the UI links out to PubMed.
Article text is under publisher copyright and is not NCBI's to sublicense — so it
stays where it lives.

An NCBI API key is optional and only raises rate limits.

---

## What this project does not do with the data

- No full text of any article is stored anywhere.
- No source is scraped: every one is read through its documented public API.
- Nothing is presented as H2H's own finding. Every value shows where it came from,
  and a value we could not fetch says so rather than being quietly omitted.
