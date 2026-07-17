"""The pre-warmer: fill the catalog before anyone opens a drug.

This is the user's original ask -- "die daten ziehen in eine Db speichern" -- as a
background service. It enriches drugs nobody has opened yet, so opening them is
instant instead of paying the first-view fetch, and "Waiting for sources…" stops
holding the page hostage on four external APIs.

It is deliberately not a new pipeline. It reuses the exact enrich job the lazy
on-demand path uses, filtered to never-enriched drugs
(`enrich_catalog(only_unenriched=True)`). That one filter is the whole dedup and
resumability story:

  - it skips anything the on-demand path (or a previous pass) already enriched, so it
    never redoes finished work;
  - last_enriched_at is the bookmark a crash-and-restart resumes from -- no separate
    checkpoint to keep consistent;
  - a race with an on-demand enrich of the same still-null drug is possible and
    harmless, because enrich_drug upserts: the worst case is one drug fetched twice.

Bounded by construction: enrich_catalog processes one drug at a time and commits
every few, so ChEMBL is never hammered and progress is saved incrementally. The
existing per-source retries ride out its outages; a drug ChEMBL was down for keeps
its source_failed facts and is retried on the next pass (its last_enriched_at is
stamped, so it is not re-picked -- freshness/re-enrichment is a later step, C5).

Runs as its own container -- same image, worker command -- see docker-compose.yml.
A pass enriches every currently-unenriched drug, then it sleeps and checks again,
which is how drugs added to the catalog later get warmed too.
"""

from __future__ import annotations

import asyncio
import logging

from backend.config import get_settings
from backend.db import dispose_engine, get_sessionmaker
from backend.ingestion.enrich import EnrichStats, enrich_catalog

logger = logging.getLogger(__name__)


async def prewarm_once(*, limit: int | None = None) -> EnrichStats:
    """One pass: enrich every not-yet-enriched drug, highest clinical phase first."""
    async with get_sessionmaker()() as session:
        return await enrich_catalog(session, only_unenriched=True, limit=limit)


async def prewarm_forever() -> None:
    """Pass, sleep, repeat. The long-running worker body."""
    interval = get_settings().prewarm_interval_seconds
    logger.info("prewarm worker started (interval %ds)", interval)
    while True:
        try:
            stats = await prewarm_once()
        except Exception:
            # A pass must not take the worker down -- an unenriched drug is a state
            # the system already handles honestly, so a failed pass just means the
            # next one retries. Log and carry on.
            logger.exception("prewarm pass failed; retrying after the interval")
        else:
            if stats.drugs == 0:
                logger.info("prewarm: catalog is warm, nothing to do")
            else:
                logger.info("prewarm pass done -- %s", stats.report().replace("\n", " |"))
        await asyncio.sleep(interval)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs the request URL at INFO and our NCBI calls carry api_key=; mute it
    # here too, so the worker's logs cannot leak the key any more than the API's can.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        await prewarm_forever()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
