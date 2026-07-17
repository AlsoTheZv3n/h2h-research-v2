"""Abstract persistence and vector search.

The text in this table is never served. See NOTICE.md: NLM does not own these
abstracts and cannot license them onward, so they live here to be embedded and read
by the chat model in-process, and nothing else. Every method below returns either
metadata (pmid, title, journal, year) or text destined for a prompt -- never text
destined for a response body. `backend/tests/test_output_boundary.py` holds the API
to that.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.embeddings import embed_documents
from backend.ingestion.literature import LiteratureRecord
from backend.models import Abstract, DrugAbstract


@dataclass(frozen=True, slots=True)
class RetrievedAbstract:
    """One hit. `text` is prompt-bound; the rest is citation material."""

    pmid: str
    title: str | None
    journal: str | None
    year: int | None
    text: str
    distance: float

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


class LiteratureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_abstracts(self, chembl_id: str) -> bool:
        """Whether this drug's literature has been fetched at all.

        The `not_analyzed` question, one layer down: no rows means nobody looked, and
        that is different from having looked and found nothing.
        """
        stmt = select(DrugAbstract.pmid).where(DrugAbstract.drug_chembl_id == chembl_id).limit(1)
        return (await self.session.execute(stmt)).first() is not None

    async def save(self, chembl_id: str, record: LiteratureRecord) -> int:
        """Store a fetch result. Returns how many abstracts were embedded.

        A failed record writes nothing -- deliberately. Unlike a fact, where an
        outage is itself worth recording and gets a `source_failed` row, this table
        is an index rather than a claim: an absent row means "not indexed", the
        retriever simply finds less, and the next request retries. The drug's *facts*
        are where the outage is on the record.
        """
        if not record.ok or not record.articles:
            return 0

        with_text = [a for a in record.articles if a.text]
        # One batch, one model call, off the event loop. Embedding per article would
        # reload nothing but would pay the per-call overhead 20 times.
        vectors = await embed_documents([a.text or "" for a in with_text])
        by_pmid = {a.pmid: v for a, v in zip(with_text, vectors, strict=True)}

        for article in record.articles:
            stmt = insert(Abstract).values(
                pmid=article.pmid,
                title=article.title,
                text=article.text,
                journal=article.journal,
                year=article.year,
                # None for an article with no abstract -- which the CHECK constraint
                # requires, since a vector with no text behind it would retrieve and
                # then ground an answer on nothing.
                embedding=by_pmid.get(article.pmid),
                retrieved_at=record.retrieved_at,
            )
            # Idempotent: the same PMID surfaces for several drugs, and re-fetching a
            # drug must refresh rather than collide.
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Abstract.pmid],
                    set_={
                        "title": stmt.excluded.title,
                        "text": stmt.excluded.text,
                        "journal": stmt.excluded.journal,
                        "year": stmt.excluded.year,
                        "embedding": stmt.excluded.embedding,
                        "retrieved_at": stmt.excluded.retrieved_at,
                    },
                )
            )

        link = insert(DrugAbstract).values(
            [{"drug_chembl_id": chembl_id, "pmid": a.pmid, "rank": a.rank} for a in record.articles]
        )
        await self.session.execute(
            link.on_conflict_do_update(
                index_elements=[DrugAbstract.drug_chembl_id, DrugAbstract.pmid],
                set_={"rank": link.excluded.rank},
            )
        )
        await self.session.commit()
        return len(with_text)

    async def search(
        self, chembl_id: str, query_vector: list[float], limit: int = 5
    ) -> list[RetrievedAbstract]:
        """The nearest abstracts *for this drug*.

        Filtered by drug first, and that is the whole design. An unfiltered nearest-
        neighbour search over every abstract in the table would happily return a
        beautifully on-topic paper about a different molecule -- and the model, given
        it as context for a question about this one, would have no way to know. The
        structured facts pin the drug; the vectors only choose which of *its* papers
        are relevant to the question.
        """
        distance = Abstract.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(Abstract, distance)
            .join(DrugAbstract, DrugAbstract.pmid == Abstract.pmid)
            .where(
                DrugAbstract.drug_chembl_id == chembl_id,
                # Records with no abstract carry no vector and cannot be ranked;
                # without this they sort as NULL and can lead the results.
                Abstract.embedding.isnot(None),
            )
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            RetrievedAbstract(
                pmid=abstract.pmid,
                title=abstract.title,
                journal=abstract.journal,
                year=abstract.year,
                text=abstract.text or "",
                distance=float(dist),
            )
            for abstract, dist in rows
        ]

    async def forget_drug(self, chembl_id: str) -> None:
        """Drop this drug's links. Orphaned abstracts are left for a sweep."""
        await self.session.execute(
            delete(DrugAbstract).where(DrugAbstract.drug_chembl_id == chembl_id)
        )
        await self.session.commit()
