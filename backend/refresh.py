"""The refresh cron: fill the catalog and keep it fresh.

This replaces the pre-warmer. That was a Dauer-Worker churning every few minutes to
enrich never-touched drugs; this is a scheduled job that does two things per pass:

  fill     enrich drugs nobody has ever opened, so the first visitor pays nothing;
  refresh  re-enrich drugs last looked at more than `freshness_days` ago, so a fact
           that changed at the source (a new trial, a corrected potency) does not sit
           stale forever.

Both fall out of one query -- last_enriched_at IS NULL for fill, `< cutoff` for
refresh -- so there is no new pipeline and no separate bookkeeping; it reuses the exact
enrich job the lazy on-demand path uses. The lazy path stays as the on-demand fallback
for a drug opened before the cron reaches it.

Two shapes, one job:
  python -m backend.refresh          # the in-stack service: a pass, then sleep, repeat
  python -m backend.refresh --once   # a single pass and exit, for a real external cron
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import timedelta

from backend.config import get_settings
from backend.db import dispose_engine, get_sessionmaker
from backend.ingestion.base import utcnow
from backend.ingestion.enrich import EnrichStats, enrich_catalog
from backend.ingestion.enrich_cancer import CancerEnrichStats, enrich_cancer_catalog

logger = logging.getLogger(__name__)


async def refresh_once(*, limit: int | None = None) -> tuple[EnrichStats, CancerEnrichStats]:
    """One pass over BOTH catalogs: enrich every never-touched drug and cancer, and re-enrich
    any gone stale. Cancers ride the same fill+refresh query as drugs (last_enriched_at IS NULL
    for fill, `< cutoff` for refresh), so a cancer enriched before a new block shipped picks up
    its epidemiology/survival facts on the next pass rather than sitting on 'not collected'."""
    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.freshness_days)
    async with get_sessionmaker()() as session:
        drugs = await enrich_catalog(
            session, only_unenriched=True, stale_before=cutoff, limit=limit
        )
        cancers = await enrich_cancer_catalog(
            session, only_unenriched=True, stale_before=cutoff, limit=limit
        )
        return drugs, cancers


async def refresh_forever() -> None:
    """Pass, sleep, repeat. The scheduled-service body -- daily by default, not a poll."""
    settings = get_settings()
    logger.info(
        "refresh cron started (interval %ds, freshness %dd)",
        settings.refresh_interval_seconds,
        settings.freshness_days,
    )
    while True:
        try:
            drugs, cancers = await refresh_once()
        except Exception:
            # A pass must not take the service down: an unenriched or stale drug/cancer is a
            # state the system already handles honestly, so a failed pass just means the
            # next one retries. Log and carry on.
            logger.exception("refresh pass failed; retrying after the interval")
        else:
            if drugs.drugs == 0 and cancers.cancers == 0:
                logger.info("refresh: catalog is warm and fresh, nothing to do")
            else:
                logger.info(
                    "refresh pass done -- drugs: %s | cancers: %s",
                    drugs.report().replace("\n", " |"),
                    cancers.report().replace("\n", " |"),
                )
        await asyncio.sleep(settings.refresh_interval_seconds)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fill and refresh the catalog.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single pass and exit (for a host cron / cloud scheduler)",
    )
    parser.add_argument("--limit", type=int, help="only the first N drugs this pass")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs the request URL at INFO and our NCBI calls carry api_key=; mute it so
    # the cron's logs cannot leak the key any more than the API's can.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        if args.once:
            drugs, cancers = await refresh_once(limit=args.limit)
            print("\n=== refresh: drugs ===")
            print(drugs.report())
            print("\n=== refresh: cancers ===")
            print(cancers.report())
        else:
            await refresh_forever()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
