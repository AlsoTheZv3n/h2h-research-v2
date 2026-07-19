"""Lazy, on-demand cancer briefs -- the disease-side twin of services/briefs.py.

Same state machine (not_analyzed / enriching / ready), same in-flight dedup, same
stale-while-revalidate. Kept as a parallel module rather than a generalized one so the
drug brief service is untouched; the BriefState enum is the one shared piece, imported
rather than redefined. See briefs.py for the reasoning behind each choice.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.cache import invalidate_cancer_detail
from backend.config import get_settings
from backend.db import get_sessionmaker
from backend.ingestion.base import utcnow
from backend.ingestion.enrich_cancer import CancerEnrichStats, build_cancer_sources, enrich_cancer
from backend.ingestion.http import build_client
from backend.models import Cancer
from backend.services.briefs import BriefState

logger = logging.getLogger(__name__)

# Cancers currently being enriched, so N readers of one page cause one fetch. In-process
# only, like the drug side, and harmless to double-run because the upserts are idempotent.
_in_flight: dict[str, asyncio.Task[None]] = {}

_INTERACTIVE_TIMEOUT = 30.0
_INTERACTIVE_ATTEMPTS = 2
# Five sources now (Open Targets landscape + pipeline, Eurostat mortality, SEER survival,
# ClinicalTrials.gov trial reality), each a few seconds; 90s leaves headroom for the slower stat
# endpoints and CT.gov's two requests without stalling the page.
_ENRICH_DEADLINE = 90.0


async def _enrich_in_background(disease_id: str, maker: async_sessionmaker[AsyncSession]) -> None:
    """Fetch every source for one cancer, in its own session (the request that triggered
    this has already returned, so the caller's session is closed)."""
    try:
        async with maker() as session:
            cancer = await session.get(Cancer, disease_id)
            if cancer is None:
                return
            async with build_client(
                timeout=_INTERACTIVE_TIMEOUT, attempts=_INTERACTIVE_ATTEMPTS
            ) as client:
                stats = CancerEnrichStats()
                sources = await build_cancer_sources(session)
                await asyncio.wait_for(
                    enrich_cancer(
                        session,
                        cancer,
                        client,
                        sources,
                        stats,
                        commit_each=True,
                    ),
                    timeout=_ENRICH_DEADLINE,
                )
                await session.commit()
            await invalidate_cancer_detail(disease_id)
            logger.info(
                "lazily enriched cancer %s: %d facts, %d source failures",
                disease_id,
                stats.facts_written,
                stats.records_failed,
            )
    except TimeoutError:
        logger.warning(
            "lazy cancer enrichment of %s timed out after %.0fs", disease_id, _ENRICH_DEADLINE
        )
    except Exception as exc:
        logger.warning("lazy cancer enrichment of %s failed: %s", disease_id, exc)
    finally:
        _in_flight.pop(disease_id, None)


def _is_stale(last_enriched_at: datetime) -> bool:
    return last_enriched_at < utcnow() - timedelta(days=get_settings().freshness_days)


def _start_refresh(disease_id: str, maker: async_sessionmaker[AsyncSession] | None) -> None:
    task = asyncio.create_task(_enrich_in_background(disease_id, maker or get_sessionmaker()))
    _in_flight[disease_id] = task


async def get_or_start_cancer_brief(
    session: AsyncSession,
    disease_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Where is this cancer's brief, and start building it if nobody has. Returns
    immediately; enrichment runs in the background. See get_or_start_brief."""
    cancer = await session.get(Cancer, disease_id)
    if cancer is None:
        return BriefState.NOT_ANALYZED  # caller 404s; nothing to enrich

    # Already enriched: serve the stored brief. The in-flight check is after this so a
    # background refresh never flips a ready brief back to ENRICHING and blanks the page.
    if cancer.last_enriched_at is not None:
        if _is_stale(cancer.last_enriched_at) and disease_id not in _in_flight:
            _start_refresh(disease_id, maker)
            logger.info("stale-while-revalidate: background refresh for cancer %s", disease_id)
        return BriefState.READY

    if disease_id in _in_flight:
        return BriefState.ENRICHING
    _start_refresh(disease_id, maker)
    logger.info("lazy cancer enrichment started for %s", disease_id)
    return BriefState.ENRICHING


async def retry_cancer_brief(
    session: AsyncSession,
    disease_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Re-fetch every source for a cancer, even one already enriched -- for when a source
    was down. Facts upsert on (disease, key, source), so a recovered source overwrites
    its source_failed rows. Collapses onto an in-flight run, so a double-click is one fetch."""
    if disease_id in _in_flight:
        return BriefState.ENRICHING

    cancer = await session.get(Cancer, disease_id)
    if cancer is None:
        return BriefState.NOT_ANALYZED

    _start_refresh(disease_id, maker)
    logger.info("retry cancer enrichment started for %s", disease_id)
    return BriefState.ENRICHING


def is_cancer_enriching(disease_id: str) -> bool:
    return disease_id in _in_flight
