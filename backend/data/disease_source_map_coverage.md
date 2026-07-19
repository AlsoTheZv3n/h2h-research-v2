# Disease-source mapping coverage (Gate 1)

How much of the cancer catalog the Eurostat (epidemiology) and SEER (survival) source
vocabularies can attach to, resolved **by MONDO ontology ancestors, never by name string**.

- **Mapping:** [`disease_source_map.csv`](disease_source_map.csv) — 20 mapped Eurostat ICD-10
  sites + 3 recorded-unmappable aggregates, plus 24 SEER site codes, resolving to **25
  distinct MONDO categories** (many shared across the two sources).
- **Method:** for each of the 1,321 catalog cancers (E2E fixtures excluded), fetch its MONDO
  ancestors from Open Targets; it is `exact` if its own MONDO id is a mapped category,
  `rollup` if an ancestor is, `unmapped` otherwise. No text comparison anywhere. This counts
  a cancer as covered if *any* mapped ancestor exists; the resolver additionally sends a
  genuinely ambiguous multi-parent cancer (two incomparable mapped ancestors) to `unmapped`,
  so the covered figures below are an upper bound on what actually attaches.
- **Measured:** 2026-07-19, against the live catalog + Open Targets. The brain and uterine
  nodes were widened, and the SEER survival vocabulary extended, after review (see the
  revision sections below), which is why coverage exceeds the initial Gate-1 commit.

## Both numbers — and why both are needed

"66.6% of cancers" reads as middling; "79.8% of the pipeline weight" reads as flattering.
Both are true; only together are they honest. This is the **union** across both sources — a
cancer counts as covered if it attaches to Eurostat OR SEER.

| basis | exact | rollup | unmapped | **covered (exact+rollup)** |
|---|---|---|---|---|
| **catalog entries** (n=1,321) | 21 (1.6%) | 859 (65.0%) | 441 (33.4%) | **880 (66.6%)** |
| **pipeline weight** (by drug count) | 30.6% | 49.2% | 20.2% | **79.8%** |

Pipeline weight uses drug count per cancer as a proxy for how likely a page is actually
opened — so coverage is highest exactly where readers go.

### Per source — the two blocks are not covered equally

The union hides which block a page actually gets. Measured separately:

| source (block) | categories | entries covered | pipeline weight |
|---|---|---|---|
| **Eurostat** (epidemiology) | 20 | 66.6% | 79.8% |
| **SEER** (survival) | 24 | 65.0% | 78.7% |

Survival was the narrower of the two until the SEER vocabulary was extended from 16 to 24
sites (see *SEER survival extension* below); it now nearly matches epidemiology. A cancer can
still show one block and not the other — e.g. an entity with a Eurostat site but no SEER one
renders the epidemiology bars and an honest "not available for this cancer" for survival.

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

## SEER survival extension

The SEER vocabulary lagged Eurostat: several entities with a Eurostat mortality site had no
SEER survival site, so their survival card read "not available" even though SEER carries the
data. Eight SEER sites were added (each verified live to return a populated stage-wise or
all-stages figure), mapped to the same MONDO entities the Eurostat side already used:

- **oral cavity & pharynx** (site 3 → `MONDO_0005627`, the head & neck node — same over-claim
  caveat as the Eurostat side), **stomach** (18), **ovary** (61), **prostate** (66),
  **urinary bladder** (71), **thyroid** (80).
- **Hodgkin lymphoma** (83 → `MONDO_0004952`). **Non-Hodgkin lymphoma was deliberately NOT
  added**: MONDO dual-classifies the lymphoid leukemias (CLL, ALL, and others) under *both*
  leukemia and non-Hodgkin lymphoma, so an NHL site would make those cancers hit two
  incomparable mapped ancestors — leukemia (90) and NHL — which `resolve()` correctly refuses
  to break, sending them to `unmapped` and dropping the real leukemia survival they show today.
  Leaving NHL out keeps the lymphoid leukemias on their leukemia site; a pure-NHL page shows
  survival "not available" (as it did before), never a regression. Hodgkin has no such overlap.

### Myeloma — survival fixed, epidemiology a documented limitation

`MONDO` nests **plasma cell myeloma** under "lymphoma" (`MONDO_0005062`), so a myeloma page was
rolling its *mortality* up to the Eurostat `C81-C86` lymphoma figures — medically wrong, myeloma
is not a lymphoma. There is no clean fix on the Eurostat side: myeloma's ICD home is `C90`,
which sits in the unmappable `C88_C90_C96` grab-bag, and Eurostat exposes no separate myeloma
rate; and `C81-C86` must map to the broad "lymphoma" node to serve *both* Hodgkin and NHL (the
narrower alternative would drop Hodgkin's epidemiology, a worse trade). So the epidemiology
rollup stays, **labelled** as broader-than-myeloma, with the limitation recorded in the CSV
`note`. Survival, however, is now correct: SEER carries a dedicated **myeloma** site (89 →
`MONDO_0009693`), so myeloma survival resolves **exact**, not through lymphoma.
