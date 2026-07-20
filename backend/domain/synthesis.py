"""Page-level synthesis: what the evidence adds up to (Epic C).

Not generated prose -- a small set of DERIVED THRESHOLD RULES over the facts already on the page,
each pointing back to the block it came from so the reader can check it. Thresholds are judgements,
disclosed here as named constants, never passed off as measurements.

The derived-value discipline holds throughout: a statement is COMPUTED ONLY when its inputs are
present. An absent, failed or empty fact yields no statement -- never a 0-substituted one -- so the
synthesis can never assert something the evidence does not support. A page with no facts gets an
empty synthesis, not a wall of confident nothings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Disclosed judgements (not measurements). Each is the single place its rule's threshold lives.
CROWDED_PIPELINE = 50
"""A development field with >= this many drugs/candidates reads as crowded rather than sparse."""
HIGH_ATTRITION = 0.15
""">= this share of the SCANNED trials having stopped is notable attrition worth surfacing."""
WIDE_STAGE_GAP = 30.0
"""A localized-vs-distant 5-year-survival gap at least this wide (percentage points) means the
outcome hinges on stage at diagnosis -- the 'catch it early' story."""


@dataclass
class Statement:
    """One synthesis line: a derived reading and the anchor id of the block it came from."""

    text: str
    block: str

    def as_dict(self) -> dict[str, str]:
        return {"text": self.text, "block": self.block}


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _stage_rate(survival: dict[str, Any], needle: str) -> float | None:
    """The 5-year survival rate for the SEER summary stage whose name contains `needle`."""
    for stage in survival.get("by_stage") or []:
        if needle in (stage.get("stage") or "").lower():
            return _num(stage.get("rate"))
    return None


def cancer_synthesis(
    landscape: dict[str, Any] | None,
    pipeline: dict[str, Any] | None,
    trial_reality: dict[str, Any] | None,
    survival: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """The cancer page's "so what", as derived statements. Each arg is a fact's value, or None when
    that fact is missing/failed/empty -- in which case its statements are simply absent."""
    out: list[Statement] = []

    if landscape:
        n_strong = landscape.get("n_strong")
        if isinstance(n_strong, int):
            out.append(Statement(f"{n_strong:,} strongly-associated targets", "target-landscape"))
        # drug_status lives on the displayed top targets, so this counts "of the top", not of all.
        unexploited = [
            t for t in (landscape.get("targets") or []) if t.get("drug_status") == "unexploited"
        ]
        if unexploited:
            n = len(unexploited)
            verb = "has" if n == 1 else "have"
            out.append(
                Statement(
                    f"{n} of the top targets {verb} no drug anywhere — the unexploited opportunity",
                    "target-landscape",
                )
            )

    if pipeline:
        total = pipeline.get("total")
        if isinstance(total, int):
            verdict = "Crowded field" if total >= CROWDED_PIPELINE else "Sparse field"
            out.append(Statement(f"{verdict}: {total:,} drugs in development", "pipeline"))

    if trial_reality:
        stopped = (trial_reality.get("stopped") or {}).get("count")
        scanned = trial_reality.get("n_trials_scanned")
        if (
            isinstance(stopped, int)
            and isinstance(scanned, int)
            and scanned > 0
            and stopped / scanned >= HIGH_ATTRITION
        ):
            out.append(
                Statement(
                    f"Notable attrition: {stopped:,} of {scanned:,} scanned trials stopped",
                    "trial-reality",
                )
            )

    if survival and survival.get("staged"):
        loc = _stage_rate(survival, "local")
        dist = _stage_rate(survival, "distant")
        if loc is not None and dist is not None and (loc - dist) >= WIDE_STAGE_GAP:
            out.append(
                Statement(
                    f"Outcomes hinge on stage: {round(loc)}% localized vs {round(dist)}% "
                    f"distant 5-year survival",
                    "survival",
                )
            )

    return [s.as_dict() for s in out]
