"""Gate 1 resolution: a catalog cancer -> a source category, by MONDO ancestry ONLY.

The load-bearing rules, each with a mutation that turns its test red:
  - resolution is by id/ancestry, never by name (label) string;
  - a rollup can never be served without the entity its numbers describe;
  - `unmapped` is a distinct state, not a collapsed empty/failure;
  - the CLOSEST mapped ancestor wins when a source nests categories (SEER leukaemia > AML).
"""

from __future__ import annotations

import pytest

from backend.services.disease_map import MatchType, Resolution, resolve

# real MONDO ids
BREAST, LUNG, PANCREAS, LEUKEMIA, AML = (
    "MONDO_0007254",
    "MONDO_0008903",
    "MONDO_0009831",
    "MONDO_0005059",
    "MONDO_0018874",
)
NSCLC, SCLC, TNBC, PDAC, ROOT = (
    "MONDO_0005233",
    "MONDO_0008433",
    "MONDO_0005494",
    "MONDO_0005184",
    "MONDO_0004992",
)

EUROSTAT = {
    BREAST: ("C50", "Breast (C50)"),
    LUNG: ("C33_C34", "Trachea, bronchus & lung (C33-C34)"),
    PANCREAS: ("C25", "Pancreas (C25)"),
    LEUKEMIA: ("C91-C95", "Leukaemia (C91-C95)"),
}
EUROSTAT_ANC: dict[str, frozenset[str]] = {k: frozenset() for k in EUROSTAT}  # non-nested

SEER = {LEUKEMIA: ("90", "Leukemia"), AML: ("96", "Acute Myeloid Leukemia (AML)")}
# leukaemia is AML's ancestor
SEER_ANC: dict[str, frozenset[str]] = {AML: frozenset({LEUKEMIA}), LEUKEMIA: frozenset()}


class TestResolve:
    def test_exact_when_the_cancer_is_the_mapped_category(self) -> None:
        r = resolve(BREAST, [ROOT], EUROSTAT, EUROSTAT_ANC)
        assert r.match_type is MatchType.EXACT
        assert (r.target_mondo, r.source_code) == (BREAST, "C50")

    def test_nsclc_and_sclc_rollup_to_lung_while_lung_is_exact(self) -> None:
        # The design case: a specific page shows the broader lung-cancer figures -> rollup,
        # and it MUST name lung as the target so it is never passed off as NSCLC's.
        for narrow in (NSCLC, SCLC):
            r = resolve(narrow, [LUNG, ROOT], EUROSTAT, EUROSTAT_ANC)
            assert r.match_type is MatchType.ROLLUP
            assert r.target_mondo == LUNG
            assert r.source_code == "C33_C34"
            assert "lung" in (r.source_label or "").lower()
        assert resolve(LUNG, [ROOT], EUROSTAT, EUROSTAT_ANC).match_type is MatchType.EXACT

    def test_tnbc_rolls_up_to_breast_and_pdac_to_pancreas(self) -> None:
        assert resolve(TNBC, [BREAST, ROOT], EUROSTAT, EUROSTAT_ANC).target_mondo == BREAST
        assert resolve(PDAC, [PANCREAS, ROOT], EUROSTAT, EUROSTAT_ANC).target_mondo == PANCREAS

    def test_closest_wins_when_a_source_nests_categories(self) -> None:
        # An AML subtype has BOTH AML and leukaemia as mapped SEER ancestors. It must roll up
        # to AML (the closest), NOT leukaemia -- else the more-specific site is thrown away.
        subtype = "MONDO_0016736"  # some AML subtype
        r = resolve(subtype, [AML, LEUKEMIA, ROOT], SEER, SEER_ANC)
        assert r.match_type is MatchType.ROLLUP
        assert (r.target_mondo, r.source_code) == (AML, "96")
        # AML itself is exact against its own SEER site.
        assert resolve(AML, [LEUKEMIA, ROOT], SEER, SEER_ANC).match_type is MatchType.EXACT

    def test_unmapped_when_no_ancestor_is_a_mapped_category(self) -> None:
        r = resolve("MONDO_9999999", [ROOT], EUROSTAT, EUROSTAT_ANC)
        assert r.match_type is MatchType.UNMAPPED
        assert not r.available

    def test_ambiguous_tie_is_unmapped_never_a_silent_pick(self) -> None:
        # Two incomparable mapped ancestors (breast AND lung, neither nested) -> a genuine
        # tie. No silent tie-break: honestly unmapped.
        r = resolve("MONDO_TIE", [BREAST, LUNG, ROOT], EUROSTAT, EUROSTAT_ANC)
        assert r.match_type is MatchType.UNMAPPED

    def test_a_lymphoid_leukemia_keeps_its_leukemia_survival_because_nhl_is_unmapped(self) -> None:
        # MONDO dual-classifies lymphoid leukemias (CLL, ALL) under BOTH leukemia AND non-Hodgkin
        # lymphoma. If NHL were a mapped SEER category, such a cancer would hit two incomparable
        # mapped ancestors -> a tie -> UNMAPPED, silently dropping its real leukemia survival.
        cll, nhl = "MONDO_0004948", "MONDO_0018908"
        # The real SEER map omits NHL, so leukemia is the only hit -> the CLL keeps its survival.
        r = resolve(cll, [LEUKEMIA, nhl, ROOT], SEER, SEER_ANC)
        assert r.match_type is MatchType.ROLLUP
        assert r.source_code == "90"
        # The contrapositive that justifies the omission: had NHL been mapped too, resolve() would
        # see two incomparable leaves and (correctly, no silent pick) return UNMAPPED.
        seer_with_nhl = {**SEER, nhl: ("86", "Non-Hodgkin Lymphoma")}
        anc = {**SEER_ANC, nhl: frozenset()}
        tied = resolve(cll, [LEUKEMIA, nhl, ROOT], seer_with_nhl, anc)
        assert tied.match_type is MatchType.UNMAPPED

    def test_resolution_matches_ids_not_labels(self) -> None:
        # A map whose LABEL says "breast" but whose key is an unrelated MONDO. A cancer with
        # breast's real id (not in this map, no mapped ancestor) must be UNMAPPED -- proving
        # resolution never matches the label text. Name-match this and it would wrongly hit.
        misleading = {"MONDO_0000001": ("X", "Breast cancer statistics")}
        r = resolve(BREAST, [ROOT], misleading, {"MONDO_0000001": frozenset()})
        assert r.match_type is MatchType.UNMAPPED


class TestResolutionInvariants:
    def test_a_rollup_cannot_exist_without_its_target_entity(self) -> None:
        # G1-T2: the whole point is that a broader entity's figures are NAMED. A rollup
        # (or exact) with no target/label is forbidden at construction.
        with pytest.raises(ValueError):
            Resolution(MatchType.ROLLUP)
        with pytest.raises(ValueError):
            Resolution(MatchType.EXACT, target_mondo=BREAST)  # target but no label

    def test_unmapped_is_a_distinct_state(self) -> None:
        # G1-T4: unmapped must not collapse into "available". The three states are distinct.
        assert Resolution(MatchType.UNMAPPED).available is False
        assert Resolution(MatchType.ROLLUP, LUNG, "C33_C34", "lung").available is True
        assert len({MatchType.EXACT, MatchType.ROLLUP, MatchType.UNMAPPED}) == 3
