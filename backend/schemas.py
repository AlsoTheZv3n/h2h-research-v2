"""API response shapes.

The shape is the product's promise: every fact carries its source and its status,
and an unsupported fact is visibly flagged rather than hidden. A bare `null` in a
response would collapse "we could not reach ChEMBL" into "this drug has no
mechanism" -- the exact confusion the fact model exists to prevent, leaking out
through the API. So facts are envelopes, not values.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.ingestion.base import FactStatus
from backend.models.drug import DataMaturity
from backend.services.briefs import BriefState


class SourcedFact(BaseModel):
    """One fact, with everything needed to trust or distrust it.

    This is what the UI's citation chip and its red "unverified" chip render from.
    """

    value: Any | None = None
    status: FactStatus
    source: str
    source_url: str | None = None
    retrieved_at: datetime
    error: str | None = Field(
        default=None, description="Why the value is missing. Only set when status is source_failed."
    )
    confidence: float | None = None


class DrugSummary(BaseModel):
    """An overview row. Index columns only -- no molecular detail.

    Deliberately unsourced: the overview is a scannable index, and hanging a
    provenance envelope off every cell would make it neither light nor scannable.
    The detail brief is where evidence gets argued.
    """

    chembl_id: str
    pref_name: str | None = None
    drug_type: str | None = None
    max_phase: int | None = None
    primary_target: str | None = None
    target_class: str | None = None
    primary_indication: str | None = None
    maturity: DataMaturity
    updated_at: datetime


class DrugList(BaseModel):
    items: list[DrugSummary]
    total: int
    limit: int
    offset: int


class FacetCount(BaseModel):
    """One facet option and how many rows match it, given the OTHER active filters. The overview
    shows this as a "(N)" beside each option, so a reader sees what a filter would narrow to before
    clicking it. Shared by the drug and cancer overviews; the facets endpoint returns a mapping of
    facet name -> the option counts for that facet."""

    value: str
    count: int


class SynthesisStatement(BaseModel):
    """One page-level synthesis line (Epic C): a derived reading and the anchor id of the block it
    was derived from, so the reader can jump to and check the evidence behind it."""

    text: str
    block: str


class DrugDetail(BaseModel):
    """The evidence brief: the catalog row plus every fact we hold, with provenance."""

    chembl_id: str
    pref_name: str | None = None
    maturity: DataMaturity

    drug_type: str | None = None
    """ChEMBL/Open Targets modality, e.g. "Small molecule", "Antibody drug conjugate"."""

    is_small_molecule: bool = True
    """Whether the small-molecule data model applies.

    Computed here rather than in the UI. index_only has two causes -- a biologic, or
    a small molecule ChEMBL has no structure for -- and 87 catalog drugs are the
    second. A client inferring modality from "index_only and no SMILES" tells the
    reader auranofin is an antibody, which is both false and unsourced. One rule,
    one place.
    """

    has_structure: bool = False
    """Whether there is a structure to draw. A separate axis from modality: a small
    molecule can lack one, and that absence is a measurement, not a class of drug."""

    smiles: str | None = None
    """The canonical SMILES the structure is rendered from -- the catalog column, the
    same value structure.svg draws. Carried here so the detail page has ONE source of
    truth for the structure: it was deriving `has_structure` from the server while
    reading the SMILES text off a separately-fetched ChEMBL fact, which disagree the
    moment ChEMBL fails on a re-fetch (a drawn structure with no formula beneath it, or
    the reverse). has_structure is now just `smiles is not None`, one axis, one place."""

    state: BriefState = BriefState.READY
    """Where this brief is in its life, which is a different axis from any fact's
    status. `not_analyzed` and `enriching` mean we have not looked yet -- neither is
    "we looked and found nothing", and the UI must never render them as such."""

    refreshing: bool = False
    """A READY brief whose facts aged past the freshness window, so a background refresh
    is running (stale-while-revalidate). The facts shown are the stored ones, served
    without waiting; the client may poll and swap in the fresh brief when it lands. This
    is not `enriching` -- there ARE facts, and the reader is not blocked."""

    last_enriched_at: datetime | None = None

    facts: dict[str, list[SourcedFact]] = Field(
        default_factory=dict,
        description=(
            "Keyed by fact name; a list because sources disagree. ChEMBL and Open"
            " Targets both assert a mechanism, and keeping both is the evidence --"
            " picking one would be us making the call, silently."
        ),
    )

    unavailable: list[str] = Field(
        default_factory=list,
        description=(
            "Fact keys where every source failed. Surfaced at the top level so a"
            " client cannot mistake an outage for an absence without looking."
        ),
    )

    synthesis: list[SynthesisStatement] = Field(
        default_factory=list,
        description="The page-level 'so what' (C2): derived threshold statements over the facts, "
        "each linking to its block. Empty when no rule's inputs are present -- computed "
        "server-side so the client renders, never invents, the reading.",
    )


class CancerSummary(BaseModel):
    """A cancer overview row. Index columns only, mirroring DrugSummary.

    n_drugs and n_targets are the two Open Targets counts the seed keeps only cancers
    for; they double as sort keys and as the richness a reader scans the table by.
    """

    disease_id: str
    name: str
    therapeutic_area: str | None = None
    n_drugs: int
    n_targets: int
    last_enriched_at: datetime | None = None
    updated_at: datetime


class CancerList(BaseModel):
    items: list[CancerSummary]
    total: int
    limit: int
    offset: int


class TdlCriterion(BaseModel):
    """One pass/fail (or 'unknown') mark that explains a target's TDL verdict (C3)."""

    label: str
    state: str  # "pass" | "fail" | "unknown"


class TdlVerdict(BaseModel):
    """A Pharos-style Target Development Level (C3): the level, a short reading, and the criteria
    that produced it. Surfaces the Tchem middle -- potent chemical matter with no approved drug."""

    level: str  # "Tclin" | "Tchem" | "Tbio" | "Tdark"
    label: str
    criteria: list[TdlCriterion]


class CancerDetail(BaseModel):
    """A cancer's evidence brief: the catalog row plus every fact we hold, with
    provenance. The disease-side twin of DrugDetail.

    `state` is not_analyzed until enrich_cancer has looked, enriching while it fetches,
    ready once facts are stored -- never "ready with nothing", which would tell the
    reader a cancer has no evidence when the truth is we have not looked.
    """

    disease_id: str
    name: str
    therapeutic_area: str | None = None
    n_drugs: int
    n_targets: int
    last_enriched_at: datetime | None = None

    state: BriefState = BriefState.NOT_ANALYZED

    refreshing: bool = False
    """A READY brief whose facts aged past the freshness window, being revalidated in
    the background (stale-while-revalidate). Stored facts are shown now; poll until it
    clears. Not `enriching` -- there ARE facts, and the reader is not blocked."""

    facts: dict[str, list[SourcedFact]] = Field(
        default_factory=dict,
        description="Keyed by fact name (e.g. 'target_landscape'); a list because "
        "sources can disagree. Each carries its own source, status and provenance.",
    )

    unavailable: list[str] = Field(
        default_factory=list,
        description="Fact keys where every source failed. Hoisted so a client cannot "
        "mistake an outage for an absence without looking.",
    )

    catalog_drug_ids: list[str] = Field(
        default_factory=list,
        description="Of the drugs in the pipeline fact, the ChEMBL ids the catalog holds "
        "-- so the UI links only the ones with a brief and shows the rest as plain text.",
    )

    target_catalog_drug: dict[str, str] = Field(
        default_factory=dict,
        description="For each landscape target's Ensembl id, one catalog drug (ChEMBL id) "
        "that acts on it -- the drugged flag's separate, weaker catalog-link signal. A "
        "target absent here has no drug in OUR catalog, which is NOT 'unexploited' (the "
        "world's answer, from Open Targets); it just gets no link. Joined on Ensembl id.",
    )

    synthesis: list[SynthesisStatement] = Field(
        default_factory=list,
        description="The page-level 'so what' (C1): derived threshold statements over the facts "
        "above, each linking to the block it came from. Empty when no rule's inputs are present -- "
        "computed here so the client renders, never invents, the reading.",
    )

    target_tdl: dict[str, TdlVerdict] = Field(
        default_factory=dict,
        description="For each landscape target's Ensembl id, its Pharos-style Target Development "
        "Level (C3): the level plus the pass/fail criteria that produced it. Derived from drug "
        "status and whether the catalog binds it potently; a parallel map, not on the fact.",
    )


class TargetDetail(BaseModel):
    """A target's evidence brief: the catalog row plus every fact we hold, with provenance.
    The target-side twin of CancerDetail (the cancer page, run backwards).

    `state` is not_analyzed until enrich_target has looked, enriching while it fetches, ready
    once facts are stored -- never "ready with nothing", which would tell the reader a target
    drives no cancers when the truth is we have not looked. `name` and `n_cancers` are null
    until enriched (measured by the reverse query), never defaulted to 0.
    """

    ensembl_id: str
    symbol: str
    name: str | None = None
    n_cancers: int | None = None
    last_enriched_at: datetime | None = None

    state: BriefState = BriefState.NOT_ANALYZED

    refreshing: bool = False
    """A READY brief whose facts aged past the freshness window, being revalidated in the
    background (stale-while-revalidate). Stored facts are shown now; poll until it clears."""

    facts: dict[str, list[SourcedFact]] = Field(
        default_factory=dict,
        description="Keyed by fact name (e.g. 'associated_cancers'); a list because sources "
        "can disagree. Each carries its own source, status and provenance. Every cancer in the "
        "associated_cancers fact is in our catalog by construction, so all are live links.",
    )

    unavailable: list[str] = Field(
        default_factory=list,
        description="Fact keys where every source failed. Hoisted so a client cannot mistake "
        "an outage for an absence without looking.",
    )

    catalog_drugs: list[str] = Field(
        default_factory=list,
        description="ChEMBL ids of drugs in OUR catalog that act on this target (joined on the "
        "Ensembl id). An empty list is 'no such drug in our catalog', NOT 'undruggable'.",
    )
