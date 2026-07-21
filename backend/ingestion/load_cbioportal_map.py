"""Load the curated MONDO -> cBioPortal-study crosswalk from its CSV into the DB.

The CSV (`backend/data/cbioportal_study_map.csv`) is the reviewable source of truth; this
mirrors it into the `cbioportal_study_map` table the alteration-frequency source reads.
Idempotent: re-running upserts each row (keyed by mondo_id), so editing the CSV and reloading
is safe. The twin of load_disease_map, with two extra guards molecular data + the licence
condition demand:

  - one study per mondo (the PK already enforces it; the loader also rejects a duplicate mondo
    in the CSV with a named line, so a copy-paste error is caught at load, not at a silent
    upsert-overwrite);
  - `commercial_ok` must parse to a real boolean, and a row that is not clearly redistributable
    (commercial_ok != true) is REFUSED at load -- the whitelist is enforced here and again in the
    fetch adapter, so a restricted study cannot enter the crosswalk by a typo.

Run:  uv run python -m backend.ingestion.load_cbioportal_map
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
from backend.models import CBioPortalStudyMap

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "cbioportal_study_map.csv"

# Every column but note is required: a row must name its entity, its study, its label and its
# licence status. note (the curation justification) is optional.
_REQUIRED = ("mondo_id", "study_id", "source_label", "commercial_ok")

_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f", ""}


def _parse_bool(raw: str, *, line_no: int, path: Path) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"{path.name} line {line_no}: commercial_ok {raw!r} is not a boolean")


def _rows(path: Path) -> list[dict[str, str | bool | None]]:
    with path.open(newline="", encoding="utf-8") as f:
        out: list[dict[str, str | bool | None]] = []
        seen_mondo: set[str] = set()
        # Header is line 1; enumerate from 2 so an error names the file's actual line.
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            values = {
                k: (row.get(k) or "").strip()
                for k in ("mondo_id", "study_id", "source_label", "commercial_ok", "note")
            }
            for col in _REQUIRED:
                if not values[col]:
                    raise ValueError(
                        f"{path.name} line {line_no}: required column '{col}' is empty or missing"
                    )
            commercial_ok = _parse_bool(values["commercial_ok"], line_no=line_no, path=path)
            if not commercial_ok:
                # The licence whitelist, enforced at load: a study with a commercial-use
                # restriction is not freely redistributable, so it must not enter the crosswalk.
                # Recorded as a hard error (with the line) rather than a silent skip, so a curator
                # sees the row was rejected and why.
                raise ValueError(
                    f"{path.name} line {line_no}: study {values['study_id']!r} has "
                    "commercial_ok=false -- restricted studies must not be listed (ODbL "
                    "per-study commercial restriction); remove the row"
                )
            mondo = values["mondo_id"]
            if mondo in seen_mondo:
                # One canonical study per entity: a second row for the same mondo would silently
                # overwrite the first at upsert. Reject it here, named, so the duplicate is fixed.
                raise ValueError(
                    f"{path.name} line {line_no}: duplicate mondo {mondo} -- one canonical "
                    "study per cancer (samples must not be pooled across cohorts)"
                )
            seen_mondo.add(mondo)
            out.append(
                {
                    "mondo_id": mondo,
                    "study_id": values["study_id"],
                    "source_label": values["source_label"],
                    "commercial_ok": commercial_ok,
                    "note": (values["note"] or None),
                }
            )
        return out


async def load(session: AsyncSession, *, path: Path = CSV_PATH) -> int:
    """Upsert every CSV row into cbioportal_study_map. Returns the row count loaded."""
    rows = _rows(path)
    for r in rows:
        stmt = insert(CBioPortalStudyMap).values(**r)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CBioPortalStudyMap.mondo_id],
            set_={
                "study_id": stmt.excluded.study_id,
                "source_label": stmt.excluded.source_label,
                "commercial_ok": stmt.excluded.commercial_ok,
                "note": stmt.excluded.note,
            },
        )
        await session.execute(stmt)
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load the MONDO -> cBioPortal-study crosswalk.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        n = await load(session, path=args.csv)
        await session.commit()
    print(f"loaded {n} cbioportal_study_map rows from {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
