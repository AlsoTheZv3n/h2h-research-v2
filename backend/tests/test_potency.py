"""Potency summarization, against adagrasib's real ChEMBL response.

The golden set in fixtures/adagrasib_ic50.json is the live payload, captured and
trimmed to the fields the summarizer reads. It is committed because ChEMBL is down
about as often as it is up, and a golden test that needs the network is not a test.

What it proves is the module's reason to exist: the spike could only say "adagrasib
has 30 IC50s", and those 30 rows turn out to hold 23 off-target measurements --
cell lines, a CDK7 assay, and two SARS-CoV-2 screens. The answer is in the other 7.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.domain import summarize_ic50

FIXTURES = Path(__file__).parent / "fixtures"
KRAS = "CHEMBL2189121"  # adagrasib's mechanism target: GTPase KRas


@pytest.fixture(scope="session")
def adagrasib() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((FIXTURES / "adagrasib_ic50.json").read_text())
    return payload


@pytest.fixture
def activities(adagrasib: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = adagrasib["activities"]
    return rows


def _activity(
    target_id: str | None,
    target_name: str,
    value: float | None,
    *,
    relation: str = "=",
    units: str = "nM",
) -> dict[str, Any]:
    return {
        "target_chembl_id": target_id,
        "target_pref_name": target_name,
        "standard_value": None if value is None else str(value),
        "standard_relation": relation,
        "standard_units": units,
        "standard_type": "IC50",
    }


class TestFixtureIsTheRealThing:
    def test_the_fixture_matches_what_chembl_returned(self, adagrasib: dict[str, Any]) -> None:
        """Guards the premise. If this drifts, every expectation below is fiction."""
        assert adagrasib["total_count"] == 30
        assert len(adagrasib["activities"]) == 30
        assert adagrasib["mechanism_target_chembl_id"] == KRAS
        assert adagrasib["mechanism_of_action"] == "GTPase KRas inhibitor"


class TestAdagrasibGoldenSet:
    def test_off_target_noise_is_excluded(self, activities: list[dict[str, Any]]) -> None:
        """23 of the 30 rows measure something that is not KRAS."""
        s = summarize_ic50(activities, KRAS)

        assert s.n_activities == 30
        assert s.n_on_target == 7
        assert sum(s.off_target.values()) == 23
        # The rows that make a naive average meaningless, by name.
        assert s.off_target["SARS-CoV-2"] == 2
        assert s.off_target["MIA PaCa-2"] == 6
        assert s.off_target["NCI-H358"] == 6

    def test_censored_bounds_are_flagged_not_averaged(
        self, activities: list[dict[str, Any]]
    ) -> None:
        """One on-target row is a "<" bound: counted, reported, kept out of the median."""
        s = summarize_ic50(activities, KRAS)

        assert s.n_censored == 1
        assert s.n_exact == 6
        assert s.n_on_target == s.n_exact + s.n_censored

    def test_the_headline_is_a_sane_on_target_potency(
        self, activities: list[dict[str, Any]]
    ) -> None:
        """Median 10 nM for a KRAS G12C inhibitor is a number a reader can act on.

        The raw spread across all 30 rows runs to 50,000 nM -- that outlier is an
        off-target screen, and quoting it would misrepresent the drug.
        """
        s = summarize_ic50(activities, KRAS)

        assert s.is_decision_grade
        assert s.median_nm == pytest.approx(10.0)
        assert s.min_nm == pytest.approx(5.0)
        assert s.max_nm == pytest.approx(133.0)

        raw_max = max(float(a["standard_value"]) for a in activities if a["standard_value"])
        assert raw_max == pytest.approx(50000.0)
        assert s.max_nm is not None and s.max_nm < raw_max / 100

    def test_units_are_consistent(self, activities: list[dict[str, Any]]) -> None:
        """Every adagrasib row happens to be nM -- so nothing was dropped for units."""
        s = summarize_ic50(activities, KRAS)
        assert s.other_units == {}

    def test_what_was_discarded_stays_visible(self, activities: list[dict[str, Any]]) -> None:
        """6 of 30 rows carry the headline. A summary hiding that is the same lie
        the spike told, in nicer clothes."""
        d = summarize_ic50(activities, KRAS).as_dict()

        assert d["n_activities"] == 30
        assert d["n_exact"] == 6
        assert d["n_censored"] == 1
        assert sum(d["off_target"].values()) == 23
        assert d["units"] == "nM"
        assert d["target_chembl_ids"] == [KRAS]


class TestEdges:
    def test_without_a_known_target_it_refuses_to_quote_a_potency(
        self, activities: list[dict[str, Any]]
    ) -> None:
        """No target means no way to separate signal from an off-target screen.
        Say so, rather than averaging 30 rows into a confident wrong number."""
        s = summarize_ic50(activities, None)

        assert s.median_nm is None
        assert s.is_decision_grade is False
        assert s.n_activities == 30
        assert sum(s.off_target.values()) == 30

    def test_only_censored_rows_yields_no_median(self) -> None:
        rows = [_activity(KRAS, "GTPase KRas", 10000.0, relation=">") for _ in range(3)]
        s = summarize_ic50(rows, KRAS)

        assert s.n_on_target == 3
        assert s.n_censored == 3
        assert s.median_nm is None
        assert s.is_decision_grade is False

    def test_no_activities_at_all(self) -> None:
        s = summarize_ic50([], KRAS)
        assert s.n_activities == 0
        assert s.is_decision_grade is False

    def test_mixed_units_are_dropped_and_reported(self) -> None:
        """Adagrasib is all-nM, but other molecules are not: reading a 0.05 uM row
        as 0.05 nM would be a 1000x error in the headline number."""
        rows = [
            _activity(KRAS, "GTPase KRas", 5.0),
            _activity(KRAS, "GTPase KRas", 0.05, units="uM"),
        ]
        s = summarize_ic50(rows, KRAS)

        assert s.n_on_target == 2
        assert s.n_exact == 1
        assert s.other_units == {"uM": 1}
        assert s.median_nm == pytest.approx(5.0)

    def test_median_not_mean(self) -> None:
        """One outlier must not drag the headline; a mean here would read ~20,005."""
        rows = [_activity(KRAS, "K", v) for v in (5.0, 6.0, 7.0, 8.0, 100000.0)]
        assert summarize_ic50(rows, KRAS).median_nm == pytest.approx(7.0)

    def test_missing_relation_counts_as_exact(self) -> None:
        """ChEMBL omits standard_relation on some rows; "=" is the documented default."""
        rows = [{"target_chembl_id": KRAS, "standard_value": "5", "standard_units": "nM"}]
        s = summarize_ic50(rows, KRAS)

        assert s.n_exact == 1
        assert s.median_nm == pytest.approx(5.0)


class TestMultiTargetDrugs:
    """A multi-kinase inhibitor has several real targets.

    Taking mechanisms[0] would file the rest as off-target -- a false claim about the
    drug's defining mechanism -- and quote the median against whichever target ChEMBL
    happened to return first. Same defect as molecules[0], one endpoint over.
    """

    ABL1 = "CHEMBL1862"
    SRC = "CHEMBL267"

    def test_every_mechanism_target_is_on_target(self) -> None:
        rows = [
            _activity(self.ABL1, "ABL1", 1.0),
            _activity(self.SRC, "SRC", 3.0),
            _activity("CHEMBL_OTHER", "some cell line", 40000.0),
        ]
        s = summarize_ic50(rows, [self.ABL1, self.SRC])

        assert s.n_on_target == 2
        assert s.n_exact == 2
        assert s.median_nm == pytest.approx(2.0)
        assert s.off_target == {"some cell line": 1}
        assert s.target_chembl_ids == sorted([self.ABL1, self.SRC])

    def test_taking_only_the_first_target_would_misreport(self) -> None:
        """Pins the regression: with just ABL1, SRC becomes 'off-target'."""
        rows = [_activity(self.ABL1, "ABL1", 1.0), _activity(self.SRC, "SRC", 3.0)]

        both = summarize_ic50(rows, [self.ABL1, self.SRC])
        first_only = summarize_ic50(rows, [self.ABL1])

        assert both.n_on_target == 2
        assert first_only.n_on_target == 1
        assert "SRC" in first_only.off_target

    def test_a_single_id_is_still_accepted(self) -> None:
        """Convenience: most drugs have one target, and callers should not wrap it."""
        s = summarize_ic50([_activity(KRAS, "GTPase KRas", 10.0)], KRAS)
        assert s.n_on_target == 1
        assert s.target_chembl_ids == [KRAS]
