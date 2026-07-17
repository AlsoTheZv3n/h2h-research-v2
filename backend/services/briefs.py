"""Lazy, on-demand enrichment.

The alternative was pre-enriching thousands of drugs against a source that 500s a
third of the time -- hours of work to make a catalog that a user opens ten pages of.
Instead the first person to open a drug pays for it, once, and everyone after gets
it from Postgres. ChEMBL being down stops being a blocker and becomes "open it again
later", which the honest failure state already says out loud.

The state machine the API exposes:

    not_analyzed  nobody has ever asked the sources about this drug. NOT "no data".
    enriching     a fetch is in flight right now; come back in a moment.
    ready         facts are stored; the brief is served from them.

`not_analyzed` is a fourth state alongside a fact's ok/empty/source_failed, and it
means something none of those do: we have not looked. Collapsing it into "empty"
would be this project's founding bug, one level up again.
"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db import get_sessionmaker
from backend.ingestion.enrich import EnrichStats, enrich_drug
from backend.ingestion.http import build_client
from backend.models import Drug
from backend.repositories import DrugRepository

logger = logging.getLogger(__name__)


class BriefState(StrEnum):
    NOT_ANALYZED = "not_analyzed"
    ENRICHING = "enriching"
    READY = "ready"


# Drugs currently being enriched, so N readers of the same page cause one fetch and
# not N. In-process only: this is a single-instance app, and the alternative (a Redis
# lock) buys correctness we do not yet need at a complexity we would have to maintain.
# The upsert semantics make a duplicate run harmless anyway -- this is about not
# hammering ChEMBL, not about consistency.
_in_flight: dict[str, asyncio.Task[None]] = {}

# A tighter budget than the bulk loader's. The loader can afford 4 retries against a
# 120s timeout -- nobody is watching it. Here somebody is: measured, that budget lets
# a single stalled ChEMBL request run ~8 minutes, and the reader spends all of it
# looking at "analyzing". Failing at ~35s and showing a red "chembl unavailable" chip
# is the better answer -- it is honest, the rest of the brief is already on screen,
# and re-opening the page tries again.
_INTERACTIVE_TIMEOUT = 30.0
_INTERACTIVE_ATTEMPTS = 2

# Belt and braces: even 2 x 30s x four adapters could crawl if every one of them
# stalls. Past this the brief is finished with whatever came back.
_ENRICH_DEADLINE = 90.0


async def _enrich_in_background(chembl_id: str, maker: async_sessionmaker[AsyncSession]) -> None:
    """Fetch every source for one drug, in its own session.

    Its own session because the request that triggered this has already returned:
    the caller's session is closed by the time this runs.
    """
    try:
        async with maker() as session:
            drug = await session.get(Drug, chembl_id)
            if drug is None:
                return
            async with build_client(
                timeout=_INTERACTIVE_TIMEOUT, attempts=_INTERACTIVE_ATTEMPTS
            ) as client:
                from backend.ingestion.enrich import build_adapters, build_literature_fetcher

                stats = EnrichStats()
                await asyncio.wait_for(
                    enrich_drug(
                        session,
                        drug,
                        build_adapters(client),
                        stats,
                        build_literature_fetcher(client),
                    ),
                    timeout=_ENRICH_DEADLINE,
                )
                await session.commit()
            logger.info(
                "lazily enriched %s: %d facts, %d source failures",
                chembl_id,
                stats.facts_written,
                stats.records_failed,
            )
    except TimeoutError:
        # Past the deadline. The drug stays not_analyzed rather than being stamped
        # with a half-brief: re-opening the page retries, which is the honest offer.
        logger.warning("lazy enrichment of %s timed out after %.0fs", chembl_id, _ENRICH_DEADLINE)
    except Exception as exc:
        logger.warning("lazy enrichment of %s failed: %s", chembl_id, exc)
    finally:
        _in_flight.pop(chembl_id, None)


async def get_or_start_brief(
    session: AsyncSession,
    chembl_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Where is this drug's brief, and start building it if nobody has.

    Returns immediately; enrichment runs in the background. The page shows an honest
    "analyzing" state and polls, rather than holding an HTTP request open for the
    30-60s ChEMBL routinely takes.

    `maker` builds the background task's own session -- the request's session is
    closed by the time that task runs. Injectable because the default reads the
    DATABASE_URL from settings, which in a test is not the database the test is
    looking at: the work would land in the developer's dev database and the
    assertions would fail against an empty one.
    """
    if chembl_id in _in_flight:
        return BriefState.ENRICHING

    repo = DrugRepository(session)
    drug = await repo.get(chembl_id)
    if drug is None:
        return BriefState.NOT_ANALYZED  # caller 404s; nothing to enrich

    if drug.last_enriched_at is not None:
        return BriefState.READY

    task = asyncio.create_task(_enrich_in_background(chembl_id, maker or get_sessionmaker()))
    _in_flight[chembl_id] = task
    logger.info("lazy enrichment started for %s", chembl_id)
    return BriefState.ENRICHING


async def retry_brief(
    session: AsyncSession,
    chembl_id: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> BriefState:
    """Re-fetch every source for a drug, even one already enriched.

    The normal path serves a READY brief from storage and never looks again, which is
    right for the common case. Retry is for the other one: a source was down when we
    last looked, the brief carries its source_failed rows, and the reader is asking us
    to look again. Facts upsert on (drug, key, source), so a source that has recovered
    overwrites its failed rows with real values, and one still down just rewrites the
    same source_failed -- honest either way, and never worse than before.

    Collapses onto the in-flight run if one is already going, so a double-click is one
    fetch, not two.
    """
    if chembl_id in _in_flight:
        return BriefState.ENRICHING

    drug = await DrugRepository(session).get(chembl_id)
    if drug is None:
        return BriefState.NOT_ANALYZED  # caller 404s

    task = asyncio.create_task(_enrich_in_background(chembl_id, maker or get_sessionmaker()))
    _in_flight[chembl_id] = task
    logger.info("retry enrichment started for %s", chembl_id)
    return BriefState.ENRICHING


def is_enriching(chembl_id: str) -> bool:
    return chembl_id in _in_flight
