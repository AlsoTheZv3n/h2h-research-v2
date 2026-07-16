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
from backend.ingestion.chembl import ChEMBLAdapter
from backend.ingestion.clinicaltrials import ClinicalTrialsAdapter
from backend.ingestion.http import USER_AGENT, RetryTransport, build_client
from backend.ingestion.opentargets import OpenTargetsAdapter
from backend.ingestion.pubmed import PubMedAdapter

__all__ = [
    "USER_AGENT",
    "ChEMBLAdapter",
    "ClinicalTrialsAdapter",
    "Fact",
    "FactStatus",
    "OpenTargetsAdapter",
    "PubMedAdapter",
    "RetryTransport",
    "SourceAdapter",
    "SourceRecord",
    "build_client",
    "fact",
    "failed",
]
