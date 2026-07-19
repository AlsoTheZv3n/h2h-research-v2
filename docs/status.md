# Project status — H2H

The map. Replaces chat history as the source of truth. Updated 2026-07-19.

Verified against the repo, not a remembered list (`gh pr/issue list`, `git branch/tag/log`). Where the
last planning list disagreed with reality, this file follows reality — see *Reconciliation* at the end.

---

## Where it stands

Live on `main` (all merged):

- **Two entities, one spine.** Drugs (ChEMBL-derived, ~3,900) and cancers (Open Targets disease spine,
  ~1,320), a `Drugs | Cancers` nav.
- **Drug page:** structure, binding & potency (median + range over exact on-target measurements, not a
  raw count), mechanism, clinical status, chat/ask box.
- **Cancer page:** target landscape (association score, tractability, **drugged / in dev / unexploited /
  unknown** flag), pipeline (phase distribution + filterable table), **epidemiology** (Eurostat
  age-standardised mortality by country) and **survival** (SEER 5-year relative survival by stage) — each
  section loads and fails independently (Block C), attached via the Gate-1 MONDO crosswalk.
- **Honest states everywhere:** ok / empty (measured-none) / source_failed (amber) / not-collected /
  pending, plus the cancer-mapping states **unmapped** ("not available for this cancer") and **rollup**
  (names the broader entity, e.g. "lung cancer — broader than NSCLC").
- **Worker/latency:** lazy on-open enrichment + stale-while-revalidate; a refresh cron (now with a cancer
  arm) fills and refreshes both catalogs.

**Tags:** **`v2.0.0`** — "the cancer entity" — is the current release, tagged on the merged cancer
expansion (Phase-0 spike → catalog → Gate 1 → Block C → Blocks A/B → SEER extension); `v1.0.0` was the
drug-only app. Since v2.0.0, `main` also carries the change-feed (#30, PR #46) and the R4 follow-ups.

**Deploy note (not code):** run `python -m backend.refresh --once` after deploy so already-enriched
cancers pick up their epidemiology/survival facts (or they read "not collected" until the next stale
refresh). New pages get the data lazily on first open.

---

## Open PRs (awaiting merge — Claude Code cannot merge)

The R4 follow-ups (**#31** OT schema smoke coverage, **#32** demo E2E guard, **#33** README refresh)
land as one PR, which also carries this status update. Nothing else is outstanding — the spike (#29),
the bookkeeping (#45) and the change-feed (#46) are all merged.

---

## The order to work in

**Done since this map was written:** the open PRs merged (#29, #45), **v2.0.0** tagged ("the cancer
entity"), the **change-feed #30** shipped (PR #46), and the **R4 follow-ups #31 / #32 / #33** landed
together (this PR). *(R4 itself was done earlier — merged as #19.)*

Next, in order:

1. **P1-T4 trial reality — #20 → #21 → #22 → #23** (gate → backend → frontend → e2e). Already scoped as
   issues from an earlier session; the last cancer block still to build.
2. **Frontend polish:** drug detail redesign **#34** → overview refinement **#35** → regenerate the GIF
   **#36** *(blocked by #34)*.
3. **Then, and only then — spike follow-ups + backlog:** S1 target page **#37**, S3 combinations **#38**,
   S4 sponsor **#39**, S5 modality **#40**; usability harness **#41**, MeSH/pub-types **#42**, cBioPortal
   **#43**, PubTator **#44**.

*(P2-B Blocks A/B/C are complete — struck from the "to build" order.)*

---

## Issue index

**Done (this session — #30 merged; #31–33 in the open R4-follow-ups PR)**
- #30 — Change-feed event table ✓ merged (PR #46)
- #31 — OT schema smoke test ✓ extended to the crosswalk (`ancestors`) + catalog (`descendants`, disease batch)
- #32 — Demo recording `MONDO_E2E_*` guard ✓ (static Vitest guard + runtime leak-assertion)
- #33 — docs: README known-gaps refresh ✓ (epi/survival shipped; S2/S4/S5 + licence-blocked epi + myeloma)

**P1-T4 — trial reality (the remaining cancer block; existing issues)**
- #24 tracking · #20 gate (CT.gov fields, live) · #21 backend source · #22 `TrialRealityCard` · #23 e2e sweep

**Frontend polish**
- #34 — drug detail-page redesign
- #35 — overview refinement (server-side facets, sortable columns, target-class facet)
- #36 — regenerate `docs/demo.gif` · **blocked by #34**

**Spike follow-ups (verdicts measured — `experiment/spike-backlog/REPORT.md`)**
- #37 — S1 green: target detail page (OT reverse query, joined by ID)
- #38 — S3 green: observed combinations (arm structure, drop the ~4% ambiguous)
- #39 — S4 amber: sponsor dimension (curated top-50–100, labelled normalised)
- #40 — S5 amber: modality badge/filter (reliable for ADC/antibody/cell, honest about vaccines)

**Backlog (not scheduled)**
- #41 — usability & comprehension harness ([spec](specs/usability-harness.md))
- #42 — MeSH + publication types on the PubMed adapter
- #43 — cBioPortal alteration frequency *(new source → Gate-0 first)*
- #44 — PubTator extracted relations *(new source → Gate-0; needs an "extracted, not curated" status)*

---

## Known gaps (dropped / limited, with reasons)

Mirrors the README's known-gaps section, in more detail (the README refresh **#33** is done).

- **S2 tissue-agnostic badge — dropped.** An organ-span metric measures *commercial breadth*, not
  *biomarker agnosticism*. Measured on the golden set it failed both ways: bevacizumab (broad, not
  agnostic) tied pembrolizumab at 18 organs, and lung-bound osimertinib (12) outranked genuinely
  tissue-agnostic larotrectinib (7) and selpercatinib (5). No badge without a biomarker-defined signal
  Open Targets does not expose.
- **S4 sponsor counts — unnormalised.** 3,489 distinct raw strings across 12k oncology trials; big pharma
  fragments across subsidiaries (~4:1 in the head — Pfizer 5, Merck ~6, Janssen ~6, Roche 3). Display is
  fine; aggregate counts are wrong until a curated map exists. **Merck KGaA (DE) ≠ Merck & Co (US).**
- **S5 mRNA vaccines — not in the drug catalog.** Individualised mRNA cancer vaccines have no fixed
  compound; they are absent or mis-typed (BNT111/116, mRNA-4157 absent; autogene cevumeran →
  "Oligonucleotide"). They surface via trial-reality (mRNA-4157: 11 trials), never as catalog drugs — a
  modality filter over the drug table cannot see them.
- **Epidemiology is European mortality, not global incidence.** GLOBOCAN (all-rights-reserved),
  IHME-GBD / OWID (non-redistributable) and CI5 are licence-blocked; the epi block uses Eurostat
  age-standardised mortality (open, redistributable) instead — deaths, not incidence.
- **Myeloma epidemiology rolls up to lymphoma (labelled).** MONDO nests plasma cell myeloma under
  "lymphoma" and Eurostat has no separate myeloma rate (C90 is in an unmappable grab-bag); the rollup is
  named. Myeloma *survival* is exact (SEER site 89).

---

## Reconciliation — how the plan differed from reality

The last planning list treated much of the cancer work as blocked/to-do. Verified against the repo:

- **Done and merged (not open work):** R3 (#18), R4 flag (#19), Gate 1 (#25), Block C (#26), Blocks A/B
  epidemiology + survival (#27), SEER extension (#28). The "blocked by the R3 PR" / "Phase 2-B to build"
  framing is stale.
- **Only one PR is open:** #29 (the backlog spike).
- **P1-T4 (trial reality)** already had issues #20–24 from an earlier session — reused, not recreated.
- **`phase-d-chat` branch** is 0 commits ahead of `main` (fully merged) — a deletable leftover, no lost
  work.
