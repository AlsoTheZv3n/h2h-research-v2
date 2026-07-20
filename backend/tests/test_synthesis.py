"""The cancer page's derived synthesis (C1). Each statement is a disclosed threshold rule over an
existing fact; the tests prove-fail the thresholds (fires above, silent below) and pin the
derived-value discipline (an absent input yields no statement, never a 0-substituted one)."""

from __future__ import annotations

from backend.domain.synthesis import (
    CROWDED_PIPELINE,
    HIGH_ATTRITION,
    WIDE_STAGE_GAP,
    cancer_synthesis,
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

    def test_missing_inputs_yield_no_statements_never_a_zero(self) -> None:
        # The derived-value discipline: absent facts -> empty synthesis, not "0 targets / 0 drugs".
        assert cancer_synthesis(None, None, None, None) == []

    def test_no_unexploited_statement_when_none_are_unexploited(self) -> None:
        drugged = {"n_strong": 5, "targets": [{"symbol": "X", "drug_status": "approved"}]}
        out = cancer_synthesis(drugged, None, None, None)
        assert not any("unexploited" in s["text"] for s in out)
        assert any("5 strongly-associated" in s["text"] for s in out)
