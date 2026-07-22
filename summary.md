# H2H Research v2 — Summary der umgesetzten Changes

_Stand: 2026-07-22 · Evaluations- und Test-Leitfaden. Prosa auf Deutsch, technische Bezeichner
(Pfade, `data-testid`, Entities, Befehle) in Englisch, weil sie so im Code/UI stehen._

---

## 0. Kurzfassung

- **Alles auf `main`, gemerged, CI grün.** Sieben Roadmap-Items (N1, N2, #42, #43, #39, #40, #44)
  plus die Interpretations-Ebene (Epic A–E) sind implementiert, getestet und im Main-Branch.
- **Verifizierung:** 470 Backend-Tests, 227 Frontend-Tests, e2e durch den echten Stack, plus die
  Comprehension-Harness (LLM liest die gerenderten Seiten) für jede leser-sichtbare Änderung.
- **Die laufende compose-App ist auf dem aktuellen Stand** (neu gebaut). Öffne sie unter
  **`http://localhost:5175`**. Das Hero-GIF im README (`docs/demo.gif`) wurde ebenfalls neu
  aufgenommen und zeigt den aktuellen Funktionsumfang.

---

## 1. App starten / testen

```powershell
# im Repo-Root
docker compose up -d --build          # Frontend + API aus main; zieht auch den refresh-Worker hoch

# Migrationen + Crosswalks sind auf der compose-DB bereits angewendet/geladen.
# Falls du auf einer frischen DB startest, explizit:
#   $env:DATABASE_URL="postgresql+asyncpg://h2h:h2h@localhost:5433/h2h"
#   uv run alembic upgrade head
#   uv run python -m backend.ingestion.load_cbioportal_map
#   uv run python -m backend.ingestion.load_sponsor_map
#   uv run python -m backend.ingestion.load_mesh_disease_map
```

**Lazy enrichment:** Die meisten Krebs-/Target-Seiten reichern sich beim ersten Öffnen selbst an
(stale-while-revalidate über die Revalidate-Migrationen). Der erste Aufruf kann kurz „enriching…"
zeigen — danach kommt es aus Postgres.

**Schon fertig angereicherte Demo-Entities** (sofort sichtbar):

| Entity | URL | zeigt neu |
|---|---|---|
| Cutaneous melanoma | `/cancers/MONDO_0005012` | Mutation frequency (**measured**, z. B. BRAF ~53 %) |
| NSCLC | `/cancers/MONDO_0005233` | Top sponsors (normalisiert), Mutation frequency (**no cohort** = ehrlicher Zustand), Modalitäts-Hinweis |
| EGFR (Target) | `/targets/ENSG00000146648` | Mutation frequency by cancer, **Extracted relations** (PubTator) |
| BRAF (Target) | `/targets/ENSG00000157764` | Mutation frequency by cancer |
| Osimertinib (Drug) | `/drugs/CHEMBL3353410` | Selectivity/Potency, Key papers mit Publikationstyp, Synthese |

---

## 2. Was gebaut wurde — nach Seite, mit Test-Anleitung

### 2a. Drug-Detailseite (z. B. `/drugs/CHEMBL3353410`)

- **Potency als Selektivitätsprofil** (Epic A). Karte „Selectivity & potency": Verdikt **Selective vs
  Multi-target**, Log-Skala-Ranking, **Assay-Arten getrennt** (Target-binding vs Cell-line vs
  unassigned), Warnung bei hohem Ausschlussanteil.
- **Key papers nach Relevanz + Publikationstyp** (B4 + **#42**): Onkologie-Relevanz statt Aktualität,
  **Pub-Typ-Badge** (RCT, Review, …) und ein eigenes **„not yet indexed"** für frische Paper —
  bewusst getrennt von „geringe Relevanz" (None-vs-0).
- **Synthese „What the evidence adds up to"** (C2) oben, jede Aussage verlinkt auf ihren Block.
- **Physchem-Implikation** (B1), **Mechanismen dedupliziert** (B2).

### 2b. Cancer-Detailseite (z. B. `/cancers/MONDO_0005012`)

- **Target landscape** mit selbsterklärendem Association-Score (B5) + **TDL-Badges** (C3, inkl.
  Tchem-Mitte „chemical matter, none approved").
- **Mutation frequency** (**#43**, cBioPortal): pro Landscape-Gen, ehrliche Zustände getrennt
  (**measured** / **measured_zero** = 0 %, profiliert aber nie mutiert / **not measured** /
  **„No matched cohort"** ≠ 0 %). Scope („somatic mutation, a floor") + ODbL-Zitat dran.
- **Pipeline** + Modalitäts-Filter + **Census-Hinweis** (**#40**): reflektiert den *Katalog*, nicht
  jeden Trial (mRNA-Vaccines absent/mistyped).
- **Trial reality** + **Top sponsors normalisiert** (**#39**): Töchter zusammengeführt, gelabelt;
  **Merck KGaA ≠ Merck & Co**. Plus **Silent-Stalling** (E3).
- **Epidemiology / Survival**, **Synthese** (C1), demotierte Blöcke (C4).

### 2c. Target-Detailseite (z. B. `/targets/ENSG00000146648`)

- **Associated cancers** (S1): per ID gefiltert.
- **Mutation frequency by cancer** (**#43**, Transponierte): pro Kohorte, gerankt.
- **Extracted relations** (**#44**, PubTator): NLP-**extrahiert**, abgesetzt (gestrichelter Rahmen +
  **„Extracted, not curated"**-Banner), Zahl als **co-mentions** (Aufmerksamkeit, nicht Evidenz),
  nie mit kuratierten Karten vermischt. Krankheiten verlinken, wenn MeSH→MONDO bridged.

### 2d. Querschnitt

- **Ehrliche Zustände** durchgängig: `ok`/`empty`/`source_failed`/`not_analyzed`/`unmapped`/
  `extracted` getrennt — **None ≠ 0**.
- **Quellen-Widerspruch** als eigener Zustand (E1). **Per-Fact-Freshness** (E4, „Checked yesterday").
  **Provenienz** hinter dem „i"-Icon.

---

## 3. Verifizierung — was du gegenprüfen kannst

- **Tests:** Backend `cd backend; uv run --env-file ../.env pytest -q` (470), Frontend
  `cd frontend; npx vitest run` (227), e2e `E2E_BASE_URL=http://localhost:5175 npx playwright test`.
  Statisch: `uv run ruff check backend`, `uv run mypy backend`, `cd frontend; npm run typecheck`.
- **Prove-fail:** jeder Honest-State-Test prüft die Unterscheidung, die kaputtgehen könnte
  (measured_zero ≠ not_measured, extracted ≠ curated, Merck KGaA ≠ Merck & Co).
- **Harness-Reports** (LLM liest die Seiten, Triage in-file):
  `frontend/eval/usability/report-2026-07-21-42-literature.md`, `-43-mutation-frequency.md`,
  `-39-sponsors.md`, `-44-pubtator.md`.
- **Gate-0-Spike-Verdikte:** in den PR-Bodys + Issue-Kommentaren zu **#43** (amber — ODbL) und
  **#44** (green — NLM public domain).
- **Live gegengeprüft:** BRAF 53 % Melanom / 58,6 % papilläres Schilddrüsen-CA; KRAS 29,7 % /
  EGFR 12,4 % / TP53 52,1 % im Lungenadeno; EGFR→Gefitinib/Erlotinib/Cetuximab als Inhibitoren.

---

## 4. Bewusste Grenzen & Scope-Entscheidungen (nicht Bugs)

- **cBioPortal (#43):** ~**23 Tumortypen** (TCGA PanCancer, xref-verifiziert); Rest „not measured",
  nie 0. **Mutation-only** (Copy-Number/Fusionen bewusst ausgeschlossen + gelabelt). Lizenz ODbL mit
  Pflicht-Zitat + Whitelist.
- **PubTator (#44):** **extrahiert, nicht kuratiert** — überall markiert. Disease-Link partiell
  (~211 MeSH→MONDO); ohne Bridge = unverlinkte Erwähnung. Chemikalien als MeSH-Namen.
- **#39 Sponsoren:** ~52 fragmentierte Pharma-Strings normalisiert; akademischer Long-Tail bleibt.
- **Geparkt / won't-do:** **#79 (E2)** — beide OT-Ansätze tot; als `wontfix` geschlossen.

---

## 5. Noch offen (nicht in diesem Durchgang gemacht)

- **#77 (D4)** — 20 Minuten mit einer echten Onkolog:in; nur der Outreach-Entwurf existiert
  (`docs/outreach-d4.md`). `#85` (Epic-D-Tracker) hängt daran.
- **Code-Quality-Audit (#101–#109, Epic #109)** — angelegt, im Backlog. **Phase 1 = messen &
  berichten** (`docs/quality-audit.md`), **Phase 2 = fixen in Wert-Reihenfolge**. Noch **nicht
  gestartet**.

---

## 6. Wo im Code (für die Detail-Evaluierung)

| Feature | Backend | Frontend |
|---|---|---|
| #42 Literatur/Pub-Typen | `ingestion/literature.py`, `ingestion/enrich.py` | `components/KeyPapersList.tsx` |
| #43 Mutation frequency | `ingestion/cbioportal.py`, `ingestion/gene_ids.py`, `data/cbioportal_study_map.csv` | `components/AlterationFrequencyCard.tsx`, `TargetAlterationCard.tsx` |
| #39 Sponsoren | `ingestion/ctgov_cancer.py`, `data/sponsor_normalisation.csv` | `components/TrialRealityCard.tsx` |
| #40 Modalitäts-Hinweis | — | `components/PipelineCard.tsx` |
| #44 Extracted relations | `ingestion/pubtator.py`, `data/mesh_disease_map.csv` | `components/ExtractedRelationsCard.tsx` |
| Synthese / TDL / Disagreement | `domain/synthesis.py`, `domain/tdl.py`, `domain/disagreement.py` | `components/SynthesisPanel.tsx`, `TdlBadge.tsx` |

Alle neuen Sources folgen `fetch → store → serve` mit ehrlichen Zuständen; alle Joins per ID/Ontologie,
nie per Namens-String.
