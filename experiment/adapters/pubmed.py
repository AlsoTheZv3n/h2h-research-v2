"""PubMed (NCBI E-utilities): literature hit count plus a few recent titles."""
from __future__ import annotations
import os
import httpx
from .base import SourceRecord, utcnow

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PubMedAdapter:
    name = "pubmed"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.api_key = os.getenv("NCBI_API_KEY") or None

    def _params(self, extra: dict) -> dict:
        p = {"db": "pubmed", "retmode": "json"}
        if self.api_key:
            p["api_key"] = self.api_key
        p.update(extra)
        return p

    def fetch(self, drug: str) -> SourceRecord:
        prov = {"source_url": f"https://pubmed.ncbi.nlm.nih.gov/?term={drug}",
                "retrieved_at": utcnow()}
        try:
            r = self.client.get(ESEARCH, params=self._params({
                "term": drug, "retmax": 5, "sort": "relevance"}))
            r.raise_for_status()
            result = r.json().get("esearchresult", {})
            count = int(result.get("count", 0))
            ids = result.get("idlist", []) or []

            titles: list[str] = []
            if ids:
                rs = self.client.get(ESUMMARY, params=self._params({"id": ",".join(ids)}))
                if rs.status_code == 200:
                    docs = rs.json().get("result", {})
                    titles = [docs[i].get("title", "") for i in docs.get("uids", [])]

            fields = {"n_pubmed": count, "sample_titles": titles}
            return SourceRecord(self.name, drug, ok=count > 0, fields=fields, provenance=prov)
        except Exception as e:  # noqa: BLE001
            return SourceRecord(self.name, drug, ok=False, provenance=prov, error=str(e))
