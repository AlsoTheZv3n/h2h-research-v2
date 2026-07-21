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
WELL_STUDIED_TRIALS = 20
""">= this many registered trials marks a drug as well-studied rather than early or sparse."""


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


def drug_synthesis(
    max_phase: Any,
    selectivity: dict[str, Any] | None,
    n_trials: Any,
    has_terminated: Any,
) -> list[dict[str, str]]:
    """The drug page's "so what" (C2). Same discipline as cancer_synthesis: each statement is a
    disclosed threshold rule over a fact, computed only when its input is present (an absent fact
    yields no statement, never a defaulted one), and links to the block it came from."""
    out: list[Statement] = []

    # Maturity: the single most orienting fact -- has it reached patients, and how far.
    if isinstance(max_phase, int) and not isinstance(max_phase, bool):
        if max_phase >= 4:
            out.append(Statement("Approved — reached phase 4", "clinical"))
        else:
            out.append(Statement(f"In development — reached phase {max_phase}", "clinical"))

    # Selectivity: the potency card's own verdict, hoisted -- what it mainly targets, how tightly.
    reference = (selectivity or {}).get("reference")
    n_targets = (selectivity or {}).get("n_targets")
    if reference and isinstance(n_targets, int):
        name = reference.get("gene_symbol") or reference.get("target_pref_name")
        if name:
            if n_targets <= 1:
                out.append(Statement(f"Selective for {name}", "potency"))
            else:
                out.append(Statement(f"Multi-target: {n_targets} within 100x", "potency"))

    if (
        isinstance(n_trials, int)
        and not isinstance(n_trials, bool)
        and n_trials >= WELL_STUDIED_TRIALS
    ):
        out.append(Statement(f"Well-studied: {n_trials:,} registered trials", "clinical"))

    # A red flag worth surfacing up top, not buried in the clinical block.
    if has_terminated is True:
        out.append(Statement("Terminated or withdrawn trials on record", "clinical"))

    return [s.as_dict() for s in out]
