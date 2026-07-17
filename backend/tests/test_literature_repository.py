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


def _article(pmid: str, text: str | None, rank: int = 0, title: str = "T") -> Article:
    return Article(pmid=pmid, title=title, text=text, journal="J Test", year=2024, rank=rank)


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

    async def test_a_failed_fetch_writes_nothing(self, session: AsyncSession, drugs: None) -> None:
        repo = LiteratureRepository(session)
        failed = LiteratureRecord("q", (), utcnow(), error="NCBI timed out")

        assert await repo.save(OSI, failed) == 0
        assert await repo.has_abstracts(OSI) is False

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
        assert await repo.has_abstracts(OSI) is False
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
