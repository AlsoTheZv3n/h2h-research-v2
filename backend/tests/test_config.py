"""Settings that survive the documented setup path.

`.env.example` is not decoration: "copy it to .env" is step one of the README, so
every value in it is a real input this code will see.
"""

from __future__ import annotations

import pytest

from backend.config import Settings


class TestNcbiIdentification:
    def test_defaults_identify_the_client(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.ncbi_tool == "h2h-research"
        assert "@" in s.ncbi_email

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_blank_env_var_falls_back_rather_than_winning(
        self, blank: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The trap `.env.example` sets: `NCBI_EMAIL=` with nothing after it.

        pydantic reads that as a set value of "", which beats the default -- so we
        would send `email=` empty to NCBI on every request and undo the whole point
        of identifying ourselves. Nothing raises; requests just start being throttled
        one day, for a reason invisible from this side.
        """
        monkeypatch.setenv("NCBI_EMAIL", blank)
        monkeypatch.setenv("NCBI_TOOL", blank)

        s = Settings(_env_file=None)  # type: ignore[call-arg]

        assert s.ncbi_email == "noreply@h2h-research.invalid"
        assert s.ncbi_tool == "h2h-research"

    def test_a_real_address_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NCBI_EMAIL", " dev@example.org ")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.ncbi_email == "dev@example.org"
