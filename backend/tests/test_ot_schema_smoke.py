"""R4-5: guard against Open Targets schema drift on the fields we actually use.

Three fields have already drifted out from under this codebase -- maximumClinicalTrialPhase
became maximumClinicalStage, linkedTargets was removed, and knownDrugs turned out never to
exist on Target. Each first showed up as a silently empty card, not an error. This posts the
REAL query constants the ingestion path sends -- across enrichment, the disease crosswalk and
the catalog build -- against the live API and fails loudly on the next drift. Open Targets
names the offending field in its errors array, so the failure points straight at what to fix.

It hits the network, so it is marked `live_ot` and deselected from the default (CI) run.
Invoke it on demand or on a schedule:  uv run pytest -m live_ot
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.ingestion import cancer_catalog, enrich_cancer, opentargets

pytestmark = pytest.mark.live_ot

# (name, query, variables, resolved_path) for every OT query the app sends -- the enrichment
# path, the disease crosswalk, and the catalog builder. Real, stable ids so each query also
# resolves data -- NSCLC, EGFR's Ensembl id, osimertinib's ChEMBL id. `resolved_path` is the
# key path down `data` to the payload that MUST come back non-empty: a field rename fails GraphQL
# validation (an errors array), but an id that stops resolving comes back as `{"data": {...:
# null}}` with NO error -- the silent EFO->MONDO root remap this repo has already been bitten by.
# Asserting the payload resolves catches that second, quieter failure, which `data is truthy`
# alone does not (a `{"disease": null}` dict is truthy).
_QUERIES: list[tuple[str, str, dict[str, Any], tuple[str, ...]]] = [
    (
        "target_landscape",
        enrich_cancer._TARGET_LANDSCAPE_QUERY,
        {"id": "MONDO_0005233", "n": 5},
        ("disease", "associatedTargets", "rows"),
    ),
    (
        "target_drug_status",
        enrich_cancer._TARGET_DRUG_STATUS_QUERY,
        {"ids": ["ENSG00000146648"]},
        ("targets",),
    ),
    (
        "pipeline",
        enrich_cancer._PIPELINE_QUERY,
        {"id": "MONDO_0005233"},
        ("disease", "drugAndClinicalCandidates", "rows"),
    ),
    # The crosswalk's ontology walk: epidemiology + survival attach a cancer by resolving its
    # MONDO ancestors against the disease map. If `ancestors` drifts (or the id stops resolving),
    # every epi/survival card silently degrades to unmapped -- so it is guarded like the rest.
    # _fetch_mapped_ancestors sends the same `disease { id ancestors }` fields (aliased per hit),
    # so this one probe covers that dynamically-built query's surface too.
    (
        "ancestors",
        enrich_cancer._ANCESTORS_QUERY,
        {"id": "MONDO_0005233"},
        ("disease", "ancestors"),
    ),
    # The catalog builder's two OT queries -- how the cancer spine itself is seeded. A field-name
    # drift errors; a root-id remap resolves to null with no error and would silently build an
    # EMPTY catalog on a fresh deploy (the EFO->MONDO migration cancer_catalog's CANCER_ROOT
    # records). The resolved_path assertion catches BOTH.
    ("catalog_descendants", cancer_catalog._DESCENDANTS_QUERY, {}, ("disease", "descendants")),
    (
        "catalog_disease_batch",
        "{ " + cancer_catalog._DISEASE_FRAGMENT.format(i=0, id="MONDO_0005233") + " }",
        {},
        ("d0", "id"),
    ),
    ("drug_search", opentargets._SEARCH, {"q": "osimertinib"}, ("search", "hits")),
    ("drug_detail", opentargets._DRUG, {"id": "CHEMBL3353410"}, ("drug", "id")),
]


def _walk(data: Any, path: tuple[str, ...]) -> Any:
    """Follow `path` down nested dicts, returning None the moment a step is missing or null --
    so a resolved-to-null id (`{"disease": null}`) yields a falsy result, not a KeyError."""
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


@pytest.mark.parametrize(
    "name,query,variables,resolved_path", _QUERIES, ids=[q[0] for q in _QUERIES]
)
async def test_live_query_has_no_schema_drift(
    name: str, query: str, variables: dict[str, Any], resolved_path: tuple[str, ...]
) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(enrich_cancer.ENDPOINT, json={"query": query, "variables": variables})
    r.raise_for_status()
    body = r.json()
    # A renamed/removed field fails GraphQL validation -> an errors array naming it. That is
    # the loud drift; treat any error as a hard failure.
    assert "errors" not in body, f"Open Targets schema drift in {name}: {body['errors']}"
    # The quiet drift: the query validated but the id no longer resolves (or the field emptied),
    # so the payload we depend on is null/absent with no error at all. Assert it came back.
    resolved = _walk(body.get("data"), resolved_path)
    assert resolved, (
        f"{name}: query validated but resolved no data at {'/'.join(resolved_path)} "
        f"-- a null/remapped id or emptied field (silent drift, no GraphQL error). "
        f"data={body.get('data')!r}"
    )
