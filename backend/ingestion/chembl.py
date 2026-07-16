"""ChEMBL: molecule structure, physchem properties, IC50 activities, mechanism."""

from __future__ import annotations

from typing import Any

import httpx

from backend.domain.potency import summarize_ic50
from backend.ingestion.base import SourceRecord, fact, failed, utcnow

BASE = "https://www.ebi.ac.uk/chembl/api/data"

# The facts each enrichment call is responsible for. Declared once so the success
# and failure paths cannot drift apart: a key written on success but forgotten in
# the `except` produces no row at all, which means the API can never list it in
# `unavailable[]` -- the outage goes invisible. Worse, a re-ingest during an outage
# would leave a stale status=ok row in place while its siblings' retrieved_at moved
# on, turning a missing fact into an actively wrong one.
_MECHANISM_KEYS = ("moa", "all_moas", "action_type", "target_chembl_id", "target_chembl_ids")
_ACTIVITY_KEYS = ("n_ic50", "n_ic50_scanned", "ic50_summary")


def pick_molecule(molecules: list[dict[str, Any]], drug: str) -> dict[str, Any] | None:
    """Resolve the molecule whose name actually IS the drug.

    molecule/search.json ranks by structural relevance, not by name. Measured on the
    live API: for "sotorasib" an unnamed analogue scores 33 and the real SOTORASIB
    (CHEMBL4535757) scores 21 -- so molecules[0] is the wrong compound, returned with
    a valid SMILES and no error. It reads as a thin source, not as a misresolution,
    which is why nothing downstream can catch it.

    Requiring a name or synonym hit turns that silent corruption into an explicit
    "unresolved", which is a useful answer. The wrong molecule never is.
    """
    q = drug.strip().lower()
    for mol in molecules:
        if (mol.get("pref_name") or "").lower() == q:
            return mol
        for syn in mol.get("molecule_synonyms") or []:
            if (syn.get("molecule_synonym") or "").lower() == q:
                return mol
    return None


class ChEMBLAdapter:
    name = "chembl"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch(self, drug: str) -> SourceRecord:
        retrieved_at = utcnow()
        prov: dict[str, Any] = {"source_url": None, "retrieved_at": retrieved_at}
        try:
            r = await self.client.get(f"{BASE}/molecule/search.json", params={"q": drug})
            r.raise_for_status()
            molecules = r.json().get("molecules", [])
        except Exception as exc:
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(exc))

        if not molecules:
            return SourceRecord(
                self.name, drug, ok=False, provenance=prov, error="no ChEMBL molecule match"
            )

        mol = pick_molecule(molecules, drug)
        if mol is None:
            seen = [m.get("molecule_chembl_id") for m in molecules[:5]]
            return SourceRecord(
                self.name,
                drug,
                ok=False,
                provenance=prov,
                error=f"no ChEMBL molecule named {drug!r}; top hits: {seen}",
            )

        cid = mol.get("molecule_chembl_id")
        if not cid:
            # No ID means no entity to hang facts on -- and nothing the catalog could
            # key. Hard failure, like an unresolved name.
            return SourceRecord(
                self.name,
                drug,
                ok=False,
                provenance=prov,
                error=f"ChEMBL matched {drug!r} but returned no molecule_chembl_id",
            )

        url = f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/"
        prov["source_url"] = url
        return await self._build(drug, mol, str(cid), url, retrieved_at)

    async def _build(
        self,
        drug: str,
        mol: dict[str, Any],
        cid: str,
        url: str,
        retrieved_at: Any,
    ) -> SourceRecord:
        def ok(value: Any) -> Any:
            return fact(value, self.name, source_url=url, retrieved_at=retrieved_at)

        structures = mol.get("molecule_structures") or {}
        props = mol.get("molecule_properties") or {}

        facts = {
            "chembl_id": ok(cid),
            "pref_name": ok(mol.get("pref_name")),
            "smiles": ok(structures.get("canonical_smiles")),
            "mw": ok(_as_float(props.get("full_mwt"))),
            "alogp": ok(_as_float(props.get("alogp"))),
            "hbd": ok(_as_int(props.get("hbd"))),
            "hba": ok(_as_int(props.get("hba"))),
            "psa": ok(_as_float(props.get("psa"))),
            "ro5_violations": ok(_as_int(props.get("num_ro5_violations"))),
            "max_phase": ok(_as_int(mol.get("max_phase"))),
        }

        # Everything below is enrichment: the molecule is already resolved, so a flaky
        # sub-endpoint must not discard it. The spike threw away a SMILES and 57 IC50s
        # because mechanism.json 500'd at the end -- under-reporting coverage, which is
        # the same lie as over-reporting it. Each degrades to its own source_failed fact.
        #
        # Mechanism first: its target_chembl_id is what makes the activities readable.
        # Without it there is no way to tell a KRAS measurement from a SARS-CoV-2 screen.
        target_ids: list[str] = []
        try:
            mech = await self.client.get(
                f"{BASE}/mechanism.json", params={"molecule_chembl_id": cid}
            )
            mech.raise_for_status()
            mechanisms = mech.json().get("mechanisms", [])
            # Every mechanism, not [0]. List order is not authority -- the same rule
            # pick_molecule enforces one endpoint earlier. Dasatinib has ABL1, SRC,
            # KIT and PDGFRA; taking the first would file the other three as
            # "off-target" and quote potency against whichever row came back first.
            target_ids = list(
                dict.fromkeys(
                    m["target_chembl_id"] for m in mechanisms if m.get("target_chembl_id")
                )
            )
            moas = list(
                dict.fromkeys(
                    m["mechanism_of_action"] for m in mechanisms if m.get("mechanism_of_action")
                )
            )
            action_types = list(
                dict.fromkeys(m["action_type"] for m in mechanisms if m.get("action_type"))
            )
            facts["moa"] = ok(moas[0] if moas else None)
            facts["all_moas"] = ok(moas)
            facts["action_type"] = ok(action_types[0] if action_types else None)
            facts["target_chembl_id"] = ok(target_ids[0] if target_ids else None)
            facts["target_chembl_ids"] = ok(target_ids)
        except Exception as exc:
            for key in _MECHANISM_KEYS:
                facts[key] = failed(self.name, f"mechanism: {exc}", source_url=url)

        try:
            act = await self.client.get(
                f"{BASE}/activity.json",
                params={"molecule_chembl_id": cid, "standard_type": "IC50", "limit": 100},
            )
            act.raise_for_status()
            body = act.json()
            activities = body.get("activities", [])
            # From page_meta, not len(): the page saturates at `limit` (osimertinib
            # returns 100 of a true 701) and reads as a real measurement.
            facts["n_ic50"] = ok((body.get("page_meta") or {}).get("total_count"))
            facts["n_ic50_scanned"] = ok(len(activities))
            # The count is a row count, not a potency. Measured on adagrasib: 23 of
            # its 30 IC50s are off-target (cell lines, a CDK7 assay, two SARS-CoV-2
            # screens), so this is where the number becomes an answer.
            facts["ic50_summary"] = ok(summarize_ic50(activities, target_ids).as_dict())
        except Exception as exc:
            for key in _ACTIVITY_KEYS:
                facts[key] = failed(self.name, f"activity: {exc}", source_url=url)

        # ok means "the molecule resolved", not "it has a structure". The spike's
        # `bool(smiles) or n_ic50` was fine for a small-molecule probe but wrong here:
        # ChEMBL resolves trastuzumab deruxtecan (CHEMBL4297844) with a name, phase 4
        # and a mechanism, and simply has no SMILES for it -- because it is a biologic.
        # That absence is a finding, not a failure, and it belongs in `maturity`.
        # Calling it not-ok would drop the ADC from the catalog the product wants it in.
        return SourceRecord(
            self.name,
            drug,
            ok=True,
            facts=facts,
            provenance={"source_url": url, "retrieved_at": retrieved_at},
        )


def _as_float(value: Any) -> float | None:
    """ChEMBL serializes decimals as strings ("560.61"). Coerce at the boundary."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
