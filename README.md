# H2H -- source probe (experiment)

A throwaway spike that answers one question before we build anything:
**do the sources actually return usable data for real oncology drugs?**

If yes, the adapters here graduate to the main app almost unchanged -- they already
return a normalized `SourceRecord`; the app just persists it instead of printing it.

## Run

```bash
uv sync
uv run python probe.py
```

Run it locally -- the external APIs (EBI/ChEMBL, ClinicalTrials.gov, Open Targets,
NCBI) are not reachable from every sandbox.

Optional: `cp .env.example .env` and add an `NCBI_API_KEY` for higher PubMed limits.

## What it probes

| Source | Adapter | Pulls |
|---|---|---|
| ChEMBL | `adapters/chembl.py` | SMILES, physchem props, IC50 activities, mechanism |
| ClinicalTrials.gov | `adapters/clinicaltrials.py` | trial count, phases, max phase, terminations |
| Open Targets | `adapters/opentargets.py` | drug type, max phase, mechanism, targets, indications |
| PubMed | `adapters/pubmed.py` | literature hit count + sample titles |

Seed drugs are in `drugs.py` (mostly KRAS G12C for a dense entity space, plus one
different target and one ADC to see where the small-molecule model breaks).

## Outputs (`out/`)

- `coverage.csv` + a printed coverage table
- `raw_<drug>.json` -- full normalized response per drug (inspect these first)
- `structure_<drug>.svg` -- proof that RDKit renders the structure
- `data_quality.html` -- ydata-profiling report (if installed)
- a console summary: how many drugs got SMILES / IC50 / trials / mechanism / literature

## What to look for

- Do small molecules get a valid SMILES that renders? (The ADC likely won't -- that
  tells us v1 = small molecules only.)
- Are IC50 values present and sane?
- Do the Open Targets field names still match? (Schema drifts -- verify here, not in the app.)
- Which cards from the mockup would actually be populated vs empty?
