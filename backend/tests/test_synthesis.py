"""The cancer page's derived synthesis (C1). Each statement is a disclosed threshold rule over an
existing fact; the tests prove-fail the thresholds (fires above, silent below) and pin the
derived-value discipline (an absent input yields no statement, never a 0-substituted one)."""

from __future__ import annotations

from backend.domain.synthesis import (
    CROWDED_PIPELINE,
    HIGH_ATTRITION,
    STALE_TRIAL_YEARS,
    WELL_STUDIED_TRIALS,
    WIDE_STAGE_GAP,
    cancer_synthesis,
    drug_synthesis,
)

LANDSCAPE = {
    "n_strong": 117,
    "targets": [
        {"symbol": "EGFR", "drug_status": "approved"},
        {"symbol": "KRAS", "drug_status": "unexploited"},
        {"symbol": "STK11", "drug_status": "unexploited"},
    ],
}
PIPELINE = {"total": 1072}
TRIALS = {"n_trials_scanned": 1000, "stopped": {"count": 172}}
SURVIVAL = {
    "staged": True,
    "by_stage": [
        {"stage": "Localized", "rate": 65.5},
        {"stage": "Regional", "rate": 38.2},
        {"stage": "Distant", "rate": 10.5},
    ],
}


def _blocks(statements: list[dict[str, str]]) -> set[str]:
    return {s["block"] for s in statements}


def _text_for(statements: list[dict[str, str]], block: str) -> str:
    return next(s["text"] for s in statements if s["block"] == block)


class TestCancerSynthesis:
    def test_a_rich_cancer_produces_a_statement_per_dimension(self) -> None:
        out = cancer_synthesis(LANDSCAPE, PIPELINE, TRIALS, SURVIVAL)
        assert _blocks(out) == {"target-landscape", "pipeline", "trial-reality", "survival"}
        # The unexploited opportunity is the finding, phrased as such.
        landscape_texts = [s["text"] for s in out if s["block"] == "target-landscape"]
        assert any("117" in t for t in landscape_texts)
        assert any("no drug anywhere" in t and "2 of the top" in t for t in landscape_texts)
        assert "Crowded field: 1,072" in _text_for(out, "pipeline")
        assert "172 of 1,000" in _text_for(out, "trial-reality")
        assert "66% localized vs 10% distant" in _text_for(out, "survival")

    def test_pipeline_threshold_flips_crowded_to_sparse(self) -> None:
        crowded = cancer_synthesis(None, {"total": CROWDED_PIPELINE}, None, None)
        assert "Crowded field" in _text_for(crowded, "pipeline")
        sparse = cancer_synthesis(None, {"total": CROWDED_PIPELINE - 1}, None, None)
        assert "Sparse field" in _text_for(sparse, "pipeline")

    def test_attrition_is_silent_below_the_threshold(self) -> None:
        below = cancer_synthesis(
            None, None, {"n_trials_scanned": 1000, "stopped": {"count": 100}}, None
        )
        assert below == []  # 10% < 15%
        at = cancer_synthesis(
            None,
            None,
            {"n_trials_scanned": 1000, "stopped": {"count": int(1000 * HIGH_ATTRITION)}},
            None,
        )
        assert _blocks(at) == {"trial-reality"}

    def test_stage_gap_is_silent_when_survival_does_not_hinge_on_stage(self) -> None:
        narrow = {
            "staged": True,
            "by_stage": [
                {"stage": "Localized", "rate": 50.0},
                {"stage": "Distant", "rate": 50.0 - (WIDE_STAGE_GAP - 1)},
            ],
        }
        assert cancer_synthesis(None, None, None, narrow) == []
        wide = {
            "staged": True,
            "by_stage": [
                {"stage": "Localized", "rate": 50.0},
                {"stage": "Distant", "rate": 50.0 - WIDE_STAGE_GAP},
            ],
        }
        assert _blocks(cancer_synthesis(None, None, None, wide)) == {"survival"}

    def test_a_leukemia_with_no_stage_decomposition_gets_no_stage_statement(self) -> None:
        # staged=False (leukemias): there is no localized/distant split to hinge on.
        unstaged = {"staged": False, "by_stage": []}
        assert cancer_synthesis(None, None, None, unstaged) == []

    def test_silent_stalling_fires_when_no_new_trial_in_years(self) -> None:
        # E3: no attrition inputs here, so only the stalling rule can fire on this trial fact.
        stalled = {"latest_registration": "2019-05-01"}
        out = cancer_synthesis(None, None, stalled, None, now_year=2026)
        assert (
            _text_for(out, "trial-reality") == "Silent stalling: no new trial registered since 2019"
        )

    def test_silent_stalling_is_silent_for_a_recently_registered_field(self) -> None:
        # A new trial within STALE_TRIAL_YEARS -> active, no stalling line.
        recent = {"latest_registration": "2025-01-01"}
        assert cancer_synthesis(None, None, recent, None, now_year=2026) == []

    def test_silent_stalling_fires_exactly_at_the_threshold(self) -> None:
        at = {"latest_registration": f"{2026 - STALE_TRIAL_YEARS}-01-01"}
        assert _blocks(cancer_synthesis(None, None, at, None, now_year=2026)) == {"trial-reality"}

    def test_silent_stalling_withheld_without_a_date_or_a_clock(self) -> None:
        # Missing latest_registration -> nothing (never inferred). No now_year -> rule skipped.
        assert cancer_synthesis(None, None, {"n_trials_scanned": 5}, None, now_year=2026) == []
        assert cancer_synthesis(None, None, {"latest_registration": "2010-01-01"}, None) == []

    def test_missing_inputs_yield_no_statements_never_a_zero(self) -> None:
        # The derived-value discipline: absent facts -> empty synthesis, not "0 targets / 0 drugs".
        assert cancer_synthesis(None, None, None, None) == []

    def test_no_unexploited_statement_when_none_are_unexploited(self) -> None:
        drugged = {"n_strong": 5, "targets": [{"symbol": "X", "drug_status": "approved"}]}
        out = cancer_synthesis(drugged, None, None, None)
        assert not any("unexploited" in s["text"] for s in out)
        assert any("5 strongly-associated" in s["text"] for s in out)


SELECTIVE = {"reference": {"gene_symbol": "EGFR", "target_pref_name": "EGFR"}, "n_targets": 1}
MULTI = {"reference": {"gene_symbol": "PDGFRA"}, "n_targets": 6}


def _text_for_block(statements: list[dict[str, str]], block: str) -> list[str]:
    return [s["text"] for s in statements if s["block"] == block]


class TestDrugSynthesis:
    def test_an_approved_selective_well_studied_drug_reads_as_such(self) -> None:
        # Osimertinib-shaped: approved, selective for EGFR, past the trials cut, with attrition.
        out = drug_synthesis(max_phase=4, selectivity=SELECTIVE, n_trials=384, has_terminated=True)
        clinical = _text_for_block(out, "clinical")
        assert "Approved — reached phase 4" in clinical
        assert any("Well-studied: 384" in t for t in clinical)
        assert "Terminated or withdrawn trials on record" in clinical
        assert "Selective for EGFR" in _text_for_block(out, "potency")

    def test_phase_below_4_reads_in_development(self) -> None:
        out = drug_synthesis(max_phase=2, selectivity=None, n_trials=None, has_terminated=None)
        assert "In development — reached phase 2" in _text_for_block(out, "clinical")

    def test_multi_target_drug_says_so(self) -> None:
        out = drug_synthesis(max_phase=None, selectivity=MULTI, n_trials=None, has_terminated=None)
        assert "Multi-target: 6 within 100x" in _text_for_block(out, "potency")

    def test_well_studied_is_silent_below_the_cut(self) -> None:
        below = drug_synthesis(
            max_phase=None, selectivity=None, n_trials=WELL_STUDIED_TRIALS - 1, has_terminated=None
        )
        assert below == []
        at = drug_synthesis(
            max_phase=None, selectivity=None, n_trials=WELL_STUDIED_TRIALS, has_terminated=None
        )
        assert any("Well-studied" in s["text"] for s in at)

    def test_no_attrition_statement_when_not_terminated(self) -> None:
        # has_terminated False is a measured "no", not a red flag -- no statement.
        out = drug_synthesis(max_phase=4, selectivity=None, n_trials=None, has_terminated=False)
        assert not any("Terminated" in s["text"] for s in out)

    def test_missing_inputs_yield_no_statements(self) -> None:
        assert (
            drug_synthesis(max_phase=None, selectivity=None, n_trials=None, has_terminated=None)
            == []
        )
