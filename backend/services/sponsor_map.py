"""Load the curated raw->canonical sponsor map from the DB for the trial-reality source.

Returns a plain dict {raw_name: canonical_name}. The trial-reality source normalises each trial's
lead-sponsor string through it before counting: `canonical = sponsor_map.get(raw, raw)`, so an
uncurated string (mostly already-distinct academic centres) normalises to itself. Aggregate counts
are then labelled `sponsors_normalised` so a reader knows subsidiaries were merged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import SponsorNormalisation

# raw_name -> canonical_name
SponsorMap = dict[str, str]


async def load_sponsor_map(session: AsyncSession) -> SponsorMap:
    rows = (await session.execute(select(SponsorNormalisation))).scalars().all()
    return {r.raw_name: r.canonical_name for r in rows}
