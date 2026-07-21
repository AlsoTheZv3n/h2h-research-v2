"""Load the MeSH-id -> MONDO map from the DB for the PubTator source.

Returns {mesh_id: (mondo_id, mondo_label)}. The PubTator source resolves an extracted disease's
MeSH id through it to decide whether the disease is one our catalog holds (link it) or not (an
unlinked extracted mention). Join by ID -- never by the disease name string.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import MeshDiseaseMap

# mesh_id -> (mondo_id, mondo_label)
MeshMap = dict[str, tuple[str, str]]


async def load_mesh_map(session: AsyncSession) -> MeshMap:
    rows = (await session.execute(select(MeshDiseaseMap))).scalars().all()
    return {r.mesh_id: (r.mondo_id, r.mondo_label) for r in rows}
