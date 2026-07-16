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

# Schema drift, verified live 2026-07: `maximumClinicalTrialPhase` is now
# `maximumClinicalStage` (and returns a string enum like "APPROVAL", not a 0-4 int),
# and `linkedTargets` is gone -- targets are derived from the MoA rows instead.
_DRUG = """
query Drug($id: String!) {
  drug(chemblId: $id) {
    id
    name
    drugType
    maximumClinicalStage
    mechanismsOfAction { rows { mechanismOfAction actionType targets { approvedSymbol } } }
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
        # Surface the GraphQL `errors` array: on schema drift the server names the
        # renamed field, and that message is the single most useful thing this spike
        # can report. Discarding it leaves an opaque 400 -- or, on a 200-with-errors
        # partial failure, null fields with no error at all.
        body = None
        try:
            body = r.json()
        except ValueError:
            pass  # non-JSON (e.g. a 502 HTML page): fall through to raise_for_status
        if body and body.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "") for e in body["errors"]))
        r.raise_for_status()
        return (body or {}).get("data") or {}

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
            # Keep every mechanism: the ADC has two genuinely distinct ones
            # (ERBB2 binder + TOP1 inhibitor) and rows[0] would drop half the answer.
            moas = list(dict.fromkeys(
                r.get("mechanismOfAction") for r in moa_rows if r.get("mechanismOfAction")))
            targets = sorted({t.get("approvedSymbol")
                              for r in moa_rows for t in (r.get("targets") or [])
                              if t.get("approvedSymbol")})
            fields = {
                "ot_id": drug_id,
                "drug_type": d.get("drugType"),
                # Renamed from max_phase: this is a string enum ("APPROVAL", "PHASE_3"),
                # not the 0-4 int that clinicaltrials.py emits under `max_phase`.
                "max_stage": d.get("maximumClinicalStage"),
                "moa": moas[0] if moas else None,
                "all_moas": moas,
                # Derived from MoA rows, so 0 can mean "no targets annotated on the
                # mechanism" rather than "no targets" -- not the old linkedTargets count.
                "n_targets": len(targets),
                "targets": targets,
                "n_indications": (d.get("indications") or {}).get("count"),
            }
            return SourceRecord(self.name, drug, ok=bool(d), fields=fields, provenance=prov)
        except Exception as e:  # noqa: BLE001
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
