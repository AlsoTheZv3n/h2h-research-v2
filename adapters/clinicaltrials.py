"""ClinicalTrials.gov v2: trial count, phases, max phase, completion/termination flags."""
from __future__ import annotations
import httpx
from .base import SourceRecord, utcnow

BASE = "https://clinicaltrials.gov/api/v2/studies"
_PHASE_ORDER = {"EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}


class ClinicalTrialsAdapter:
    name = "clinicaltrials"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(self, drug: str) -> SourceRecord:
        prov = {"source_url": f"https://clinicaltrials.gov/search?intr={drug}",
                "retrieved_at": utcnow()}
        try:
            r = self.client.get(BASE, params={
                "query.intr": drug,
                "pageSize": 100,
                "fields": ",".join([
                    "protocolSection.identificationModule.nctId",
                    "protocolSection.statusModule.overallStatus",
                    "protocolSection.designModule.phases",
                ]),
            })
            r.raise_for_status()
            studies = r.json().get("studies", [])
            phases: list[str] = []
            statuses: list[str] = []
            for s in studies:
                ps = s.get("protocolSection", {})
                phases.extend(ps.get("designModule", {}).get("phases", []) or [])
                st = ps.get("statusModule", {}).get("overallStatus")
                if st:
                    statuses.append(st)
            max_phase = max((_PHASE_ORDER.get(p, -1) for p in phases), default=-1)
            fields = {
                "n_trials": len(studies),
                "phases": sorted(set(phases)),
                "max_phase": max_phase,
                "has_completed": any(s == "COMPLETED" for s in statuses),
                "has_terminated": any(s in ("TERMINATED", "WITHDRAWN", "SUSPENDED")
                                      for s in statuses),
            }
            return SourceRecord(self.name, drug, ok=len(studies) > 0,
                                fields=fields, provenance=prov)
        except Exception as e:  # noqa: BLE001
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
