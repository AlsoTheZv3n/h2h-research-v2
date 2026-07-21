"""Load the curated MONDO -> cBioPortal-study crosswalk from the DB for the enrichment worker.

The twin of disease_map.load_source_maps, for the cbioportal_study_map table. Returns a plain
dict {mondo_id: (study_id, source_label)} keyed by the catalog cancer -- attachment is EXACT MONDO
match (no rollup: a molecular profile is subtype-specific). Only redistributable rows
(commercial_ok) are returned: the licence whitelist is enforced again here, so even a row that
slipped past the loader guard cannot reach a fetch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CBioPortalStudyMap

# mondo_id -> (study_id, source_label)
StudyMap = dict[str, tuple[str, str]]


async def load_study_map(session: AsyncSession) -> StudyMap:
    rows = (await session.execute(select(CBioPortalStudyMap))).scalars().all()
    return {r.mondo_id: (r.study_id, r.source_label) for r in rows if r.commercial_ok}
