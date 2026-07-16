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
    primary_indication: str | None = None
    maturity: DataMaturity
    updated_at: datetime


class DrugList(BaseModel):
    items: list[DrugSummary]
    total: int
    limit: int
    offset: int


class DrugDetail(BaseModel):
    """The evidence brief: the catalog row plus every fact we hold, with provenance."""

    chembl_id: str
    pref_name: str | None = None
    maturity: DataMaturity

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
