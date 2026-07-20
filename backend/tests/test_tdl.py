"""The Target Development Level verdict (C3). Golden targets across every category (prove-fail),
and the honest-state pin: an unresolved drug status reads 'unknown', never a false fail."""

from __future__ import annotations

from typing import Any

from backend.domain.tdl import tdl_verdict


def _state(v: dict[str, Any], label_start: str) -> str:
    return str(next(c["state"] for c in v["criteria"] if c["label"].startswith(label_start)))


class TestTdlVerdict:
    def test_an_approved_target_is_tclin(self) -> None:
        v = tdl_verdict("approved", has_potent_ligand=True)
        assert v["level"] == "Tclin"
        assert _state(v, "Approved") == "pass"

    def test_a_clinical_candidate_is_tchem(self) -> None:
        v = tdl_verdict("clinical", has_potent_ligand=False)
        assert v["level"] == "Tchem"
        assert _state(v, "Approved") == "fail"
        assert _state(v, "In clinical") == "pass"

    def test_the_missing_middle_potent_ligand_but_no_drug_anywhere_is_tchem(self) -> None:
        # The cell C3 exists to surface: Open Targets says no drug anywhere, yet the catalog holds a
        # potent binder -- chemical matter with no approval. Not Tbio.
        v = tdl_verdict("unexploited", has_potent_ligand=True)
        assert v["level"] == "Tchem"
        assert _state(v, "Approved") == "fail"
        assert _state(v, "In clinical") == "fail"
        assert _state(v, "Potent ligand") == "pass"
        # OT RESOLVED the status (unexploited = no drug anywhere): "none approved" is earned here.
        assert "none approved" in v["label"]

    def test_unexploited_with_no_ligand_is_tbio(self) -> None:
        v = tdl_verdict("unexploited", has_potent_ligand=False)
        assert v["level"] == "Tbio"
        assert _state(v, "Potent ligand") == "fail"

    def test_unknown_with_no_ligand_is_tdark(self) -> None:
        v = tdl_verdict("unknown", has_potent_ligand=False)
        assert v["level"] == "Tdark"

    def test_a_potent_ligand_rescues_an_unresolved_target_from_tdark(self) -> None:
        # OT never resolved the drug status, but the catalog has a potent binder -- real chemical
        # matter, so Tchem, not Tdark.
        v = tdl_verdict("unknown", has_potent_ligand=True)
        assert v["level"] == "Tchem"

    def test_unresolved_tchem_does_not_claim_none_approved(self) -> None:
        # The honest-state pin on the LABEL: OT never resolved the drug status, so even though a
        # potent ligand makes this Tchem, the verdict must NOT assert "none approved" -- approval
        # was never measured, and the ligand itself might be an approved drug (EGFR/osimertinib).
        # It reads "approval not measured", and the drug criteria stay unknown, never a false mark.
        v = tdl_verdict("unknown", has_potent_ligand=True)
        assert v["level"] == "Tchem"
        assert "none approved" not in v["label"]
        assert "not measured" in v["label"]
        assert _state(v, "Approved") == "unknown"
        assert _state(v, "In clinical") == "unknown"
        assert _state(v, "Potent ligand") == "pass"

    def test_unresolved_drug_criteria_read_unknown_not_a_false_fail(self) -> None:
        # The honest-state pin: with drug_status unknown, "Approved" / "In clinical" are NOT ✗ --
        # OT did not measure them. Only the catalog-ligand criterion (measured) is pass/fail.
        v = tdl_verdict("unknown", has_potent_ligand=False)
        assert _state(v, "Approved") == "unknown"
        assert _state(v, "In clinical") == "unknown"
        assert _state(v, "Potent ligand") == "fail"
