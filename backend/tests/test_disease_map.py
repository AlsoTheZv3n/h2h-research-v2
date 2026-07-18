"""The disease source->MONDO crosswalk: the loader mirrors the curated CSV into the table,
and an unmappable category stays NULL (recorded), not dropped."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.load_disease_map import load
from backend.models import DiseaseSourceMap


async def _by_key(session: AsyncSession, source: str, code: str) -> DiseaseSourceMap | None:
    return await session.get(DiseaseSourceMap, (source, code))


class TestLoadDiseaseMap:
    async def test_loads_the_csv_and_keeps_unmappable_rows_null(
        self, session: AsyncSession
    ) -> None:
        n = await load(session)
        await session.commit()
        assert n > 0

        total = await session.scalar(select(func.count()).select_from(DiseaseSourceMap))
        assert total == n  # every row landed

        # A mapped rollup category resolves to the broad MONDO, with a label the UI can use.
        lung = await _by_key(session, "eurostat", "C33_C34")
        assert lung is not None
        assert lung.mondo_id == "MONDO_0008903"
        assert "lung" in lung.source_label.lower()

        # SEER carries an AML-specific site -> exact entity, not a leukaemia rollup.
        aml = await _by_key(session, "seer", "96")
        assert aml is not None
        assert aml.mondo_id == "MONDO_0018874"

        # The ICD grab-bag is recorded UNMAPPABLE (mondo_id NULL) with a reason -- a visible
        # decision, never a silently missing row that would read as "not in the source".
        grab = await _by_key(session, "eurostat", "C88_C90_C96")
        assert grab is not None
        assert grab.mondo_id is None
        assert grab.note and "unmappable" in grab.note.lower()

    async def test_reload_is_idempotent(self, session: AsyncSession) -> None:
        first = await load(session)
        await session.commit()
        again = await load(session)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(DiseaseSourceMap))
        # A second load upserts in place -- no duplicate rows (the PK is source+code).
        assert first == again == total
