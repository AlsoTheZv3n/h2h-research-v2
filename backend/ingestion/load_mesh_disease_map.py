"""Load the derived MeSH-id -> MONDO map from its CSV into the DB.

The CSV (`backend/data/mesh_disease_map.csv`) records MONDO's MeSH cross-references for the catalog
cancers that carry one; this mirrors it into the `mesh_disease_map` table the PubTator source reads
to link an extracted gene->disease relation to our cancer page. Idempotent: re-running upserts each
row (keyed by mesh_id). The twin of the other crosswalk loaders.

Run:  uv run python -m backend.ingestion.load_mesh_disease_map
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.models import MeshDiseaseMap

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "mesh_disease_map.csv"

_REQUIRED = ("mesh_id", "mondo_id", "mondo_label")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            values = {k: (row.get(k) or "").strip() for k in _REQUIRED}
            for col in _REQUIRED:
                if not values[col]:
                    raise ValueError(
                        f"{path.name} line {line_no}: required column '{col}' is empty or missing"
                    )
            mesh = values["mesh_id"]
            if mesh in seen:
                raise ValueError(
                    f"{path.name} line {line_no}: duplicate mesh_id {mesh!r} -- one MONDO per MeSH"
                )
            seen.add(mesh)
            out.append(values)
        return out


async def load(session: AsyncSession, *, path: Path = CSV_PATH) -> int:
    """Upsert every CSV row into mesh_disease_map. Returns the row count loaded."""
    rows = _rows(path)
    for r in rows:
        stmt = insert(MeshDiseaseMap).values(**r)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MeshDiseaseMap.mesh_id],
            set_={"mondo_id": stmt.excluded.mondo_id, "mondo_label": stmt.excluded.mondo_label},
        )
        await session.execute(stmt)
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load the MeSH-id -> MONDO map.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        n = await load(session, path=args.csv)
        await session.commit()
    print(f"loaded {n} mesh_disease_map rows from {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
