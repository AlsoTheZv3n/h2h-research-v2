"""Drug and fact persistence."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, func, or_, select
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

# maturity is a native enum, so ordering by the column directly sorts alphabetically
# (full, index_only, partial) -- which is not the order anyone means. This ranks it so
# a complete brief comes first, which is the default sort: the drugs a reader can
# explore right now, and which load instantly, belong at the top.
_MATURITY_RANK = case(
    (Drug.maturity == DataMaturity.FULL, 3),
    (Drug.maturity == DataMaturity.PARTIAL, 2),
    else_=1,  # index_only
)

# The columns the overview's headers can sort by. Anything not here falls back to the
# data-completeness rank rather than erroring on a bad ?sort= value.
_SORT_COLUMNS = {
    "data": _MATURITY_RANK,
    "name": Drug.pref_name,
    "phase": Drug.max_phase,
    "target": Drug.primary_target,
    "indication": Drug.primary_indication,
}


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
        q: str | None = None,
        target: str | None = None,
        max_phase: int | None = None,
        modality: str | None = None,
        maturity: DataMaturity | None = None,
        has_target: bool | None = None,
        sort: str = "data",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Drug], int]:
        """One page of the overview, filtered and sorted in SQL, plus the total.

        Filter -> sort -> page, all in Postgres, composed with the count. The catalog
        is ~3,900 rows; sending them all to the client to filter there would be both
        slow and a lie about "the DB is the only thing the website reads". The total is
        counted over the *filtered* set, not len()'d over the page -- the spike shipped
        the bug where a page length read as the total and osimertinib's 383 trials
        showed as 100.
        """
        filters = []
        if q:
            # Partial and case-insensitive, across the three things someone would
            # actually type into a search box. An exact match was unusable: people
            # type one character at a time, so every keystroke but the last returned
            # nothing, which reads as a broken field rather than a strict one.
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    Drug.pref_name.ilike(pattern),
                    Drug.chembl_id.ilike(pattern),
                    Drug.primary_target.ilike(pattern),
                )
            )
        if target:
            # Exact-but-case-insensitive: this one is a facet ("show me the KRAS
            # programs"), not a search box, and it is set from a known value.
            filters.append(func.lower(Drug.primary_target) == target.strip().lower())
        if max_phase is not None:
            filters.append(Drug.max_phase >= max_phase)
        if modality:
            filters.append(func.lower(Drug.drug_type) == modality.strip().lower())
        if maturity is not None:
            filters.append(Drug.maturity == maturity)
        if has_target is not None:
            # "Has an annotated target" vs "does not". A real facet: many catalog rows
            # have no target resolved yet, and letting the reader exclude them is the
            # difference between a findable table and a wall.
            filters.append(
                Drug.primary_target.isnot(None) if has_target else Drug.primary_target.is_(None)
            )

        total = await self.session.scalar(select(func.count()).select_from(Drug).where(*filters))

        column = _SORT_COLUMNS.get(sort, _MATURITY_RANK)
        ordered = (column.desc() if order == "desc" else column.asc()).nullslast()
        rows = await self.session.execute(
            select(Drug)
            .where(*filters)
            # chembl_id last as a stable tiebreaker: every other sort key is nullable
            # or non-unique, so without it tied rows have no defined order. Postgres may
            # then order them differently per query, and since LIMIT/OFFSET is applied
            # per query, a paging client sees one drug twice and never sees another --
            # while `total` stays correct. A trustworthy count over a lossy list.
            .order_by(ordered, Drug.chembl_id)
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
