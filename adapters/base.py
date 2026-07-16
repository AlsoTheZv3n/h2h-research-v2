"""Shared adapter contract. This interface is the thing that graduates to the
main app unchanged: in the spike an adapter returns a SourceRecord we print;
in the app the same fetch() output gets persisted to Postgres."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceRecord:
    """Normalized result from one source for one drug."""
    source: str
    drug: str
    ok: bool
    fields: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "drug": self.drug,
            "ok": self.ok,
            "fields": self.fields,
            "provenance": self.provenance,
            "error": self.error,
        }


@runtime_checkable
class SourceAdapter(Protocol):
    name: str
    def fetch(self, drug: str) -> SourceRecord: ...
