"""Source disagreement (E1). Prove-fail the phase comparator: conflicting sources surface a
disagreement, agreeing (or near-agreeing) sources do not, and only OK, comparable values count."""

from __future__ import annotations

from typing import Any

from backend.domain.disagreement import SourceValue, drug_disagreements


def _sv(value: Any, source: str, url: str | None = None) -> SourceValue:
    return SourceValue(value=value, source=source, source_url=url)


class TestPhaseDisagreement:
    def test_two_ints_that_conflict_surface_a_disagreement(self) -> None:
        # ClinicalTrials.gov says phase 3, ChEMBL says phase 4 -- a whole phase apart.
        out = drug_disagreements(
            {
                "max_phase": [_sv(4, "chembl", "http://chembl")],
                "ct_max_phase": [_sv(3, "clinicaltrials", "http://ct")],
            }
        )
        assert len(out) == 1
        d = out[0]
        assert d["label"] == "Clinical phase"
        assert d["block"] == "clinical"
        by_source = {v["source"]: v for v in d["values"]}
        assert by_source["chembl"]["display"] == "phase 4"
        assert by_source["clinicaltrials"]["display"] == "phase 3"
        assert by_source["chembl"]["source_url"] == "http://chembl"

    def test_int_vs_open_targets_enum_normalizes_before_comparing(self) -> None:
        # OT enum PHASE_2 (=2) vs ClinicalTrials.gov int 4 -- a real conflict across scales.
        out = drug_disagreements(
            {
                "ct_max_phase": [_sv(4, "clinicaltrials")],
                "max_stage": [_sv("PHASE_2", "opentargets")],
            }
        )
        assert len(out) == 1
        by_source = {v["source"]: v["display"] for v in out[0]["values"]}
        # Each source shows its own granularity: the int as 'phase N', OT in its own words.
        assert by_source["clinicaltrials"] == "phase 4"
        assert by_source["opentargets"] == "phase 2"

    def test_agreeing_sources_produce_no_false_positive(self) -> None:
        # All three agree at phase 4 (OT APPROVAL normalizes to 4) -- silence, not a disagreement.
        out = drug_disagreements(
            {
                "max_phase": [_sv(4, "chembl")],
                "ct_max_phase": [_sv(4, "clinicaltrials")],
                "max_stage": [_sv("APPROVAL", "opentargets")],
            }
        )
        assert out == []

    def test_near_agreement_within_a_phase_is_not_a_conflict(self) -> None:
        # ChEMBL phase 2 vs an OT 'phase 2/3' (2.5): half a phase apart -- near-agreement, withheld.
        out = drug_disagreements(
            {
                "max_phase": [_sv(2, "chembl")],
                "max_stage": [_sv("PHASE_2_3", "opentargets")],
            }
        )
        assert out == []

    def test_a_single_source_never_disagrees_with_itself(self) -> None:
        assert drug_disagreements({"ct_max_phase": [_sv(3, "clinicaltrials")]}) == []

    def test_no_phase_facts_yields_nothing(self) -> None:
        assert drug_disagreements({}) == []
        assert drug_disagreements({"smiles": [_sv("CCO", "chembl")]}) == []

    def test_unmappable_open_targets_stage_does_not_participate(self) -> None:
        # OT UNKNOWN is not comparable; with only one other source there is nothing to conflict
        # with, so no disagreement is manufactured from an unmapped value.
        out = drug_disagreements(
            {
                "ct_max_phase": [_sv(3, "clinicaltrials")],
                "max_stage": [_sv("UNKNOWN", "opentargets")],
            }
        )
        assert out == []

    def test_out_of_range_or_bool_ints_are_ignored(self) -> None:
        # A phase outside 0-4 (bad data) and a bool are not comparable phase values.
        out = drug_disagreements(
            {
                "max_phase": [_sv(9, "chembl")],
                "ct_max_phase": [_sv(True, "clinicaltrials")],
            }
        )
        assert out == []

    def test_a_conflict_among_three_shows_all_three_sources(self) -> None:
        out = drug_disagreements(
            {
                "max_phase": [_sv(4, "chembl")],
                "ct_max_phase": [_sv(4, "clinicaltrials")],
                "max_stage": [_sv("PHASE_1", "opentargets")],
            }
        )
        assert len(out) == 1
        # Two sources agree at 4 and one differs -- the reader sees the full picture, all three.
        assert {v["source"] for v in out[0]["values"]} == {
            "chembl",
            "clinicaltrials",
            "opentargets",
        }
