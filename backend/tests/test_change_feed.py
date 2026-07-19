"""The change feed logs a fact's value/status changes -- and only real changes, not the
identical re-fetch the refresh cron does every cycle. That distinction is the whole point:
without it the feed is either empty (never logs) or noise (logs every refresh)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import SourceRecord, fact, failed
from backend.models import DataMaturity, Drug
from backend.repositories.cancers import CancerRepository
from backend.repositories.change_feed import recent_changes
from backend.repositories.drugs import DrugRepository

DISEASE = "MONDO_0005233"
CHEMBL = "CHEMBL_CF"


def _rec(key: str, value: object, *, source: str = "opentargets") -> SourceRecord:
    return SourceRecord(source, "q", ok=True, facts={key: fact(value, source)})


def _rec_failed(key: str, *, source: str = "opentargets") -> SourceRecord:
    return SourceRecord(source, "q", ok=False, facts={key: failed(source, "boom")})


async def _seed_cancer(session: AsyncSession) -> CancerRepository:
    repo = CancerRepository(session)
    await repo.upsert_cancer(DISEASE, name="lung", therapeutic_area=None, n_drugs=0, n_targets=0)
    await session.commit()
    return repo


class TestChangeFeed:
    async def test_a_value_change_logs_exactly_one_event(self, session: AsyncSession) -> None:
        repo = await _seed_cancer(session)
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        # A later enrichment sees a different value.
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 5}))
        await session.commit()

        events = await recent_changes(session, entity_id=DISEASE)
        assert len(events) == 1
        e = events[0]
        assert (e.entity_type, e.key, e.source) == ("cancer", "pipeline", "opentargets")
        assert e.old_value == {"total": 3}
        assert e.new_value == {"total": 5}
        assert (e.old_status, e.new_status) == ("ok", "ok")

    async def test_a_first_insert_logs_nothing(self, session: AsyncSession) -> None:
        repo = await _seed_cancer(session)
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        # Nothing changed -- there was no prior value.
        assert await recent_changes(session, entity_id=DISEASE) == []

    async def test_an_identical_refetch_logs_nothing(self, session: AsyncSession) -> None:
        repo = await _seed_cancer(session)
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        # The refresh cron re-writes the SAME value (retrieved_at moves, the answer does not).
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        assert await recent_changes(session, entity_id=DISEASE) == []

    async def test_a_status_flip_is_a_change_even_ok_to_source_failed(
        self, session: AsyncSession
    ) -> None:
        repo = await _seed_cancer(session)
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        # The source went down on the next attempt: ok -> source_failed, value -> NULL.
        await repo.save_record(DISEASE, _rec_failed("pipeline"))
        await session.commit()

        events = await recent_changes(session, entity_id=DISEASE)
        assert len(events) == 1
        e = events[0]
        assert (e.old_status, e.new_status) == ("ok", "source_failed")
        assert e.old_value == {"total": 3}
        assert e.new_value is None

    async def test_drug_facts_log_under_entity_type_drug(self, session: AsyncSession) -> None:
        session.add(Drug(chembl_id=CHEMBL, maturity=DataMaturity.INDEX_ONLY))
        await session.commit()
        repo = DrugRepository(session)
        await repo.save_record(CHEMBL, _rec("mechanism", "EGFR inhibitor", source="chembl"))
        await session.commit()
        await repo.save_record(CHEMBL, _rec("mechanism", "EGFR/HER2 inhibitor", source="chembl"))
        await session.commit()

        events = await recent_changes(session, entity_type="drug")
        assert len(events) == 1
        assert events[0].entity_id == CHEMBL
        assert events[0].new_value == "EGFR/HER2 inhibitor"

    async def test_recent_changes_is_scoped_and_newest_first(self, session: AsyncSession) -> None:
        repo = await _seed_cancer(session)
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 1}))
        await session.commit()
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 2}))
        await session.commit()
        await repo.save_record(DISEASE, _rec("pipeline", {"total": 3}))
        await session.commit()
        # Two changes (1->2, 2->3), newest first, and scoping to a different entity returns none.
        events = await recent_changes(session, entity_id=DISEASE)
        assert [e.new_value for e in events] == [{"total": 3}, {"total": 2}]
        assert await recent_changes(session, entity_id="MONDO_9999999") == []
