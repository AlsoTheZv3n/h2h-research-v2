# H2H -- source probe (experiment)

A throwaway spike that answers one question before we build anything:
**do the sources actually return usable data for real oncology drugs?**

If yes, the adapters here graduate to the main app almost unchanged -- they already
return a normalized `SourceRecord`; the app just persists it instead of printing it.

## Run

```bash
uv sync
uv run python probe.py    # ~15-20 min; ChEMBL /activity is the slow leg
```

Run it locally -- the external APIs (EBI/ChEMBL, ClinicalTrials.gov, Open Targets,
NCBI) are not reachable from every sandbox.

Python is pinned to `>=3.11,<3.14` (`.python-version`: 3.12). The upper bound is
load-bearing: without it uv picks 3.14, where the scientific wheels don't exist yet.

Optional: `cp .env.example .env` and add an `NCBI_API_KEY` for higher PubMed limits.

## What it probes

| Source | Adapter | Pulls |
|---|---|---|
| ChEMBL | `adapters/chembl.py` | SMILES, physchem props, IC50 activities, mechanism |
| ClinicalTrials.gov | `adapters/clinicaltrials.py` | trial count, phases, max phase, terminations |
| Open Targets | `adapters/opentargets.py` | drug type, max stage, mechanisms, targets, indications |
| PubMed | `adapters/pubmed.py` | literature hit count + sample titles |

Seed drugs are in `drugs.py` (mostly KRAS G12C for a dense entity space, plus one
different target and one ADC to see where the small-molecule model breaks).

## Outputs (`out/`)

- `coverage.csv` + a printed coverage table
- `raw_<drug>.json` -- full normalized response per drug (inspect these first)
- `structure_<drug>.svg` -- one SVG, proof that RDKit renders the structure
- a console summary: how many drugs got SMILES / IC50 / trials / mechanism / literature

## Reading the output

**Read the `errors` column before any number.** A source outage and a genuine coverage
gap look identical in a count, so the summary block flags when the `N/5` figures are a
floor rather than a finding. `None` in a count means "not measured", `0` means
"measured, none found" -- they are not collapsed.

Then check `chembl_id` / `chembl_pref_name`: ChEMBL's molecule search ranks by structure,
not name, so a wrong-molecule match is otherwise invisible (see below).

## What to look for

- Do small molecules get a valid SMILES that renders? (The ADC won't -- that
  tells us v1 = small molecules only.)
- Are IC50 values present and sane? (Currently only *present* is answered -- the
  adapter counts activities without checking units, censored `>`/`<` bounds, or target.)
- Do the Open Targets field names still match? (Schema drifts -- verify here, not in the app.)
- Which cards from the mockup would actually be populated vs empty?

## Findings so far

- **Open Targets drifted.** `maximumClinicalTrialPhase` is now `maximumClinicalStage` and
  returns a string enum (`"APPROVAL"`), not the 0-4 int that `clinicaltrials.py` still emits
  as `max_phase`. `linkedTargets` is gone; targets are derived from the MoA rows. The old
  query 400s, and because GraphQL validates the whole document up front, that zeroed the
  *entire* source -- which read as "Open Targets carries nothing".
- **ChEMBL name resolution is not optional.** `molecule/search.json` ranks by structural
  relevance: for `sotorasib` an unnamed analog outranks SOTORASIB itself. Taking the top hit
  silently describes the wrong compound with a valid SMILES and no error.
- **ChEMBL is the least reliable source** -- broad 500s (including `status.json`) and
  30-60s latencies on `/activity`, seen repeatedly. The main app needs caching, not just retries.
- **ClinicalTrials.gov 403s unknown User-Agents.** Its WAF allowlists known client tokens;
  a bare `h2h-experiment/0.1` and even `Mozilla/5.0` are rejected. See `USER_AGENT` in `probe.py`.
- Counts come from `totalCount` / `page_meta.total_count`, not `len(page)` -- the latter
  silently capped osimertinib at 100 trials (true: 383) and 100 IC50s (true: 701).
