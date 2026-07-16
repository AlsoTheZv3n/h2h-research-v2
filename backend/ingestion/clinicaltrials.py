"""ClinicalTrials.gov v2: trial count, phases, max phase, completion/termination."""

from __future__ import annotations

from typing import Any

import httpx

from backend.ingestion.base import SourceRecord, fact, utcnow

BASE = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_ORDER = {"EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}

# One page is enough. Measured: paginating both capping drugs to exhaustion leaves
# max_phase / has_completed / has_terminated byte-identical, because they are
# saturating reducers (max/any) -- a drug with any PHASE4 trial among 219 has many.
# countTotal gives the true count without the round-trips.
_PAGE_SIZE = 1000


class ClinicalTrialsAdapter:
    name = "clinicaltrials"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch(self, drug: str) -> SourceRecord:
        retrieved_at = utcnow()
        url = f"https://clinicaltrials.gov/search?intr={drug}"
        prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}

        try:
            r = await self.client.get(
                BASE,
                params={
                    "query.intr": drug,
                    # Without countTotal the response carries no total at all, and
                    # len(studies) silently caps at pageSize: osimertinib reported
                    # 100 trials against a true 383.
                    "countTotal": "true",
                    "pageSize": _PAGE_SIZE,
                    "fields": ",".join(
                        [
                            "protocolSection.identificationModule.nctId",
                            "protocolSection.statusModule.overallStatus",
                            "protocolSection.designModule.phases",
                        ]
                    ),
                },
            )
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(exc))

        studies = body.get("studies", [])
        phases: list[str] = []
        statuses: list[str] = []
        for s in studies:
            ps = s.get("protocolSection", {})
            phases.extend(ps.get("designModule", {}).get("phases", []) or [])
            status = ps.get("statusModule", {}).get("overallStatus")
            if status:
                statuses.append(status)

        max_phase = max((_PHASE_ORDER.get(p, -1) for p in phases), default=None)
        if max_phase is not None and max_phase < 0:
            max_phase = None  # only unrecognized phase labels: unknown, not "phase -1"

        def ok(value: Any) -> Any:
            return fact(value, self.name, source_url=url, retrieved_at=retrieved_at)

        n_total = body.get("totalCount")
        facts = {
            "n_trials": ok(n_total),
            "n_trials_scanned": ok(len(studies)),
            "phases": ok(sorted(set(phases))),
            "ct_max_phase": ok(max_phase),
            "has_completed": ok(any(s == "COMPLETED" for s in statuses)),
            "has_terminated": ok(
                any(s in ("TERMINATED", "WITHDRAWN", "SUSPENDED") for s in statuses)
            ),
        }
        return SourceRecord(self.name, drug, ok=bool(n_total), facts=facts, provenance=prov)
