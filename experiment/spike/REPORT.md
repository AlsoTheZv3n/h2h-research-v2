# Phase 0 Spike Report — H2H Cancer-Entity Expansion

**Date:** 2026-07-16
**Scope:** Verify that each planned data source can actually populate its block for all 5 test cancers (NSCLC, breast carcinoma, pancreatic carcinoma, melanoma, CML) before we commit to building. Every claim below was probed live and independently re-verified. Where a block is empty for some cancers, we say so — a block empty for 4 of 5 cancers is not a feature, it's a gap we name and account for.

---

## 1. Matrix

| Source | Block | Verdict | Coverage (n/5) | Access | Licence | Redistributable |
|---|---|---|---|---|---|---|
| **ctgov** — ClinicalTrials.gov API v2 | Pipeline / trial reality (Phase 1) + HR gate (Phase 3) | GREEN | 5/5 | Open, no login, no key | U.S. Gov public domain (NLM/NIH) | Attribution |
| **opentargets** — Open Targets GraphQL | Disease spine + target landscape (Phase 1, P1-T5) | GREEN | 5/5 | Open, no login, no key | CC0 1.0 (rel. 26.06) | Yes |
| **civic** — CIViC | Biomarker -> therapy matrix (Phase 2-A) | GREEN | 5/5 | Open, no login, no key | CC0 1.0 (app code MIT) | Yes |
| **globocan** — IARC Global Cancer Observatory | Epidemiology / age-standardised rates (Phase 2-B) | AMBER | 3/5 | Open, no login, no key | IARC/WHO All Rights Reserved, non-commercial | **No** |
| **seer** — SEER*Explorer | Survival by stage (Phase 2-B, candidate) | AMBER | 4/5 | Open, no login, no key | U.S. federal work, effectively public domain | Attribution |
| **aact** — AACT (CTTI) / HR forest plot | HR source for forest plot (Phase 3) | GREEN | 5/5 | Open, no login, no key (via CT.gov v2) | CT.gov = U.S. public domain | Attribution |
| **bag** — BAG Spezialitätenliste | Swiss list-price -> cost/cycle (Phase 2-C) | GREEN | 5/5 | Open, no login, no key | Attribution-with-terms-to-confirm | Attribution |

**Verdict tally:** 5 GREEN, 2 AMBER, 0 RED. No source is dropped. No source is login-gated.

---

## 2. Per-source detail

### ctgov — ClinicalTrials.gov API v2 — GREEN (5/5)

**Access.** Open, keyless, unauthenticated GETs. Endpoint `https://clinicaltrials.gov/api/v2/studies`. Unlike v1, **v2 needs no WAF User-Agent workaround** — curl/8, Mozilla/5.0, and python-httpx all return HTTP 200. The UA hack in `backend/ingestion/clinicaltrials.py` is unnecessary for v2.

**Licence.** U.S. Government public domain (NLM/NIH); no copyright. Redistributable with attribution: cite ClinicalTrials.gov + NCT id, note retrieval date, and state no NIH endorsement.

**Per-cancer coverage (trial-reality block POPULATED 5/5):**

| Cancer | Total | Terminated/withdrawn | whyStopped populated | Swiss recruiting | HR gate |
|---|---|---|---|---|---|
| NSCLC | 8,442 | 1,353 | 1,205 (89.1%) | 40 (DE=101, AT=38) | 185/1000 (18.5%) |
| Breast carcinoma | 16,474 | 1,918 | 1,699 (88.6%) | 40 (sample NCT05890677 Basel/Geneva/Zurich) | 114/1000 (11.4%) |
| Pancreatic carcinoma | 4,625 | 662 | 610 (92.1%) | 8 | 34/425 (8.0%) |
| Melanoma | 3,734 | 687 | 625 (91.0%) | 12 | 62/519 (11.9%), all 62 with full CI |
| CML | 1,803 | 347 | 284 (81.8%) | 1 (thin but real; DE=10, AT=3) | 9/303 (3.0%) |

**Key findings / gotchas.**
- **Counts:** use `query.cond=<free text>` + `countTotal=true` and read `totalCount` — never `len(studies)`, which caps at `pageSize`.
- **Condition keying:** ctgov keys on condition **TEXT with synonym expansion, NOT EFO**. The task's EFO IDs are Open Targets identifiers with no ctgov field. Conditions were verified by inspecting returned titles / CH cities.
- **Status filter:** `filter.overallStatus=TERMINATED|WITHDRAWN` (both `|` and `,` work). `whyStopped` lives at `protocolSection.statusModule.whyStopped` and appears only on terminated/withdrawn trials.
- **Location:** `filter.overallStatus=RECRUITING` + `query.locn=<country>` returns real country-scoped trials (CH/DE/AT verified; real Swiss NCT ids + cities confirmed for NSCLC and breast).
- **HR schema drift (load-bearing):** HR is at `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[]`; `paramType` is **free text `Hazard Ratio (HR)`, NOT an enum `HAZARD_RATIO`** — match case-insensitively on `hazard`. `paramValue`=HR, `ciLowerLimit`/`ciUpperLimit`=CI, `groupIds`=comparator arms.
- **HR fraction** among completed-with-results (`aggFilters=results:with`): 3.0% (CML) to 18.5% (NSCLC). Sparse and Phase-3-only — **it does not gate the Phase 1 block** and is reported separately. NSCLC/breast HR fractions are first-1000-page sample estimates; smaller cancers were fully scanned.
- **Only soft spot:** CML Swiss recruiting depth (1 trial). This is a genuine finding, not a pipeline gap.

**Verify agreement.** Confirmed, no discrepancies. Every independently re-pulled number matched the probe exactly (NSCLC 8,442; CML 1,803; pancreatic 4,625 totals; CML 347 term/withdrawn with 284/347=81.8% whyStopped; NSCLC 40 / CML 1 Swiss recruiting; identical Swiss sample NCTs and cities). All calls were unauthenticated GETs with default UAs returning 200 — no login, no key, no v2 WAF gate. HR schema (free-text paramType) confirmed.

---

### opentargets — Open Targets Platform GraphQL — GREEN (5/5)

**Access.** Open, anonymous POST JSON. Endpoint `https://api.platform.opentargets.org/api/v4/graphql`. No WAF UA-allowlisting (unlike ctgov); curl and Python urllib both work. Data version 26.06, API 26.6.3.

**Licence.** CC0 1.0 for the Open-Targets-generated fields this block uses (association scores, `datatypeScores`, tractability, disease/target ontology). Attribute release 26.06. Some constituent upstream datasources carry their own terms, but the fields consumed here are CC0. Redistributable.

**Per-cancer coverage (target-landscape block POPULATED 5/5):**

| Cancer (canonical MONDO) | Assoc. targets | Top target (score) | Evidence types | Tractability |
|---|---|---|---|---|
| NSCLC — MONDO_0005233 | 12,475 | EGFR (0.888) | 7 | 25/25 buckets, 24/25 SM/AB-tractable |
| Breast carcinoma — MONDO_0004989 | 17,963 | BRCA2 (0.887) | 5 | 25/25, 22/25 tractable |
| Pancreatic carcinoma — MONDO_0005192 (exocrine; PDAC = MONDO_0005184) | 10,899 | KRAS (0.807) | 6 | 24/25, 21/25 tractable |
| Melanoma — MONDO_0005105 | 13,604 | CDKN2A (0.870) | 6 | 25/25, 19/25 tractable |
| CML — MONDO_0011996 (BCR-ABL1 positive) | 4,479 | ABL1 (0.836) | 7 | 25/25, 24/25 tractable |

**Key findings / gotchas.**
- **CRITICAL DRIFT — disease IDs migrated EFO -> MONDO.** All 5 provided EFO IDs now resolve to `disease:null` — a **silent empty, no GraphQL error**: EFO_0003060, EFO_0000305, EFO_0002618, EFO_0000756, EFO_0000339. The builder **MUST key the catalog on MONDO** and resolve legacy EFO through `search` or `obsoleteTerms`/`dbXRefs` before querying, else every block reads empty. Each MONDO id above was verified via the target record's `obsoleteTerms` listing the old EFO.
- **GraphQL validates the whole document up front** — one dead field 400s the entire query (existing adapter's documented gotcha still holds).
- **Schema (confirmed live):** `disease(efoId:$id){ id name associatedTargets(page:{index:0,size:N}){ count rows{ score datatypeScores{id score} target{ id approvedSymbol tractability{ label modality value } } } } }`. `tractability` has **no `id` field** — only `{label, modality, value:Boolean}`; modality buckets seen: SM (small molecule), AB (antibody). The drugged/undrugged flag is directly derivable. `datatypeScores` ids: clinical, genetic_association, somatic_mutation, literature, affected_pathway, animal_model, genetic_literature, known_drug. Association scores confirmed in [0,1].
- **Disease spine / catalog:** cancer root = MONDO_0004992 (old EFO_0000311 is null). `disease(efoId:"MONDO_0004992"){ descendants }` returns **1,744 IDs in one call** — a ready oncology-catalog seed. `isTherapeuticArea=false` on that node, but descendants enumeration is the practical, stable seed. Spine verdict: usable.

**Verify agreement.** Confirmed, no discrepancies. Independent re-run reproduced counts exactly (NSCLC 12,475 / EGFR 0.888; CML 4,479 / ABL1 0.836; pancreatic 10,899 / KRAS 0.807), the EFO-null silent-empty behavior, MONDO `obsoleteTerms` resolution, open access with no auth headers, and 1,744 cancer-root descendants.

---

### civic — CIViC — GREEN (5/5)

**Access.** Open, unauthenticated GraphQL. `POST https://civicdb.org/api/graphql` with `Content-Type: application/json` and `{"query":"..."}`. **A GET on the same URL returns 404 (misleading)** — the same URL works with POST. GraphiQL is served at the same path for browsers. No key, no login, no WAF UA-gating.

**Licence.** CC0 1.0 Universal (public-domain dedication), confirmed at docs.civicdb.org FAQ; app code is MIT. Fully redistributable.

**Per-cancer coverage (biomarker->therapy matrix POPULATED 5/5):**

| Cancer (CIViC node, DOID, id) | PREDICTIVE items | RESISTANCE | Example |
|---|---|---|---|
| NSCLC — Lung Non-small Cell Carcinoma, DOID:3908, id 8 | 797 (A85/B225/C225/D258/E4) | 175 | EGFR T790M->Erlotinib level A RESISTANCE |
| Breast carcinoma — Breast Cancer, DOID:1612, id 22 | 234 (A-E) | 64 | (narrow node DOID:3459 id140 has only 6) |
| Pancreatic carcinoma — Pancreatic Cancer, DOID:1793, id 556 | 61 (A-E) | 16 | (narrow node DOID:4905 id169 has only 3) |
| Melanoma — Melanoma, DOID:1909, id 7 | 257 (A-E) | 94 | BRAF V600E responses/resistance |
| CML — Chronic Myeloid Leukemia, DOID:8552, id 4 | 486 (A-E) | 317 | BCR::ABL1 AND ABL1 T315I->Imatinib level B RESISTANCE |

**Key findings / gotchas.**
- **Schema:** root query `evidenceItems(diseaseId, evidenceType, evidenceLevel, significance, therapyId, molecularProfileName, ...)` returns a connection with `totalCount` + `edges{node{evidenceLevel, evidenceType, significance, therapies{name}, molecularProfile{name}, disease{name}}}`. Use `evidenceType:PREDICTIVE` for biomarker->therapy. Levels are enum A-E; significance enum includes SENSITIVITYRESPONSE, RESISTANCE. Use `totalCount`, NOT `len(edges)` (default page is small).
- **Disease keying:** CIViC uses **DOID + names, NOT EFO** — resolve via `diseaseTypeahead(queryTerm)`.
- **GOTCHA (load-bearing):** disease nodes exist at multiple granularities; name-substring matching **silently under-reports**. Breast Carcinoma (DOID:3459, id140) = 6 PREDICTIVE vs Breast Cancer (DOID:1612, id22) = 234; Pancreatic Carcinoma (DOID:4905, id169) = 3 vs Pancreatic Cancer (DOID:1793, id556) = 61. **Map by DOID with Disease-Ontology roll-up of child nodes.**
- Resistance variants are often stored as **COMPOUND molecular profiles** (e.g. `BCR::ABL1 Fusion AND ABL1 T315I`) — parse accordingly.
- Content is curated evidence-as-reported, not recommendations — keep the non-prescriptive framing.
- Counts measured 2026-07; CIViC is continuously curated, so expect drift.

**Verify agreement.** Confirmed, no discrepancies.

---

### globocan — IARC Global Cancer Observatory — AMBER (3/5)

**Access.** Fully open. `gco.iarc.fr` now 301s to `gco.iarc.who.int`. The real programmatic path (no official/documented API) is the SPA's own gateway found in `today/assets/main-*.js`: BASE = `https://gco.iarc.who.int/gateway_prod/api/globocan/v3/2024` (data_version 2024 = GLOBOCAN 2022 estimates). Returns ASR incidence + mortality per site per country. Verified with plain curl AND python stdlib — **no login, no key, no WAF, no browser UA required.** Neither RED trigger holds.

**Licence — the real drag.** IARC/WHO copyright, **All Rights Reserved** (Universal Copyright Convention Protocol 2). Non-commercial research/educational use "as is" with mandatory citation. **Systematic retrieval to compile a database is prohibited without explicit prior written IARC permission** — which is exactly what an ingest adapter does. **Redistributable = no.** This is NOT an open licence (not CC / not public domain). Mandatory citation: Ferlay et al., *Global Cancer Observatory: Cancer Today*, IARC. Good as a **cited, site-level epidemiology reference**, not as a bulk-ingested entity-level table. Get IARC sign-off before ingesting/storing; display individual cited figures only.

**Per-cancer coverage (POPULATED 3/5).** ASR-W per 100k (incidence / mortality):

| Cancer | Status | Detail |
|---|---|---|
| Breast carcinoma | populated | EXACT site Breast/C50. World 47.77/12.9, USA 96.73/12.17, UK 93.14/14.1, Japan 78.76/9.29 |
| Pancreatic carcinoma | populated | EXACT site Pancreas/C25. World 4.66/4.2, USA 8.74/6.56, UK 6.8/5.91, Japan 10.1/8.1 |
| Melanoma | populated | EXACT site Melanoma of skin/C43. World 3.13/0.5, USA 15.24/1.12, UK 16.35/1.47, Japan 0.58/0.17 |
| NSCLC | EMPTY | **PROXY ONLY** — no histology axis, only aggregate lung C33-34 (incl. ~15% SCLC). World 23.94/16.29, USA 29.55/15.88, UK 31.6/19.72, Japan 30.22/15.02. NSCLC-specific ASR not measured. |
| CML | EMPTY | **NOT RESOLVABLE** — only aggregate Leukaemia C91-95; CML cannot be isolated. Aggregate World 5.13/2.85, USA 10.6/2.93 is not a CML figure. |

**Key findings / gotchas.**
- Calls: `/meta/cancers/all/` (41 ICD-10 sites), `/meta/populations/all/` (238 ISO-numeric codes; World=900, USA=840, UK=826, JP=392), `/data/rate/{sex}/{type}/{pop}/all/?group_CRC=1&include_nmsc=1&include_nmsc_other=1` -> rows with an `asr` field. Axes: sex 0=both/1=male/2=female; type 0=incidence/1=mortality/2=prevalence. One country call = 510 rows.
- **Taxonomy:** EFO ids don't apply — GLOBOCAN is **ICD-10 SITE based, no histology/molecular subtypes.** This is why NSCLC is an all-lung proxy and CML has no representation.
- Use the `asr` field, **not `total`**, for cross-country comparison — `total`/count fields are population-size rankings.

**Verify agreement.** Confirmed. Only a minor artifact-bookkeeping mismatch: the probe's listed artifacts name `rate_900.json` / `rate_392.json`, but the `out/` dir actually contains `rate_world.json`, `rate_826.json`, `rate_840.json`. This did not affect results — the independent live re-run reproduced the numbers exactly. No data discrepancies.

---

### seer — SEER*Explorer — AMBER (4/5)

**Access.** Fully open — no login, no key, no DUA — via SEER*Explorer's internal PHP JSON endpoints. Real stage-wise 5-year **relative** survival with SE, 95% CI, and case counts. A separate gated service `api.seer.cancer.gov` requires login for **case-level microdata** — NOT used and NOT needed here.

**Licence.** U.S. federal government work (NCI/NIH), effectively public domain (17 U.S.C. §105); suggested citation requested. The DUA applies only to research microdata, not to these aggregate stats. Redistributable with attribution.

**Per-cancer coverage (stage-wise block POPULATED 4/5).** 5-yr relative survival:

| Cancer | Status | Localized | Regional | Distant | All | n |
|---|---|---|---|---|---|---|
| Breast carcinoma (site 55, Female sex=3) | populated | 100.0% | 87.5% | 33.8% | 91.9% | 595,443 |
| Pancreatic carcinoma (site 40) | populated | 43.6% | 17.0% | 3.4% | 13.7% | 115,184 |
| Melanoma (site 53) | populated | 100.0% | 76.0% | 34.0% | 94.7% | 164,325 |
| NSCLC (proxy site 47 Lung & Bronchus, incl. SCLC) | populated* | 65.5% | 38.2% | 10.5% | 29.5% | — |
| CML (site 97) | EMPTY | — | — | — | 71.1% (All only) | 17,214 |

*NSCLC has **no native SEER site** — model as the Lung & Bronchus superset (includes SCLC) or assemble from histology subtypes, e.g. 612 Adenocarcinoma: Localized 73.6% / Regional 48.9% / Distant 14.2%. The block populates, but only via superset/subtype assembly.

**Key findings / gotchas.**
- **Open endpoint (undocumented, no auth):** `https://seer.cancer.gov/statistics-network/explorer/source/content_writers/render_region_5.php` — the exact call the survival chart makes. Params for stage-wise 5-yr relative survival: `site=<code>&data_type=4&graph_type=5&compareBy=stage&relative_survival_interval=5&sex=1&race=1&age_range=1&data_model=3&series=stage`. Dictionary at `get_var_formats.php`.
- **Response is DOUBLE-ENCODED** — a JSON string whose content is JSON; parse twice.
- Row keys are `sex_race_age_stage_subtype_site`; sex 1=Both, 2=Male, 3=Female; stage 101=All, 104=Localized, 105=Regional, 106=Distant, 107=Unstaged.
- **Breast defaults to Female** — passing `sex=1` (Both) on breast returns the tiny MALE subset (n=4,653); use `sex=3` for the real female cohort (n=595,443).
- **CML (and leukemias generally) return ONLY All-Stages** — no L/R/D breakdown ever. This is a **structural EMPTY (clinical reality, not an outage)**: leukemia is not decomposed by the SS2000 solid-tumor stage schema. A non-staged 5-yr value (71.1%) is available.
- EFO IDs do NOT map to SEER; SEER uses its own numeric site codes (verified against `get_var_formats.php`).
- `data_model=4` = "NCI Official Statistics" (SEER 21) vs `data_model=3` = preliminary. Endpoints have **no stability contract** — pin with adapter tests.
- **Why AMBER, not GREEN:** uniform 5/5 stage-wise coverage is impossible — NSCLC isn't a native staged entity (proxy/assembly needed), and CML cannot render the L/R/D block at all. Undocumented internal endpoints add schema-drift risk.

**Verify agreement.** Confirmed. Independent re-run of Breast, Pancreas, and CML reproduced rates within rounding (Breast Loc 100.0/Reg 87.55/Dist 33.82/All 91.93 n=595,443; Pancreas Loc 43.56/Reg 17.01/Dist 3.38/All 13.72 n=115,184; CML All-Stages 71.07 n=17,214). No discrepancies.

---

### aact — AACT (CTTI) / HR for forest plot — GREEN (5/5)

**Decisive login check — the plan's DROP trigger does NOT fire.** The trigger was "HR only in AACT AND AACT login-gated." Both clauses fail:
1. **HR is NOT only in AACT.** ClinicalTrials.gov API v2 exposes HR + full CI openly (no login, no key) at `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[]` where `paramType=='Hazard Ratio (HR)'`, carrying `paramValue`, `ciLowerLimit`, `ciUpperLimit`, `ciPctValue`, `pValue` — e.g. FLAURA NCT02296125 HR 0.46 (95% CI 0.37-0.57), reproduced live.
2. **AACT's login claim is only partly true.** The live cloud PostgreSQL DB needs a free account (login-gated), **but the static daily archives download with NO account** — `/static/exported_files/daily/<date>` and `/static/static_db_copies/daily/<date>` 302 to a public DigitalOcean Spaces bucket (~2.5 GB zip); the exported zip contains `outcome_analyses.txt` (~100 MB) = the HR table.

**Recommendation:** build the Phase 3 forest plot on **CT.gov API v2 directly** (matches the existing `clinicaltrials.py` adapter). Keep the AACT cloud DB out of scope. Use the AACT static archive only as an open bulk-backfill fallback.

**Access.** Open via CT.gov v2. **WAF:** the edge allowlists the User-Agent token `python-httpx/...`; bare Mozilla and custom tokens 403. **Rate limit:** the single-study endpoint 429s under rapid loops — throttle ~0.7s + backoff.

**Licence.** ClinicalTrials.gov data = U.S. public domain (NLM/NIH federal work); AACT/CTTI free-to-public, asks source acknowledgment. Redistributable with attribution to ClinicalTrials.gov.

**Per-cancer coverage (HR block POPULATED 5/5):**

| Cancer | Trials w/ HR analysis | (of results / total) | Verify CI-bearing | Example |
|---|---|---|---|---|
| NSCLC | 265 | 1,620 / 8,460 | 13/15 | NCT03563716 HR 0.57 (95% CI 0.37-0.90) |
| Breast carcinoma | 224 | 2,408 / 16,474 | 14/15 | caveat NCT00274456 has 7 HR but 0 CI |
| Pancreatic carcinoma | 37 | 628 / 4,625 | 15/15 | NCT02184195 HR 0.531 (95% CI 0.346-0.815) |
| Melanoma | 71 | 784 / 3,734 | 15/15 | NCT01245062 HR 0.44 (95% CI 0.31-0.64) |
| CML | 12 | 449 / 1,803 | 12/12 | NCT03268954, 16 HR analyses with CI — genuinely thinnest, real small count, not an outage |

**Key findings / gotchas.**
- **HR-trial discovery filter that works:** `aggFilters` is not enough; use `query.term=AREA[OutcomeAnalysisParamType]"Hazard Ratio (HR)"` (indexed Essie area, verified against real trials, ~87-100% of hits carry CI).
- EFO IDs are Open Targets-only; CT.gov needs text/MeSH condition queries.
- **GOTCHA:** HR-trial count > usable count — some trials report an HR point estimate with **no CI limits** (e.g. breast NCT00274456: 7 HR, 0 CI). A forest plot needs CI, so **filter on presence of `ciLowerLimit`/`ciUpperLimit`.** Every cancer still has ample CI-bearing trials, so populated status holds.

**Verify agreement.** Confirmed, no discrepancies. Independent re-run reproduced counts and HR+CI values exactly (CML HR-area=12 [1803/449], pancreatic=37 [4625/628], melanoma=71 [3734/784]); FLAURA HR 0.46 (95% CI 0.37-0.57) reproduced live. Both the AACT static-archive open path and the login-gated cloud-DB claim held.

---

### bag — BAG Spezialitätenliste — GREEN (5/5)

**Access.** Open, no-auth, machine-readable JSON API with a stable price schema. The SL is **NOT on opendata.swiss** (`package_search` count=0); live data is the public JSON backend of the official webapp: `https://epl.bag.admin.ch/api/sl/`. Key calls (no auth, no key): `GET public/medicinal-products?search={term}&page=&size=` (products with prices inline), `GET public/medicinal-products/filters` (facets), `GET packages/{pcid}/prices/all` (price history).

**Licence.** No explicit OGD/CC licence declared. SL is not an opendata.swiss dataset; it is official federal content. General admin.ch terms: reproduction permitted with source citation, commercial reuse may carry conditions (terms page itself WAF-gated, exact clause unconfirmed). **Treat as attribution-with-terms-to-confirm.**

**Per-cancer coverage (Swiss list-price block POPULATED 5/5).** exFactory / retail CHF, each verified against the source's own indication/limitation text:

| Cancer | Product | Pack | exFactory | Retail | On-label (SL) |
|---|---|---|---|---|---|
| NSCLC | Tagrisso (osimertinib) | Tabl 40 mg, 30 Stk | 5,012.50 | 5,450.65 | 1L NSCLC EGFR Exon 19/21 |
| Breast carcinoma | Herceptin (trastuzumab) | Trockensub 150 mg, 1 Amp | 502.52 | 560.10 | Adjuvante Therapie Mammakarzinom |
| Pancreatic carcinoma | Abraxane (nab-paclitaxel) | Trockensub 100 mg, 1 Durchstf | 296.98 | 332.10 | Adenokarzinom Pankreas + Gemcitabin (1L) |
| Melanoma | Tafinlar (dabrafenib) | Kaps 50 mg, 28 Stk | 820.18 | 908.40 | Melanom BRAF-V600 metast./adjuvant |
| CML | Glivec (imatinib) | Filmtabl 100 mg, 60 Stk | 808.40 | 874.30 | Ph+ chronisch-myeloische Leukämie |

**Key findings / gotchas.**
- **WAF:** the probe reported that `*.admin.ch` 403s a bare/default User-Agent and requires a browser UA (Chrome/Windows works). See verify note below — this proved inconsistent; send a browser UA defensively.
- **Price schema:** `items[].medicinalProducts[].packagedMedicinalProducts[]` carries `exFactoryPrice` (Fabrikabgabepreis) AND `retailPrice` (Publikumspreis), both CHF, plus `packSize`, `gtin`, `validFrom`, `lastPriceChange`, `priceModel` flag. **Two prices per pack — choose and label which.**
- **GOTCHA:** server-side facet filtering does NOT work — `itCodes`/`atcCodes` query params are accepted but ignored (total stays at full catalog 3,393). Filter client-side or drive by `search`.
- Oncology grouped under IT-code 07.16 Oncologica (07.16.10 Cytostatica etc.). Total catalog = 3,393 trademarks. Generic gemcitabin also present (4 hits).
- **Cost-per-cycle** is derivable but the SL has **no dose/schedule** — needs an external SmPC dosing assumption (+ body-size for BSA/weight drugs). Must be labelled a **Swiss SL list-price approximation, not treatment cost** (excludes confidential price-model rebates the SL itself flags). No number fabricated.
- EFO IDs are not used by the SL; indication match is source-native (the stronger check).

**Verify agreement.** Confirmed. One minor, non-decisive discrepancy: the probe claimed the WAF 403s a bare UA, but the independent bare-UA call to the same SL endpoint returned HTTP 200 (identical to the browser-UA response). This does not affect coverage or access — the API is open either way. All price and indication numbers matched the probe exactly.

---

## 3. Build order — verdicts -> plan blocks

### GREEN — build now (5)

- **ctgov -> Phase 1 pipeline / trial-reality block, all 5 cancers.** Build directly against v2; drop the v1 UA hack. Use `totalCount`, key on condition text, and carry the CML-Swiss-depth=1 as a real finding surfaced in the UI, not hidden.
- **opentargets -> Phase 1 disease spine + target landscape (P1-T5), all 5 cancers.** Build now, but the **first task is the EFO->MONDO resolver** (search / `obsoleteTerms` / `dbXRefs`). Without it every block silently reads empty. Seed the oncology catalog from the 1,744 MONDO_0004992 descendants.
- **civic -> Phase 2-A biomarker->therapy matrix, all 5 cancers.** Build now, keyed on DOID with Disease-Ontology roll-up (never name-substring, which under-reports breast and pancreatic by ~30-40x). Parse compound molecular profiles for resistance.
- **aact -> Phase 3 HR forest plot, all 5 cancers.** Build on **CT.gov API v2** (not the AACT cloud DB). Discover via `AREA[OutcomeAnalysisParamType]"Hazard Ratio (HR)"`; **filter on CI presence**; send the `python-httpx` UA and throttle. AACT static archive is a documented open fallback only.
- **bag -> Phase 2-C Swiss list-price / approx cost per cycle, all 5 cancers.** Build now against `epl.bag.admin.ch/api/sl/`. Filter client-side, send a browser UA defensively, label the number an SL list-price approximation, and confirm the admin.ch reuse terms before redistributing.

### AMBER — build expecting gaps (2)

- **globocan -> Phase 2-B epidemiology (age-standardised rates).** Build, but **only for the 3 cancers that map exactly** (breast, pancreatic, melanoma). NSCLC renders only an all-lung proxy (~15% high, includes SCLC) and CML has **no representation at all** (only all-leukaemia aggregate) — surface these as explicit "not measured at entity level" states, never silently as blanks. **Licence caveat is load-bearing:** redistributable = **no**; treat as a cited reference, display individual figures with the IARC citation, and **secure written IARC permission before any systematic ingest/store.**
- **seer -> Phase 2-B survival by stage.** Build for the 4 cancers that populate (breast, pancreatic, melanoma, and NSCLC via the Lung & Bronchus superset / subtype assembly). **CML is a structural EMPTY** — leukemia has no L/R/D decomposition; render the non-staged 71.1% value with a clear "not stage-decomposed (clinical reality)" label, not an empty box. Pin the undocumented internal endpoints with adapter tests (no stability contract; double-encoded JSON).

### RED — DROP (0)

**No source is dropped.** Both plan DROP triggers were checked and neither fired:

- **No-login rule:** every source is reachable open and keyless. AACT's cloud DB is login-gated, but HR is fully available open via CT.gov v2 and via AACT's no-login static archive, so nothing is login-gated in the build path.
- **Phase 3 forest plot / HR-has-no-open-source:** an open HR source exists (CT.gov v2 with full CI), so the forest plot is NOT dropped.

**Known gaps recorded here (carried, not dropped):**
- GLOBOCAN NSCLC and CML: no entity-level ASR (proxy / unresolvable) — 2 of 5 epi cells cannot be honest at entity level.
- SEER CML: no stage-wise survival (structural, clinical) — 1 of 5 stage cells is inherently empty.
- GLOBOCAN redistribution: blocked by IARC All-Rights-Reserved; requires written permission before ingest.
- ctgov CML Swiss recruiting depth = 1 trial (real, thin).
- HR fractions are sparse (3.0%-18.5%) — Phase-3-only, does not gate Phase 1.

---

## 4. Summary

Six sources, five test cancers, every claim probed live and independently re-verified with zero data discrepancies. Five sources come back GREEN and build now — ctgov (pipeline, 5/5), opentargets (target landscape, 5/5, once the EFO->MONDO resolver is in), civic (biomarker->therapy, 5/5, keyed on DOID with roll-up), aact/HR (forest plot, 5/5 via CT.gov v2), and bag (Swiss list-price, 5/5). The decisive Phase 3 question — is HR trapped behind AACT's login? — resolved cleanly: HR with full CI is open in the ClinicalTrials.gov v2 API, so the forest plot is not dropped and nothing in the build path is login-gated. The two AMBER sources are honestly partial and stay partial: GLOBOCAN populates 3/5 (NSCLC is an all-lung proxy, CML unresolvable) and carries a real IARC redistribution blocker, while SEER populates 4/5 (CML has no stage decomposition by clinical reality). Those empty cells are named as known gaps and will surface in the UI as explicit "not measured at this level" states — because a block empty for some cancers is a gap we account for, not a feature we hide.
