"""The disease source->MONDO crosswalk: the loader mirrors the curated CSV into the table,
and an unmappable category stays NULL (recorded), not dropped."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.load_disease_map import _rows, load
from backend.models import DiseaseSourceMap
from backend.services.disease_map import load_source_maps

_HEADER = "source,source_code,source_label,mondo_id,note\n"


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

    async def test_seer_survival_sites_extend_to_epi_only_entities(
        self, session: AsyncSession
    ) -> None:
        await load(session)
        await session.commit()
        # Entities that had a Eurostat mortality site but no SEER survival site until the
        # extension -> survival read "not available"; now they resolve to their own SEER site.
        prostate = await _by_key(session, "seer", "66")
        assert prostate is not None and prostate.mondo_id == "MONDO_0008315"
        # Myeloma survival now resolves EXACT to its own site, not through the lymphoma rollup.
        myeloma = await _by_key(session, "seer", "89")
        assert myeloma is not None and myeloma.mondo_id == "MONDO_0009693"
        # Hodgkin is mapped (no leukemia overlap)...
        hodgkin = await _by_key(session, "seer", "83")
        assert hodgkin is not None and hodgkin.mondo_id == "MONDO_0004952"
        # ...but non-Hodgkin lymphoma is deliberately OMITTED: MONDO dual-classifies lymphoid
        # leukemias (CLL, ALL) under BOTH leukemia and NHL, so an NHL site would tie them to
        # UNMAPPED and silently drop their real leukemia survival. Guard against a re-add.
        seer = (await load_source_maps(session))["seer"]
        assert "MONDO_0018908" not in seer  # non-Hodgkin lymphoma
        assert "MONDO_0005059" in seer  # leukemia kept -> CLL/ALL still roll up to survival


class TestLoadSourceMaps:
    async def test_groups_by_source_by_mondo_and_skips_unmappable(
        self, session: AsyncSession
    ) -> None:
        await load(session)
        await session.commit()
        maps = await load_source_maps(session)
        assert set(maps) == {"eurostat", "seer"}
        # keyed by MONDO -> (code, label), per source
        assert maps["eurostat"]["MONDO_0008903"][0] == "C33_C34"  # lung
        assert maps["seer"]["MONDO_0018874"][0] == "96"  # AML exact site
        # Unmappable rows (mondo_id NULL) are NOT resolution targets -> never leak a None key.
        assert all(mondo for src in maps.values() for mondo in src)


class TestLoadValidation:
    """A data typo must be caught HERE, at load, with the offending line named -- never stored
    as an empty string / lost mapping that detonates deep in per-cancer resolution."""

    def test_rejects_a_blank_required_field(self, tmp_path: Path) -> None:
        # Valid code + mondo, but a blank source_label. NOT NULL accepts "" in the DB, so
        # without this guard it would survive to the resolver and raise a mid-request 500
        # (Resolution forbids a target it cannot name). Reject at load, naming the column.
        p = tmp_path / "bad.csv"
        p.write_text(_HEADER + "eurostat,C99,,MONDO_0001234,\n", encoding="utf-8")
        with pytest.raises(ValueError, match="source_label"):
            _rows(p)

    def test_rejects_a_short_row_without_an_opaque_crash(self, tmp_path: Path) -> None:
        # A truncated row leaves trailing columns as None (DictReader fills them). The guard
        # must turn that into a clear ValueError, not an opaque AttributeError from .strip().
        p = tmp_path / "short.csv"
        p.write_text(_HEADER + "eurostat,C99\n", encoding="utf-8")
        with pytest.raises(ValueError):
            _rows(p)

    async def test_rejects_duplicate_mondo_within_a_source(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        # Two codes -> the same MONDO in one source would silently overwrite each other in the
        # resolver's mondo-keyed map (non-deterministically, no ORDER BY). Reject at load.
        p = tmp_path / "dup.csv"
        p.write_text(
            _HEADER
            + "eurostat,C50,Breast,MONDO_0007254,\n"
            + "eurostat,C50X,Breast dup,MONDO_0007254,\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate"):
            await load(session, path=p)

    async def test_same_mondo_in_different_sources_is_allowed(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        # The real CSV maps breast to BOTH eurostat C50 and seer 55 -- the same MONDO across
        # DIFFERENT sources is legitimate (each source keeps its own map) and must NOT trip
        # the duplicate guard, which is per-source.
        p = tmp_path / "cross.csv"
        p.write_text(
            _HEADER + "eurostat,C50,Breast,MONDO_0007254,\n" + "seer,55,Breast,MONDO_0007254,\n",
            encoding="utf-8",
        )
        assert await load(session, path=p) == 2
