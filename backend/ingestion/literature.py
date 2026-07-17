"""Fetching abstracts from PubMed for the retrieval index.

Separate from `pubmed.py` on purpose. That adapter produces *facts* -- a count and a
few titles, values with provenance that the API serves. This produces *documents*:
text that is never served, exists only to be embedded and read by the chat model,
and is governed by the rules in NOTICE.md. Same source, same client, two different
things with two different obligations, so they do not share a code path that could
let one's rules leak into the other.

Fetching is per drug and on demand -- never a sweep over the catalog. 3,900 drugs at
20 abstracts each is ~78,000 records, which at the 3 requests/second E-utilities
allows an anonymous client is a bulk job of the kind NCBI explicitly asks you to run
against their FTP mirrors on a weekend instead.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from backend.ingestion.base import utcnow
from backend.ingestion.pubmed import safe_error

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Enough for a question about a drug to find its own answer, few enough to stay a
# per-drug lookup rather than a crawl.
DEFAULT_LIMIT = 20


@dataclass(frozen=True, slots=True)
class Article:
    """One PubMed record, parsed.

    `text is None` means this record has no abstract -- common and unremarkable for
    editorials, letters and meeting reports. It is a measurement, not a failure, and
    the caller must not retry it.
    """

    pmid: str
    title: str | None
    text: str | None
    journal: str | None
    year: int | None
    rank: int


@dataclass(frozen=True, slots=True)
class LiteratureRecord:
    query: str
    articles: tuple[Article, ...]
    retrieved_at: datetime
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _all_text(el: ET.Element | None) -> str:
    """Every character under this element, including inside inline markup.

    `.text` stops at the first child, and PubMed titles and abstracts are full of
    <i>, <sub> and <sup> for gene names and formulae -- so `.text` on "EGFR<sup>
    T790M</sup> mutations" silently yields "EGFR". itertext walks the whole subtree.
    """
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _abstract_of(article: ET.Element) -> str | None:
    """The whole abstract, including every section of a structured one.

    This is the trap in the PubMed XML. Roughly a quarter of clinical abstracts are
    *structured*: several <AbstractText> elements carrying Label="INTRODUCTION",
    "METHODS", "RESULTS", "CONCLUSIONS". Reading `.//AbstractText` and taking the
    first one returns the introduction alone and drops the conclusion -- the one
    section an evidence question actually turns on -- while still returning
    plausible, well-formed prose that nothing downstream can tell is a quarter of
    the paper. Join them all, and keep the labels, since they are what tells the
    model that a number came from RESULTS rather than from background.
    """
    parts: list[str] = []
    for el in article.findall(".//Abstract/AbstractText"):
        body = _all_text(el)
        if not body:
            continue
        label = el.get("Label")
        parts.append(f"{label}: {body}" if label else body)
    return "\n\n".join(parts) if parts else None


def _year_of(article: ET.Element) -> int | None:
    """The publication year, from whichever of PubMed's several date shapes is used.

    <PubDate> carries either <Year>, or a <MedlineDate> free-text string like
    "2022 Jan-Feb" or "1998-1999" for which no Year element exists at all. Reading
    only Year loses those silently.
    """
    pub = article.find(".//Journal/JournalIssue/PubDate")
    if pub is None:
        return None
    if (year := pub.findtext("Year")) and year.isdigit():
        return int(year)
    medline = pub.findtext("MedlineDate") or ""
    head = medline[:4]
    return int(head) if head.isdigit() else None


def parse_articles(xml: str) -> list[Article]:
    """PubmedArticleSet -> Articles, in document order.

    Order matters: efetch returns records in the order the ids were given, which is
    the relevance order esearch produced, and that ranking is PubMed's opinion rather
    than ours -- the only free relevance signal available.
    """
    root = ET.fromstring(xml)
    # Well-formed is not the same as ours. NCBI answers an over-rate or blocked
    # client with an HTML error page and a 200, and HTML parses as XML perfectly
    # happily -- so findall("PubmedArticle") returns nothing and being throttled
    # reads as "this drug has no literature". ET.ParseError never fires. Checking the
    # root tag is the only thing between those two meanings.
    if root.tag != "PubmedArticleSet":
        raise ET.ParseError(f"expected a PubmedArticleSet, got <{root.tag}>")

    out: list[Article] = []
    # PubmedBookArticle is a different element with a different shape (book chapters,
    # GeneReviews). Taking .//PMID across the whole set would mix them in with a
    # title-less, abstract-less shell. Only journal articles are indexed here.
    for rank, article in enumerate(root.findall("PubmedArticle")):
        pmid = article.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue
        out.append(
            Article(
                pmid=pmid,
                title=_all_text(article.find(".//ArticleTitle")) or None,
                text=_abstract_of(article),
                journal=article.findtext(".//Journal/ISOAbbreviation")
                or article.findtext(".//Journal/Title"),
                year=_year_of(article),
                rank=rank,
            )
        )
    return out


class LiteratureFetcher:
    """esearch for PMIDs, efetch for their abstracts. Two calls per drug."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
        tool: str = "h2h-research",
        email: str = "noreply@h2h-research.invalid",
    ) -> None:
        self.client = client
        self.api_key = api_key or None
        self.tool = tool
        self.email = email

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        p: dict[str, Any] = {"db": "pubmed", "tool": self.tool, "email": self.email}
        if self.api_key:
            p["api_key"] = self.api_key
        p.update(extra)
        return p

    async def fetch(self, drug: str, limit: int = DEFAULT_LIMIT) -> LiteratureRecord:
        retrieved_at = utcnow()
        try:
            r = await self.client.get(
                ESEARCH,
                params=self._params(
                    {"retmode": "json", "term": drug, "retmax": limit, "sort": "relevance"}
                ),
            )
            r.raise_for_status()
            result = r.json().get("esearchresult") or {}
            # E-utilities reports failure inside a 200 with an ERROR key and no count.
            # raise_for_status sees nothing wrong. Same trap as the fact adapter.
            if result.get("ERROR"):
                return LiteratureRecord(drug, (), retrieved_at, error=str(result["ERROR"]))
            ids = list(result.get("idlist") or [])
        except Exception as exc:
            return LiteratureRecord(drug, (), retrieved_at, error=safe_error(exc))

        if not ids:
            # Measured, and the answer is nothing. Not an error: this drug has no
            # literature under this name.
            return LiteratureRecord(drug, (), retrieved_at)

        try:
            rf = await self.client.get(
                EFETCH, params=self._params({"retmode": "xml", "id": ",".join(ids)})
            )
            rf.raise_for_status()
            articles = parse_articles(rf.text)
        except ET.ParseError as exc:
            # A truncated or throttle-page response parses as garbage rather than
            # raising HTTP -- name it rather than letting it read as "no articles".
            return LiteratureRecord(drug, (), retrieved_at, error=f"efetch returned no XML: {exc}")
        except Exception as exc:
            return LiteratureRecord(drug, (), retrieved_at, error=safe_error(exc))

        return LiteratureRecord(drug, tuple(articles), retrieved_at)
