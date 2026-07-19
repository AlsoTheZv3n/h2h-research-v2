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

**Tags:** last release **`v1.0.0`** = the drug app (commit #12). `main` is **11 commits ahead**: the
entire cancer expansion (Phase-0 spike → catalog → Gate 1 → Block C → Blocks A/B → SEER extension) is
merged but **untagged** — a `v1.1.0`/`v2.0.0` release is implicit and unblocked.

**Deploy note (not code):** run `python -m backend.refresh --once` after deploy so already-enriched
cancers pick up their epidemiology/survival facts (or they read "not collected" until the next stale
refresh). New pages get the data lazily on first open.

---

## Open PRs (awaiting merge — Claude Code cannot merge)

| PR | contains |
|---|---|
| **#29** | Backlog spike (`experiment/spike-backlog/`): five candidates measured, verdicts. `experiment/` only, no app code. |

Plus **this bookkeeping** (issues + `docs/status.md` + `docs/specs/usability-harness.md`) will land as its
own docs PR.

---

## The order to work in

1. **Merge the open PRs** — user action (Claude Code can't merge).
2. **Change-feed event table — #30 (time-sensitive).** The refresh cron overwrites the delta; capture it
   before the next full refresh or it is lost retroactively.
3. **R4 follow-ups + robustness:** OT schema smoke test **#31**, demo-fixture exclusion **#32**, README
   known-gaps refresh **#33**. *(R4 itself is done — merged as #19.)*
4. **P1-T4 trial reality — #20 → #21 → #22 → #23** (gate → backend → frontend → e2e). Already scoped as
   issues from an earlier session; the last cancer block still to build.
5. **Frontend polish:** drug detail redesign **#34** → overview refinement **#35** → regenerate the GIF
   **#36** *(blocked by #34)*.
6. **Then, and only then — spike follow-ups + backlog:** S1 target page **#37**, S3 combinations **#38**,
   S4 sponsor **#39**, S5 modality **#40**; usability harness **#41**, MeSH/pub-types **#42**, cBioPortal
   **#43**, PubTator **#44**.

*(P2-B Blocks A/B/C are complete — struck from the "to build" order.)*

---

## Issue index

**Time-sensitive**
- #30 — Change-feed event table (capture the delta before the next refresh) · `time-sensitive`

**Robustness / follow-ups**
- #31 — OT schema smoke test (fail loudly on field drift)
- #32 — Demo recording: exclude `MONDO_E2E_*` fixtures · `good first issue`
- #33 — docs: refresh README known-gaps (epi/survival shipped; add S2/S4/S5) · `docs`

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

Mirrors the README section, in more detail. Tracked for the README refresh in **#33**.

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
