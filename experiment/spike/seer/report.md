# SEER spike report (KEY: seer)

Phase 0 throwaway data spike. Question: can a stage-wise (Localized / Regional /
Distant) 5-year RELATIVE survival block render POPULATED per cancer, from an OPEN
SEER source with NO account?

TL;DR: Yes, for solid tumors. SEER*Explorer aggregate statistics are served by
public JSON endpoints -- no login, no API key, no data-use agreement. Real
stage-wise 5-year relative survival came back for 4 of the 5 target cancers.
CML returns only "All Stages" because leukemia is not stage-decomposed (a genuine,
clinical EMPTY -- not a source failure).

## (a) Access -- what is open vs. gated

| Thing | Auth | Used here |
|---|---|---|
| SEER*Explorer aggregate stats (seer.cancer.gov/statistics-network/explorer/) | None -- fully open | YES |
| SEER research microdata API (api.seer.cancer.gov) | Login required (signed DUA) | No -- avoided |

The SEER*Explorer web app does not use a documented REST API; it calls internal
PHP JSON endpoints under
.../statistics-network/explorer/source/content_writers/. These respond 200
application/json to a plain curl with a browser User-Agent, no cookie, no
token, no CSRF header. Endpoints exercised:

- get_var_formats.php -- the full code<->label dictionary (site, stage, data_type...).
- render_region_5.php -- the data call the survival chart itself makes.
- (render_region_{1,2,3}_controls.php, load_json_asset.php -- control metadata.)

The gated api.seer.cancer.gov is a different service (case-level microdata) and
is not needed for aggregate stage-wise survival. Per the no-login rule: the
open path clears it; the gated microdata path would be RED, but we never touch it.

## (b) Coverage -- stage-wise 5-year relative survival, measured per cancer

Real render_region_5.php output. Query: data_type=4 (Survival),
graph_type=5 (5-Year Survival), compareBy=stage,
relative_survival_interval=5, race=1 (All), age_range=1 (All),
data_model=3 (Preliminary Estimates, Selected Registries 2000-2024). Rate =
5-year relative survival %.

| Cancer | SEER site | Localized | Regional | Distant | All Stages | State |
|---|---|---|---|---|---|---|
| NSCLC | 47 Lung & Bronchus* | 65.5% | 38.2% | 10.5% | 29.5% | POPULATED* |
| Breast (Female) | 55 Breast | 100.0% | 87.5% | 33.8% | 91.9% | POPULATED |
| Pancreatic | 40 Pancreas | 43.6% | 17.0% | 3.4% | 13.7% | POPULATED |
| Melanoma | 53 Melanoma of Skin | 100.0% | 76.0% | 34.0% | 94.7% | POPULATED |
| CML | 97 CML | -- | -- | -- | 71.1% | EMPTY (stage block) |

* NSCLC is not a native SEER*Explorer entity. There is no "NSCLC" site. Options:
- Site 47 "Lung and Bronchus" (shown above) -- includes small-cell, so it is a
  superset of NSCLC, not NSCLC exactly.
- Histology subtypes, which exclude small-cell and can be combined to equal
  NSCLC: 612 Adenocarcinoma (Localized 73.6% / Regional 48.9% / Distant 14.2%),
  610 Squamous, 613 Large-cell. Each returns full stage-wise survival. A faithful
  NSCLC block would sum/select these rather than use site 47.

CML EMPTY is real, not an outage. render_region_5.php returned HTTP 200 with a
single row -- stage 101 All Stages (71.1%) -- and no Localized/Regional/Distant.
Leukemias are not assigned the SS2000 solid-tumor stage schema, so the stage-wise
block cannot populate for CML by construction. Honest state: EMPTY (measured,
none), never zero. CML can populate a plain (non-staged) 5-year survival figure.

Every value above is a stage-specific 5-year relative survival rate with
standard error, 95% CI, and case count in the raw payload
(data_series = [rate, rate_se, lower_ci, upper_ci, count]). Verified 2026-07-18.

### ID verification against the source
Site codes confirmed from get_var_formats.php, not assumed: 47 Lung and Bronchus,
55 Breast, 40 Pancreas, 53 Melanoma of the Skin, 97 Chronic Myeloid Leukemia (CML).
The task's Open Targets EFO IDs do NOT map to SEER; SEER uses its own numeric
site codes, and NSCLC (EFO_0003060) has no 1:1 SEER site (documented above).

## (c) Licence / terms

SEER*Explorer content is produced by the U.S. National Cancer Institute (NIH/HHS).
As a U.S. federal government work it is generally public domain (17 U.S.C.
Section 105); NCI's reuse policy allows reuse of its graphics and text, typically
without permission, with a suggested citation requested (SEER*Explorer, NCI). The
signed data-use agreement applies to the SEER research microdata, not to these
published aggregate statistics. Net: aggregate stage-wise survival is
redistributable with attribution, effectively public domain.

## Verdict: AMBER (green-leaning for solid tumors)

Rationale. Access is unambiguously open and the data is excellent: real
stage-wise 5-year relative survival, with SE/CI/counts, for 4 of 5 targets, from
endpoints requiring no auth. That alone clears the no-login bar and would render a
rich survival card for Breast, Pancreatic, Melanoma, and NSCLC.

Two honest caveats keep it from GREEN:
1. NSCLC is not a native entity -- it must be modeled as a Lung-and-Bronchus
   superset (includes SCLC) or assembled from histology subtypes. Data is there;
   the entity mapping is not free.
2. CML cannot render the stage-wise block (leukemia isn't stage-decomposed) --
   a structural EMPTY, so the stage-wise block is inapplicable to 1 of 5. A
   generic (non-staged) survival value is available for CML.

So the block is a strong POPULATED for solid tumors and needs per-cancer handling
(staged vs. non-staged; NSCLC proxy). Availability is high; uniform 5/5 stage-wise
coverage is not achievable because one target is a liquid tumor.

### Risks / notes for the next builder
- Endpoints are undocumented and internal -- no stability contract. They can
  change without notice (schema drift risk). Pin behavior in an adapter test.
- Response is double-encoded: a JSON string whose content is JSON. Parse twice.
- Row keys are sex_race_age_stage_subtype_site. sex: 1 = Both, 2 = Male, 3 =
  Female. Breast defaults to Female (site is female-dominant); passing sex=1
  (Both) on breast returns the Male subset instead -- use sex=3 for the
  representative female cohort.
- data_model=3 = Preliminary Estimates (Selected Registries 2000-2024). For
  "NCI Official Statistics" use data_model=4 (SEER 21, 2000-2023).
- No API key raises limits, but be a good citizen: cache, set a real User-Agent.
  (Unlike ClinicalTrials.gov, SEER did not 403 a bare UA, but Mozilla/5.0 was used.)

## Files
- probe.sh -- the raw curl calls (access check, dictionary, per-cancer survival).
- probe.py -- stdlib-only version that fetches and prints the coverage table.
- var_formats.json -- captured SEER code<->label dictionary (written by probe.sh).
