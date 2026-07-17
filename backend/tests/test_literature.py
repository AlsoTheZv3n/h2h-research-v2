"""Parsing PubMed's XML, against the shapes it really returns.

Every fixture here is modelled on a record efetch actually served while this was
written, not on what the DTD permits. The traps are all the same species: the naive
parse returns well-formed, plausible text, so nothing downstream can tell that it is
wrong -- and an abstract that is quietly a quarter of itself is worse than no
abstract, because the model will ground on it and cite it.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from backend.ingestion.literature import LiteratureFetcher, parse_articles

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _set(*articles: str) -> str:
    return f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>"


STRUCTURED = """
<PubmedArticle><MedlineCitation><PMID>37924972</PMID>
<Article>
  <Journal><ISOAbbreviation>J Thorac Oncol</ISOAbbreviation>
    <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>MUC1-C Is a Common Driver of Acquired Osimertinib Resistance.</ArticleTitle>
  <Abstract>
    <AbstractText Label="INTRODUCTION">Osimertinib is standard of care.</AbstractText>
    <AbstractText Label="METHODS">We profiled resistant lines.</AbstractText>
    <AbstractText Label="RESULTS">MUC1-C was upregulated in all models.</AbstractText>
    <AbstractText Label="CONCLUSIONS">MUC1-C is a therapeutic target.</AbstractText>
  </Abstract>
</Article></MedlineCitation></PubmedArticle>
"""

PLAIN = """
<PubmedArticle><MedlineCitation><PMID>36482474</PMID>
<Article>
  <Journal><ISOAbbreviation>J Hematol Oncol</ISOAbbreviation>
    <JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>Therapeutic strategies for EGFR-mutated NSCLC.</ArticleTitle>
  <Abstract><AbstractText>A single unlabelled paragraph.</AbstractText></Abstract>
</Article></MedlineCitation></PubmedArticle>
"""

# An editorial: a real record, with no abstract at all.
NO_ABSTRACT = """
<PubmedArticle><MedlineCitation><PMID>11111111</PMID>
<Article>
  <Journal><ISOAbbreviation>Lancet</ISOAbbreviation>
    <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>An editorial with no abstract.</ArticleTitle>
</Article></MedlineCitation></PubmedArticle>
"""

MARKUP = """
<PubmedArticle><MedlineCitation><PMID>22222222</PMID>
<Article>
  <Journal><ISOAbbreviation>Nature</ISOAbbreviation>
    <JournalIssue><PubDate>
      <MedlineDate>2022 Jan-Feb</MedlineDate>
    </PubDate></JournalIssue></Journal>
  <ArticleTitle>EGFR<sup>T790M</sup> mutations in <i>vitro</i>.</ArticleTitle>
  <Abstract><AbstractText>IC<sub>50</sub> was 12 nM.</AbstractText></Abstract>
</Article></MedlineCitation></PubmedArticle>
"""

BOOK = """
<PubmedBookArticle><BookDocument><PMID>33333333</PMID>
  <ArticleTitle>A GeneReviews chapter.</ArticleTitle>
</BookDocument></PubmedBookArticle>
"""


class TestParsing:
    def test_a_structured_abstract_keeps_every_section(self) -> None:
        """The expensive one. Four <AbstractText> elements, not one.

        `.//AbstractText` and take-the-first returns "Osimertinib is standard of
        care." -- fluent, on topic, and missing the methods, the results and the
        conclusion. A model handed that would answer from the background section of
        a paper whose findings it never saw, and cite it correctly while doing so.
        """
        [art] = parse_articles(_set(STRUCTURED))

        assert art.text is not None
        for section in ("INTRODUCTION", "METHODS", "RESULTS", "CONCLUSIONS"):
            assert section in art.text
        # The part that carries the finding, not just the part that sets it up.
        assert "MUC1-C was upregulated" in art.text
        assert "MUC1-C is a therapeutic target" in art.text

    def test_labels_are_kept_not_stripped(self) -> None:
        """Which section a number came from changes what it means.

        "12 nM" under RESULTS is a finding; the same string under INTRODUCTION is
        someone else's prior work being recapped.
        """
        [art] = parse_articles(_set(STRUCTURED))
        assert art.text is not None
        assert art.text.startswith("INTRODUCTION: ")

    def test_an_unlabelled_abstract_gets_no_invented_label(self) -> None:
        [art] = parse_articles(_set(PLAIN))
        assert art.text == "A single unlabelled paragraph."

    def test_no_abstract_is_none_rather_than_empty_string(self) -> None:
        """Editorials and letters have no abstract. That is a measurement.

        None, not "": the schema's CHECK pairs a NULL text with a NULL embedding, and
        an empty string would sail past it and be embedded -- a vector pointing at
        nothing, which retrieves and then grounds a claim on zero characters.
        """
        [art] = parse_articles(_set(NO_ABSTRACT))
        assert art.text is None
        assert art.title == "An editorial with no abstract."

    def test_inline_markup_is_read_through(self) -> None:
        """`.text` stops at the first child element.

        PubMed marks up gene names and formulae constantly. On this title `.text`
        yields "EGFR" and drops the T790M -- the entire point of the paper -- and on
        the abstract it yields "IC" and drops the 50 and the value.
        """
        [art] = parse_articles(_set(MARKUP))
        assert art.title == "EGFRT790M mutations in vitro."
        assert art.text == "IC50 was 12 nM."

    def test_a_medline_date_still_yields_a_year(self) -> None:
        """<PubDate> has no <Year> when it carries a free-text MedlineDate."""
        [art] = parse_articles(_set(MARKUP))
        assert art.year == 2022

    def test_book_records_are_skipped_not_half_parsed(self) -> None:
        """PubmedBookArticle is a different element with a different shape.

        A `.//PMID` sweep would pull it in as a title-less shell.
        """
        arts = parse_articles(_set(PLAIN, BOOK))
        assert [a.pmid for a in arts] == ["36482474"]

    def test_rank_preserves_pubmed_relevance_order(self) -> None:
        arts = parse_articles(_set(STRUCTURED, PLAIN, NO_ABSTRACT))
        assert [a.rank for a in arts] == [0, 1, 2]
        assert arts[0].pmid == "37924972"

    def test_an_empty_set_is_no_articles_not_a_crash(self) -> None:
        assert parse_articles(_set()) == []


@pytest.fixture
def client() -> Any:
    return httpx.AsyncClient()


class TestFetcher:
    @respx.mock
    async def test_fetches_and_parses(self, client: Any) -> None:
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"idlist": ["37924972"]}})
        )
        respx.get(f"{EUTILS}/efetch.fcgi").mock(
            return_value=httpx.Response(200, text=_set(STRUCTURED))
        )

        rec = await LiteratureFetcher(client).fetch("osimertinib")

        assert rec.ok
        assert len(rec.articles) == 1
        assert "CONCLUSIONS" in (rec.articles[0].text or "")

    @respx.mock
    async def test_no_hits_is_empty_not_an_error(self, client: Any) -> None:
        """ "Nobody has published on this" and "we could not ask" are different."""
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"idlist": []}})
        )
        rec = await LiteratureFetcher(client).fetch("nothingol")

        assert rec.ok
        assert rec.articles == ()

    @respx.mock
    async def test_an_error_inside_a_200_is_an_error(self, client: Any) -> None:
        """E-utilities reports failure in the body, with a 200 and no count."""
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"ERROR": "bad request"}})
        )
        rec = await LiteratureFetcher(client).fetch("x")

        assert not rec.ok
        assert rec.articles == ()

    @respx.mock
    async def test_a_dead_efetch_is_an_error_not_an_empty_result(self, client: Any) -> None:
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"idlist": ["1"]}})
        )
        respx.get(f"{EUTILS}/efetch.fcgi").mock(return_value=httpx.Response(500))

        rec = await LiteratureFetcher(client).fetch("x")

        # The distinction the whole project turns on: an outage must never read as
        # "this drug has no literature".
        assert not rec.ok
        assert rec.error is not None
        assert rec.articles == ()

    @respx.mock
    async def test_a_throttle_page_is_an_error_not_zero_articles(self, client: Any) -> None:
        """NCBI answers an over-rate client with an HTML page and a 200.

        It parses as neither XML nor articles. Letting ET.ParseError fall through as
        "no articles found" would turn being throttled into a finding about the drug.
        """
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"idlist": ["1"]}})
        )
        respx.get(f"{EUTILS}/efetch.fcgi").mock(
            return_value=httpx.Response(200, text="<html><body>Too many requests</body></html>")
        )

        rec = await LiteratureFetcher(client).fetch("x")

        assert not rec.ok
        assert rec.articles == ()

    @respx.mock
    async def test_the_api_key_never_reaches_the_error_string(self, client: Any) -> None:
        """httpx builds its messages from the full URL, which carries api_key=.

        The fact adapter leaked the NCBI key into a served tooltip exactly this way.
        This fetcher's errors are not served, but they are logged -- and a key in a
        log on a public CI run is still a published key.
        """
        respx.get(f"{EUTILS}/esearch.fcgi").mock(return_value=httpx.Response(500))

        rec = await LiteratureFetcher(client, api_key="SECRET-KEY-123").fetch("x")

        assert not rec.ok
        assert "SECRET-KEY-123" not in (rec.error or "")

    @respx.mock
    async def test_both_calls_identify_the_client(self, client: Any) -> None:
        search = respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"idlist": ["1"]}})
        )
        fetch = respx.get(f"{EUTILS}/efetch.fcgi").mock(
            return_value=httpx.Response(200, text=_set(PLAIN))
        )

        await LiteratureFetcher(client, tool="h2h-test", email="dev@example.org").fetch("x")

        for route in (search, fetch):
            params = route.calls.last.request.url.params
            assert params["tool"] == "h2h-test"
            assert params["email"] == "dev@example.org"
