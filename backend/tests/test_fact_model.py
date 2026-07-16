"""The core distinction: None (not measured) is not 0 (measured, nothing found).

These tests exist because the spike shipped this bug twice, in both directions:
first an outage read as "no data", then a partial failure discarded data we had.
They pin the contract at the type level and at the database level.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import Fact, FactStatus, SourceRecord, fact, failed
from backend.models import DataMaturity
from backend.repositories import DrugRepository
from backend.repositories.drugs import classify_maturity


class TestFactClassification:
    def test_zero_is_a_measurement_not_a_failure(self) -> None:
        """0 trials is a finding about the drug, not about our pipeline."""
        f = fact(0, "clinicaltrials")
        assert f.status is FactStatus.EMPTY
        assert f.value == 0
        assert f.error is None

    def test_failure_carries_no_value_and_names_a_reason(self) -> None:
        f = failed("chembl", "500 Internal Server Error")
        assert f.status is FactStatus.SOURCE_FAILED
        assert f.value is None
        assert "500" in (f.error or "")

    def test_a_value_is_ok(self) -> None:
        f = fact(57, "chembl")
        assert f.status is FactStatus.OK
        assert f.value == 57

    @pytest.mark.parametrize("empty_value", [None, 0, [], "", {}])
    def test_empty_shapes_are_all_measurements(self, empty_value: object) -> None:
        assert fact(empty_value, "src").status is FactStatus.EMPTY

    def test_ok_cannot_be_valueless(self) -> None:
        with pytest.raises(ValueError, match="must carry a value"):
            Fact(value=None, status=FactStatus.OK, source="chembl")

    def test_failed_cannot_carry_a_value(self) -> None:
        """The type refuses the exact bug the spike shipped: a zero standing in for an outage."""
        with pytest.raises(ValueError, match="cannot carry a value"):
            Fact(value=0, status=FactStatus.SOURCE_FAILED, source="chembl")


class TestPersistence:
    async def test_record_round_trips_with_all_three_statuses(self, session: AsyncSession) -> None:
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL4535757", pref_name="SOTORASIB")
        record = SourceRecord(
            source="chembl",
            query="sotorasib",
            ok=True,
            facts={
                "smiles": fact("CC1=CC=CC=C1", "chembl", source_url="https://example.org/x"),
                "n_ic50": fact(0, "chembl"),
                "moa": failed("chembl", "mechanism: 500 Internal Server Error"),
            },
        )
        await repo.save_record("CHEMBL4535757", record)
        await session.commit()

        rows = {r.key: r for r in await repo.facts_for("CHEMBL4535757")}

        assert rows["smiles"].status is FactStatus.OK
        assert rows["smiles"].value == "CC1=CC=CC=C1"

        # The whole point: both are NULL-ish, and they still say different things.
        assert rows["n_ic50"].status is FactStatus.EMPTY
        assert rows["n_ic50"].value == 0

        assert rows["moa"].status is FactStatus.SOURCE_FAILED
        assert rows["moa"].value is None
        assert "500" in (rows["moa"].error or "")

    async def test_a_missing_value_is_sql_null_not_json_null(self, session: AsyncSession) -> None:
        """A failed fact stores SQL NULL, not the JSON scalar `null`.

        SQLAlchemy encodes Python None into JSONB as `null` by default -- a *value*,
        which sails straight past `value IS NULL` and disarms the CHECK constraints.
        Same None, two meanings, one layer below the one this table guards.
        """
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL5")
        await repo.save_record(
            "CHEMBL5",
            SourceRecord("chembl", "x", ok=False, facts={"moa": failed("chembl", "500")}),
        )
        await session.commit()

        kind = await session.scalar(
            sa.text(
                "SELECT CASE WHEN value IS NULL THEN 'sql_null'"
                " ELSE jsonb_typeof(value) END FROM fact WHERE drug_chembl_id = 'CHEMBL5'"
            )
        )
        assert kind == "sql_null", f"expected SQL NULL, got JSONB {kind}"

    async def test_database_rejects_a_failed_fact_with_a_value(self, session: AsyncSession) -> None:
        """The CHECK constraint is the last line of defence.

        Even if some future code path bypasses the Fact type, Postgres refuses to
        store an outage that claims to have measured something.
        """
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL1")
        await session.commit()

        with pytest.raises(sa.exc.IntegrityError):
            await session.execute(
                sa.text(
                    "INSERT INTO fact (drug_chembl_id, key, source, value, status, retrieved_at)"
                    " VALUES ('CHEMBL1', 'n_trials', 'ct', '0'::jsonb, 'source_failed', now())"
                )
            )
            await session.commit()

    async def test_rerun_updates_in_place(self, session: AsyncSession) -> None:
        """The loader is re-run to fill gaps after an outage; it must not duplicate."""
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL2")
        for value in (1, 2):
            await repo.save_record(
                "CHEMBL2",
                SourceRecord("chembl", "x", ok=True, facts={"n_ic50": fact(value, "chembl")}),
            )
        await session.commit()

        rows = await repo.facts_for("CHEMBL2")
        assert len(rows) == 1
        assert rows[0].value == 2

    async def test_two_sources_may_assert_the_same_key(self, session: AsyncSession) -> None:
        """ChEMBL and Open Targets both claim a mechanism; keeping both is the evidence."""
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL3")
        await repo.save_record(
            "CHEMBL3",
            SourceRecord("chembl", "x", ok=True, facts={"moa": fact("KRas inhibitor", "chembl")}),
        )
        await repo.save_record(
            "CHEMBL3",
            SourceRecord(
                "opentargets", "x", ok=True, facts={"moa": fact("KRas inhibitor", "opentargets")}
            ),
        )
        await session.commit()

        rows = await repo.facts_for("CHEMBL3")
        assert {r.source for r in rows} == {"chembl", "opentargets"}

    async def test_a_failed_fetch_never_nulls_out_good_columns(self, session: AsyncSession) -> None:
        """Re-running the loader during a ChEMBL outage must not erase what we had.

        This is learning #3 as a database guarantee: a source_failed fact is not
        allowed to promote itself into the catalog and overwrite a real value.
        """
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL4")
        good = SourceRecord(
            "chembl",
            "x",
            ok=True,
            facts={"smiles": fact("CCO", "chembl"), "mw": fact(46.07, "chembl")},
        )
        await repo.promote_index_columns("CHEMBL4", good)
        await session.commit()

        outage = SourceRecord(
            "chembl",
            "x",
            ok=False,
            facts={"smiles": failed("chembl", "500"), "mw": failed("chembl", "500")},
        )
        await repo.promote_index_columns("CHEMBL4", outage)
        await session.commit()

        drug = await repo.get("CHEMBL4")
        assert drug is not None
        await session.refresh(drug)
        assert drug.smiles == "CCO"
        assert drug.mw == pytest.approx(46.07)


class TestMaturity:
    def test_biologic_without_structure_is_index_only(self) -> None:
        """The ADC appears in the overview, honestly labelled -- not as empty cards."""
        assert classify_maturity("Antibody drug conjugate", None, False) is DataMaturity.INDEX_ONLY

    def test_small_molecule_with_potency_is_full(self) -> None:
        assert classify_maturity("Small molecule", "CCO", True) is DataMaturity.FULL

    def test_structure_without_potency_is_partial(self) -> None:
        assert classify_maturity("Small molecule", "CCO", False) is DataMaturity.PARTIAL
