"""The shared adapter contract.

This is the interface every source implements, and the place where the spike's
hardest-won lesson becomes a type:

    None != 0

`None` means "not measured" -- the source was unreachable, or the sub-request that
would have produced this field failed. `0` (or `[]`, or `""`) means "measured, and
the answer is nothing". Collapsing them reports an outage as a finding about the
data, which is the one answer this system must never give. A count of 0 trials is a
fact about a drug; a count of None is a fact about our pipeline.

So a field is never a bare value: it is a `Fact` carrying a `FactStatus` alongside
it, and the two failure modes get distinct statuses that survive all the way into
the API response and the UI's "unverified" chip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


def utcnow() -> datetime:
    return datetime.now(UTC)


class FactStatus(StrEnum):
    """Why a fact's value looks the way it does."""

    OK = "ok"
    """The source answered and produced a value."""

    EMPTY = "empty"
    """The source answered, and the answer is "nothing". A real finding."""

    SOURCE_FAILED = "source_failed"
    """The source (or the sub-request behind this field) failed. NOT a finding.

    `value` is None here, and that None means "unknown", never "zero".
    """


@dataclass(frozen=True, slots=True)
class Fact:
    """One field, with the provenance and status that make it trustworthy."""

    value: Any | None
    status: FactStatus
    source: str
    source_url: str | None = None
    retrieved_at: datetime = field(default_factory=utcnow)
    # Populated only for SOURCE_FAILED: what went wrong, in the operator's words.
    error: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.status is FactStatus.SOURCE_FAILED and self.value is not None:
            raise ValueError("a failed fact cannot carry a value")
        if self.status is FactStatus.OK and self.value is None:
            raise ValueError("an ok fact must carry a value; use EMPTY or SOURCE_FAILED")


def fact(
    value: Any,
    source: str,
    *,
    source_url: str | None = None,
    confidence: float | None = None,
    retrieved_at: datetime | None = None,
) -> Fact:
    """A measured fact, classified by its own value.

    `None` in, `EMPTY` out -- because a source that answered "no mechanism annotated"
    genuinely measured nothing. Only an adapter that *failed* may call `failed()`, and
    it must do so explicitly. Making the failure path the explicit one is deliberate:
    the spike's bug was a failure quietly taking the shape of an empty result.
    """
    empty = value is None or value == 0 or value == [] or value == "" or value == {}
    return Fact(
        value=value,
        status=FactStatus.EMPTY if empty else FactStatus.OK,
        source=source,
        source_url=source_url,
        retrieved_at=retrieved_at or utcnow(),
        confidence=confidence,
    )


def failed(
    source: str,
    error: str,
    *,
    source_url: str | None = None,
    retrieved_at: datetime | None = None,
) -> Fact:
    """A fact we could not measure. Never a zero."""
    return Fact(
        value=None,
        status=FactStatus.SOURCE_FAILED,
        source=source,
        source_url=source_url,
        retrieved_at=retrieved_at or utcnow(),
        error=error,
    )


@dataclass
class SourceRecord:
    """Normalized result from one source for one drug.

    In the spike this was printed; in the app it is persisted. The shape is the same
    -- that is what let the adapters graduate almost unchanged.
    """

    source: str
    query: str
    ok: bool
    facts: dict[str, Fact] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    # Set when the *resolve* failed (hard failure: no entity, so no facts at all).
    # Individual enrichment failures live in their own Fact.error instead.
    error: str | None = None

    outage: bool = False
    """True when the resolve failed because the *source* did -- a 500, a timeout.

    Distinct from an error with outage=False, which means the source answered and
    simply does not know this drug. Two different sentences that a bare `error`
    conflates:

        outage      "we could not ask ChEMBL"      -> the drug's keys are unknown
        no match    "ChEMBL has no such molecule"  -> a real, if unhelpful, answer

    The caller needs the difference: an outage must become source_failed facts, or a
    brief with no ChEMBL rows at all reports `unavailable: []` and tells the reader
    nothing failed.
    """

    @property
    def failed_facts(self) -> dict[str, Fact]:
        return {k: v for k, v in self.facts.items() if v.status is FactStatus.SOURCE_FAILED}

    def value(self, key: str, default: Any = None) -> Any:
        """Read a value, keeping None distinct from a missing key."""
        f = self.facts.get(key)
        return default if f is None else f.value


@runtime_checkable
class SourceAdapter(Protocol):
    """One source, one implementation. The plugin seam."""

    name: str

    owned_keys: tuple[str, ...]
    """Every fact key this adapter is responsible for.

    Declared so an outage can be written down. When the resolve itself fails there
    are no facts to degrade -- and a source that contributes no rows at all leaves
    the brief saying `unavailable: []`, which asserts that nothing failed. The caller
    synthesizes a source_failed fact per key instead, so the outage appears where the
    reader is looking.
    """

    async def fetch(self, drug: str) -> SourceRecord: ...
