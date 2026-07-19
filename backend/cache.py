"""Redis cache wiring."""

from __future__ import annotations

import logging

import redis.asyncio as redis

from backend.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

# Bumped whenever the cached DrugDetail shape changes. Without it, a brief serialized
# by the previous schema outlives the deploy and deserializes with the new fields at
# their defaults -- e.g. a pre-`smiles` brief comes back with smiles=None, and the
# structure card, which now reads only that field, declares a structure missing that is
# actually there. The version is part of the key, so old-shape entries are simply never
# read again and expire on their own.
_DETAIL_SCHEMA_VERSION = "v2"


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def detail_cache_key(chembl_id: str) -> str:
    """The one place the detail cache key is spelled, so the read, the write and every
    invalidation cannot drift -- and so the schema version travels with all of them."""
    return f"drug:detail:{_DETAIL_SCHEMA_VERSION}:{chembl_id}"


# The cancer brief has its own shape and its own version, so a change to one cannot
# strand entries of the other. v4: target_landscape fact reshaped to carry the strong-
# association count + threshold beside the displayed targets. v5: each displayed target
# gained an Ensembl id + a drugged/in-development/unexploited status. v6: the trial-reality
# block (ClinicalTrials.gov by condition) added a `trial_reality` fact to the brief.
_CANCER_DETAIL_SCHEMA_VERSION = "v6"


def cancer_detail_cache_key(disease_id: str) -> str:
    """The disease-side twin of detail_cache_key."""
    return f"cancer:detail:{_CANCER_DETAIL_SCHEMA_VERSION}:{disease_id}"


async def invalidate_detail(chembl_id: str) -> None:
    """Drop a drug's cached brief. Best-effort: a dead cache degrades latency, never
    correctness, so a failure here is logged and swallowed rather than raised."""
    try:
        await get_redis().delete(detail_cache_key(chembl_id))
    except Exception as exc:
        logger.warning("detail cache invalidation failed for %s: %s", chembl_id, exc)


async def invalidate_cancer_detail(disease_id: str) -> None:
    """Drop a cancer's cached brief. Best-effort, like invalidate_detail."""
    try:
        await get_redis().delete(cancer_detail_cache_key(disease_id))
    except Exception as exc:
        logger.warning("cancer detail cache invalidation failed for %s: %s", disease_id, exc)


# The target brief has its own shape and its own version, so a change to one entity's brief
# cannot strand entries of another. v1: the first target detail -- associated_cancers (the
# Open Targets reverse query, filtered to our cancer catalog) plus the drugs our catalog holds
# against the target.
_TARGET_DETAIL_SCHEMA_VERSION = "v1"


def target_detail_cache_key(ensembl_id: str) -> str:
    """The target-side twin of detail_cache_key."""
    return f"target:detail:{_TARGET_DETAIL_SCHEMA_VERSION}:{ensembl_id}"


async def invalidate_target_detail(ensembl_id: str) -> None:
    """Drop a target's cached brief. Best-effort, like invalidate_detail."""
    try:
        await get_redis().delete(target_detail_cache_key(ensembl_id))
    except Exception as exc:
        logger.warning("target detail cache invalidation failed for %s: %s", ensembl_id, exc)


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


def reset_redis() -> None:
    """Drop the client without awaiting its close. For tests: the singleton binds to the
    loop that opened it, so the next test (a fresh loop) must get a fresh client. Awaiting
    aclose() here can hang when a just-cancelled background task still holds a connection,
    so the reference is simply dropped -- the OS reclaims the socket, and in a test that
    is harmless."""
    global _client
    _client = None
