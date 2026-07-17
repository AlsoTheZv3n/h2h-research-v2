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


def _safe_error(exc: Exception) -> str:
    """An error message with no credentials in it.

    httpx builds its messages from the full request URL, and ours carries
    `api_key=` when one is configured. That string does not stay in a log: it is
    stored on the fact, served by the API and rendered into a tooltip -- so the
    optional NCBI key would be published by the very field whose job is honestly
    describing the pipeline.

    A status code says everything the reader needs; the URL adds nothing they
    cannot see on the citation chip.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from NCBI"
    if isinstance(exc, httpx.TimeoutException):
        return "NCBI timed out"
    # Anything else: the type, never the message -- we do not know what a stranger's
    # exception put in its string.
    return type(exc).__name__


class PubMedAdapter:
    name: str = "pubmed"
    owned_keys: tuple[str, ...] = ("n_pubmed", "sample_titles")

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
        tool: str = "h2h-research",
        email: str = "noreply@h2h-research.invalid",
    ) -> None:
        self.client = client
        # Optional: only raises rate limits. Nothing here requires it.
        self.api_key = api_key or None
        self.tool = tool
        self.email = email

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        # tool and email are not optional courtesies -- the E-utilities usage
        # guidelines require both on every request, and v0.1.0 shipped without them.
        # They are how NCBI identifies a client and contacts its operator instead of
        # silently blocking the IP, which is the failure mode you cannot debug from
        # this side: requests simply start failing and nothing says why.
        p: dict[str, Any] = {
            "db": "pubmed",
            "retmode": "json",
            "tool": self.tool,
            "email": self.email,
        }
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
            # outage: the source failed, so its keys are unknown -- not zero.
            return SourceRecord(
                self.name, drug, ok=False, provenance=prov, error=_safe_error(exc), outage=True
            )

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
            facts["sample_titles"] = failed(
                self.name, f"esummary: {_safe_error(exc)}", source_url=url
            )

        return SourceRecord(self.name, drug, ok=count > 0, facts=facts, provenance=prov)
