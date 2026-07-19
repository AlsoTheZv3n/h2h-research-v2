"""Load the committed demo fixture into the database.

Real rows from a real ingest -- osimertinib (a full brief), the ADC (the biologic
case), sotorasib and adagrasib -- captured once and committed. This is not synthetic
data; it is what the adapters actually returned.

It exists because the honest path takes an hour. ChEMBL answers in tens of seconds
and fails about a third of the time, so a new checkout that wants to *see* the thing,
and a CI run that wants to test the UI, should not have to negotiate with it. The
ingestion path is proven separately: `backend/tests/test_enrich.py` drives the real
adapters into a real database.

What this does NOT prove is the network hop -- so never let it stand in for
enrichment when the question is "does the pipeline work".

Run:  docker compose exec api python -m backend.ingestion.seed_demo
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.base import utcnow
from backend.ingestion.load_disease_map import load as load_disease_map

logger = logging.getLogger(__name__)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "demo.json"


async def seed(session: AsyncSession, *, fixture: Path = FIXTURE) -> tuple[int, int]:
    """Insert the fixture. Idempotent: upserts, so re-running is a no-op."""
    payload: dict[str, Any] = json.loads(fixture.read_text())
    now = utcnow()

    # last_enriched_at is stamped only for drugs that actually carry facts. A catalog-only
    # row (the scoping demo's atorvastatin has zero facts) must keep it NULL -- "never
    # enriched" -- or it asserts an enrichment that never happened, the exact
    # never-asked-vs-asked collapse the model's last_enriched_at exists to prevent.
    enriched_ids = {fact["drug_chembl_id"] for fact in payload["facts"]}

    for drug in payload["drugs"]:
        await session.execute(
            text(
                """
                INSERT INTO drug (chembl_id, pref_name, smiles, mw, alogp, hbd, hba, psa,
                                  ro5_violations, drug_type, max_phase, primary_target,
                                  target_class, primary_indication, maturity, in_scope,
                                  last_enriched_at)
                VALUES (:chembl_id, :pref_name, :smiles, :mw, :alogp, :hbd, :hba, :psa,
                        :ro5_violations, :drug_type, :max_phase, :primary_target,
                        :target_class, :primary_indication, CAST(:maturity AS data_maturity),
                        :in_scope, :last_enriched)
                ON CONFLICT (chembl_id) DO UPDATE SET
                    pref_name = excluded.pref_name,
                    smiles = excluded.smiles,
                    maturity = excluded.maturity,
                    primary_target = excluded.primary_target,
                    target_class = excluded.target_class,
                    in_scope = excluded.in_scope,
                    last_enriched_at = excluded.last_enriched_at
                """
            ),
            {**drug, "last_enriched": now if drug["chembl_id"] in enriched_ids else None},
        )

    for fact in payload["facts"]:
        await session.execute(
            text(
                """
                INSERT INTO fact (drug_chembl_id, key, source, value, status, source_url,
                                  retrieved_at, error, confidence)
                VALUES (:drug_chembl_id, :key, :source, CAST(:value AS jsonb),
                        CAST(:status AS fact_status), :source_url, :now, :error, :confidence)
                ON CONFLICT (drug_chembl_id, key, source) DO UPDATE SET
                    value = excluded.value,
                    status = excluded.status,
                    error = excluded.error,
                    retrieved_at = excluded.retrieved_at
                """
            ),
            {
                **fact,
                # value is JSONB and NULL must stay SQL NULL, not the JSON scalar
                # `null` -- the CHECK constraints compare against IS NULL, and a
                # JSON null sails straight past them.
                "value": None if fact["value"] is None else json.dumps(fact["value"]),
                "now": now,
            },
        )

    await session.commit()
    return len(payload["drugs"]), len(payload["facts"])


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with get_sessionmaker()() as session:
        drugs, facts = await seed(session)
        # The disease source->MONDO crosswalk is reference data, not a demo fixture, but this is
        # the DB-setup hook every environment runs -- so load it here (idempotent) so the
        # epidemiology and survival sources can actually resolve a cancer to Eurostat/SEER
        # rather than reporting everything "not available" against an empty table.
        crosswalk = await load_disease_map(session)
        await session.commit()
    print(f"seeded {drugs} drugs, {facts} facts, {crosswalk} disease-map rows from {FIXTURE.name}")


if __name__ == "__main__":
    asyncio.run(main())
