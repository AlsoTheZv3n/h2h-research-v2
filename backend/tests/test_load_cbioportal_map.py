"""The MONDO -> cBioPortal-study crosswalk loader (#43): mirrors the curated CSV into the table,
enforces one study per entity, and REFUSES a study that is not freely redistributable (the licence
whitelist, held in code, not just curation)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.load_cbioportal_map import _rows, load
from backend.models import CBioPortalStudyMap
from backend.services.cbioportal_map import load_study_map

_HEADER = "mondo_id,study_id,source_label,commercial_ok,note\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "map.csv"
    p.write_text(_HEADER + body, encoding="utf-8")
    return p


class TestLoadCBioPortalMap:
    async def test_loads_the_real_csv_and_a_known_row_resolves(self, session: AsyncSession) -> None:
        n = await load(session)
        await session.commit()
        assert n > 0
        total = await session.scalar(select(func.count()).select_from(CBioPortalStudyMap))
        assert total == n  # every row landed

        skcm = await session.get(CBioPortalStudyMap, "MONDO_0005012")
        assert skcm is not None
        assert skcm.study_id == "skcm_tcga_pan_can_atlas_2018"
        assert skcm.commercial_ok is True
        assert skcm.note and "xref-verified" in skcm.note

        # The worker-facing map is keyed by mondo -> (study, label).
        study_map = await load_study_map(session)
        assert study_map["MONDO_0005012"] == (
            "skcm_tcga_pan_can_atlas_2018",
            skcm.source_label,
        )

    async def test_reload_is_idempotent(self, session: AsyncSession) -> None:
        first = await load(session)
        await session.commit()
        again = await load(session)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(CBioPortalStudyMap))
        assert first == again == total

    def test_a_restricted_study_is_refused_at_load(self, tmp_path: Path) -> None:
        # The licence whitelist: commercial_ok=false must never enter the crosswalk.
        path = _write(
            tmp_path,
            "MONDO_1,restricted_study,A restricted cohort,false,commercial restriction\n",
        )
        with pytest.raises(ValueError, match="commercial_ok=false"):
            _rows(path)

    def test_a_duplicate_mondo_is_refused(self, tmp_path: Path) -> None:
        # One canonical study per entity: two rows for one mondo would pool cohorts.
        path = _write(
            tmp_path,
            "MONDO_1,study_a,Cohort A,true,\nMONDO_1,study_b,Cohort B,true,\n",
        )
        with pytest.raises(ValueError, match="duplicate mondo"):
            _rows(path)

    def test_a_non_boolean_commercial_ok_is_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "MONDO_1,study_a,Cohort A,maybe,\n")
        with pytest.raises(ValueError, match="not a boolean"):
            _rows(path)

    def test_a_missing_required_column_is_named(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "MONDO_1,,Cohort A,true,\n")  # empty study_id
        with pytest.raises(ValueError, match="study_id"):
            _rows(path)

    async def test_load_study_map_defensively_drops_a_non_commercial_row(
        self, session: AsyncSession
    ) -> None:
        # Even if a restricted row reached the table (it cannot via the loader), the service layer
        # filters it out -- the whitelist is enforced twice.
        session.add(
            CBioPortalStudyMap(
                mondo_id="MONDO_9",
                study_id="restricted_study",
                source_label="Restricted",
                commercial_ok=False,
                note="planted directly, bypassing the loader guard",
            )
        )
        await session.commit()
        study_map = await load_study_map(session)
        assert "MONDO_9" not in study_map
