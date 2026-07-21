"""Load the curated raw->canonical sponsor normalisation map from its CSV into the DB.

The CSV (`backend/data/sponsor_normalisation.csv`) is the reviewable source of truth; this mirrors
it into the `sponsor_normalisation` table the trial-reality source reads. Idempotent: re-running
upserts each row (keyed by raw_name). The twin of load_disease_map / load_cbioportal_map.

A guard specific to this map: a raw string must never map to two different canonicals (the CSV is
keyed by raw_name, so a duplicate would silently overwrite at upsert) -- rejected here, named.

Run:  uv run python -m backend.ingestion.load_sponsor_map
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
from backend.models import SponsorNormalisation

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "sponsor_normalisation.csv"

_REQUIRED = ("raw_name", "canonical_name")


def _rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as f:
        out: list[dict[str, str | None]] = []
        seen: set[str] = set()
        # Header is line 1; enumerate from 2 so an error names the file's actual line.
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            values = {k: (row.get(k) or "").strip() for k in ("raw_name", "canonical_name", "note")}
            for col in _REQUIRED:
                if not values[col]:
                    raise ValueError(
                        f"{path.name} line {line_no}: required column '{col}' is empty or missing"
                    )
            raw = values["raw_name"]
            if raw in seen:
                raise ValueError(
                    f"{path.name} line {line_no}: duplicate raw_name {raw!r} -- a raw string maps "
                    "to exactly one canonical (a second row would be silently lost at upsert)"
                )
            seen.add(raw)
            out.append(
                {
                    "raw_name": raw,
                    "canonical_name": values["canonical_name"],
                    "note": (values["note"] or None),
                }
            )
        return out


async def load(session: AsyncSession, *, path: Path = CSV_PATH) -> int:
    """Upsert every CSV row into sponsor_normalisation. Returns the row count loaded."""
    rows = _rows(path)
    for r in rows:
        stmt = insert(SponsorNormalisation).values(**r)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SponsorNormalisation.raw_name],
            set_={
                "canonical_name": stmt.excluded.canonical_name,
                "note": stmt.excluded.note,
            },
        )
        await session.execute(stmt)
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load the sponsor normalisation map.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        n = await load(session, path=args.csv)
        await session.commit()
    print(f"loaded {n} sponsor_normalisation rows from {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
