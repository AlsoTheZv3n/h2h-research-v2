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

## PubMed / NCBI E-utilities — read locally, never redistributed

<https://pubmed.ncbi.nlm.nih.gov/>

Literature counts, PMIDs, titles, and — since v0.2.0 — abstract text, fetched into
this instance's own database to answer questions about a drug.

**This line moved, and it is worth saying so plainly.** Through v0.1.0 this section
read *"deliberately metadata only — abstracts are not stored, cached or
redistributed"*. Storing them is a real change from what was published, so it is
recorded here as a change rather than quietly edited away. What did **not** move is
the part that carries the actual obligation: **nothing is redistributed.**

The reason the two are separable is NLM's own position:

> NLM does not claim the copyright on the abstracts in PubMed; however, journal
> publishers or authors may. NLM provides no legal advice concerning distribution of
> copyrighted materials, consult your legal counsel.
> — [NCBI Website and Data Usage Policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)

So NCBI has no rights in the abstracts to grant us, and does not pretend to.
Downloading them is what E-utilities is for and NCBI points bulk users at local
copies; **publishing them onward is the act nobody has cleared.** This project draws
its line exactly there:

| | |
|---|---|
| Fetched on demand, per drug, when you open its brief | yes — never as a bulk job |
| Stored in the Postgres running on your machine | yes |
| Committed to this repository, its fixtures, or its Docker image | **never** |
| Returned by the API — in any response, on any path | **never** |
| Shown to you as text | **never**: you get the citation and a link to PubMed |

The fourth row is the one that matters and the one that is easy to get wrong. An
abstract is only ~250 words and is already the abridgement of the paper, so a
"short snippet" is a large fraction of the work and the substantive part of it — the
intuition that snippets are harmless comes from long-form text and does not carry
over. The chat model reads abstracts to ground its answer; what leaves the process
is a synthesis plus citations. `backend/tests/test_output_boundary.py` asserts this
against every route the API exposes, because a UI that renders 50 words is cosmetic
if the JSON behind it carried all 250.

Per NCBI's usage guidelines every request identifies itself with `tool=` and
`email=` (configure `NCBI_EMAIL`; see `.env.example`). An API key is optional and
only raises the rate limit from 3 to 10 requests per second.

Literature data is **courtesy of the U.S. National Library of Medicine.** This
project is not affiliated with or endorsed by NLM, NIH or HHS, and does not use the
PubMed wordmark or logo.

---

## What this project does not do with the data

- No full text of any article is fetched or stored — only abstracts, and only into
  the local database described above.
- No abstract text is ever served, exported or committed. See the table above.
- No source is scraped: every one is read through its documented public API.
- Nothing is presented as H2H's own finding. Every value shows where it came from,
  and a value we could not fetch says so rather than being quietly omitted.

## Freshness

NCBI asks redistributors to keep data current or say that it isn't. H2H caches what
it fetched and stamps every fact with `retrieved_at`, which the UI shows on the
citation chip. Nothing here is a live mirror of any source: it is what that source
said on that date, and the date is always on screen next to the value.
