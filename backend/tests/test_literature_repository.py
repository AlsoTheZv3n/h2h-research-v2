"""Abstract storage and vector search, against real Postgres and real embeddings.

Real pgvector, because the interesting failures are all in the database: the CHECK
constraint that pairs text with a vector, the join that keeps one drug's papers out
of another's answer, and NULL embeddings sorting to the front of an ORDER BY.

Real embeddings too -- bge runs on CPU in milliseconds, and a stubbed embedder would
turn "is this actually retrieving on meaning?" into "does this call the function I
told it to call".
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.embeddings import embed_query
from backend.ingestion.base import utcnow
from backend.ingestion.literature import Article, LiteratureRecord
from backend.models import Drug
from backend.repositories.literature import LiteratureRepository

OSI = "CHEMBL_OSI_TEST"
SOTO = "CHEMBL_SOTO_TEST"


def _article(
    pmid: str,
    text: str | None,
    rank: int = 0,
    title: str = "T",
    publication_types: tuple[str, ...] = (),
    indexed: bool = False,
) -> Article:
    return Article(
        pmid=pmid,
        title=title,
        text=text,
        journal="J Test",
        year=2024,
        rank=rank,
        publication_types=publication_types,
        indexed=indexed,
    )


def _record(*articles: Article) -> LiteratureRecord:
    return LiteratureRecord(query="q", articles=articles, retrieved_at=utcnow())


@pytest.fixture
async def drugs(session: AsyncSession) -> None:
    for cid, name in ((OSI, "osimertinib"), (SOTO, "sotorasib")):
        session.add(Drug(chembl_id=cid, pref_name=name))
    await session.commit()


class TestSaving:
    async def test_stores_and_embeds_only_what_has_text(
        self, session: AsyncSession, drugs: None
    ) -> None:
        repo = LiteratureRepository(session)

        embedded = await repo.save(
            OSI,
            _record(
                _article("100", "Osimertinib inhibits EGFR T790M.", rank=0),
                # An editorial: fetched, no abstract. Stored, not embedded.
                _article("101", None, rank=1),
            ),
        )

        assert embedded == 1
        hits = await repo.search(OSI, await embed_query("EGFR inhibition"), limit=10)
        # The record with no abstract is in the table but must never be retrievable:
        # it has nothing to ground on.
        assert [h.pmid for h in hits] == ["100"]

    async def test_re_fetching_a_drug_does_not_collide(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The same PMID arrives again -- from a re-fetch, or from another drug."""
        repo = LiteratureRepository(session)
        await repo.save(OSI, _record(_article("200", "First version.")))
        await repo.save(OSI, _record(_article("200", "Corrected version.")))

        hits = await repo.search(OSI, await embed_query("version"), limit=5)
        assert len(hits) == 1
        assert hits[0].text == "Corrected version."

    async def test_one_pmid_can_belong_to_two_drugs(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """A paper on EGFR/KRAS co-mutation is literature for both drugs.

        Stored once, linked twice -- the reason `abstract` is keyed by PMID.
        """
        repo = LiteratureRepository(session)
        shared = _article("300", "Co-mutation of EGFR and KRAS in NSCLC.")
        await repo.save(OSI, _record(shared))
        await repo.save(SOTO, _record(shared))

        for cid in (OSI, SOTO):
            hits = await repo.search(cid, await embed_query("co-mutation"), limit=5)
            assert [h.pmid for h in hits] == ["300"]

    async def test_a_failed_fetch_leaves_the_drug_unsearched(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """An outage must not be recorded as a search, or we would never retry."""
        repo = LiteratureRepository(session)
        failed = LiteratureRecord("q", (), utcnow(), error="NCBI timed out")

        assert await repo.save(OSI, failed) == 0
        assert await repo.was_searched(OSI) is False

    async def test_a_search_that_found_nothing_is_still_a_search(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The bug review caught, pinned so it cannot come back.

        This project exists to keep "nobody looked" apart from "we looked and there
        is nothing", and the literature layer merged them: both produced zero link
        rows, and `has_abstracts` -- the only thing anyone asked -- returned False
        for both. Twenty-five tests around this file, and not one of them asked the
        question this one asks.
        """
        repo = LiteratureRepository(session)
        assert await repo.was_searched(OSI) is False

        # PubMed answered. It has nothing on this drug. That is a measurement.
        empty = LiteratureRecord("nothingol", (), utcnow())
        assert empty.ok
        assert await repo.save(OSI, empty) == 0

        assert await repo.was_searched(OSI) is True, (
            "a successful search that found nothing reads as never having searched"
        )
        assert await repo.search(OSI, await embed_query("anything")) == []

    async def test_a_refresh_drops_a_paper_pubmed_no_longer_returns(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """A re-fetch replaces the drug's papers; it does not add to them.

        PubMed's relevance ranking moves. Upserting alone leaves last month's top hit
        linked forever, so the index slowly becomes the union of every answer PubMed
        has ever given -- which nothing downstream accounts for, and which the
        same-PMID update test above cannot see.
        """
        repo = LiteratureRepository(session)
        await repo.save(
            OSI,
            _record(
                _article("500", "Still relevant next month.", rank=0),
                _article("501", "Drops out of the top hits.", rank=1),
            ),
        )
        assert len(await repo.search(OSI, await embed_query("relevant"), limit=10)) == 2

        # The next fetch no longer returns 501.
        await repo.save(OSI, _record(_article("500", "Still relevant next month.", rank=0)))

        hits = await repo.search(OSI, await embed_query("relevant"), limit=10)
        assert [h.pmid for h in hits] == ["500"]

    async def test_a_refresh_does_not_unlink_another_drugs_paper(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The delete is scoped to one drug. Sotorasib keeps its shared paper."""
        repo = LiteratureRepository(session)
        shared = _article("600", "Co-mutation of EGFR and KRAS.")
        await repo.save(OSI, _record(shared))
        await repo.save(SOTO, _record(shared))

        # Osimertinib re-fetches and this paper is gone from its results.
        await repo.save(OSI, _record(_article("601", "Something else entirely.")))

        assert [h.pmid for h in await repo.search(SOTO, await embed_query("co-mutation"))] == [
            "600"
        ]

    async def test_the_schema_refuses_a_vector_with_no_text(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The CHECK, from the ORM's side rather than from psql.

        A vector with no text behind it is the worst row in this table: it ranks, it
        gets retrieved, and it hands the model an empty document to answer from.
        """
        from backend.models import Abstract

        session.add(Abstract(pmid="999", text=None, embedding=[0.1] * 384, retrieved_at=utcnow()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


class TestSearch:
    async def test_retrieves_on_meaning_not_on_keywords(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The claim vectors are here to make. No shared words between query and hit.

        If this passed with a stubbed embedder it would prove nothing; with the real
        model it is the difference between semantic retrieval and an ILIKE.
        """
        repo = LiteratureRepository(session)
        await repo.save(
            OSI,
            _record(
                _article("1", "Patients developed resistance to therapy after 18 months."),
                _article("2", "Synthesis of the compound was achieved in six steps."),
            ),
        )

        hits = await repo.search(OSI, await embed_query("Why does the drug stop working?"), limit=1)

        assert [h.pmid for h in hits] == ["1"]

    async def test_another_drugs_paper_never_leaks_in(
        self, session: AsyncSession, drugs: None
    ) -> None:
        """The most dangerous retrieval bug this design can have.

        Sotorasib's paper is the better semantic match for a KRAS question. Asked
        about osimertinib, an unfiltered nearest-neighbour search returns it -- and
        the model, handed a beautifully on-topic paper about a different molecule,
        has no way to know it is answering about the wrong drug. It would cite it
        correctly, too. The drug filter is load-bearing, not a tidy-up.
        """
        repo = LiteratureRepository(session)
        await repo.save(SOTO, _record(_article("10", "Sotorasib covalently binds KRAS G12C.")))
        await repo.save(OSI, _record(_article("11", "Osimertinib pharmacokinetics in plasma.")))

        hits = await repo.search(OSI, await embed_query("KRAS G12C covalent binding"), limit=5)

        assert [h.pmid for h in hits] == ["11"]
        assert all("Sotorasib" not in h.text for h in hits)

    async def test_a_drug_nobody_looked_at_is_empty_not_an_error(
        self, session: AsyncSession, drugs: None
    ) -> None:
        repo = LiteratureRepository(session)
        assert await repo.was_searched(OSI) is False
        assert await repo.search(OSI, await embed_query("anything")) == []

    async def test_hits_carry_what_a_citation_needs(
        self, session: AsyncSession, drugs: None
    ) -> None:
        repo = LiteratureRepository(session)
        await repo.save(OSI, _record(_article("42", "Body.", title="A real title")))

        [hit] = await repo.search(OSI, await embed_query("body"), limit=1)

        assert hit.title == "A real title"
        assert hit.year == 2024
        assert hit.url == "https://pubmed.ncbi.nlm.nih.gov/42/"
        assert 0.0 <= hit.distance <= 2.0


class TestRelevanceRerank:
    """B4: the shown titles are ranked by oncology relevance, not recency, using the abstracts
    already fetched. Real embeddings, because the whole claim is that this ranks on MEANING."""

    async def test_the_oncology_paper_leads_the_off_topic_ones(
        self, session: AsyncSession, drugs: None
    ) -> None:
        from backend.ingestion.enrich import _rank_titles_by_relevance
        from backend.models import Drug
        from backend.repositories.drugs import DrugRepository

        repo = LiteratureRepository(session)
        # A drug's PubMed hits by name include off-topic papers; only one is about its cancer use.
        rec = _record(
            _article(
                "1",
                "A transgenic mouse model of Alzheimer's disease with amyloid-beta plaques and "
                "cognitive decline; no relation to cancer.",
                rank=0,
                title="Alzheimer mouse model",
                indexed=True,
            ),
            _article(
                "2",
                "The drug inhibits its kinase target and induces regression of the tumour in "
                "patients with this malignancy; an antitumour, oncology result.",
                rank=1,
                title="Antitumour efficacy in the clinic",
                publication_types=("Journal Article", "Randomized Controlled Trial"),
                indexed=True,
            ),
            _article(
                "3",
                "Hepatic stellate cell activation and the progression of liver fibrosis in a "
                "non-oncological model.",
                rank=2,
                title="Liver fibrosis pathway",
                indexed=True,
            ),
        )
        await repo.save(OSI, rec)

        drug = await session.get(Drug, OSI)
        assert drug is not None
        await _rank_titles_by_relevance(session, drug, "osimertinib", utcnow(), rec.articles)

        facts = {f.key: f for f in await DrugRepository(session).facts_for(OSI)}
        rel = facts["relevant_titles"]
        assert rel.status.value == "ok"
        assert rel.source == "pubmed"
        titles = rel.value
        assert isinstance(titles, list)
        names = [t["title"] for t in titles]
        # The oncology paper leads; recency (rank order) would have led with the Alzheimer's one.
        assert names[0] == "Antitumour efficacy in the clinic"
        # And the off-topic papers rank below it, not above.
        assert names.index("Antitumour efficacy in the clinic") < names.index(
            "Alzheimer mouse model"
        )
        # #42: the leading paper carries its most-weighty publication type (the evidence hierarchy),
        # not the generic "Journal Article".
        assert titles[0]["publication_type"] == "Randomized Controlled Trial"
        assert titles[0]["indexed"] is True

    async def test_skips_when_no_abstract_has_text(
        self, session: AsyncSession, drugs: None
    ) -> None:
        # Nothing embedded -> no relevant_titles fact, and the block falls back to sample_titles.
        from backend.ingestion.enrich import _rank_titles_by_relevance
        from backend.models import Drug
        from backend.repositories.drugs import DrugRepository

        rec = _record(_article("9", None, title="No body"))
        await LiteratureRepository(session).save(OSI, rec)
        drug = await session.get(Drug, OSI)
        assert drug is not None
        await _rank_titles_by_relevance(session, drug, "osimertinib", utcnow(), rec.articles)

        facts = {f.key for f in await DrugRepository(session).facts_for(OSI)}
        assert "relevant_titles" not in facts

    async def test_an_unindexed_paper_is_labelled_not_ranked_down(
        self, session: AsyncSession, drugs: None
    ) -> None:
        # #42's trap: a recent, not-yet-MeSH-indexed paper must ride through as indexed=False (a
        # label), never sunk in the ranking -- the ranking is embedding relevance, not a MeSH match.
        from backend.ingestion.enrich import _rank_titles_by_relevance
        from backend.models import Drug
        from backend.repositories.drugs import DrugRepository

        rec = _record(
            _article(
                "10",
                "A first-in-human trial of this drug against the tumour; strong antitumour signal.",
                title="Fresh oncology trial",
                indexed=False,  # just posted, not yet indexed
            ),
        )
        await LiteratureRepository(session).save(OSI, rec)
        drug = await session.get(Drug, OSI)
        assert drug is not None
        await _rank_titles_by_relevance(session, drug, "osimertinib", utcnow(), rec.articles)

        rel = {f.key: f for f in await DrugRepository(session).facts_for(OSI)}["relevant_titles"]
        item = rel.value[0]
        assert item["title"] == "Fresh oncology trial"
        # Not sunk: it still ranks (the only paper) and is honestly flagged, not dropped.
        assert item["indexed"] is False
        assert item["publication_type"] is None  # no meaningful type -> no false badge
