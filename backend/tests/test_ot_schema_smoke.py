"""R4-5: guard against Open Targets schema drift on the fields we actually use.

Three fields have already drifted out from under this codebase -- maximumClinicalTrialPhase
became maximumClinicalStage, linkedTargets was removed, and knownDrugs turned out never to
exist on Target. Each first showed up as a silently empty card, not an error. This posts the
REAL query constants (the ones the adapters send) against the live API and fails loudly on
the next drift -- Open Targets names the offending field in its errors array, so the failure
points straight at what to fix.

It hits the network, so it is marked `live_ot` and deselected from the default (CI) run.
Invoke it on demand or on a schedule:  uv run pytest -m live_ot
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.ingestion import enrich_cancer, opentargets

pytestmark = pytest.mark.live_ot

# (name, query, variables) for every OT query the app sends. Real, stable ids so the query
# also resolves data -- NSCLC, EGFR's Ensembl id, osimertinib's ChEMBL id.
_QUERIES: list[tuple[str, str, dict[str, Any]]] = [
    ("target_landscape", enrich_cancer._TARGET_LANDSCAPE_QUERY, {"id": "MONDO_0005233", "n": 5}),
    ("target_drug_status", enrich_cancer._TARGET_DRUG_STATUS_QUERY, {"ids": ["ENSG00000146648"]}),
    ("pipeline", enrich_cancer._PIPELINE_QUERY, {"id": "MONDO_0005233"}),
    ("drug_search", opentargets._SEARCH, {"q": "osimertinib"}),
    ("drug_detail", opentargets._DRUG, {"id": "CHEMBL3353410"}),
]


@pytest.mark.parametrize("name,query,variables", _QUERIES, ids=[q[0] for q in _QUERIES])
async def test_live_query_has_no_schema_drift(
    name: str, query: str, variables: dict[str, Any]
) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(enrich_cancer.ENDPOINT, json={"query": query, "variables": variables})
    r.raise_for_status()
    body = r.json()
    # A renamed/removed field fails GraphQL validation -> an errors array naming it. That is
    # exactly the drift we want surfaced, so treat any error as a hard failure.
    assert "errors" not in body, f"Open Targets schema drift in {name}: {body['errors']}"
    assert body.get("data"), f"{name}: query returned no data payload"
