"""Lazy, on-demand target briefs -- the target-side twin of services/cancer_briefs.py.

Same state machine (not_analyzed / enriching / ready), same in-flight dedup, same
stale-while-revalidate. Kept parallel rather than generalized so the other brief services are
untouched; BriefState is the one shared piece, imported rather than redefined.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.cache import invalidate_target_detail
from backend.config import get_settings
from backend.db import get_sessionmaker
from backend.ingestion.base import utcnow
from backend.ingestion.enrich_target import TargetEnrichStats, enrich_target
from backend.ingestion.http import build_client
from backend.models import Target
from backend.repositories.cancers import CancerRepository
from backend.services.briefs import BriefState

logger = logging.getLogger(__name__)

# Targets currently being enriched, so N readers of one page cause one fetch. In-process only,
# and harmless to double-run because the upserts are idempotent.
_in_flight: dict[str, asyncio.Task[None]] = {}

_INTERACTIVE_TIMEOUT = 30.0
_INTERACTIVE_ATTEMPTS = 2
# One source (the Open Targets reverse query), a few seconds; 30s is ample headroom.
_ENRICH_DEADLINE = 30.0


async def _enrich_in_background(ensembl_id: str, maker: async_sessionmaker[AsyncSession]) -> None:
    """Fetch the source for one target, in its own session (the triggering request has
    already returned, so its session is closed)."""
    try:
        async with maker() as session:
            target = await session.get(Target, ensembl_id)
            if target is None:
                return
            catalog_ids = await CancerRepository(session).all_cancer_ids()
            async with build_client(
                timeout=_INTERACTIVE_TIMEOUT, attempts=_INTERACTIVE_ATTEMPTS
            ) as client:
                stats = TargetEnrichStats()
                await asyncio.wait_for(
                    enrich_target(session, target, client, catalog_ids, stats, commit_each=True),
                    timeout=_ENRICH_DEADLINE,
                )
                await session.commit()
            await invalidate_target_detail(ensembl_id)
            logger.info(
                "lazily enriched target %s: %d facts, %d source failures",
                ensembl_id,
                stats.facts_written,
                stats.records_failed,
            )
    except TimeoutError:
        logger.warning(
            "lazy target enrichment of %s timed out after %.0fs", ensembl_id, _ENRICH_DEADLINE
        )
    except Exception as exc:
        logger.warning("lazy target enrichment of %s failed: %s", ensembl_id, exc)
    finally:
        _in_flight.pop(ensembl_id, None)


def _is_stale(last_enriched_at: datetime) -> bool:
    return last_enriched_at < utcnow() - timedelta(days=get_settings().freshness_days)


def _start_refresh(ensembl_id: str, maker: async_sessionmaker[AsyncSession] | None) -> None:
    task = asyncio.create_task(_enrich_in_background(ensembl_id, maker or get_sessionmaker()))
    _in_flight[ensembl_id] = task


async def get_or_start_target_brief(
    session: AsyncSession,
    ensembl_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Where is this target's brief, and start building it if nobody has. Returns immediately;
    enrichment runs in the background. See get_or_start_cancer_brief."""
    target = await session.get(Target, ensembl_id)
    if target is None:
        return BriefState.NOT_ANALYZED  # caller 404s; nothing to enrich

    # Already enriched: serve the stored brief. The in-flight check is after this so a
    # background refresh never flips a ready brief back to ENRICHING and blanks the page.
    if target.last_enriched_at is not None:
        if _is_stale(target.last_enriched_at) and ensembl_id not in _in_flight:
            _start_refresh(ensembl_id, maker)
            logger.info("stale-while-revalidate: background refresh for target %s", ensembl_id)
        return BriefState.READY

    if ensembl_id in _in_flight:
        return BriefState.ENRICHING
    _start_refresh(ensembl_id, maker)
    logger.info("lazy target enrichment started for %s", ensembl_id)
    return BriefState.ENRICHING


async def retry_target_brief(
    session: AsyncSession,
    ensembl_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Re-fetch the source for a target, even one already enriched -- for when Open Targets was
    down. Facts upsert on (target, key, source), so a recovered source overwrites its
    source_failed row. Collapses onto an in-flight run."""
    if ensembl_id in _in_flight:
        return BriefState.ENRICHING

    target = await session.get(Target, ensembl_id)
    if target is None:
        return BriefState.NOT_ANALYZED

    _start_refresh(ensembl_id, maker)
    logger.info("retry target enrichment started for %s", ensembl_id)
    return BriefState.ENRICHING


def is_target_enriching(ensembl_id: str) -> bool:
    return ensembl_id in _in_flight
