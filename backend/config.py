"""Application settings. Values come from the environment or a local .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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

    # Optional: raises PubMed (E-utilities) rate limits. Never required.
    ncbi_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
