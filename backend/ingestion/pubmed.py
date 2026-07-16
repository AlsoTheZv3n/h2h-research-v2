"""PubMed (NCBI E-utilities): literature hit count plus a few recent titles.

Metadata only, deliberately: counts, PMIDs and titles, linking out for the rest.
Storing full text would put us outside what PubMed's terms allow.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.ingestion.base import SourceRecord, fact, failed, utcnow

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PubMedAdapter:
    name = "pubmed"

    def __init__(self, client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self.client = client
        # Optional: only raises rate limits. Nothing here requires it.
        self.api_key = api_key or None

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        p: dict[str, Any] = {"db": "pubmed", "retmode": "json"}
        if self.api_key:
            p["api_key"] = self.api_key
        p.update(extra)
        return p

    async def fetch(self, drug: str) -> SourceRecord:
        retrieved_at = utcnow()
        url = f"https://pubmed.ncbi.nlm.nih.gov/?term={drug}"
        prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}

        try:
            r = await self.client.get(
                ESEARCH, params=self._params({"term": drug, "retmax": 5, "sort": "relevance"})
            )
            r.raise_for_status()
            result = r.json().get("esearchresult") or {}
            # E-utilities reports failures *inside* a 200: {"esearchresult": {"ERROR":
            # "..."}}, with no count key. raise_for_status sees nothing wrong, so a
            # count defaulting to 0 would classify as EMPTY -- "measured, no
            # literature" -- and persist indistinguishably from a drug that genuinely
            # has none. Never default a count: a missing count means we did not measure.
            if result.get("ERROR") or result.get("count") is None:
                reason = result.get("ERROR") or "esearch returned no count"
                return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(reason))
            count = int(result["count"])
            ids = result.get("idlist", []) or []
        except Exception as exc:
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(exc))

        def ok(value: Any) -> Any:
            return fact(value, self.name, source_url=url, retrieved_at=retrieved_at)

        facts = {"n_pubmed": ok(count)}

        # Titles are a nice-to-have on top of the count: degrade this alone rather
        # than losing the count with it.
        try:
            titles: list[str] = []
            if ids:
                rs = await self.client.get(ESUMMARY, params=self._params({"id": ",".join(ids)}))
                rs.raise_for_status()
                docs = rs.json().get("result", {})
                titles = [docs[i].get("title", "") for i in docs.get("uids", [])]
            facts["sample_titles"] = ok(titles)
        except Exception as exc:
            facts["sample_titles"] = failed(self.name, f"esummary: {exc}", source_url=url)

        return SourceRecord(self.name, drug, ok=count > 0, facts=facts, provenance=prov)
