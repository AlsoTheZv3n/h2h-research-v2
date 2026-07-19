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
drug-only app. Since v2.0.0, `main` carries the change-feed (#30, PR #46), the R4 follow-ups (#31–33,
PR #47), P1-T4 trial reality in full (#21 PR #48, #22/#23 PR #49) and the drug-page bug-fixes (#34,
PR #50). The overview per-facet counts (finishing #35) are in the open PR that carries this update.

**Deploy note (not code):** run `python -m backend.refresh --once` after deploy so already-enriched
cancers pick up their epidemiology/survival facts (or they read "not collected" until the next stale
refresh). New pages get the data lazily on first open.

---

## Open PRs (awaiting merge — Claude Code cannot merge)

The **overview per-facet counts** (finishing #35 — the rest of the overview refinement, server-side
facets + sortable columns + target-class facet, already shipped) land as one PR, which also carries
this status update. Nothing else is outstanding — the spike (#29), bookkeeping (#45), change-feed
(#46), R4 follow-ups (#47), P1-T4 (#48, #49) and the drug-page bug-fixes (#50) are merged.

---

## The order to work in

**Done since this map was written:** #29 & #45 merged, **v2.0.0** tagged, the **change-feed #30** (PR
#46), the **R4 follow-ups #31/#32/#33** (PR #47), and **P1-T4 trial reality** in full — gate #20
(GREEN), backend #21 (PR #48), UI #22 + e2e #23 (PR #49), #24 closed. *(R4 itself was done earlier as
#19; P2-B Blocks A/B/C are complete.)* The cancer detail page's evidence blocks are done. **#34** (drug
redesign, shipped as b3f833a) was closed by a bug-fix PR (#50). Like #31/#32/#34, **#35's overview
refinement was already shipped** (server-side facets, sortable columns, target-class facet); the open
PR adds the one missing piece — per-facet option counts — and closes it.

Next, in order:

1. **Regenerate the GIF — #36** (unblocked — the drug redesign it targets has shipped). The last
   frontend-polish item.
2. **Then, and only then — spike follow-ups + backlog:** S1 target page **#37**, S3 combinations **#38**,
   S4 sponsor **#39**, S5 modality **#40**; usability harness **#41**, MeSH/pub-types **#42**, cBioPortal
   **#43**, PubTator **#44**.

---

## Issue index

**Done (recently)**
- #30 — Change-feed event table ✓ (PR #46)
- #31/#32/#33 — R4 follow-ups ✓ (PR #47)
- #20–24 — P1-T4 trial reality ✓ end-to-end (gate, backend #48, UI + e2e #49)
- #34 — drug detail redesign ✓ (b3f833a); remaining bugs fixed in PR #50
- #35 — overview refinement ✓ (server-side facets, sortable columns, target-class facet already
  shipped; per-facet option counts added in the open PR)

**Frontend polish (remaining)**
- #36 — regenerate `docs/demo.gif` · unblocked (the #34 redesign has shipped)

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

*Snapshot from when this map was first written (at #45). Later merges are tracked in "The order to work
in" above, not here — so the "open"/"done" states below read as of that point, not today.*

The last planning list treated much of the cancer work as blocked/to-do. Verified against the repo at
the time:

- **Done and merged (not open work):** R3 (#18), R4 flag (#19), Gate 1 (#25), Block C (#26), Blocks A/B
  epidemiology + survival (#27), SEER extension (#28). The "blocked by the R3 PR" / "Phase 2-B to build"
  framing is stale.
- **One PR was open then:** #29 (the backlog spike) — since merged.
- **P1-T4 (trial reality)** already had issues #20–24 from an earlier session — reused, not recreated.
- **`phase-d-chat` branch** is 0 commits ahead of `main` (fully merged) — a deletable leftover, no lost
  work.
