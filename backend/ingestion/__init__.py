"""Source adapters and the shared contract they implement.

Adapters are a plugin layer: one per source, all behind `SourceAdapter`. Entity
resolution deliberately is not -- that is typed cross-entity logic and stays cohesive.
"""

from __future__ import annotations

from backend.ingestion.base import (
    Fact,
    FactStatus,
    SourceAdapter,
    SourceRecord,
    fact,
    failed,
)

__all__ = [
    "Fact",
    "FactStatus",
    "SourceAdapter",
    "SourceRecord",
    "fact",
    "failed",
]
