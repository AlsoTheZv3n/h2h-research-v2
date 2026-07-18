"""Load the curated disease source->MONDO crosswalk from its CSV into the DB.

The CSV (`backend/data/disease_source_map.csv`) is the reviewable source of truth; this
mirrors it into the `disease_source_map` table the resolver reads. Idempotent: re-running
upserts each row, so editing the CSV and reloading is safe.

Run:  uv run python -m backend.ingestion.load_disease_map
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
from backend.models import DiseaseSourceMap

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "disease_source_map.csv"


def _rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as f:
        out: list[dict[str, str | None]] = []
        for row in csv.DictReader(f):
            out.append(
                {
                    "source": row["source"].strip(),
                    "source_code": row["source_code"].strip(),
                    "source_label": row["source_label"].strip(),
                    # Empty cell -> NULL: an unmappable category, not the empty string.
                    "mondo_id": (row["mondo_id"].strip() or None),
                    "note": (row["note"].strip() or None),
                }
            )
        return out


async def load(session: AsyncSession, *, path: Path = CSV_PATH) -> int:
    """Upsert every CSV row into disease_source_map. Returns the row count loaded."""
    rows = _rows(path)
    for r in rows:
        stmt = insert(DiseaseSourceMap).values(**r)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DiseaseSourceMap.source, DiseaseSourceMap.source_code],
            set_={
                "source_label": stmt.excluded.source_label,
                "mondo_id": stmt.excluded.mondo_id,
                "note": stmt.excluded.note,
            },
        )
        await session.execute(stmt)
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load the disease source->MONDO crosswalk.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        n = await load(session, path=args.csv)
        await session.commit()
    print(f"loaded {n} disease_source_map rows from {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
