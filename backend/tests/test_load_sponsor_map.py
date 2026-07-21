"""The sponsor normalisation loader (#39): mirrors the curated CSV into the table, and -- the trap
this map exists to prevent -- keeps Merck KGaA (DE) and Merck & Co / MSD (US) as DISTINCT
canonicals."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.load_sponsor_map import _rows, load
from backend.models import SponsorNormalisation
from backend.services.sponsor_map import load_sponsor_map

_HEADER = "raw_name,canonical_name,note\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "sponsors.csv"
    p.write_text(_HEADER + body, encoding="utf-8")
    return p


class TestLoadSponsorMap:
    async def test_loads_the_real_csv_and_the_two_mercks_stay_distinct(
        self, session: AsyncSession
    ) -> None:
        n = await load(session)
        await session.commit()
        assert n > 0
        total = await session.scalar(select(func.count()).select_from(SponsorNormalisation))
        assert total == n

        smap = await load_sponsor_map(session)
        # A subsidiary rolls up to its parent...
        assert smap["Seagen Inc."] == "Pfizer"
        assert smap["Genentech, Inc."] == "Roche"
        # ...but the two Mercks map to two DIFFERENT canonicals -- never merged.
        us = smap["Merck Sharp & Dohme LLC"]
        de = smap["Merck KGaA, Darmstadt, Germany"]
        assert us != de
        assert "US" in us and ("DE" in de or "Darmstadt" in de)

    async def test_reload_is_idempotent(self, session: AsyncSession) -> None:
        first = await load(session)
        await session.commit()
        again = await load(session)
        await session.commit()
        total = await session.scalar(select(func.count()).select_from(SponsorNormalisation))
        assert first == again == total

    def test_a_duplicate_raw_name_is_refused(self, tmp_path: Path) -> None:
        # A raw string mapping to two canonicals would be silently lost at upsert.
        path = _write(tmp_path, "Acme Onc,Pfizer,\nAcme Onc,Roche,\n")
        with pytest.raises(ValueError, match="duplicate raw_name"):
            _rows(path)

    def test_a_missing_canonical_is_named(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "Acme Onc,,a note but no canonical\n")
        with pytest.raises(ValueError, match="canonical_name"):
            _rows(path)

    def test_commas_in_names_are_parsed_via_csv_quoting(self, tmp_path: Path) -> None:
        # Many real strings carry commas ("Genentech, Inc."); the CSV reader must handle them.
        path = _write(tmp_path, '"Genentech, Inc.",Roche,Roche subsidiary\n')
        rows = _rows(path)
        assert rows == [
            {"raw_name": "Genentech, Inc.", "canonical_name": "Roche", "note": "Roche subsidiary"}
        ]
