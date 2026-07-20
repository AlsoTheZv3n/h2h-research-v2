"""The selectivity profile: rank a drug's measured targets by potency, relative to the reference.

The golden set is the point, and it encodes the two failure modes real ChEMBL data throws:

  cell-line masquerade   a cell-based HUVEC screen (33 nM) is MORE potent than vatalanib's real
                         reference VEGFR2 (54 nM); without the molecular-target filter a cell
                         line becomes the reference.
  single-row outliers    imatinib carries a lone 0.06 nM ERBB2 IC50 and a lone 0.11 nM EGFR IC50
                         (both n=1, likely erroneous) that would anchor the profile and push its
                         real targets ABL1 / KIT / PDGFRA (well-measured, 18-200 nM) below the
                         threshold; the corroboration gate (>= MIN_MEASUREMENTS) drops them.

Both were seen on live ChEMBL during A1's real-stack verification; the fixtures reproduce them.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.domain.potency import summarize_ic50
from backend.domain.selectivity import SELECTIVITY_THRESHOLD_FOLD, compute_selectivity

VEGFR2 = "CHEMBL279"
VEGFR1 = "CHEMBL1868"
VEGFR3 = "CHEMBL1955"
EGFR = "CHEMBL203"
KIT = "CHEMBL1936"
ERBB2 = "CHEMBL1824"
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


def _rows(tid: str, name: str, *values: float, **kw: Any) -> list[dict[str, Any]]:
    return [_act(tid, name, v, **kw) for v in values]


# Vatalanib's real single-protein VEGFR-family profile (medians from live ChEMBL), plus the two
# traps: a single ultra-potent ERBB2 outlier (n=1) and cell-based screens more potent than the
# reference.
VATALANIB = [
    *_rows(VEGFR2, "Vascular endothelial growth factor receptor 2", 50.0, 54.0, 58.0),
    *_rows(VEGFR1, "Vascular endothelial growth factor receptor 1", 135.0, 145.0),
    *_rows(VEGFR3, "Vascular endothelial growth factor receptor 3", 190.0, 200.0),
    *_rows(KIT, "Mast/stem cell growth factor receptor Kit", 700.0, 760.0),
    *_rows(ERBB2, "Receptor tyrosine-protein kinase erbB-2", 0.5),  # lone outlier -> dropped
    *_rows("CELL_HUVEC", "HUVEC", 33.0, bao_label="cell-based format"),  # cell line, more potent
    *_rows("CELL_A549", "A549", 21160.0, bao_label="cell-based format"),
]


class TestGoldenSet:
    def test_vatalanib_is_selective_for_the_vegfr_family(self) -> None:
        p = compute_selectivity(VATALANIB)
        assert p.reference is not None
        # The reference is the most potent CORROBORATED MOLECULAR target -- VEGFR2, not the more-
        # potent HUVEC cell screen (excluded by format) and not the lone 0.5 nM ERBB2 (excluded by
        # corroboration).
        assert p.reference.target_chembl_id == VEGFR2
        assert p.reference.median_nm == 54.0
        # The two most potent targets are the VEGFR family.
        assert [t.target_chembl_id for t in p.targets[:2]] == [VEGFR2, VEGFR1]
        assert all("growth factor receptor" in t.target_pref_name.lower() for t in p.targets[:3])
        # KIT at 730 nM is ~13.5x the reference -- within 100x, so still a target.
        kit = next(t for t in p.targets if t.target_chembl_id == KIT)
        assert kit.fold_vs_reference == pytest.approx(730.0 / 54.0)
        assert kit.is_target
        assert p.n_targets == 4  # VEGFR2, VEGFR1, VEGFR3, KIT
        # The traps are counted, not hidden:
        assert p.n_uncorroborated_targets == 1  # ERBB2 (n=1)
        assert p.n_excluded_rows == 2  # the two cell-based rows

    def test_vatalanib_a_cell_line_never_becomes_the_reference(self) -> None:
        p = compute_selectivity(VATALANIB)
        names = {t.target_pref_name for t in p.targets}
        assert "HUVEC" not in names and "A549" not in names
        # HUVEC (33 nM) is more potent than the reference (54): without the molecular filter it
        # would anchor the profile.
        assert p.reference is not None and p.reference.median_nm > 33.0

    def test_imatinib_targets_abl_kit_pdgfr_not_a_single_row_outlier(self) -> None:
        rows = [
            *_rows(PDGFRA, "Platelet-derived growth factor receptor alpha", 15.0, 18.0, 21.0),
            *_rows(KIT, "Mast/stem cell growth factor receptor Kit", 55.0, 61.0),
            *_rows(ABL1, "Tyrosine-protein kinase ABL1", 190.0, 210.0),
            *_rows(ERBB2, "Receptor tyrosine-protein kinase erbB-2", 0.06),  # lone outlier
            *_rows(EGFR, "Epidermal growth factor receptor", 0.11),  # lone outlier
        ]
        p = compute_selectivity(rows)
        # The reference is imatinib's most potent WELL-MEASURED target, not the 0.06 nM ERBB2
        # outlier that would otherwise anchor everything.
        assert p.reference is not None and p.reference.target_chembl_id == PDGFRA
        assert {t.target_chembl_id for t in p.targets} == {PDGFRA, KIT, ABL1}
        assert p.n_targets == 3
        assert p.n_uncorroborated_targets == 2  # ERBB2, EGFR (both n=1)

    def test_osimertinib_is_selective_for_egfr(self) -> None:
        rows = [
            *_rows(EGFR, "Epidermal growth factor receptor", 10.0, 12.66, 15.0),
            *_rows(KIT, "Mast/stem cell growth factor receptor Kit", 3900.0, 4100.0),
        ]
        p = compute_selectivity(rows)
        assert p.reference is not None and p.reference.target_chembl_id == EGFR
        # KIT at ~316x is beyond 100x -> not a real target.
        assert p.n_targets == 1
        kit = next(t for t in p.targets if t.target_chembl_id == KIT)
        assert not kit.is_target and kit.fold_vs_reference > SELECTIVITY_THRESHOLD_FOLD


class TestProveFailOldDefinition:
    def test_single_target_summary_misreports_vatalanib(self) -> None:
        """The old single-target method, gated on a ChEMBL mechanism target, buries the reference.

        Point it at KIT (a real but not most-potent vatalanib target) and it quotes 730 nM, an
        order of magnitude weaker than the true reference VEGFR2 (54 nM) which it dumps off-target.
        """
        old = summarize_ic50(VATALANIB, [KIT])
        new = compute_selectivity(VATALANIB)
        assert old.median_nm == 730.0
        assert "Vascular endothelial growth factor receptor 2" in old.off_target
        assert new.reference is not None and new.reference.target_chembl_id == VEGFR2
        assert new.reference.median_nm < old.median_nm


class TestHonestStates:
    def test_a_single_measurement_target_is_not_ranked_but_counted(self) -> None:
        # One target, one measurement: too weak to place a selectivity claim -> not ranked,
        # counted as uncorroborated. Never silently kept as the reference.
        p = compute_selectivity(_rows(EGFR, "EGFR", 5.0))
        assert p.reference is None
        assert p.n_uncorroborated_targets == 1
        assert p.n_targets == 0

    def test_no_molecular_binding_rows_yields_an_empty_profile(self) -> None:
        p = compute_selectivity(
            _rows("CELL_A549", "A549", 100.0, 110.0, bao_label="cell-based format")
        )
        assert p.reference is None
        assert p.targets == []
        assert p.n_excluded_rows == 2

    def test_censored_and_non_nm_rows_do_not_rank(self) -> None:
        rows = [
            *_rows(EGFR, "EGFR", 5000.0, 6000.0, relation=">"),
            *_rows(EGFR, "EGFR", 5.0, 6.0, units="uM"),
        ]
        p = compute_selectivity(rows)
        assert p.reference is None  # bounds and uM values are not exact nM measurements
        assert p.n_protein_rows == 0
        assert p.n_excluded_rows == 4

    def test_a_target_potency_is_the_median_of_its_exact_rows(self) -> None:
        p = compute_selectivity(_rows(EGFR, "EGFR", 10.0, 20.0, 30.0))
        assert p.reference is not None
        assert p.reference.median_nm == 20.0
        assert p.reference.n == 3
