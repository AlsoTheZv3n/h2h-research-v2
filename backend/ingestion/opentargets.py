"""Open Targets (GraphQL v4): drug type, max clinical stage, mechanisms, targets, indications."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx

from backend.ingestion.base import SourceRecord, fact, utcnow

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

_SEARCH = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["drug"]) {
    hits { id name entity }
  }
}
"""

# Verified against the live schema, 2026-07. Two fields drifted out from under the
# spike's original query:
#   maximumClinicalTrialPhase -> maximumClinicalStage  (and it is a *string* enum now,
#                                                       "APPROVAL"/"PHASE_3", not 0-4)
#   linkedTargets             -> gone; derive targets from the MoA rows instead
# GraphQL validates the whole document before executing any of it, so those two dead
# fields 400'd the request and took drugType, mechanismsOfAction and indications --
# all still valid -- down with them. The source then read as carrying nothing at all.
_DRUG = """
query Drug($id: String!) {
  drug(chemblId: $id) {
    id
    name
    drugType
    maximumClinicalStage
    mechanismsOfAction {
      rows {
        mechanismOfAction
        actionType
        targets { approvedSymbol targetClass { label level } }
      }
    }
    indications { count rows { disease { name } } }
  }
}
"""


def _pick_target_class(entries: list[dict[str, Any]] | None) -> str | None:
    """A target's family, at the level that makes a useful facet.

    Open Targets returns the ChEMBL protein-class hierarchy as a flat list tagged by
    level -- for EGFR: l1 Enzyme, l2 Kinase, l3 Protein Kinase, ... l5 the single
    protein. l1 is too coarse to slice a catalog by (everything with a mechanism is an
    "Enzyme"); l5 is one protein, which is what `primary_target` already says. l2 is
    the family a reader means -- "Kinase", "Protease", "Hydrolase" -- so prefer it,
    fall back to l1 when that is all the target carries, and to None when it carries no
    class at all. None is honest: it becomes the overview's "Unclassified", not an
    invented bucket.
    """
    by_level = {e.get("level"): e.get("label") for e in (entries or []) if e.get("label")}
    return by_level.get("l2") or by_level.get("l1")


class OpenTargetsAdapter:
    name: str = "opentargets"
    owned_keys: tuple[str, ...] = (
        "ot_id",
        "drug_type",
        "max_stage",
        "ot_moa",
        "all_moas",
        "targets",
        "target_class",
        "n_indications",
        "indications",
    )

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        r = await self.client.post(ENDPOINT, json={"query": query, "variables": variables})
        # Surface the `errors` array. On drift the server names the renamed field --
        # the single most useful thing it can tell us -- and discarding it leaves an
        # opaque 400. It also closes the real blind spot: a 200-with-errors partial
        # failure would otherwise yield null fields with no error at all.
        body: dict[str, Any] | None = None
        with contextlib.suppress(ValueError):
            # Non-JSON (a 502 HTML page) leaves body None and falls through to
            # raise_for_status, which reports the status instead of a parse error.
            body = r.json()
        if body and body.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "") for e in body["errors"]))
        r.raise_for_status()
        return (body or {}).get("data") or {}

    async def fetch(self, drug: str) -> SourceRecord:
        retrieved_at = utcnow()
        prov: dict[str, Any] = {"source_url": None, "retrieved_at": retrieved_at}
        try:
            hits = (await self._gql(_SEARCH, {"q": drug})).get("search", {}).get("hits", [])
            if not hits:
                return SourceRecord(
                    self.name, drug, ok=False, provenance=prov, error="no Open Targets drug hit"
                )
            drug_id = hits[0].get("id")
            url = f"https://platform.opentargets.org/drug/{drug_id}"
            prov["source_url"] = url
            d = (await self._gql(_DRUG, {"id": drug_id})).get("drug") or {}
        except Exception as exc:
            # outage: the source failed, so its keys are unknown -- not absent. A
            # schema drift lands here too, which is right: the fields are unknowable
            # until the query is fixed. See SourceRecord.outage.
            return SourceRecord(
                self.name, drug, ok=False, provenance=prov, error=str(exc), outage=True
            )

        def ok(value: Any) -> Any:
            return fact(value, self.name, source_url=url, retrieved_at=retrieved_at)

        moa_rows = (d.get("mechanismsOfAction") or {}).get("rows") or []
        # Keep every mechanism: the ADC has two genuinely distinct ones (an ERBB2
        # binder and a TOP1 inhibitor) and rows[0] would drop half the answer.
        moas = list(
            dict.fromkeys(
                r.get("mechanismOfAction") for r in moa_rows if r.get("mechanismOfAction")
            )
        )
        # One pass keeps each symbol's family beside it, so target_class below is the
        # class of the *same* symbol that becomes primary_target -- not a second,
        # separately-sorted answer that could disagree with it.
        class_by_symbol: dict[str, str | None] = {}
        for r in moa_rows:
            for t in r.get("targets") or []:
                sym = t.get("approvedSymbol")
                if sym and sym not in class_by_symbol:
                    class_by_symbol[sym] = _pick_target_class(t.get("targetClass"))
        targets = sorted(class_by_symbol)
        # The class of the primary target -- targets[0], exactly what _promote lifts
        # into primary_target -- so the overview's target and its class always agree.
        primary_target_class = class_by_symbol.get(targets[0]) if targets else None

        facts = {
            "ot_id": ok(drug_id),
            "drug_type": ok(d.get("drugType")),
            # Kept under its own key: this is a string enum, while ClinicalTrials.gov
            # emits an int under ct_max_phase and ChEMBL an int under max_phase.
            # Merging three different scales into one column loses the meaning.
            "max_stage": ok(d.get("maximumClinicalStage")),
            "ot_moa": ok(moas[0] if moas else None),
            "all_moas": ok(moas),
            # Derived from the MoA rows since linkedTargets is gone, so 0 here means
            # "no targets annotated on the mechanism" -- divarasib's rows carry none.
            "targets": ok(targets),
            # The primary target's protein family, for the overview's target-class
            # facet. EMPTY (None) when the target carries no class, which the overview
            # reads as "Unclassified" -- distinct from a source_failed outage.
            "target_class": ok(primary_target_class),
            "n_indications": ok((d.get("indications") or {}).get("count")),
            "indications": ok(
                [
                    row["disease"]["name"]
                    for row in ((d.get("indications") or {}).get("rows") or [])
                    if row.get("disease", {}).get("name")
                ]
            ),
        }
        return SourceRecord(self.name, drug, ok=bool(d), facts=facts, provenance=prov)
