"""ChEMBL: molecule structure, physchem properties, IC50 bioactivities, mechanism."""
from __future__ import annotations
import httpx
from .base import SourceRecord, utcnow

BASE = "https://www.ebi.ac.uk/chembl/api/data"


def _pick(molecules: list[dict], drug: str) -> dict | None:
    """Resolve the molecule whose name actually IS the drug.

    molecule/search.json ranks by structural relevance, not name: for "sotorasib"
    an unnamed analog outranks SOTORASIB itself. Taking molecules[0] silently
    describes the wrong compound, so require a name/synonym hit instead.
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
            mol = _pick(molecules, drug)
            if mol is None:
                seen = [m.get("molecule_chembl_id") for m in molecules[:5]]
                return SourceRecord(
                    self.name, drug, ok=False, provenance=prov,
                    error=f"no ChEMBL molecule named {drug!r}; top hits: {seen}")
            cid = mol.get("molecule_chembl_id")
            prov["source_url"] = f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/"

            structures = mol.get("molecule_structures") or {}
            props = mol.get("molecule_properties") or {}
            smiles = structures.get("canonical_smiles")

            # The two calls below are enrichment: the molecule is already resolved, so
            # a flaky sub-endpoint must not discard it. But a failure must not read as
            # "no IC50s" either -- so degrade the field to None (not 0) and record why.
            # None means "not measured", 0 means "measured, none found".
            warnings: list[str] = []

            activities, n_ic50 = [], None
            try:
                act = self.client.get(f"{BASE}/activity.json", params={
                    "molecule_chembl_id": cid, "standard_type": "IC50", "limit": 100})
                act.raise_for_status()
                act_body = act.json()
                activities = act_body.get("activities", [])
                # len(activities) is capped by limit; the true total is in page_meta.
                n_ic50 = (act_body.get("page_meta") or {}).get("total_count")
            except Exception as e:  # noqa: BLE001
                warnings.append(f"activity: {e}")

            mechanisms = []
            try:
                mech = self.client.get(f"{BASE}/mechanism.json",
                                       params={"molecule_chembl_id": cid})
                mech.raise_for_status()
                mechanisms = mech.json().get("mechanisms", [])
            except Exception as e:  # noqa: BLE001
                warnings.append(f"mechanism: {e}")

            fields = {
                "chembl_id": cid,
                "chembl_pref_name": mol.get("pref_name"),
                "smiles": smiles,
                "mw": props.get("full_mwt"),
                "alogp": props.get("alogp"),
                "hbd": props.get("hbd"),
                "hba": props.get("hba"),
                "psa": props.get("psa"),
                "ro5_violations": props.get("num_ro5_violations"),
                "n_ic50": n_ic50,
                "n_ic50_scanned": len(activities),
                "moa": mechanisms[0].get("mechanism_of_action") if mechanisms else None,
                "action_type": mechanisms[0].get("action_type") if mechanisms else None,
            }
            ok = bool(smiles) or bool(n_ic50)
            # Partial success still carries `error`: the molecule resolved, but the
            # errors column must say which sub-fields are missing and why.
            return SourceRecord(self.name, drug, ok=ok, fields=fields, provenance=prov,
                                error="; ".join(warnings) or None)
        except Exception as e:  # noqa: BLE001 - spike: capture everything
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
