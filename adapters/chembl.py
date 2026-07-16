"""ChEMBL: molecule structure, physchem properties, IC50 bioactivities, mechanism."""
from __future__ import annotations
import httpx
from .base import SourceRecord, utcnow

BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLAdapter:
    name = "chembl"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(self, drug: str) -> SourceRecord:
        prov = {"source_url": None, "retrieved_at": utcnow()}
        try:
            r = self.client.get(f"{BASE}/molecule/search.json", params={"q": drug})
            r.raise_for_status()
            molecules = r.json().get("molecules", [])
            if not molecules:
                return SourceRecord(self.name, drug, ok=False, provenance=prov,
                                    error="no ChEMBL molecule match")
            mol = molecules[0]
            cid = mol.get("molecule_chembl_id")
            prov["source_url"] = f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/"

            structures = mol.get("molecule_structures") or {}
            props = mol.get("molecule_properties") or {}
            smiles = structures.get("canonical_smiles")

            act = self.client.get(f"{BASE}/activity.json", params={
                "molecule_chembl_id": cid, "standard_type": "IC50", "limit": 100})
            activities = act.json().get("activities", []) if act.status_code == 200 else []

            mech = self.client.get(f"{BASE}/mechanism.json",
                                   params={"molecule_chembl_id": cid})
            mechanisms = mech.json().get("mechanisms", []) if mech.status_code == 200 else []

            fields = {
                "chembl_id": cid,
                "smiles": smiles,
                "mw": props.get("full_mwt"),
                "alogp": props.get("alogp"),
                "hbd": props.get("hbd"),
                "hba": props.get("hba"),
                "psa": props.get("psa"),
                "ro5_violations": props.get("num_ro5_violations"),
                "n_ic50": len(activities),
                "moa": mechanisms[0].get("mechanism_of_action") if mechanisms else None,
                "action_type": mechanisms[0].get("action_type") if mechanisms else None,
            }
            ok = bool(smiles) or len(activities) > 0
            return SourceRecord(self.name, drug, ok=ok, fields=fields, provenance=prov)
        except Exception as e:  # noqa: BLE001 - spike: capture everything
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
