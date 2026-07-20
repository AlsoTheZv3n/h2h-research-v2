"""The selectivity profile: rank a drug's measured targets by potency, relative to the reference.

The golden set is the point. Vatalanib is the bug that motivated this (#61): its most potent
molecular target, VEGFR2 (~54 nM), is not in its ChEMBL mechanism annotation, so the single-
target summarizer dumped it as off-target and quoted a ~9,887 nM median over cell-based screens
-- contradicting its own "VEGFR inhibitor" mechanism card. The method must instead rank VEGFR2 as
the reference. And a real trap in the data: a cell-based HUVEC screen (33 nM) is MORE potent than
VEGFR2 (54 nM), so without the molecular-target filter HUVEC would become the reference.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.domain.potency import summarize_ic50
from backend.domain.selectivity import (
    SELECTIVITY_THRESHOLD_FOLD,
    compute_selectivity,
)

# Real ChEMBL target ids where known; the test asserts on names + the reference, so the exact
# ids only need to be distinct.
VEGFR2 = "CHEMBL279"
VEGFR1 = "CHEMBL1868"
VEGFR3 = "CHEMBL1955"
EGFR = "CHEMBL203"
PDGFRB = "CHEMBL1913"
KIT = "CHEMBL1936"
ABL1 = "CHEMBL1862"
PDGFRA = "CHEMBL2007"


def _act(
    target_chembl_id: str,
    target_pref_name: str,
    value: float | None,
    *,
    bao_label: str = "single protein format",
    relation: str = "=",
    units: str = "nM",
) -> dict[str, Any]:
    """One ChEMBL IC50 activity row, in the shape the adapter passes through."""
    return {
        "target_chembl_id": target_chembl_id,
        "target_pref_name": target_pref_name,
        "standard_type": "IC50",
        "standard_relation": relation,
        "standard_value": None if value is None else str(value),
        "standard_units": units,
        "bao_label": bao_label,
    }


# Vatalanib's real single-protein profile (medians from live ChEMBL), plus the cell-based screens
# that the current method folded into its headline. HUVEC (33) is deliberately more potent than
# VEGFR2 (54) -- the molecular filter must still make VEGFR2 the reference.
VATALANIB = [
    _act(VEGFR2, "Vascular endothelial growth factor receptor 2", 54.0),
    _act(VEGFR1, "Vascular endothelial growth factor receptor 1", 140.0),
    _act(VEGFR3, "Vascular endothelial growth factor receptor 3", 195.0),
    _act(EGFR, "Epidermal growth factor receptor", 458.0),
    _act(PDGFRB, "Platelet-derived growth factor receptor beta", 490.0),
    _act(KIT, "Mast/stem cell growth factor receptor Kit", 730.0),
    _act("CELL_HUVEC", "HUVEC", 33.0, bao_label="cell-based format"),
    _act("CELL_A549", "A549", 21160.0, bao_label="cell-based format"),
    _act("CELL_HT29", "HT-29", 22110.0, bao_label="cell-based format"),
]


class TestGoldenSet:
    def test_vatalanib_is_selective_for_the_vegfr_family(self) -> None:
        p = compute_selectivity(VATALANIB)
        assert p.reference is not None
        # The reference is the most potent MOLECULAR target -- VEGFR2, not the more-potent
        # HUVEC cell screen, and not an arbitrary mechanism-annotation target.
        assert p.reference.target_pref_name == "Vascular endothelial growth factor receptor 2"
        assert p.reference.median_nm == 54.0
        # The three most potent targets are the VEGFR family.
        top3 = [t.target_pref_name for t in p.targets[:3]]
        assert all("Vascular endothelial growth factor" in n for n in top3)
        # KIT at 730 nM is ~13.5x the reference -- still within 100x, so still a target.
        kit = next(t for t in p.targets if t.target_chembl_id == KIT)
        assert kit.fold_vs_reference == pytest.approx(730.0 / 54.0)
        assert kit.is_target
        # Six molecular targets, all within the threshold; the cell lines are not targets at all.
        assert len(p.targets) == 6
        assert p.n_targets == 6

    def test_vatalanib_cell_lines_never_enter_the_ranking(self) -> None:
        p = compute_selectivity(VATALANIB)
        names = {t.target_pref_name for t in p.targets}
        assert "HUVEC" not in names
        assert "A549" not in names
        # HUVEC (33 nM) is more potent than the reference (54): dropping the molecular filter
        # would make a cell line the reference. This is why the filter is load-bearing.
        assert p.reference is not None and p.reference.median_nm > 33.0
        assert p.n_excluded_rows == 3  # the three cell-based rows

    def test_imatinib_targets_abl_kit_pdgfr(self) -> None:
        rows = [
            _act(PDGFRA, "Platelet-derived growth factor receptor alpha", 70.0),
            _act(KIT, "Mast/stem cell growth factor receptor Kit", 100.0),
            _act(ABL1, "Tyrosine-protein kinase ABL1", 200.0),
        ]
        p = compute_selectivity(rows)
        assert p.reference is not None and p.reference.target_chembl_id == PDGFRA
        # All three sit within 100x of the top target -> all real targets.
        assert p.n_targets == 3
        assert {t.target_chembl_id for t in p.targets} == {PDGFRA, KIT, ABL1}

    def test_osimertinib_is_selective_for_egfr(self) -> None:
        rows = [
            _act(EGFR, "Epidermal growth factor receptor", 12.66),
            # A distant, incidental target well beyond the threshold.
            _act(KIT, "Mast/stem cell growth factor receptor Kit", 4000.0),
        ]
        p = compute_selectivity(rows)
        assert p.reference is not None and p.reference.target_chembl_id == EGFR
        # KIT at ~316x is beyond 100x -> not a real target.
        assert p.n_targets == 1
        kit = next(t for t in p.targets if t.target_chembl_id == KIT)
        assert not kit.is_target
        assert kit.fold_vs_reference > SELECTIVITY_THRESHOLD_FOLD


class TestProveFailOldDefinition:
    def test_single_target_summary_misreports_vatalanib(self) -> None:
        """The old single-target method, gated on ChEMBL mechanism annotation, misreports.

        Vatalanib's mechanism annotation does not include VEGFR2 under the id its activities use
        (the bug's root). Feeding the summarizer only an annotated target (EGFR) quotes potency
        against the wrong target and buries the real most-potent one.
        """
        old = summarize_ic50(VATALANIB, [EGFR])
        new = compute_selectivity(VATALANIB)
        # Old: EGFR (458 nM) is "on target", VEGFR2 (54 nM) is dumped as off-target.
        assert old.median_nm == 458.0
        assert "Vascular endothelial growth factor receptor 2" in old.off_target
        # New: VEGFR2 is correctly the reference, an order of magnitude more potent.
        assert new.reference is not None
        assert new.reference.target_chembl_id == VEGFR2
        assert new.reference.median_nm < old.median_nm


class TestHonestStates:
    def test_no_molecular_binding_rows_yields_an_empty_profile(self) -> None:
        # Only cell-based screens: nothing to rank as target affinity. Empty, not a guess.
        rows = [_act("CELL_A549", "A549", 100.0, bao_label="cell-based format")]
        p = compute_selectivity(rows)
        assert p.reference is None
        assert p.targets == []
        assert p.n_excluded_rows == 1

    def test_censored_and_non_nm_rows_do_not_rank(self) -> None:
        rows = [
            _act(EGFR, "Epidermal growth factor receptor", 5000.0, relation=">"),
            _act(EGFR, "Epidermal growth factor receptor", 5.0, units="uM"),
        ]
        p = compute_selectivity(rows)
        assert p.reference is None  # a bound and a uM value are not exact nM measurements
        assert p.n_protein_rows == 0
        assert p.n_excluded_rows == 2

    def test_a_target_potency_is_the_median_of_its_exact_rows(self) -> None:
        rows = [
            _act(EGFR, "EGFR", 10.0),
            _act(EGFR, "EGFR", 20.0),
            _act(EGFR, "EGFR", 30.0),
        ]
        p = compute_selectivity(rows)
        assert p.reference is not None
        assert p.reference.median_nm == 20.0
        assert p.reference.n == 3
