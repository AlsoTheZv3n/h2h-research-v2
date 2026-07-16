"""ChEMBL: molecule structure, physchem properties, IC50 activities, mechanism."""

from __future__ import annotations

from typing import Any

import httpx

from backend.ingestion.base import SourceRecord, fact, failed, utcnow

BASE = "https://www.ebi.ac.uk/chembl/api/data"


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
        try:
            act = await self.client.get(
                f"{BASE}/activity.json",
                params={"molecule_chembl_id": cid, "standard_type": "IC50", "limit": 100},
            )
            act.raise_for_status()
            body = act.json()
            # From page_meta, not len(): the page saturates at `limit` (osimertinib
            # returns 100 of a true 701) and reads as a real measurement.
            facts["n_ic50"] = ok((body.get("page_meta") or {}).get("total_count"))
            facts["n_ic50_scanned"] = ok(len(body.get("activities", [])))
        except Exception as exc:
            facts["n_ic50"] = failed(self.name, f"activity: {exc}", source_url=url)

        try:
            mech = await self.client.get(
                f"{BASE}/mechanism.json", params={"molecule_chembl_id": cid}
            )
            mech.raise_for_status()
            mechanisms = mech.json().get("mechanisms", [])
            facts["moa"] = ok(mechanisms[0].get("mechanism_of_action") if mechanisms else None)
            facts["action_type"] = ok(mechanisms[0].get("action_type") if mechanisms else None)
            facts["target_chembl_id"] = ok(
                mechanisms[0].get("target_chembl_id") if mechanisms else None
            )
        except Exception as exc:
            facts["moa"] = failed(self.name, f"mechanism: {exc}", source_url=url)

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
