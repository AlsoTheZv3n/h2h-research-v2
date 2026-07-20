"""Turn a pile of ChEMBL IC50 activities into a SELECTIVITY PROFILE you can act on.

`summarize_ic50` answers one question -- "how potent, on the drug's own mechanism target(s)"
-- and it is wrong for the multi-target drugs that dominate oncology. Vatalanib's headline
reads "9,887 nM median" because its most potent measured target, VEGFR2 at ~54 nM, is not in
its ChEMBL *mechanism* annotation and so was dumped as off-target, while cell-based screens at
~10,000 nM were folded into the median. The page then contradicts its own mechanism card ("VEGFR
inhibitor").

The field does not pick a declared primary target. It ranks every measured target by potency,
takes the **most potent as the reference**, and expresses the others as a **fold-difference**
against it; a documented threshold below the reference (here 100x) decides what still counts as a
target. The headline judgement is selective vs promiscuous -- imatinib's nine targets all sit
within ~100x of its top target, which is why it is the most selective of imatinib/dasatinib/
nilotinib despite hitting several kinases.

This module computes that profile from the raw activity rows. Two disciplines carry over from
`potency.py`:

  molecular targets only   selectivity is about target AFFINITY, so the ranking is over
                           single-protein binding assays (ChEMBL's `bao_label`), never the
                           cell-based readouts (HUVEC, A549) that measure a cell response, not
                           binding, and would otherwise become the reference.
  exact, nM, robust        censored ">"/"<" bounds are not measurements and never rank; a
                           target's potency is the MEDIAN of its exact nM values, robust to the
                           order-of-magnitude spread a mean would launder.

Everything the ranking sets aside is counted, not silently dropped.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from backend.domain.potency import CENSORED_RELATIONS, NANOMOLAR, _to_float

# ChEMBL's BioAssay-Ontology assay format for a purified molecular target. A selectivity
# ranking is about target affinity, so only these rows rank; "cell-based format",
# "organism-based format" and the generic "assay format" measure something else and are set
# aside (their fuller separation is A3). Matched on the ontology label, not the free-text
# target name, because a cell line sits in target_pref_name just like a protein does.
PROTEIN_FORMATS = frozenset({"single protein format", "protein format"})

# How far below the reference a target may sit and still count as a real target. 100x is the
# field's usual cut (the imatinib example). A judgement, disclosed -- not a measurement.
SELECTIVITY_THRESHOLD_FOLD = 100.0

# A target must be measured at least this many times to be RANKED. ChEMBL aggregates
# heterogeneous literature, and a single erroneous row can be wildly off: imatinib carries a
# lone 0.06 nM ERBB2 IC50 and a lone 0.11 nM EGFR IC50 (both n=1) that would anchor the whole
# profile and push its real targets -- ABL1 (n=24), KIT (n=12), PDGFRA (n=5) at 18-200 nM --
# below the threshold. Selectivity is a claim about a drug's target profile; it must rest on
# corroborated measurements, not one outlier. Uncorroborated targets are counted, not silently
# dropped. A judgement, disclosed.
MIN_MEASUREMENTS = 2


@dataclass
class SelectivityTarget:
    """One molecular target the drug was measured against, placed relative to the reference."""

    target_chembl_id: str
    target_pref_name: str
    median_nm: float
    n: int
    """Exact nM binding measurements this median is over."""
    fold_vs_reference: float
    """median_nm / the reference target's median_nm. 1.0 for the reference itself."""
    is_target: bool
    """Within SELECTIVITY_THRESHOLD_FOLD of the reference -- a real target, not incidental."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_chembl_id": self.target_chembl_id,
            "target_pref_name": self.target_pref_name,
            "median_nm": self.median_nm,
            "n": self.n,
            "fold_vs_reference": round(self.fold_vs_reference, 2),
            "is_target": self.is_target,
        }


@dataclass
class SelectivityProfile:
    """A drug's measured targets, ranked by potency, relative to the most potent."""

    targets: list[SelectivityTarget] = field(default_factory=list)
    """Ranked most-potent-first. The first entry is the reference (fold 1.0)."""

    threshold_fold: float = SELECTIVITY_THRESHOLD_FOLD

    n_protein_rows: int = 0
    """Exact nM single-protein binding rows the ranking is built from (over ranked targets)."""
    n_excluded_rows: int = 0
    """Rows set aside: cell-based / organism / other format, censored, or non-nM. Reported so a
    profile built from a fraction of the rows says so (A4 warns when this dominates)."""
    n_uncorroborated_targets: int = 0
    """Molecular targets seen but measured fewer than MIN_MEASUREMENTS times, so not ranked --
    a single row is too weak to anchor or place a selectivity claim. Counted, not hidden."""

    @property
    def reference(self) -> SelectivityTarget | None:
        """The most potent measured target -- everything else is expressed relative to it."""
        return self.targets[0] if self.targets else None

    @property
    def n_targets(self) -> int:
        """Targets within the threshold of the reference -- the selectivity count (fewer = more
        selective). Includes the reference itself."""
        return sum(1 for t in self.targets if t.is_target)

    def as_dict(self) -> dict[str, Any]:
        ref = self.reference
        return {
            "reference": ref.as_dict() if ref else None,
            "targets": [t.as_dict() for t in self.targets],
            "n_targets": self.n_targets,
            "n_measured_targets": len(self.targets),
            "threshold_fold": self.threshold_fold,
            "n_protein_rows": self.n_protein_rows,
            "n_excluded_rows": self.n_excluded_rows,
            "n_uncorroborated_targets": self.n_uncorroborated_targets,
        }


def _is_protein_binding(activity: dict[str, Any]) -> bool:
    return (activity.get("bao_label") or "") in PROTEIN_FORMATS


def compute_selectivity(activities: list[dict[str, Any]]) -> SelectivityProfile:
    """Rank a molecule's measured molecular targets by potency, relative to the most potent.

    No declared primary target: the reference is whichever single-protein target the drug binds
    most potently. Targets within `threshold_fold` of it are real targets; the rest are weaker or
    incidental. Cell-based rows, censored bounds and non-nM rows do not rank (they are counted).
    """
    # target_chembl_id -> exact nM binding values against it
    by_target: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str] = {}
    excluded = 0

    for a in activities:
        tid = a.get("target_chembl_id")
        if (
            not tid
            or not _is_protein_binding(a)
            or a.get("standard_units") != NANOMOLAR
            or (a.get("standard_relation") or "=") in CENSORED_RELATIONS
        ):
            excluded += 1
            continue
        value = _to_float(a.get("standard_value"))
        if value is None or value <= 0:
            # A non-positive potency is not a measurement; a fold-ratio would divide by it.
            excluded += 1
            continue
        by_target[tid].append(value)
        names.setdefault(tid, a.get("target_pref_name") or tid)

    # Corroboration gate: a target measured only once is too weak to place or anchor a
    # selectivity claim (imatinib's lone 0.06 nM ERBB2). Rank only corroborated targets; count
    # the rest.
    corroborated = {tid: vals for tid, vals in by_target.items() if len(vals) >= MIN_MEASUREMENTS}
    n_uncorroborated = len(by_target) - len(corroborated)
    n_protein_rows = sum(len(v) for v in corroborated.values())

    # One robust potency per target, then rank most-potent (lowest nM) first.
    ranked = sorted(
        ((tid, float(median(vals)), len(vals)) for tid, vals in corroborated.items()),
        key=lambda r: r[1],
    )
    if not ranked:
        return SelectivityProfile(
            n_protein_rows=0,
            n_excluded_rows=excluded,
            n_uncorroborated_targets=n_uncorroborated,
        )

    reference_nm = ranked[0][1]
    targets = [
        SelectivityTarget(
            target_chembl_id=tid,
            target_pref_name=names[tid],
            median_nm=nm,
            n=n,
            fold_vs_reference=nm / reference_nm,
            is_target=(nm / reference_nm) <= SELECTIVITY_THRESHOLD_FOLD,
        )
        for tid, nm, n in ranked
    ]
    return SelectivityProfile(
        targets=targets,
        n_protein_rows=n_protein_rows,
        n_excluded_rows=excluded,
        n_uncorroborated_targets=n_uncorroborated,
    )
