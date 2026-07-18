# Disease-source mapping coverage (Gate 1)

How much of the cancer catalog the Eurostat (epidemiology) and SEER (survival) source
vocabularies can attach to, resolved **by MONDO ontology ancestors, never by name string**.

- **Mapping:** [`disease_source_map.csv`](disease_source_map.csv) — 22 Eurostat ICD-10 sites
  (20 mapped, 3 recorded unmappable) + the SEER site codes for the major cancers.
- **Method:** for each of the 1,321 catalog cancers (E2E fixtures excluded), fetch its MONDO
  ancestors from Open Targets; it is `exact` if its own MONDO id is a mapped category,
  `rollup` if an ancestor is, `unmapped` otherwise. No text comparison anywhere.
- **Measured:** 2026-07-18, against the live catalog + Open Targets.

## Both numbers — and why both are needed

"60.9% of cancers" reads as damning; "76.5% of the pipeline weight" reads as flattering.
Both are true; only together are they honest.

| basis | exact | rollup | unmapped | **covered (exact+rollup)** |
|---|---|---|---|---|
| **catalog entries** (n=1,321) | 20 (1.5%) | 784 (59.3%) | 517 (39.1%) | **804 (60.9%)** |
| **pipeline weight** (by drug count) | 28.9% | 47.5% | 23.5% | **76.5%** |

Pipeline weight uses drug count per cancer as a proxy for how likely a page is actually
opened — so coverage is highest exactly where readers go.

## The load-bearing consequence

**Roll-up dominates: 59.3% of entries (47.5% of weight) are `rollup`, only 1.5% `exact`.**
Most covered cancers therefore display a *broader* entity's figures — NSCLC → lung cancer
(pools SCLC), TNBC → breast cancer. Those pages must NAME the entity the numbers describe
(*"Statistics for: lung cancer — broader than NSCLC"*), never pass them off as the specific
cancer's. That is the whole reason the mapping carries `match_type` + the target entity's
label, not just a MONDO id.

Unmapped cancers (39.1% of entries) render the honest *"not available for this cancer"*
state — a property of the mapping, never a data outage.
