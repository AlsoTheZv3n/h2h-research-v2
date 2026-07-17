"""Application settings. Values come from the environment or a local .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://h2h:h2h@localhost:5432/h2h",
        description="SQLAlchemy async DSN. asyncpg driver.",
    )
    redis_url: str = "redis://localhost:6379/0"

    # Detail briefs are assembled from persisted facts, so this only bounds staleness
    # after a re-ingest -- it is not a hot path against the sources.
    cache_ttl_seconds: int = 3600

    # How long the pre-warmer waits between passes over the catalog. A pass enriches
    # every not-yet-enriched drug; the interval only governs how often it re-checks
    # for drugs added since. Long by default: the whole point is to work quietly ahead
    # of demand, not to poll.
    prewarm_interval_seconds: int = 300

    # Optional: raises PubMed (E-utilities) rate limits. Never required.
    ncbi_api_key: str | None = None

    # E-utilities asks every client to identify itself, and this is not decoration:
    # "should be a complete and valid e-mail address of the software developer", so
    # NCBI can reach an operator whose script is misbehaving before they block the IP.
    # Defaulted rather than required -- a stranger's `docker compose up` must not die
    # on a field only we can fill -- but the default names the project, not a person
    # who never agreed to field the mail.
    ncbi_tool: str = "h2h-research"
    ncbi_email: str = "noreply@h2h-research.invalid"

    # The chat's synthesis half. Absent means the chat says so plainly rather than
    # breaking -- see services/chat_providers.py. The retrieval half needs neither of
    # these: embeddings run locally, so `docker compose up` always has working search.
    anthropic_api_key: str | None = None
    # Haiku, on the user's call ("should probably suffice"). Grounding an answer in
    # a handful of abstracts is not a hard reasoning task, and the guards
    # (_fabricated_pmids, _copies_source_text) catch a weak model's mistakes
    # regardless -- so the cheap, fast model is the right default. The provider sends
    # a plain completion (no adaptive thinking, no effort), which is the only shape
    # Haiku 4.5 accepts, and which also works on Opus if you override this.
    chat_model: str = "claude-haiku-4-5"

    # Keyless fallback. Empty by default rather than pointing at localhost:11434:
    # a default that guesses wrong turns "no model configured" -- which the UI states
    # honestly -- into "connection refused", which reads as a bug in this project.
    ollama_url: str = ""
    ollama_model: str = "llama3.1:8b"

    @field_validator("ncbi_tool", "ncbi_email")
    @classmethod
    def _blank_means_unset(cls, v: str, info: ValidationInfo) -> str:
        """An empty env var falls back to the default instead of winning.

        `.env.example` carries `NCBI_EMAIL=` with nothing after it, and copying it to
        `.env` is the documented first step. Without this, pydantic reads that as the
        string "" -- a *set* value, which beats the default -- and we would send
        `email=` empty on every request: the identification requirement quietly
        undone by the file that exists to explain it. An operator who wants no email
        cannot have one anyway; the choice is between our default and nothing.
        """
        if not v.strip():
            default = cls.model_fields[info.field_name or ""].default
            return str(default)
        return v.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
