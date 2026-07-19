"""ClinicalTrials.gov v2: a drug's observed combinations vs comparisons, from ARM structure.

A trial naming drug A and drug B may be A+B (a combination) or A vs B (a comparison) -- opposite
meanings, and ONLY the arm structure tells them apart: a single arm holding >=2 drugs is a
combination; >=2 arms each a different single drug is a comparison. Name co-occurrence cannot
distinguish them, so this reads `armGroups`, never the intervention list alone.

A multi-drug trial whose arms carry no drug-level assignment is AMBIGUOUS and DROPPED, never
guessed -- the S3 spike measured ~4% of multi-drug trials there, and a guess would be
confidently wrong about half the time. The dropped count is carried for honesty, not acted on.

A separate adapter from ClinicalTrialsAdapter (which owns the saturating count/phase reducers):
this one paginates a capped sample for the arm structure those reducers do not need, so the two
stay independently correct. Both are CT.gov, so both carry source `clinicaltrials`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.ingestion.base import SourceRecord, fact, utcnow

BASE = "https://clinicaltrials.gov/api/v2/studies"

# Open Targets marks non-drug arms too; only DRUG/BIOLOGICAL interventions define a combination.
_DRUG_TYPES = {"DRUG", "BIOLOGICAL"}

# Substrings that mark a non-therapeutic arm -- a placebo/observation arm is not a "drug" for the
# combination-vs-comparison call. Mirrors the spike's is_drug_name filter.
_NON_DRUG = ("placebo", "saline", "best supportive", "observation")

_PAGE_SIZE = 200

# Scan a capped sample of the drug's trials for arm structure: enough to characterise the
# combination/comparison mix, bounded so a drug with thousands of trials (pembrolizumab) does not
# stall enrichment. The counts are over this sample and reported beside the true total, the same
# scanned-vs-total honesty the trial-reality card carries.
_SCAN_CAP = 500

# How many example trials to keep per category -- enough for the card to show a few and link out.
_EXAMPLES = 5


def _is_drug_name(name: str) -> bool:
    n = (name or "").lower()
    return bool(n) and not any(w in n for w in _NON_DRUG)


@dataclass
class _Classification:
    """One trial's classification plus the drugs that define it (the combination arm's set, or
    the distinct single-drug arms being compared) -- carried so the card can name the partners."""

    kind: str  # single-drug | combination | comparison | ambiguous
    drugs: list[str] = field(default_factory=list)


def _classify(mod: dict[str, Any]) -> _Classification:
    """Classify one trial's arms-and-interventions module. Mirrors the S3 spike's classify():
    combo wins ties (a trial with both a combination arm and single-drug arms is a combination)."""
    interventions = mod.get("interventions") or []
    drugs = {
        i["name"]
        for i in interventions
        if i.get("type") in _DRUG_TYPES and _is_drug_name(i.get("name", ""))
    }
    if len(drugs) < 2:
        return _Classification("single-drug")

    arms = mod.get("armGroups") or []
    arm_drugsets = [
        {n for n in (a.get("interventionNames") or []) if _is_drug_name(n)} for a in arms
    ]
    arm_drugsets = [s for s in arm_drugsets if s]  # arms that actually name a drug
    if not arm_drugsets:
        # Multi-drug, but no arm names a drug -> cannot tell combination from comparison. DROP.
        return _Classification("ambiguous")

    combo_arm = next((s for s in arm_drugsets if len(s) >= 2), None)
    if combo_arm is not None:
        return _Classification("combination", sorted(combo_arm))
    single_drugs = sorted({next(iter(s)) for s in arm_drugsets if len(s) == 1})
    if len(single_drugs) >= 2:
        return _Classification("comparison", single_drugs)
    return _Classification("ambiguous")


class ClinicalTrialsCombinationsAdapter:
    name: str = "clinicaltrials"
    owned_keys: tuple[str, ...] = ("combinations",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch(self, drug: str) -> SourceRecord:
        retrieved_at = utcnow()
        url = f"https://clinicaltrials.gov/search?intr={drug}"
        prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}

        try:
            studies, n_total = await self._scan(drug)
        except Exception as exc:
            # Outage: the source failed, so `combinations` is unknown, not "no combinations".
            # _save_source_record synthesises a source_failed fact for the owned key.
            return SourceRecord(
                self.name, drug, ok=False, provenance=prov, error=str(exc), outage=True
            )

        counts = {"combination": 0, "comparison": 0, "ambiguous": 0}
        examples: dict[str, list[dict[str, Any]]] = {"combination": [], "comparison": []}
        for s in studies:
            ps = s.get("protocolSection", {})
            c = _classify(ps.get("armsInterventionsModule", {}))
            if c.kind == "single-drug":
                continue
            counts[c.kind] += 1
            if c.kind in examples and len(examples[c.kind]) < _EXAMPLES:
                nct = (ps.get("identificationModule") or {}).get("nctId")
                if nct:
                    examples[c.kind].append({"nct_id": nct, "drugs": c.drugs})

        n_classifiable = counts["combination"] + counts["comparison"]
        if n_classifiable == 0:
            # The drug's trials carry no combination or comparison we can stand behind (only
            # single-drug, or only ambiguous). A measured EMPTY, not an outage. fact(None) -> EMPTY.
            return SourceRecord(
                self.name,
                drug,
                ok=True,
                provenance=prov,
                facts={
                    "combinations": fact(None, self.name, source_url=url, retrieved_at=retrieved_at)
                },
            )

        value = {
            "n_total": n_total,
            "n_scanned": len(studies),
            "n_multi_drug": n_classifiable + counts["ambiguous"],
            "n_combination": counts["combination"],
            "n_comparison": counts["comparison"],
            # Carried for honesty -- these were dropped, not guessed. The card footnotes them.
            "n_ambiguous": counts["ambiguous"],
            "combination_examples": examples["combination"],
            "comparison_examples": examples["comparison"],
        }
        return SourceRecord(
            self.name,
            drug,
            ok=True,
            provenance=prov,
            facts={
                "combinations": fact(value, self.name, source_url=url, retrieved_at=retrieved_at)
            },
        )

    async def _scan(self, drug: str) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch up to _SCAN_CAP of the drug's trials with their arm structure, plus the true
        total (countTotal on the first page), paginating by nextPageToken."""
        out: list[dict[str, Any]] = []
        token: str | None = None
        n_total: int | None = None
        while len(out) < _SCAN_CAP:
            params: dict[str, Any] = {
                "query.intr": drug,
                "pageSize": _PAGE_SIZE,
                "fields": ",".join(
                    [
                        "protocolSection.identificationModule.nctId",
                        "protocolSection.armsInterventionsModule",
                    ]
                ),
            }
            if token is None:
                params["countTotal"] = "true"
            else:
                params["pageToken"] = token
            r = await self.client.get(BASE, params=params)
            r.raise_for_status()
            body = r.json()
            if n_total is None:
                n_total = body.get("totalCount")
            out.extend(body.get("studies", []))
            token = body.get("nextPageToken")
            if not token:
                break
        return out[:_SCAN_CAP], n_total
