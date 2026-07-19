# Backlog spike — five candidates, no new sources

Measured, not reasoned. Every verdict below is backed by a throwaway probe in this directory,
run live against Open Targets, ClinicalTrials.gov v2, and the local catalog (3,923 drugs,
1,324 cancers). Confirmed the source inventory's headline: **none of these needs a new source.**
So the question is signal quality, not access.

Order run: S5 → S1 → S4 → S3 → S2 (cheapest/most decisive first; S2's metric was itself on trial).

| candidate | verdict | one line |
|---|---|---|
| S1 — target → diseases | 🟢 **green** | reverse query works, scores + real IDs, joins to the catalog by ID |
| S2 — tissue-agnostic badge | 🔴 **red** | organ-span measures *breadth*, not agnosticism — fails the golden set both ways |
| S3 — observed combinations | 🟢 **green** | 95.9% of multi-drug trials resolve combo-vs-comparison from arm structure |
| S4 — sponsor | 🟡 **amber** | displayable, but counts are wrong without a curated normalisation layer |
| S5 — modality / mRNA vaccines | 🟡 **amber** | modality field is granular; the mRNA-vaccine *category* is not reliably in the catalog |

---

## S1 — Target page: does Open Targets go backwards? 🟢 green

`target(ensemblId){ associatedDiseases { count rows { score disease { id name } } } }` works
and is the mirror of the cancer page's `associatedTargets`.

| target | total associated | scores | IDs id-shaped | join to cancer catalog (top 50) |
|---|---|---|---|---|
| EGFR | 6,459 | ✓ all | 50/50 | **35/50** |
| KRAS | 2,404 | ✓ all | 50/50 | **27/50** |
| BRCA1 | 1,359 | ✓ all | 50/50 | **29/50** |

Returns real EFO/MONDO IDs (not labels) with scores, and the IDs join to the catalog by ID.
Sensible ranking: EGFR → NSCLC 0.85, BRCA1 → breast cancer 0.84.

**Build note (not a blocker):** OT's top associations are not all cancers — KRAS's top three are
Noonan / cardiofaciocutaneous syndromes (germline RASopathies, score 0.83, above any cancer), and
BRCA1 surfaces Fanconi anemia and an Orphanet-id syndrome. The target page must **filter to
cancer via the catalog join** rather than showing OT's raw top diseases, or it will lead with
developmental syndromes. That is exactly what the ID-join does.

## S2 — Tissue-agnostic badge: does the metric separate the right drugs? 🔴 red

Metric under test: count distinct organ systems a drug's Open Targets indications span, via the
Gate-1 MONDO-ancestor walk against 18 organ-system anchors. Golden set, ranked by the metric:

| drug | class | #indications | organs spanned |
|---|---|---|---|
| pembrolizumab | positive (agnostic) | 266 | **18** |
| **bevacizumab** | **control: broad, NOT agnostic** | 275 | **18** |
| trastuzumab deruxtecan | positive | 34 | 14 |
| **osimertinib** | **negative: lung-bound** | 23 | **12** |
| larotrectinib | positive (agnostic) | 23 | **7** |
| selpercatinib | positive (agnostic) | 17 | **5** |
| abiraterone | negative: prostate | 13 | 4 |

**Both golden criteria fail:**
1. **bevacizumab (18) is indistinguishable from pembrolizumab (18).** The metric cannot separate
   "biomarker-agnostic" from "merely broad" — exactly the failure the brief anticipated.
2. **The order inverts.** Lung-bound osimertinib (12) outranks the two genuinely tissue-agnostic
   drugs, larotrectinib (7) and selpercatinib (5). A metric that ranks a lung drug above the
   NTRK/RET tumour-agnostic drugs is worse than no metric.

Root cause: OT `indications` mixes approved and every trialled indication, and coding is
inconsistent — osimertinib has been *trialled* across many organs, while the truly agnostic
drugs' approvals ("solid tumours with an NTRK fusion") code to few entities. Restricting to
approved wouldn't save it: bevacizumab is *approved* across colorectal/lung/ovary/cervix/GBM/RCC,
so broad-and-approved still ≠ agnostic. (`maxPhaseForIndication` is also rejected by the current
schema — 400 — so per-indication phase filtering isn't even cleanly available.)

**Drop it.** A "tissue-agnostic" badge needs a biomarker-defined signal (an FDA tumour-agnostic
approval, or a "regardless of histology" indication), which indication-span does not carry.
Shipping this would label widely-trialled drugs "tissue-agnostic" — confidently wrong.

## S3 — Observed combinations: combination or comparison? 🟢 green

For 20 oncology drugs, every multi-drug trial classified from the arm structure (a single arm
holding ≥2 drugs = combination; ≥2 arms each a different single drug = comparison):

- multi-drug trials: **1,924**
- unambiguously classifiable: **1,846 (95.9%)** — combination 1,594, comparison 252
- ambiguous (multi-drug, no arm-level drug assignment): **78 (4.1%)**

Buildable — **but only if the extractor reads arm structure**, not name co-occurrence (the trap:
A and B in one trial can be A+B or A vs B). The 4.1% ambiguous must be **dropped, not guessed**.

## S4 — Sponsor: how expensive is the name problem? 🟡 amber

12,000 oncology trials → **3,489 distinct raw lead-sponsor strings.** The head (top ~60) is
mostly canonical, but the collapse the brief flagged is real, and big pharma fragments hardest:

| real entity | distinct raw strings | example variants |
|---|---|---|
| Pfizer | 5 | Pfizer · Array Biopharma · Hospira · Seagen · Wyeth (each "…a subsidiary of Pfizer") |
| Merck & Co / MSD | ~6 | Merck Sharp & Dohme LLC · MSD R&D China · ArQule/Harpoon/Oncoethix subsidiaries |
| J&J / Janssen | ~6 | Janssen R&D · Janssen Cilag · Janssen Korea · Janssen K.K. |
| Roche | 3 | Hoffmann-La Roche · Genentech, Inc. · (F. Hoffmann-La Roche AG) |
| GSK | 3 | GlaxoSmithKline · Glaxo Wellcome · Sierra Oncology |
| Novartis / Sanofi | 2 each | Novartis + Novartis Pharmaceuticals · Sanofi + Genzyme |

Ratio in the pharma head ≈ **4:1**. **Displaying** `leadSponsor.name` is fine; any **aggregate**
(trials-per-sponsor, "top sponsors") is wrong without a curated map, because a company's real
total is split across its subsidiaries. And a genuine trap: **Merck KGaA (Darmstadt, Germany) is
a different company from Merck & Co / MSD (US)** — a normaliser must *not* merge them. Cost, from
Gate 1's experience: a curated mapping over the top ~50–100 sponsors covers most of the volume;
the ~3,400-string tail is mostly already-distinct academic centres.

## S5 — Modality & mRNA vaccines: is the category in the catalog? 🟡 amber

**Probe A — drug_type is granular, does not collapse:**

| Small molecule | Antibody | Unknown | Protein | ADC | Gene | Cell | Oligonucleotide | Vaccine component |
|---|---|---|---|---|---|---|---|---|
| 2,404 | 535 | 441 | 245 | 88 | 88 | 35 | 32 | 12 |

A modality badge (ADC / antibody / small-molecule / cell / …) is buildable from this.

**Probe B — the mRNA-vaccine *category* is not reliably in the catalog:**

| vaccine | in catalog? | as |
|---|---|---|
| BNT111 | **absent** | — |
| BNT116 | **absent** | — |
| mRNA-4157 | **absent** | — |
| autogene cevumeran | present | typed **"Oligonucleotide"**, not vaccine |

The catalog is ChEMBL-derived and compound-centric; individualised mRNA cancer vaccines have no
fixed compound, so they are absent or mis-typed (autogene cevumeran → Oligonucleotide;
BNT-152/153 → "Unknown"; only TOZINAMERAN, the COVID vaccine, sits under "Vaccine component").

**Asymmetry (measured):** the catalog-absent vaccines *do* have ClinicalTrials.gov trials —
BNT111 (2), BNT116 (2), **mRNA-4157 (11)**. They therefore surface on a cancer page via
trial-reality while never existing as a catalog drug. A "modality" filter over the drug catalog
would silently miss the entire mRNA-vaccine story; it lives in trials, not the drug table.

---

## Not built here — a pending schema decision (flag)

The **change feed** ("what changed since the last refresh": phase transitions, new/terminated
trials, newly indexed papers) needs no source probe — it is data already fetched. But the refresh
cron **overwrites** facts every cycle, discarding the very delta the feed is made of. Capturing it
(an event table, or fact history) is cheap now and **retroactively impossible** — once overwritten,
the change is gone. This is a schema decision to make before the next refresh runs, not a build.

## For the README's known gaps

- **Tissue-agnostic (S2): dropped.** Indication-span measures breadth, not biomarker-agnosticism;
  it ranks a lung-bound drug above genuinely tissue-agnostic ones. No badge without a
  biomarker-defined signal OT doesn't expose.
- **Sponsor counts (S4): unnormalised.** Aggregate sponsor counts undercount big pharma (fragmented
  across subsidiaries, ~4:1 in the head); display-only until a curated map exists. Merck KGaA ≠ Merck & Co.
- **mRNA vaccines (S5): not in the drug catalog.** Individualised mRNA vaccines have no fixed
  compound; they appear via trial-reality, not as catalog drugs. A modality filter cannot see them.
