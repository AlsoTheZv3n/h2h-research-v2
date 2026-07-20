"""Target Development Level (C3): a Pharos-style categorical verdict for a target.

Surfaces the missing MIDDLE -- **potent chemical matter with no approved drug** (Pharos' Tchem) --
which today collapses into "clinical"/"unexploited" and is one of the most decision-relevant cells.
The verdict explains itself with pass/fail criteria (as Pharos does), so it needs no glossary.

Derived from EXISTING data only, no new source: the target's drugged status (Open Targets,
indication-agnostic -- approved / clinical / unexploited / unknown) plus whether our catalog holds a
drug that binds it POTENTLY (the target appears as a within-threshold `is_target` in some drug's
selectivity profile). The honest-state discipline is preserved: when Open Targets never resolved the
target's drug status, the drug criteria read "unknown", never a false mark -- not-measured is
not "no".
"""

from __future__ import annotations

from typing import Any

# Pharos' Target Development Levels. Tchem is the cell this module exists to make visible.
LEVELS = ("Tclin", "Tchem", "Tbio", "Tdark")


def tdl_verdict(drug_status: str, has_potent_ligand: bool) -> dict[str, Any]:
    """The target's development level and the criteria that produced it.

    drug_status is the Open Targets flag (approved/clinical/unexploited/unknown); has_potent_ligand
    is whether any catalog drug binds this target within its selectivity threshold.
    """
    approved = drug_status == "approved"
    clinical = drug_status == "clinical"
    # Open Targets gave a definite drug answer (so the drug criteria are measured, not unknown).
    resolved = drug_status in ("approved", "clinical", "unexploited")

    if approved:
        level, label = "Tclin", "approved drug"
    elif clinical or has_potent_ligand:
        # Chemical matter exists (a clinical candidate, or a potent catalog ligand). We may only
        # say "none approved" when OT actually resolved the drug status; when it did not, a potent
        # ligand still lifts the target to Tchem (real chemical matter), but the verdict must NOT
        # assert approval either way -- the ligand itself might be an approved drug, and claiming
        # "none approved" from an unmeasured input is the exact honest-state collapse this refuses.
        if resolved:
            level, label = "Tchem", "chemical matter, none approved"
        else:
            level, label = "Tchem", "chemical matter, approval not measured"
    elif drug_status == "unexploited":
        level, label = "Tbio", "no drug anywhere"
    else:
        level, label = "Tdark", "not measured"

    def drug_state(passed: bool) -> str:
        # A drug criterion is pass/fail only when OT resolved the status; else it is unknown, never
        # a ✗ -- collapsing "not measured" into "fail" is the exact lie this codebase refuses.
        return ("pass" if passed else "fail") if resolved else "unknown"

    criteria = [
        {"label": "Approved drug (anywhere)", "state": drug_state(approved)},
        {"label": "In clinical development", "state": drug_state(approved or clinical)},
        {"label": "Potent ligand in catalog", "state": "pass" if has_potent_ligand else "fail"},
    ]
    return {"level": level, "label": label, "criteria": criteria}
