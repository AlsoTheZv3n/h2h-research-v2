"""R4-2: the drug->target relation and the landscape's catalog-link, joined on Ensembl id.

The whole point of this join is that it uses the stable Ensembl gene id, never the
alias-prone approvedSymbol -- a symbol match that is wrong looks exactly like one that is
right. And catalog absence is only ever a missing *link*, never the target's drugged status
(that comes from Open Targets, in the fact) -- collapsing the two would resurrect None-vs-0
in the highest-stakes cell.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DataMaturity
from backend.repositories.cancers import CancerRepository
from backend.repositories.drugs import DrugRepository


async def _drug_on(session: AsyncSession, chembl_id: str, ensembl_ids: list[str]) -> None:
    repo = DrugRepository(session)
    await repo.upsert_drug(chembl_id, pref_name=chembl_id, maturity=DataMaturity.INDEX_ONLY)
    await repo.sync_drug_targets(chembl_id, ensembl_ids)


class TestDrugTarget:
    async def test_sync_replaces_the_target_set_rather_than_accreting(
        self, session: AsyncSession
    ) -> None:
        drugs = DrugRepository(session)
        cancers = CancerRepository(session)
        await drugs.upsert_drug("CHEMBL_A", maturity=DataMaturity.INDEX_ONLY)
        await drugs.sync_drug_targets("CHEMBL_A", ["ENSG1", "ENSG2"])
        await session.commit()
        assert await cancers.catalog_drug_for_targets(["ENSG1", "ENSG2"]) == {
            "ENSG1": "CHEMBL_A",
            "ENSG2": "CHEMBL_A",
        }
        # Re-enrichment gives a different set: the old target is DROPPED, not kept beside the
        # new one -- so a drug that stopped acting on ENSG1 no longer links from it.
        await drugs.sync_drug_targets("CHEMBL_A", ["ENSG2", "ENSG3"])
        await session.commit()
        assert await cancers.catalog_drug_for_targets(["ENSG1"]) == {}
        assert await cancers.catalog_drug_for_targets(["ENSG3"]) == {"ENSG3": "CHEMBL_A"}

    async def test_catalog_link_joins_on_ensembl_never_symbol(self, session: AsyncSession) -> None:
        await _drug_on(session, "CHEMBL_EGFR1", ["ENSG00000146648"])  # EGFR, by its Ensembl id
        await session.commit()
        repo = CancerRepository(session)
        # The Ensembl id matches -> a link.
        assert await repo.catalog_drug_for_targets(["ENSG00000146648"]) == {
            "ENSG00000146648": "CHEMBL_EGFR1"
        }
        # The SYMBOL does not: the relation keys on the stable id only, so the alias-prone
        # "EGFR" matches nothing. This is the guard against a renamed symbol making a real
        # link vanish or a wrong one appear -- introduce symbol matching and this goes red.
        assert await repo.catalog_drug_for_targets(["EGFR"]) == {}
        # An unrelated Ensembl id -> absent, an honest "no link", never a spurious one.
        assert await repo.catalog_drug_for_targets(["ENSG00000133703"]) == {}

    async def test_catalog_link_is_a_stable_pick_when_several_drugs_share_a_target(
        self, session: AsyncSession
    ) -> None:
        # Two catalog drugs on one target -> ONE stable link (lexically smallest id), not a
        # planner-dependent pick that could differ request to request.
        await _drug_on(session, "CHEMBL_ZZZ", ["ENSG_SHARED"])
        await _drug_on(session, "CHEMBL_AAA", ["ENSG_SHARED"])
        await session.commit()
        result = await CancerRepository(session).catalog_drug_for_targets(["ENSG_SHARED"])
        assert result == {"ENSG_SHARED": "CHEMBL_AAA"}

    async def test_empty_target_list_is_no_query_and_no_link(self, session: AsyncSession) -> None:
        assert await CancerRepository(session).catalog_drug_for_targets([]) == {}
