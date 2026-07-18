# Phase 0 spike — ClinicalTrials.gov API v2 (KEY: `ctgov`)

Throwaway data spike. Real calls, real output (`probe.py` -> `probe_output.txt`;
curl equivalents in `probe.sh`). Measures whether the **trial-reality evidence
block** would render POPULATED per cancer — trials + whyStopped + CH locations —
with the hazard-ratio (Phase 3) gate reported separately.

Endpoint: `https://clinicaltrials.gov/api/v2/studies`

## Access & licence

- **Open. No API key, no login.** Every call in this spike is an unauthenticated GET.
- **WAF / User-Agent:** the v1 WAF that 403s unknown User-Agents **does NOT gate v2**.
  Verified `curl/8`, `Mozilla/5.0`, and `python-httpx/0.27` all return **200** against v2
  (probe.sh WAF block). The `USER_AGENT` workaround in `backend/ingestion/clinicaltrials.py`
  is therefore not required for v2, though sending a descriptive UA remains good hygiene.
- **Licence:** ClinicalTrials.gov data is **U.S. Government public domain** (NLM/NIH),
  no copyright, freely redistributable. Attribution norm: cite ClinicalTrials.gov and the
  NCT number; NLM asks that you not imply NIH endorsement and note the retrieval date.
  Redistributable = **yes (attribution)**.

## Query patterns (verified)

| Need | Param | Note |
|---|---|---|
| Count by disease | `query.cond=<text>` + `countTotal=true` | synonym-expanded; ctgov keys on **text, not EFO** |
| True count | `totalCount` (needs `countTotal=true`) | never `len(studies)` — caps at pageSize |
| Terminated/withdrawn | `filter.overallStatus=TERMINATED\|WITHDRAWN` | `\|` or `,` both work |
| Why stopped | `protocolSection.statusModule.whyStopped` | present only on TERMINATED/WITHDRAWN |
| Recruiting in country | `filter.overallStatus=RECRUITING` + `query.locn=<country>` | returns real CH trials (verified) |
| Has results | `aggFilters=results:with` | |
| Hazard ratio | `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[]` | see schema note below |

**EFO note:** the task's EFO IDs are Open Targets identifiers. ClinicalTrials.gov has no
EFO field; it matches free-text conditions with synonym expansion. Conditions verified by
inspecting returned briefTitles/CH cities (NSCLC -> real NSCLC trials in Lausanne/Basel).
Counts track disease prevalence (breast > NSCLC > pancreatic > melanoma > CML).

**Hazard-ratio schema (load-bearing for the app):** `analyses[].paramType` is **free text**,
e.g. `"Hazard Ratio (HR)"` — **NOT** an enum like `HAZARD_RATIO`. Match case-insensitively on
`"hazard"`. Value in `paramValue`; CI in `ciLowerLimit`/`ciUpperLimit`; compared arms via
`groupIds` (comparator derivable).

## Per-cancer coverage (measured)

| Cancer | Trials (`query.cond`) | Terminated+Withdrawn | whyStopped populated | CH recruiting | Block |
|---|---|---|---|---|---|
| NSCLC | 8,442 | 1,353 | 1,205 (**89.1%**) | 40 | **POPULATED** |
| Breast carcinoma | 16,474 | 1,918 | 1,699 (**88.6%**) | 40 | **POPULATED** |
| Pancreatic carcinoma | 4,625 | 662 | 610 (**92.1%**) | 8 | **POPULATED** |
| Melanoma | 3,734 | 687 | 625 (**91.0%**) | 12 | **POPULATED** |
| CML | 1,803 | 347 | 284 (**81.8%**) | 1 | **POPULATED** |

Location filter also verified for DE/AT (NSCLC DE=101 AT=38; CML DE=10 AT=3). Sample real
Swiss recruiting trials with CH cities: NSCLC `NCT06712316` (Baden, Lausanne),
`NCT04389632` (Chur, Lausanne); breast `NCT05890677` (Aarau, Basel, Geneva, Lausanne,
Winterthur, Zurich). CML has only **1** recruiting Swiss trial — thin but real (not an outage).

## Hazard ratio — Phase 3 gate (reported separately)

Fraction of **COMPLETED-with-results** trials carrying >=1 hazard-ratio analysis:

| Cancer | Completed w/ results | Scanned | >=1 HR analysis | Fraction |
|---|---|---|---|---|
| NSCLC | 1,077 | 1,000* | 185 | **18.5%** |
| Melanoma | 519 | 519 | 62 | **11.9%** |
| Breast | 1,719 | 1,000* | 114 | **11.4%** |
| Pancreatic | 425 | 425 | 34 | **8.0%** |
| CML | 303 | 303 | 9 | **3.0%** |

\* NSCLC/breast HR fraction is a sample estimate (first 1,000 results scanned). For melanoma,
**all 62** HR trials also carried a full CI (both limits) — HR+CI ~= HR-present, not a lossy
subset. Live examples: melanoma `NCT01245062` HR=0.44 CI[0.31, 0.64]; pancreatic `NCT02184195`
HR=0.531 CI[0.346, 0.815].

**Coverage-first verdict on HR:** usable HR+CI exists but is a **minority** — ~3% (CML) to
~18% (NSCLC) of completed-with-results trials, a small slice of *all* trials. Real and
machine-readable, but sparse: a Phase 3 HR feature would be populated for a handful of headline
trials per cancer, not most. It does **not** gate the Phase 1 trial-reality block.

## Verdict: GREEN

The trial-reality block renders **POPULATED for all 5 of 5 cancers**: dense trial counts,
terminated/withdrawn trials with **whyStopped populated 82-92%** of the time, and
country-filterable recruiting trials with real Swiss sites (4/5 with CH >= 8; CML thin at 1).
Access is open, keyless, public domain, and — unlike v1 — v2 needs no WAF User-Agent workaround.
The hazard-ratio Phase 3 gate is real but sparse (3-18.5%) and reported as a separate signal.
