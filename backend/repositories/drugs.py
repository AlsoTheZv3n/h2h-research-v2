"""Drug and fact persistence."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import FactStatus, SourceRecord
from backend.models import DataMaturity, Drug, FactRow

# Index columns the overview reads, and the source that owns each. ChEMBL owns
# structure and physchem; Open Targets owns modality and target annotation.
_CHEMBL_INDEX_FIELDS = (
    "pref_name",
    "smiles",
    "mw",
    "alogp",
    "hbd",
    "hba",
    "psa",
    "ro5_violations",
    "max_phase",
)


class DrugRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, chembl_id: str) -> Drug | None:
        return await self.session.get(Drug, chembl_id)

    async def upsert_drug(self, chembl_id: str, **columns: object) -> Drug:
        """Insert or update a catalog row.

        ON CONFLICT DO UPDATE rather than read-modify-write: the bulk loader is
        re-run to fill gaps after ChEMBL outages, and must stay idempotent under
        concurrent runs without racing itself.
        """
        values = {"chembl_id": chembl_id, **columns}
        stmt = insert(Drug).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in columns}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=[Drug.chembl_id], set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=[Drug.chembl_id])
        await self.session.execute(stmt)
        drug = await self.session.get(Drug, chembl_id)
        assert drug is not None
        return drug

    async def save_record(self, chembl_id: str, record: SourceRecord) -> None:
        """Persist every fact of one source's answer for one drug.

        Facts are written whatever their status -- a `source_failed` row is a fact
        about our pipeline and belongs in the record just as much as a value does.
        Dropping it would leave the reader unable to tell an outage from a real gap,
        which is exactly the failure the spike caught.
        """
        for key, f in record.facts.items():
            stmt = insert(FactRow).values(
                drug_chembl_id=chembl_id,
                key=key,
                source=f.source,
                value=f.value,
                status=f.status,
                source_url=f.source_url,
                retrieved_at=f.retrieved_at,
                error=f.error,
                confidence=f.confidence,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_fact_drug_key_source",
                set_={
                    "value": stmt.excluded.value,
                    "status": stmt.excluded.status,
                    "source_url": stmt.excluded.source_url,
                    "retrieved_at": stmt.excluded.retrieved_at,
                    "error": stmt.excluded.error,
                    "confidence": stmt.excluded.confidence,
                },
            )
            await self.session.execute(stmt)

    async def facts_for(self, chembl_id: str) -> Sequence[FactRow]:
        result = await self.session.execute(
            select(FactRow).where(FactRow.drug_chembl_id == chembl_id).order_by(FactRow.key)
        )
        return result.scalars().all()

    async def list_drugs(
        self,
        *,
        target: str | None = None,
        max_phase: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Drug], int]:
        """One page of the overview, plus the unpaginated total.

        The total is counted, not len()'d: the spike shipped a bug where a page
        length was reported as a total, and osimertinib's 383 trials read as 100.
        """
        filters = []
        if target:
            filters.append(Drug.primary_target == target)
        if max_phase is not None:
            filters.append(Drug.max_phase >= max_phase)

        total = await self.session.scalar(select(func.count()).select_from(Drug).where(*filters))
        rows = await self.session.execute(
            select(Drug)
            .where(*filters)
            # chembl_id last as a tiebreaker: max_phase and pref_name are both
            # nullable, so without it tied rows have no defined order. Postgres may
            # then order them differently per query, and since LIMIT/OFFSET is applied
            # per query, a paging client sees one drug twice and never sees another --
            # while `total` stays correct. A trustworthy count over a lossy list.
            .order_by(Drug.max_phase.desc().nullslast(), Drug.pref_name, Drug.chembl_id)
            .limit(limit)
            .offset(offset)
        )
        return rows.scalars().all(), int(total or 0)

    async def promote_index_columns(self, chembl_id: str, record: SourceRecord) -> None:
        """Copy a ChEMBL record's index columns into the catalog row.

        A `source_failed` fact must never overwrite a good column with NULL:
        re-running the loader during an outage would otherwise erase data we had.

        But everything else promotes, EMPTY included. `fact()` classifies 0 as EMPTY
        ("measured, and the answer is nothing"), and `ro5_violations=0` is a measured
        zero -- the best possible value. Promoting only OK dropped it to NULL, which
        the model reads as "not measured": None != 0, running backwards.
        """
        columns: dict[str, object] = {}
        for key in _CHEMBL_INDEX_FIELDS:
            f = record.facts.get(key)
            if f is not None and f.status is not FactStatus.SOURCE_FAILED:
                columns[key] = f.value
        if columns:
            await self.upsert_drug(chembl_id, **columns)


# ChEMBL's molecule_type values that the small-molecule data model covers. Anything
# else -- Antibody, Protein, Oligonucleotide, Oligosaccharide, Cell, Gene, Enzyme,
# Unknown -- is v2's problem.
SMALL_MOLECULE_TYPES = frozenset({"small molecule"})


def is_small_molecule(drug_type: str | None) -> bool:
    return (drug_type or "").strip().lower() in SMALL_MOLECULE_TYPES


def classify_maturity(drug_type: str | None, smiles: str | None, has_potency: bool) -> DataMaturity:
    """How much of a brief can we actually carry for this drug?

    Honest by construction: a biologic lands in the catalog but says up front that
    there is no structure or binding card to show, instead of rendering empty cards
    that read as missing data.

    Modality decides first, structure second. Testing only `smiles` happened to
    classify biologics correctly -- but by accident, because they usually lack one.
    ChEMBL does carry a SMILES for some peptides and conjugates, and those would have
    been offered the structure and binding cards the contract reserves for small
    molecules. The two fields are read independently from the same payload; nothing
    links them.
    """
    if not is_small_molecule(drug_type):
        return DataMaturity.INDEX_ONLY
    if not smiles:
        # A small molecule ChEMBL has no structure for: in the index, no cards.
        return DataMaturity.INDEX_ONLY
    return DataMaturity.FULL if has_potency else DataMaturity.PARTIAL
