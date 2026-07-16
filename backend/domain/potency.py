"""Turn a pile of ChEMBL IC50 activities into a potency answer you can act on.

The spike could only say "adagrasib has 30 IC50s". Measured, those 30 contain:

  - values from 1 nM to 50,000 nM -- a 50,000x spread, so any average is fiction
  - 5 censored bounds (">", "<"), which are not measurements at all
  - targets including MIA PaCa-2 and NCI-H358 (cell lines, not the target) and
    two SARS-CoV-2 assays (an off-target screen)

"n_ic50 = 30" is therefore not a number a reader can use; it is a count of rows in
a database. For a KRAS G12C programme the headline is *on-target potency*, so this
module answers that question instead:

  on-target   the activity's target must be the drug's own target, by ChEMBL ID.
              Names are free text and cell lines masquerade as targets; IDs do not.
  censored    ">" / "<" rows are counted and reported, never averaged. A ">10000"
              says "at least", and folding it into a median invents precision.
  median      over exact, on-target, nM measurements -- robust to the spread in a
              way a mean is not.

Everything excluded is reported, not silently dropped: a summary built from 7 of
30 rows must say so, or it is just a prettier version of the same lie.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import Any

# ChEMBL normalizes most affinities to nM, but not all. Mixing units silently is
# how a 50 uM screening hit becomes a "50 nM" headline.
NANOMOLAR = "nM"

# Relations that state a bound rather than a measurement. "=" and "~" are values;
# these are not.
CENSORED_RELATIONS = frozenset({">", "<", ">=", "<=", ">>", "<<"})


@dataclass
class PotencySummary:
    """On-target IC50 potency, with everything it had to discard made explicit."""

    target_chembl_ids: list[str] = field(default_factory=list)
    """Every target the drug's mechanisms name. A multi-kinase inhibitor genuinely
    has several: dasatinib hits ABL1, SRC, KIT and PDGFRA, and calling three of them
    off-target would be a false claim about its defining mechanism."""

    n_activities: int = 0
    """Every IC50 row ChEMBL returned for this molecule."""

    n_on_target: int = 0
    """Rows whose target is the drug's own target."""

    n_censored: int = 0
    """On-target rows stating a bound (">", "<"). Reported, never averaged."""

    n_exact: int = 0
    """On-target rows with an exact nM value -- the ones the median is built from."""

    median_nm: float | None = None
    min_nm: float | None = None
    max_nm: float | None = None

    off_target: dict[str, int] = field(default_factory=dict)
    """What was excluded and how often, by target name. Transparency, not noise:
    the reader should see that two SARS-CoV-2 assays were in there."""

    other_units: dict[str, int] = field(default_factory=dict)
    """On-target rows dropped for not being in nM."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_chembl_ids": self.target_chembl_ids,
            "n_activities": self.n_activities,
            "n_on_target": self.n_on_target,
            "n_censored": self.n_censored,
            "n_exact": self.n_exact,
            "median_nm": self.median_nm,
            "min_nm": self.min_nm,
            "max_nm": self.max_nm,
            "units": NANOMOLAR,
            "off_target": self.off_target,
            "other_units": self.other_units,
        }

    @property
    def is_decision_grade(self) -> bool:
        """Enough exact on-target measurements to quote a potency at all."""
        return self.n_exact > 0 and self.median_nm is not None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_ic50(
    activities: list[dict[str, Any]], target_chembl_ids: str | list[str] | None
) -> PotencySummary:
    """Summarize IC50 activities against the drug's own target(s).

    The targets come from the drug's mechanisms -- what it is *meant* to hit. Without
    them we cannot separate signal from off-target screening noise, so the summary
    reports the rows and refuses to quote a potency, rather than quoting one over
    everything.

    Accepts a single id for convenience; a drug with several mechanism targets is on
    target against all of them.
    """
    if isinstance(target_chembl_ids, str):
        target_chembl_ids = [target_chembl_ids]
    targets = set(target_chembl_ids or [])

    summary = PotencySummary(target_chembl_ids=sorted(targets), n_activities=len(activities))

    if not targets:
        # No known target: every row is unclassifiable. Say so instead of guessing.
        summary.off_target = dict(
            Counter(a.get("target_pref_name") or "unknown" for a in activities)
        )
        return summary

    exact_values: list[float] = []
    off_target: Counter[str] = Counter()
    other_units: Counter[str] = Counter()

    for a in activities:
        if a.get("target_chembl_id") not in targets:
            # Matched on ID, not name: "MIA PaCa-2" is a cell line and "SARS-CoV-2"
            # is a different organism entirely, but both sit in target_pref_name.
            off_target[a.get("target_pref_name") or "unknown"] += 1
            continue

        summary.n_on_target += 1

        units = a.get("standard_units")
        if units != NANOMOLAR:
            other_units[units or "unknown"] += 1
            continue

        if (a.get("standard_relation") or "=") in CENSORED_RELATIONS:
            summary.n_censored += 1
            continue

        value = _to_float(a.get("standard_value"))
        if value is None:
            continue
        exact_values.append(value)

    summary.off_target = dict(off_target)
    summary.other_units = dict(other_units)
    summary.n_exact = len(exact_values)

    if exact_values:
        summary.median_nm = float(median(exact_values))
        summary.min_nm = min(exact_values)
        summary.max_nm = max(exact_values)

    return summary
