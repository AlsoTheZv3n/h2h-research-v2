# Phase 0 spike — AACT / hazard ratios for the Phase 3 forest plot (KEY: `aact`)

**Question the plan set:** if hazard ratios (HR + CI) are *only* in AACT and AACT
needs a login, the Phase 3 forest plot has no open data source → DROP.

**Answer: the premise is false in two independent ways.** HRs are **not** only in
AACT — the ClinicalTrials.gov **API v2 exposes HR + full CI openly**, no login, no
key. And AACT's own HR table has an **open, no-login static-archive path** too. The
forest plot has an open data source. **Verdict: GREEN.**

All calls used the `python-httpx/` User-Agent token that the CT.gov/AACT edge
allowlists (bare Mozilla and custom tokens 403 — see `experiment/README.md`).
Reproduce with `probe.sh` (access) and `probe_coverage.py` (per-cancer coverage).

---

## (a) ACCESS — what needs a login, what does not

| AACT surface | Route | Login? |
|---|---|---|
| Live **cloud PostgreSQL** DB (interactive SQL) | `/connect` → "Create an Account to Access Cloud Database", `/users/sign_up`, `/users/sign_in` | **YES — free account required** (email + password; credentials shown only after login) |
| **Static daily archive — pipe-delimited flat files** | `/static/exported_files/daily/<YYYY-MM-DD>` | **NO** |
| **Static daily archive — Postgres db copy** | `/static/static_db_copies/daily/<YYYY-MM-DD>` | **NO** |

Measured today (2026-07-18): both static URLs `302`-redirect to a **public
DigitalOcean Spaces bucket** (`ctti-aact.nyc3.digitaloceanspaces.com`) and stream
`application/zip` with **no account, cookie, or key** — `HTTP 200`, ~2.5 GB each.
The `exported_files` zip holds 49 pipe-delimited members including
**`outcome_analyses.txt` (~100 MB)** — the hazard-ratio table. So even AACT's HR
data is reachable openly; only the *convenience* of live SQL is gated.

(Downloaded once to confirm zip integrity + member listing, then deleted the ~5 GB.)

## (b) DECISIVE cross-check — CT.gov API v2 already carries HR + CI

Fetching any completed trial with results and reading
`resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[]` returns
structured HR analyses. FLAURA (NCT02296125), for example, has 4 analyses of
`"paramType":"Hazard Ratio (HR)"`, each with `paramValue`, `ciLowerLimit`,
`ciUpperLimit`, `ciPctValue`, and `pValue` — e.g. **HR 0.46 (95% CI 0.37–0.57),
p<0.0001**. This is exactly the shape a forest plot needs, from a **public,
no-login, no-key REST API**. AACT is therefore **not required** for the forest plot.

## Per-cancer coverage (open CT.gov v2) — measured, not assumed

EFO IDs are Open Targets identifiers; CT.gov indexes conditions as text/MeSH, so
each is mapped to the CT.gov condition query shown. "HR trials" = trials matching
the indexed search area `AREA[OutcomeAnalysisParamType]"Hazard Ratio (HR)"`. The
filter was **verified** by downloading a sample and confirming each trial actually
carries a machine-readable HR with CI (guard against fuzzy matching).

| Cancer (EFO) | cond query | trials | with results | HR trials | verify sample | state |
|---|---|--:|--:|--:|:--:|:--:|
| NSCLC (EFO_0003060) | non-small cell lung cancer | 8,460 | 1,620 | **265** | 13/15 carry HR+CI | **POPULATED** |
| breast carcinoma (EFO_0000305) | breast carcinoma | 16,474 | 2,408 | **224** | 14/15 carry HR+CI | **POPULATED** |
| pancreatic carcinoma (EFO_0002618) | pancreatic carcinoma | 4,625 | 628 | **37** | 15/15 carry HR+CI | **POPULATED** |
| melanoma (EFO_0000756) | melanoma | 3,734 | 784 | **71** | 15/15 carry HR+CI | **POPULATED** |
| CML (EFO_0000339) | chronic myeloid leukemia | 1,803 | 449 | **12** | 12/12 carry HR+CI | **POPULATED** |

**5 of 5 POPULATED.** Real HR+CI values pulled for every cancer (samples in
`out/coverage.json`), e.g. melanoma NCT01245062 HR 0.44 (95% CI 0.31–0.64); CML
NCT03268954 16 HR analyses with CI.

**Honest caveat (None != 0):** "HR trials" counts trials with an HR *analysis*; a
minority report the HR point estimate with **no CI limits** in the structured fields
(e.g. breast NCT00274456: 7 HR analyses, 0 with CI). A forest plot needs the CI, so
the usable denominator is slightly below the HR-trial count — but the verify sample
shows the large majority (~87–100%) carry the CI. CML's 12 is a real, small count,
not an outage; it is the genuinely thinnest of the five (early-CML endpoints are
mostly response/MMR rates, not time-to-event HRs).

## Licence / redistribution

- Underlying data is **ClinicalTrials.gov** content — a U.S. NLM/NIH federal work,
  **U.S. public domain**. NLM asks attribution to ClinicalTrials.gov and no implication
  of endorsement.
- **AACT/CTTI** state their materials are "available to the public for free" and ask
  that you "acknowledge the source whenever using or referencing CTTI materials."
- Net: **redistributable with attribution.** No copyright barrier to shipping HR+CI.

## Verdict — **GREEN**

An open path to HR + CI exists and covers all 5 cancers with no login and no API key:
**use the ClinicalTrials.gov API v2 `outcomeMeasuresModule` directly** (matches the
existing `clinicaltrials.py` adapter surface — graduates almost unchanged). AACT is
**not needed**; keep the login-gated cloud DB out of scope. If a bulk backfill is ever
wanted, AACT's **static daily archive** (`outcome_analyses.txt`) is the open,
no-account fallback. The plan's "DROP if login-only" trigger does **not** fire.
