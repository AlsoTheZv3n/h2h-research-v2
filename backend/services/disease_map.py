"""Resolve a catalog cancer to an external source category (Eurostat / SEER) -- by MONDO id
and ontology ancestry ONLY, never by name string.

The resolution is the load-bearing half of Gate 1. A catalog cancer is granular; a source
category is broad. Resolution says which of three things is true, and -- crucially -- WHICH
ENTITY the source's numbers actually describe, so a specific page can never pass off a
broader entity's figures as its own:

  exact    the cancer IS the mapped category (breast cancer -> C50).
  rollup   the cancer is NARROWER; the figures describe the mapped ANCESTOR entity, whose
           id + label are returned so the UI can name it ("lung cancer -- broader than NSCLC").
  unmapped no ontology path -- the honest "not available for this cancer" state, a property
           of the mapping, never a data outage.

`resolve` is a pure function over ids + ancestors; the source map and the mapped ids'
ancestors are supplied by the caller (loaded from the DB / fetched from Open Targets by the
worker). No text comparison enters this path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DiseaseSourceMap

# One source's crosswalk, keyed by the MONDO entity: mondo_id -> (source_code, source_label).
SourceMap = dict[str, tuple[str, str]]


class MatchType(StrEnum):
    EXACT = "exact"
    ROLLUP = "rollup"
    # The honest "not available for this cancer": no ontology path to any mapped category.
    # A property of the mapping, kept distinct from empty / source_failed / not_analyzed.
    UNMAPPED = "unmapped"


@dataclass(frozen=True)
class Resolution:
    match_type: MatchType
    # For exact/rollup: the entity the source's numbers describe, and how to name it.
    target_mondo: str | None = None
    source_code: str | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        # A rollup (or exact) that cannot name its target is the whole failure this gate
        # exists to prevent -- broader figures shown as the specific cancer's. Forbid it at
        # construction so it can never be served.
        if self.match_type is not MatchType.UNMAPPED and not (
            self.target_mondo and self.source_label
        ):
            raise ValueError(
                f"{self.match_type.value} resolution must carry its target entity + label"
            )

    @property
    def available(self) -> bool:
        return self.match_type is not MatchType.UNMAPPED


UNMAPPED = Resolution(MatchType.UNMAPPED)


def resolve(
    cancer_mondo: str,
    cancer_ancestors: Sequence[str],
    source_map: SourceMap,
    mapped_ancestors: dict[str, frozenset[str]],
) -> Resolution:
    """Resolve one cancer against one source, by ancestry alone.

    `source_map`      mondo_id -> (source_code, source_label) for a single source.
    `mapped_ancestors` mondo_id -> the mapped ids that are its ancestors, used to pick the
                      CLOSEST hit when a source nests categories (SEER: leukaemia is an
                      ancestor of AML). Non-nested sources never need it.

    Contract for `mapped_ancestors` (the load-bearing assumption of the whole gate). The
    caller must supply the TRANSITIVE ancestor set in the correct direction -- for each mapped
    id, every mapped id that is broader than it (Open Targets `disease.ancestors` is already
    transitive). Closest-wins is only as correct as this dict:
      - miss a nested pair and two hits that should collapse stay separate -> a resolvable
        cancer degrades to a silent UNMAPPED (coverage loss, never a wrong entity);
      - record the direction backwards and a cancer rolls up to the BROADER category -- the
        exact "specific page shows broader figures" failure this gate exists to prevent.
    Fail safe: incompleteness costs coverage; only a reversed edge mis-resolves. The worker
    that computes this dict must therefore take ancestors straight from OT, never invert them.
    """
    if cancer_mondo in source_map:  # the cancer itself is a mapped category
        code, label = source_map[cancer_mondo]
        return Resolution(MatchType.EXACT, cancer_mondo, code, label)

    hits = {a for a in cancer_ancestors if a in source_map}
    if not hits:
        return UNMAPPED

    # Closest wins: drop any hit that is an ANCESTOR of another hit -- keep the most specific.
    # (leukaemia when AML is also a hit is broader, so leukaemia is dropped.)
    leaves = [
        h
        for h in hits
        if not any(h in mapped_ancestors.get(o, frozenset()) for o in hits if o != h)
    ]
    if len(leaves) == 1:
        code, label = source_map[leaves[0]]
        return Resolution(MatchType.ROLLUP, leaves[0], code, label)
    # 0 leaves (cannot happen with a non-empty DAG) or >1 incomparable leaves: a genuine tie
    # between unrelated categories. No silent tie-break -- honestly unmapped.
    return UNMAPPED


async def load_source_maps(session: AsyncSession) -> dict[str, SourceMap]:
    """Load the crosswalk from the DB, grouped by source: {source: {mondo_id: (code, label)}}.
    Unmappable rows (mondo_id NULL) are skipped -- they are recorded, not resolution targets."""
    rows = (await session.execute(select(DiseaseSourceMap))).scalars().all()
    out: dict[str, SourceMap] = {}
    for r in rows:
        if r.mondo_id:
            out.setdefault(r.source, {})[r.mondo_id] = (r.source_code, r.source_label)
    return out
