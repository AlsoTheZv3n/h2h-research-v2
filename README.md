# H2H

A biochemistry-centered evidence tool for oncology drug programs.

For a given small-molecule cancer drug, H2H aggregates a sourced **evidence brief** from open
databases: molecular structure, physchem properties, on-target binding/potency, mechanism,
selectivity, target & pathway, clinical status, and literature. Every fact carries its source and
a confidence, and unsupported facts are **visibly flagged rather than hidden**.

H2H surfaces evidence. It is explicitly **not** an ML predictor and **not** an investment advisor.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app, data model, ingestion, domain logic |
| `experiment/` | The original source-probing spike. Finished — see its README. Not part of the app. |

The spike answered one question before any app code existed: *do the sources carry the product?*
The answer is **yes, for small molecules** — all four sources deliver, and the ADC case showed
biologics need their own data model. Its corrected adapters are the basis of `backend/ingestion/`.

## Sources

All open: no login, no API key required (an NCBI key is optional and only raises PubMed rate limits).

| Source | Transport | Pulls |
|---|---|---|
| ChEMBL | REST | structure, physchem, IC50 activities, mechanism |
| ClinicalTrials.gov | REST v2 | trials, phases, status |
| Open Targets | GraphQL v4 | drug type, max stage, mechanism, target, indications |
| PubMed | E-utilities | literature counts + titles (metadata only; never full text) |

Every fact is stored with `source_url` + `retrieved_at`, and sources are attributed in the UI.
This satisfies ChEMBL's **CC BY-SA** attribution (note: share-alike) and keeps PubMed to metadata.

## Hard-won lessons

These came from running the spike against the live APIs — a code review missed all of them.
They are load-bearing; see `experiment/README.md` for the evidence.

1. **`None` ≠ `0`.** `None` means "not measured / source unavailable"; `0` means "measured,
   nothing found". The data model represents "source failed" separately from "empty result".
2. **ClinicalTrials.gov 403s unknown User-Agents.** Its WAF passes UAs carrying a
   `python-httpx/<version>` token. Never retry a 403 — it's a deterministic verdict.
3. **Enrichment failures must not discard resolved data.** A failing sub-request degrades its own
   field to `None` with a reason; the core resolve stays hard.
4. **Counts come from totals, not page length.** `len(page)` saturates silently.
5. **ChEMBL resolves by structure, not name.** Match `pref_name`/synonym, or error out — never
   take the top hit.
6. **ChEMBL is the least reliable source.** It needs caching / bulk pre-load, not live calls.
7. **Verify API schemas against live.** Open Targets v4 drifted under us.

## Development

Python is `>=3.11,<3.14`. Dependencies are managed with **uv only** — never pip.

```bash
uv sync
docker compose up          # api + postgres (pgvector) + redis
```
