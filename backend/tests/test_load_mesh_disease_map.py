"""The MeSH-id -> MONDO loader (#44): mirrors the derived CSV into the table for the PubTator
disease join."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.load_mesh_disease_map import _rows, load
from backend.models import MeshDiseaseMap
from backend.services.mesh_map import load_mesh_map

_HEADER = "mesh_id,mondo_id,mondo_label\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "mesh.csv"
    p.write_text(_HEADER + body, encoding="utf-8")
    return p


class TestLoadMeshDiseaseMap:
    async def test_loads_the_real_csv_and_a_known_bridge_resolves(
        self, session: AsyncSession
    ) -> None:
        n = await load(session)
        await session.commit()
        assert n > 0
        total = await session.scalar(select(func.count()).select_from(MeshDiseaseMap))
        assert total == n

        # NSCLC's MeSH id (D002289) bridges to our catalog MONDO -- the join PubTator uses.
        mmap = await load_mesh_map(session)
        assert mmap["D002289"] == ("MONDO_0005233", "non-small cell lung carcinoma")

    async def test_reload_is_idempotent(self, session: AsyncSession) -> None:
        first = await load(session)
        await session.commit()
        again = await load(session)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(MeshDiseaseMap))
        assert first == again == total

    def test_a_duplicate_mesh_id_is_refused(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "D000001,MONDO_1,a\nD000001,MONDO_2,b\n")
        with pytest.raises(ValueError, match="duplicate mesh_id"):
            _rows(path)

    def test_a_missing_mondo_is_named(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "D000001,,label but no mondo\n")
        with pytest.raises(ValueError, match="mondo_id"):
            _rows(path)
