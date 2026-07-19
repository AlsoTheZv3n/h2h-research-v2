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

# source_code identifies the row, source_label names the entity for the UI: both must be
# present. mondo_id/note are optional (blank mondo = an explicitly unmappable category).
_REQUIRED = ("source", "source_code", "source_label")


def _rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as f:
        out: list[dict[str, str | None]] = []
        # Header is line 1; enumerate from 2 so an error names the file's actual line.
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            # `.get(k) or ""` tolerates a short/malformed row (DictReader fills missing
            # trailing columns with None) -- a clear ValueError below, never an opaque
            # AttributeError from calling .strip() on that None.
            values = {
                k: (row.get(k) or "").strip()
                for k in ("source", "source_code", "source_label", "mondo_id", "note")
            }
            for col in _REQUIRED:
                if not values[col]:
                    # Catch the data typo HERE, at load, with the line named -- not deep in
                    # per-cancer resolution, where a blank label raises a mid-request 500.
                    raise ValueError(
                        f"{path.name} line {line_no}: required column '{col}' is empty or missing"
                    )
            out.append(
                {
                    "source": values["source"],
                    "source_code": values["source_code"],
                    "source_label": values["source_label"],
                    # Empty cell -> NULL: an unmappable category, not the empty string.
                    "mondo_id": (values["mondo_id"] or None),
                    "note": (values["note"] or None),
                }
            )
        return out


def _assert_unique_mondo_per_source(rows: list[dict[str, str | None]]) -> None:
    # The resolver keys each source's map by mondo_id; two codes mapping to the same mondo
    # within one source would silently overwrite each other there (non-deterministically --
    # the load query has no ORDER BY). Reject it at load instead of losing a category.
    seen: set[tuple[str | None, str | None]] = set()
    for r in rows:
        if r["mondo_id"] is None:
            continue
        key = (r["source"], r["mondo_id"])
        if key in seen:
            raise ValueError(
                f"duplicate mondo {r['mondo_id']} within source {r['source']} -- "
                "one source_code would be silently lost in the resolver"
            )
        seen.add(key)


async def load(session: AsyncSession, *, path: Path = CSV_PATH) -> int:
    """Upsert every CSV row into disease_source_map. Returns the row count loaded."""
    rows = _rows(path)
    _assert_unique_mondo_per_source(rows)
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
