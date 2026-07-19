"""Drug and fact persistence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import FactStatus, SourceRecord
from backend.models import DataMaturity, Drug, DrugTarget, FactRow
from backend.repositories.change_feed import log_fact_changes

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

# The facet value that means "no class recorded", mapped to target_class IS NULL. A
# named sentinel rather than a bare magic string so the API, the repo and the tests
# all agree on the one token that carries this meaning across the wire.
UNCLASSIFIED = "unclassified"

# The columns the overview's headers can sort by. Anything not here falls back to the
# data-completeness rank rather than erroring on a bad ?sort= value.
_SORT_COLUMNS = {
    "data": _MATURITY_RANK,
    "name": Drug.pref_name,
    "phase": Drug.max_phase,
    "target": Drug.primary_target,
    "class": Drug.target_class,
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
        # Log real value/status changes before the upsert overwrites the previous value.
        await log_fact_changes(
            self.session,
            entity_type="drug",
            entity_id=chembl_id,
            model=FactRow,
            id_col=FactRow.drug_chembl_id,
            facts=record.facts,
        )
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

    def _filters(
        self,
        *,
        q: str | None = None,
        target: str | None = None,
        max_phase: int | None = None,
        modality: str | None = None,
        maturity: DataMaturity | None = None,
        has_target: bool | None = None,
        target_class: str | None = None,
        include_out_of_scope: bool = False,
        exclude: frozenset[str] = frozenset(),
    ) -> list[ColumnElement[bool]]:
        """The overview's WHERE clauses, as a list, shared by the listing and the facet counts.

        `exclude` names facets whose own clause to drop: a per-facet count is over every OTHER
        active filter, so an option's count reads as "what selecting it would give" and a facet
        with a current selection still shows all its options. The scope clause is NOT a facet and
        is never excluded -- it widens to include out-of-scope drugs rather than narrowing to a
        subset, so counting a facet "as if unselected" must not also drop the scope boundary.
        """
        filters: list[ColumnElement[bool]] = []
        if q and "q" not in exclude:
            # Partial and case-insensitive, across the three things someone would actually type
            # into a search box. An exact match was unusable: people type one character at a time,
            # so every keystroke but the last returned nothing, which reads as broken not strict.
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    Drug.pref_name.ilike(pattern),
                    Drug.chembl_id.ilike(pattern),
                    Drug.primary_target.ilike(pattern),
                )
            )
        if target and "target" not in exclude:
            # Exact-but-case-insensitive: a facet ("show me the KRAS programs"), set from a value.
            filters.append(func.lower(Drug.primary_target) == target.strip().lower())
        if max_phase is not None and "max_phase" not in exclude:
            filters.append(Drug.max_phase >= max_phase)
        if modality and "modality" not in exclude:
            filters.append(func.lower(Drug.drug_type) == modality.strip().lower())
        if maturity is not None and "maturity" not in exclude:
            filters.append(Drug.maturity == maturity)
        if has_target is not None and "has_target" not in exclude:
            # "Has an annotated target" vs "does not". A real facet: many catalog rows have no
            # target resolved yet, and excluding them is the difference between a findable table
            # and a wall.
            filters.append(
                Drug.primary_target.isnot(None) if has_target else Drug.primary_target.is_(None)
            )
        if target_class and "target_class" not in exclude:
            # "unclassified" is the facet's name for target_class IS NULL -- the rows with no class
            # recorded, a real selectable group. Every other value is an exact family match.
            if target_class.strip().lower() == UNCLASSIFIED:
                filters.append(Drug.target_class.is_(None))
            else:
                filters.append(func.lower(Drug.target_class) == target_class.strip().lower())
        if not include_out_of_scope:
            # The default catalog is oncology. `IS NOT FALSE` keeps NULL (not yet judged) and True,
            # hiding only drugs positively marked out of scope -- so an unfinished scoping pass
            # hides nothing it has not actually ruled on.
            filters.append(Drug.in_scope.isnot(False))
        return filters

    async def list_drugs(
        self,
        *,
        q: str | None = None,
        target: str | None = None,
        max_phase: int | None = None,
        modality: str | None = None,
        maturity: DataMaturity | None = None,
        has_target: bool | None = None,
        target_class: str | None = None,
        include_out_of_scope: bool = False,
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
        filters = self._filters(
            q=q,
            target=target,
            max_phase=max_phase,
            modality=modality,
            maturity=maturity,
            has_target=has_target,
            target_class=target_class,
            include_out_of_scope=include_out_of_scope,
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

    async def facet_counts(
        self,
        *,
        q: str | None = None,
        target: str | None = None,
        max_phase: int | None = None,
        modality: str | None = None,
        maturity: DataMaturity | None = None,
        has_target: bool | None = None,
        target_class: str | None = None,
        include_out_of_scope: bool = False,
    ) -> dict[str, list[tuple[str, int]]]:
        """Per-facet option counts for the overview: for each categorical/boolean facet, how many
        drugs match every OTHER active filter, grouped by that facet's values (its own clause
        excluded, so an option's count is what selecting it would give and a facet keeps all its
        options while one is chosen). The free-text search and the cumulative phase range are not
        enumerable this way, so they carry no counts. Returns {facet: [(value, count), ...]}.
        """

        async def grouped(facet: str, col: Any) -> list[tuple[Any, int]]:
            filters = self._filters(
                q=q,
                target=target,
                max_phase=max_phase,
                modality=modality,
                maturity=maturity,
                has_target=has_target,
                target_class=target_class,
                include_out_of_scope=include_out_of_scope,
                exclude=frozenset({facet}),
            )
            rows = await self.session.execute(
                select(col, func.count())
                .where(*filters)
                .group_by(col)
                .order_by(func.count().desc())
            )
            return [(v, int(n)) for v, n in rows.all()]

        return {
            # Raw drug_type strings; the NULL bucket (no type recorded) is not a selectable one.
            "modality": [(str(v), n) for v, n in await grouped("modality", Drug.drug_type) if v],
            "maturity": [
                (v.value if isinstance(v, DataMaturity) else str(v), n)
                for v, n in await grouped("maturity", Drug.maturity)
                if v is not None
            ],
            # NULL is the real "unclassified" group, folded to the facet's sentinel token.
            "target_class": [
                (v if v is not None else UNCLASSIFIED, n)
                for v, n in await grouped("target_class", Drug.target_class)
            ],
            # A boolean facet -> true/false option counts.
            "has_target": [
                ("true" if v else "false", n)
                for v, n in await grouped("has_target", Drug.primary_target.isnot(None))
            ],
        }

    async def distinct_target_classes(self) -> list[str]:
        """The target-class facet's options: classes actually present, most-common first.

        Data-driven, not a hardcoded enum: which classes exist depends on what has been
        enriched, so a static list would show empty buckets and silently miss any new
        family. NULL is deliberately excluded here -- the facet appends "Unclassified"
        as a fixed final option, because "no class" is always a meaningful choice
        whether or not a given catalog snapshot happens to contain one.
        """
        result = await self.session.execute(
            select(Drug.target_class, func.count())
            # In-scope only, to match the overview's default view: a facet option that
            # returned nothing under the default filter would be a dead end.
            .where(Drug.target_class.isnot(None), Drug.in_scope.isnot(False))
            .group_by(Drug.target_class)
            .order_by(func.count().desc(), Drug.target_class)
        )
        return [row[0] for row in result.all()]

    async def sync_drug_targets(self, chembl_id: str, ensembl_ids: Sequence[str]) -> None:
        """Replace a drug's target set with the Ensembl ids it currently acts on.

        Delete-then-insert, so re-enrichment reflects the drug's current mechanisms rather
        than accreting stale ones. The caller must gate on the target_ids fact NOT being
        source_failed -- an outage must never reach here, because a cleared set here means
        the measured truth "these are the targets" (an empty list = "no targets annotated"),
        never "we could not look". Joining is by Ensembl id only; no symbol ever enters.
        """
        await self.session.execute(delete(DrugTarget).where(DrugTarget.drug_chembl_id == chembl_id))
        for eid in dict.fromkeys(ensembl_ids):  # de-dup, keep first-seen order
            self.session.add(DrugTarget(drug_chembl_id=chembl_id, target_ensembl_id=eid))

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
