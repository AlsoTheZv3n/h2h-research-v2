"""Source disagreement (Epic E1): the honest state after ok / empty / source_failed.

When the same underlying fact is fetched from more than one source and they DISAGREE, the
conflict is itself a signal about how much to trust the value -- today it is rendered as two
facts side by side and left for the reader to notice. This names it.

Derived at serve time from the facts already on the page (exactly like the synthesis), never a
stored fact status: an adapter only ever sees its own value and cannot assert a conflict. Only OK
facts participate -- an empty or failed source is a MISSING value, not a disagreeing one, and
comparing a value against an outage is the None-vs-0 lie this codebase refuses. Withheld unless at
least two sources genuinely conflict, so agreement is silent (no false positive).

Scope: only fields on a common, comparable scale are checked. The clinical-phase family (ChEMBL
`max_phase` and ClinicalTrials.gov `ct_max_phase` as ints, Open Targets `max_stage` as a string
enum) normalizes to one 0-4 ordinal and is compared with a whole-phase tolerance. Free-text fields
like the mechanism of action are deliberately NOT compared: two sources phrasing the same mechanism
differently is agreement, and only a semantic layer (a new method this epic forbids) could tell that
apart from a real conflict -- so a text mismatch would be a false positive the design refuses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

STAGE_CONFLICT_PHASES = 1.0
"""Sources must differ by at least this many whole clinical phases to count as conflicting. A
half-phase apart (e.g. ChEMBL phase 2 vs an Open Targets 'phase 2/3') is near-agreement, not a
conflict -- comparing fractional stages as exact ints would manufacture disagreements that are not
real. A disclosed judgement, like the synthesis thresholds, not a measurement."""

# The phase family: the fact keys that each assert the drug's furthest clinical stage. One source
# per key (max_phase=ChEMBL, ct_max_phase=ClinicalTrials.gov, max_stage=Open Targets).
_PHASE_KEYS = ("max_phase", "ct_max_phase", "max_stage")

# Open Targets reports the stage as an enum string. Map each to the shared 0-4 ordinal; fractional
# and boundary stages get a half-step so the tolerance above absorbs near-agreement rather than a
# naive round producing a false conflict. UNKNOWN / anything unmapped -> None (does not participate).
_OT_STAGE_ORDINAL: dict[str, float] = {
    "APPROVAL": 4.0,
    "PHASE_4": 4.0,
    "PREAPPROVAL": 3.5,
    "PHASE_3": 3.0,
    "PHASE_2_3": 2.5,
    "PHASE_2": 2.0,
    "PHASE_1_2": 1.5,
    "PHASE_1": 1.0,
    "EARLY_PHASE_1": 0.5,
    "PHASE_0": 0.0,
    "PRECLINICAL": 0.0,
}

# How each Open Targets enum reads in its own words, so a disagreement shows the source's actual
# granularity ('phase 2/3', 'approved') rather than a lossy ordinal. Ints render as 'phase N'.
_OT_STAGE_LABEL: dict[str, str] = {
    "APPROVAL": "approved",
    "PHASE_4": "phase 4",
    "PREAPPROVAL": "pre-registration",
    "PHASE_3": "phase 3",
    "PHASE_2_3": "phase 2/3",
    "PHASE_2": "phase 2",
    "PHASE_1_2": "phase 1/2",
    "PHASE_1": "phase 1",
    "EARLY_PHASE_1": "early phase 1",
    "PHASE_0": "phase 0",
    "PRECLINICAL": "preclinical",
}


@dataclass(frozen=True)
class SourceValue:
    """One source's OK value for a fact key, with where it came from -- the input the API hands in
    after filtering to OK facts (an empty/failed source is never a SourceValue)."""

    value: Any
    source: str
    source_url: str | None


def _phase_ordinal(value: Any) -> float | None:
    """The furthest-clinical-stage value on a shared 0-4 scale, or None if not comparable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if 0 <= value <= 4 else None
    if isinstance(value, str):
        return _OT_STAGE_ORDINAL.get(value.strip().upper())
    return None


def _phase_display(value: Any) -> str:
    """How a source's own phase value reads: OT's enum in its own words, ints as 'phase N'."""
    if isinstance(value, str):
        return _OT_STAGE_LABEL.get(value.strip().upper(), value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"phase {int(value)}"
    return str(value)


def _phase_conflict(by_key: Mapping[str, Sequence[SourceValue]]) -> dict[str, Any] | None:
    """A clinical-phase disagreement, or None when fewer than two sources give a comparable value
    or the spread is within tolerance (near-agreement)."""
    participating: list[tuple[float, SourceValue]] = []
    for key in _PHASE_KEYS:
        for sv in by_key.get(key, ()):  # one OK entry per key at most; skip unmapped values
            ordinal = _phase_ordinal(sv.value)
            if ordinal is not None:
                participating.append((ordinal, sv))
    if len(participating) < 2:
        return None
    ordinals = [o for o, _ in participating]
    if max(ordinals) - min(ordinals) < STAGE_CONFLICT_PHASES:
        return None
    values = [
        {"source": sv.source, "display": _phase_display(sv.value), "source_url": sv.source_url}
        for _, sv in participating
    ]
    return {"label": "Clinical phase", "block": "clinical", "values": values}


def drug_disagreements(by_key: Mapping[str, Sequence[SourceValue]]) -> list[dict[str, Any]]:
    """The drug page's cross-source conflicts. `by_key` is the OK facts grouped by key (the API
    filters out empty/failed before calling). Empty when nothing comparable conflicts."""
    out: list[dict[str, Any]] = []
    phase = _phase_conflict(by_key)
    if phase is not None:
        out.append(phase)
    return out
