"""Open Targets (GraphQL): drug type, max clinical phase, mechanisms of action,
linked targets, indications. Verify field names against the current schema --
that verification is part of what this spike is for."""
from __future__ import annotations
import httpx
from .base import SourceRecord, utcnow

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

_SEARCH = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["drug"]) {
    hits { id name entity }
  }
}
"""

_DRUG = """
query Drug($id: String!) {
  drug(chemblId: $id) {
    id
    name
    drugType
    maximumClinicalTrialPhase
    mechanismsOfAction { rows { mechanismOfAction actionType targets { approvedSymbol } } }
    linkedTargets { count rows { approvedSymbol } }
    indications { count rows { disease { name } } }
  }
}
"""


class OpenTargetsAdapter:
    name = "opentargets"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def _gql(self, query: str, variables: dict) -> dict:
        r = self.client.post(ENDPOINT, json={"query": query, "variables": variables})
        r.raise_for_status()
        return r.json().get("data", {}) or {}

    def fetch(self, drug: str) -> SourceRecord:
        prov = {"source_url": None, "retrieved_at": utcnow()}
        try:
            hits = (self._gql(_SEARCH, {"q": drug})
                    .get("search", {}).get("hits", []))
            if not hits:
                return SourceRecord(self.name, drug, ok=False, provenance=prov,
                                    error="no Open Targets drug hit")
            drug_id = hits[0].get("id")
            prov["source_url"] = f"https://platform.opentargets.org/drug/{drug_id}"
            d = self._gql(_DRUG, {"id": drug_id}).get("drug") or {}
            moa_rows = (d.get("mechanismsOfAction") or {}).get("rows") or []
            fields = {
                "ot_id": drug_id,
                "drug_type": d.get("drugType"),
                "max_phase": d.get("maximumClinicalTrialPhase"),
                "moa": moa_rows[0].get("mechanismOfAction") if moa_rows else None,
                "n_targets": (d.get("linkedTargets") or {}).get("count"),
                "n_indications": (d.get("indications") or {}).get("count"),
            }
            return SourceRecord(self.name, drug, ok=bool(d), fields=fields, provenance=prov)
        except Exception as e:  # noqa: BLE001
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
