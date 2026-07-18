# Disease-source mapping coverage (Gate 1)

How much of the cancer catalog the Eurostat (epidemiology) and SEER (survival) source
vocabularies can attach to, resolved **by MONDO ontology ancestors, never by name string**.

- **Mapping:** [`disease_source_map.csv`](disease_source_map.csv) — 20 mapped Eurostat ICD-10
  sites + 3 recorded-unmappable aggregates, plus 16 SEER site codes, resolving to **23
  distinct MONDO categories** (many shared across the two sources).
- **Method:** for each of the 1,321 catalog cancers (E2E fixtures excluded), fetch its MONDO
  ancestors from Open Targets; it is `exact` if its own MONDO id is a mapped category,
  `rollup` if an ancestor is, `unmapped` otherwise. No text comparison anywhere. This counts
  a cancer as covered if *any* mapped ancestor exists; the resolver additionally sends a
  genuinely ambiguous multi-parent cancer (two incomparable mapped ancestors) to `unmapped`,
  so the covered figures below are an upper bound on what actually attaches.
- **Measured:** 2026-07-18, against the live catalog + Open Targets. The brain and uterine
  nodes were widened after review (see *Curation revisions* below), which is why coverage
  exceeds the initial Gate-1 commit.

## Both numbers — and why both are needed

"66.6% of cancers" reads as middling; "79.8% of the pipeline weight" reads as flattering.
Both are true; only together are they honest.

| basis | exact | rollup | unmapped | **covered (exact+rollup)** |
|---|---|---|---|---|
| **catalog entries** (n=1,321) | 20 (1.5%) | 860 (65.1%) | 441 (33.4%) | **880 (66.6%)** |
| **pipeline weight** (by drug count) | 28.2% | 51.6% | 20.2% | **79.8%** |

Pipeline weight uses drug count per cancer as a proxy for how likely a page is actually
opened — so coverage is highest exactly where readers go.

## The load-bearing consequence

**Roll-up dominates: 65.1% of entries (51.6% of weight) are `rollup`, only 1.5% `exact`.**
Most covered cancers therefore display a *broader* entity's figures — NSCLC → lung cancer
(pools SCLC), TNBC → breast cancer, glioblastoma → CNS cancer. Those pages must NAME the
entity the numbers describe (*"Statistics for: lung cancer — broader than NSCLC"*), never
pass them off as the specific cancer's. That is the whole reason the mapping carries
`match_type` + the target entity's label, not just a MONDO id.

Unmapped cancers (33.4% of entries) render the honest *"not available for this cancer"*
state — a property of the mapping, never a data outage.

## Curation revisions (post-review)

Adversarial review of the crosswalk, verified live against Open Targets, corrected two nodes
that were too narrow to carry the entities they claimed:

- **Brain/CNS** (`C70-C72`, SEER 76): `MONDO_0001657` "brain cancer" → `MONDO_0002714`
  "central nervous system cancer". Glioblastoma is **not** a descendant of "brain cancer" in
  MONDO, so GBM and the gliomas silently failed to roll up; the CNS node is a clean superset
  and matches the ICD site (meninges + brain + spinal cord) better.
- **Uterine** (`C54_C55`, SEER 58): `MONDO_0011962` "endometrial cancer" → `MONDO_0002715`
  "uterine cancer". C54–C55 includes uterine sarcomas and carcinosarcoma, which are **not**
  descendants of "endometrial cancer"; they now roll up. The wider node nominally subsumes
  cervix, but closest-wins keeps cervical cancers on their own site (`C53` / SEER 57).

Two mappings are retained as least-bad with the imprecision recorded in the CSV `note`:
head & neck (`C00-C14` → `MONDO_0005627`) over-claims relative to the lip/oral/pharynx source
(no clean single MONDO node for that subset exists), and melanoma (`C43` → `MONDO_0005105`) is
the all-melanoma node against a cutaneous-only source (>90% of melanoma is cutaneous).
