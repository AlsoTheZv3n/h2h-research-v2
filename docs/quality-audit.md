# Code-quality audit — Phase 1 (measure only)

_Date: 2026-07-22 · Scope: this is a **read-only audit**. Nothing was changed, deleted, or
refactored. Each item below reports a concrete number or list plus a one-line severity call. Phase 2
(fixes, in value order) is gated on a human decision — see the last section._

Tracking issues: Q1 #101 · Q2 #102 · Q3 #103 · Q4 #104 · Q5 #105 · Q6 #106 · Q7 #107 · Q8 #108
(epic #109).

## Summary

| # | Area | Headline number | Severity |
|---|------|-----------------|----------|
| Q1 | Structure (group by domain) | 31 flat components → clean ui(15)/drug(6)/cancer(6)/target(4) split; backend already layered, `ingestion/` = 28 flat files | **low** |
| Q2 | Dependency rot & deprecations | 0 security advisories (both stacks); 3 frontend **dev** majors behind; 1 deprecated `FormEvent` | **low** |
| Q3 | Styling duplication | 0 hard-coded colours, no `@apply`, tokens are the single source; shared primitives used widely; a few small repeats | **low** |
| Q4 | Dev-facing error handling | 0 bare `except:`; 1 guessed-cause message (the precedent) + 1 silent swallow | **medium** |
| Q5 | Dead code | vulture 69 = 100% pytest-fixture false positives; knip: 18 unused type exports + 3 real dead funcs (60% conf.) | **low** |
| Q6 | Test quality (mutation) | 140/165 = **84.85%** on 3 load-bearing modules; 2 load-bearing thresholds unpinned | **medium** |
| Q7 | Docker | Solid bones; embedding-model layer caches dirty; frontend pnpm has no cache mount | **medium** |
| Q8 | CI/CD gaps | Smoke test already exists (e2e job); no supply-chain scan in CI | **low** |

Overall: the codebase is in good health. The two **medium** items worth a human's attention are Q4
(a couple of dev-facing error messages that guess or swallow) and Q6/Q7 (two untested load-bearing
thresholds; two cheap Docker cache levers). Nothing is systemic.

---

## Q1 — Structure (group by domain, not type) · #101

**Number:** 31 components in a flat `frontend/src/components/` (+ 25 colocated `*.test.tsx`, kept as-is).

**Proposed grouping** — assigned objectively by which entity page consumes each component (import
scan), not by guessing from names:

- **`ui/` (15, genuinely shared):** `Card`, `Fact`, `FactGate`, `CitationChip`, `SourceFailedChip`,
  `MaturityPill`, `TdlBadge`, `AnalyzingNotice`, `SourceAdvisory`, `SectionErrorBoundary`,
  `SectionNav`, `ResolvedSection`, `Facet`, `Pagination`, `SynthesisPanel`.
- **`drug/` (6):** `PotencyCard`, `MechanismsFact`, `CombinationsCard`, `KeyPapersList`,
  `DisagreementPanel`, `Ask`.
- **`cancer/` (6):** `TargetLandscapeCard`, `AlterationFrequencyCard`, `PipelineCard`,
  `TrialRealityCard`, `EpidemiologyCard`, `SurvivalCard`.
- **`target/` (4):** `AssociatedCancersCard`, `TargetAlterationCard`, `ExtractedRelationsCard`,
  `CatalogDrugsCard`.

Genuinely shared = used by 2+ entity pages: `SynthesisPanel` (drug + cancer), `MaturityPill` (drug
detail + overview), `AnalyzingNotice`/`SourceAdvisory` (all three detail pages),
`SectionErrorBoundary`/`SectionNav` (cancer + target), `Facet`/`Pagination` (both overviews), plus
all the primitives (`Card`/`Fact`/`FactGate`/`CitationChip`/`SourceFailedChip`).

Two judgement calls to note: `DisagreementPanel` and `Ask` are currently consumed only by the drug
page, but both are cross-cutting concepts — they land in `drug/` by today's usage, not by nature.
`TdlBadge` is a target concept but is rendered inside cancer's `TargetLandscapeCard`, so it sits in
`ui/`.

**Backend:** already grouped by layer — `api` (4), `domain` (6), `ingestion` (28), `models` (14),
`repositories` (5), `services` (10), `schemas.py` (single). This is the conventional FastAPI layout
and is fine. The one hotspot is **`ingestion/` at 28 flat files**, which would read better
sub-grouped by source (chembl*, clinicaltrials*, cbioportal, pubtator, eurostat, seer,
cancer_catalog, gene_ids, the `load_*` crosswalk loaders).

**Severity: low.** Purely organizational, zero behaviour. The flat 31-component folder is the main
candidate; the domain split above is a clean 15/6/6/4.

## Q2 — Dependency rot & deprecated APIs · #102

- **Frontend majors behind: 3, all dev dependencies** — `@testing-library/jest-dom` 6.9.1→7.0.0,
  `@types/node` 24.13.3→26.1.1, `typescript` 6.0.3→7.0.2. (Runtime deps are current; react/react-dom
  are one patch behind.)
- **Frontend advisories (`pnpm audit`, 229 deps): 0** — crit 0 / high 0 / moderate 0 / low 0.
- **TypeScript deprecations: 1** — React's deprecated `FormEvent` in
  [Ask.tsx:1](../frontend/src/components/Ask.tsx#L1) and
  [Ask.tsx:30](../frontend/src/components/Ask.tsx#L30). No other deprecated APIs found
  (`.substr`, `ReactDOM.render`, `React.FC`, `defaultProps`, `UNSAFE_*` all absent).
- **Backend majors behind: 0** — all 10 outdated packages are patch/minor (fastapi 0.139.1→.2,
  pydantic-core 2.46.4→2.47.0, anthropic, huggingface-hub, ruff, certifi, etc.). Frameworks
  (sqlalchemy 2.0.51, pydantic 2.13.4, alembic 1.18.5, httpx 0.28.1) are current.
- **Backend advisories (`pip-audit`): 0** — no known vulnerabilities.

**Severity: low.** Zero security exposure on either stack; the only real "rot" is 3 frontend dev
majors and one deprecated React type in a single file.

## Q3 — Styling duplication · #103

- **`@theme` tokens are the single source of colour.** `index.css` is 37 lines; the `@theme` block
  defines the full oklch palette (`--color-surface/card/line/ink*/unavailable*/confident*/partial*/
  accent*`). **0** hard-coded hex/rgb/hsl values in any component. **No `@apply`** — Tailwind's
  "components, not @apply" answer is respected.
- **Shared primitives are used, not bypassed:** `Card` ×15, `CitationChip` ×14, `FactGate` ×11,
  `Fact` across most cards.
- **Most-repeated class strings** (consolidation candidates, not defects): `text-sm text-ink-faint`
  ×14–15, `font-medium text-ink` ×14, `text-accent hover:underline` ×12, the unavailable-state box
  `rounded-md bg-unavailable-bg px-3 py-2 text-sm text-unavailable` ×5, the meter track
  `h-2 flex-1 rounded bg-surface` ×5.
- **Card-like panels not using `Card`: 3** — `DisagreementPanel`, `ResolvedSection`, `SynthesisPanel`
  each hand-roll a `rounded…border…` wrapper. These read as intentional visual variants (accent /
  dashed / summary), not accidental bypasses.

**Severity: low.** The design system is healthy. Actionable-but-minor: a `<Link>` for the ×12
`text-accent hover:underline`, a shared unavailable-box, and a `<Bar>` for the ×5 meter track.

## Q4 — Developer-facing error handling · #104 _(highest value to fix)_

Baseline is good: **0 bare `except:`**; the 42 `except Exception` handlers mostly log source +
operation + `{exc}` or fold the failure into an honest `failed(...)` fact (e.g.
[chembl.py:178](../backend/ingestion/chembl.py#L178) `failed(self.name, f"mechanism: {exc}")`); of 54
`raise` sites, 25 carry the offending value in an f-string and the 8 static-string raises are precise
domain invariants (`"an ok fact must carry a value; use EMPTY or SOURCE_FAILED"`); every API 404
names the id and what's missing (`f"{chembl_id} has no structure"`).

**Real findings (the worst offenders):**

1. **Guessed cause — the precedent.** [conftest.py:143](../backend/tests/conftest.py#L143):
   `except Exception` around `prepare()` reports the headline **`"postgres unreachable at {dsn}"`**
   and prescribes **`docker compose up -d postgres`** for *any* failure — including the documented
   precedent (a `chembl_id` one char past `varchar(20)`, a `DataError` at `create_all`, with the
   stack fully up). It does append `{exc}`, so the real cause is recoverable, and it carries a
   `# pragma: no cover`; but the headline guesses a cause and prescribes a wrong next action.
2. **Silent swallow.** [chembl.py:254](../backend/ingestion/chembl.py#L254): `except Exception:
   return` when fetching target symbols — on any failure it returns with **no log** (source, the
   queried ids, and `{exc}` all dropped). The one genuinely silent swallow in ingestion.
3. **Breadth (opportunity, not a bug):** some `except Exception` handlers could name the operation
   and entity id in their log line rather than the source alone.

**Not offenders:** [gene_ids.py:63](../backend/ingestion/gene_ids.py#L63) `except (TypeError,
ValueError): continue` is correct defensive per-record `int()` parsing; the 8 static raises are
precise invariants.

**Severity: medium.** This is the highest-value area to fix per the plan, but the reality is narrow:
the honesty discipline is already applied at most boundaries — the gaps are the conftest guessed
cause and one silent swallow, both small and specific.

## Q5 — Dead code · #105

- **vulture: 69 findings (min-confidence 70; identical at 90) — 100% false positives.** All 69 are
  pytest fixture parameters injected by name for a DB-seeding side effect and never referenced in the
  body (`seeded` ×28, `catalogued` ×35, `indexed_drug` ×4, `no_background_enrich` ×2) — vulture's
  known blind spot. **Zero real dead Python** at the audited threshold. Only at min-confidence 60 do
  3 plausibly-real dead functions surface (grep-confirmed no callers):
  [literature.py:193 `forget_drug`](../backend/repositories/literature.py#L193),
  [structure.py:16 `is_valid_smiles`](../backend/domain/structure.py#L16),
  [embeddings.py:43 `verify_dimension`](../backend/embeddings.py#L43).
- **knip:** 4 unused files (all false positives — standalone `tsx` tooling: `eval/usability/*`,
  `e2e/demo.convert.ts`, outside the vite/vitest graph), 1 unused export (`BriefStateContext` in
  `Fact.tsx` — used internally, just a redundant `export` keyword), **18 unused exported types** in
  `api/types.ts` (genuine but type-only, zero runtime cost, an intentional mirror of the backend API
  shape), 0 unused deps, 0 unlisted deps.

**Severity: low.** Nothing meaningful to delete. The original "cheap, high-signal" premise did not
hold — the tools' signal here is almost entirely false positives.

## Q6 — Test quality / mutation testing · #106

**Tool:** StrykerJS 9.6.1 (vitest-runner, threads pool). **Scope:** 3 load-bearing frontend logic
modules chosen for their threshold/branch logic and richest colocated tests —
`frontend/src/{association,physchem,format}.ts`. (Candidates also considered: phases, mechanisms,
targets, titles; and backend `domain/{disagreement,potency,selectivity,synthesis,tdl}.py`. Backend
mutmut was not run — the frontend path produced a real number, so the run budget went there. This is
a **scoped** result: 3 of ~12 candidate modules.)

- **Mutation score: 140/165 = 84.85%** (association 86.49%, format 83.56%, physchem 85.45%).
- **0 "no coverage" mutants** → ~100% statement coverage but ~85% mutation score: the classic
  high-line-coverage / weaker-assertion gap.
- **25 surviving mutants**, the load-bearing ones:
  - **`physchem.ts:64` Ro5 boundary `v > r.limit` → `v >= r.limit` SURVIVES** — the "value at the
    limit is not a violation" test uses `ro5_violations: 0` and returns at the count-zero branch, so
    the boundary itself is never exercised. A flip would misclassify a value exactly at a Lipinski
    limit. The **H-bond donor and acceptor Ro5 rows are entirely unexercised** (only LogP and MW
    violations are tested).
  - **`format.ts` bucket edges** — the four `formatAge` freshness buckets (`abs < 1/7/30/365` → `<=`)
    and the count-label/potency cutoffs survive; plus low-risk Intl-config cosmetics.
  - **`association.ts`** — 5 `EVIDENCE_LABEL` display strings that no test asserts
    (`known_drug`, `affected_pathway`, `literature`, `rna_expression`, `animal_model`) could change
    silently.

**Severity: medium.** Most logic is killed, but two genuinely load-bearing thresholds are not pinned
(physchem Ro5 `>`→`>=`, format freshness/potency edges) and the hbd/hba Ro5 rules are effectively
untested. The remaining survivors are low-risk display-string/Intl mutations.

## Q7 — Docker · #107

**Verify (all hold):** multi-stage **yes** (backend `python:3.12-slim` builder→runtime; frontend
`node:22-alpine` builder→`nginx-unprivileged`); non-root **yes** (backend `USER appuser` uid 1000;
frontend nginx-unprivileged uid 101 via base image); dependency layer before app code **yes** (both).

**Levers:**
- **Embedding-model layer does NOT cache cleanly.** The model bake (`Dockerfile:76`,
  `RUN python -c "...verify_dimension()"`) sits **after** the runtime `COPY backend/` (`Dockerfile:51`)
  — structurally forced there because it imports `backend.embeddings` and must run post-`USER`. So
  **any backend Python edit busts `COPY backend/` and re-downloads the ~130 MB bge-small model** (and
  hard-fails an offline build). This is the painful inner-loop cost.
- **BuildKit cache mounts: uv yes, pnpm no.** Backend `uv sync` uses
  `--mount=type=cache,target=/root/.cache/uv`; the frontend `pnpm install` has **no** cache mount.
- **Image sizes:** backend 658 MB, frontend 54.4 MB.
- **Build times:** backend cold 55.1s / warm 2.8s; frontend cold 22.6s / warm 2.5s. Backend cold ≈
  deps (25s) > apt RDKit libs (15s) > model download (8.6s).

**Severity: medium.** Bones are solid; two cheap, targeted cache wins are on the table — move the
model bake so it does not sit behind the app-code COPY, and add the pnpm cache mount. (Non-goal:
splitting Dockerfiles "for build speed" — not the lever.)

## Q8 — CI/CD gaps · #108

- **Lint/format/type/migrations enforced:** `ruff check`, `ruff format --check`, `mypy backend`,
  `alembic upgrade head` + `alembic check`, backend pytest, frontend typecheck/vitest/build. ✓
- **A smoke test already exists.** The **e2e job** is exactly the smoke test the issue asks for:
  `docker compose up -d --build` → poll `curl -fsS /health` (60×2s) → `seed_demo` → Playwright over
  the real **DB → API → browser** path. ✓
- **Gap — no supply-chain scanning in CI:** no `pip-audit`, no `pnpm audit`, no container scan
  (trivy). Both stacks are 0-advisory today (Q2), but nothing enforces that on future PRs.
- **Auto-rollback: not applicable** — presupposes a deployed environment + monitoring; this project
  runs locally via compose. Do not build process for a thing that does not exist. Revisit if a
  deployment target is added.

**Severity: low.** The smoke test is present; the only real gap is supply-chain scanning, which is a
cheap add but low-urgency given the currently clean state.

---

## Phase 2 — suggested fix order, adjusted to what the audit found

Original plan order was Q4 → Q5 → Q2 → Q1 → Q3 → Q6 → Q7/Q8. The audit contradicts two assumptions,
so the evidence-adjusted order is:

1. **Q4** — fix [conftest.py:143](../backend/tests/conftest.py#L143) (name the real cause, don't
   guess "unreachable") and [chembl.py:254](../backend/ingestion/chembl.py#L254) (log before
   returning). Small; honesty discipline applied inward.
2. **Q6** — add tests that pin the surviving load-bearing thresholds only: physchem Ro5 `>`/`>=`
   boundary, the hbd/hba Ro5 rows, and the `format` freshness/potency bucket edges. Do **not** chase
   a coverage number.
3. **Q7** — the two cache levers: reorder the embedding-model bake ahead of the app-code COPY, add
   the pnpm `--mount=type=cache`. Real daily-dev-loop pain.
4. **Q2** — replace the deprecated `FormEvent` in `Ask.tsx`, then bump the 3 frontend dev majors one
   at a time.
5. **Q8** — add a supply-chain job (`pip-audit` + `pnpm audit`, optionally trivy). Cheap, but
   0-advisory today, so low urgency.
6. **Q1** — move components into `ui/drug/cancer/target/` as its **own commit, zero behaviour
   change**, tests green before & after; optionally sub-group `ingestion/` by source.
7. **Q3** — replace the handful of repeated class strings with small shared components
   (`Link`, unavailable-box, `Bar`) where they were bypassed.
8. **Q5** — essentially nothing. Optionally, after individual review, drop the 3 dead functions and
   the redundant `export`; leave the 18 type mirrors and every vulture false positive alone.

**Demoted vs the original:** Q5 (the tools found almost only false positives — not the cheap win it
was assumed to be). **Promoted:** Q6 (surfaced two real load-bearing correctness gaps).

_Phase 2 is not started. Each fix should trace to a finding above, ship as a small verified commit,
and re-run the comprehension harness after any reader-visible change._
