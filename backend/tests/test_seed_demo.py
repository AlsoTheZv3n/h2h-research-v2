"""The demo fixture seeder, run against a real database.

The committed demo fixture is what CI's e2e stack and a fresh checkout see, so its
honest states have to survive seeding -- in particular last_enriched_at, which must
stay NULL ("never enriched") for a catalog-only row and be set only for drugs that
actually carry facts.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.seed_demo import seed
from backend.models import Drug


async def test_a_factless_catalog_row_is_seeded_as_never_enriched(session: AsyncSession) -> None:
    drugs, facts = await seed(session)
    assert drugs == 7 and facts > 0

    # Atorvastatin: the scoping demo row, out of scope and carrying zero facts. It was
    # never enriched, so last_enriched_at must be NULL -- stamping it "enriched today"
    # would assert an enrichment that never happened (and would make the pre-warmer skip
    # it as done). This is the honest state the seeder must not collapse.
    statin = await session.get(Drug, "CHEMBL393220")
    assert statin is not None
    await session.refresh(statin)
    assert statin.in_scope is False
    assert statin.last_enriched_at is None

    # A drug that does carry facts is genuinely enriched, and IS stamped.
    osimertinib = await session.get(Drug, "CHEMBL3353410")
    assert osimertinib is not None
    await session.refresh(osimertinib)
    assert osimertinib.last_enriched_at is not None
