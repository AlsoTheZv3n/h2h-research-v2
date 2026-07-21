"""Resolve Ensembl gene ids to NCBI Entrez ids -- by ID, never by symbol.

Our target catalog keys genes by Ensembl id (ENSG...); cBioPortal keys its alteration data by
Entrez id. Joining them by the gene SYMBOL would be the molecules[0] failure class one rung down
-- symbols alias and drift (MLL/KMT2A, FAM/renamed loci), so a symbol match can attach one gene's
frequency to another. This maps Ensembl -> Entrez through mygene.info, a standard gene-id service,
so the join is ID -> ID end to end.

Partial by design: a gene mygene cannot resolve is simply absent from the returned dict, so the
caller marks it NOT_MEASURED (a gene we could not join) rather than guessing -- absence of an id
is not a frequency of zero.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

logger = logging.getLogger(__name__)

MYGENE_URL = "https://mygene.info/v3/query"


async def resolve_entrez(client: httpx.AsyncClient, ensembl_ids: Sequence[str]) -> dict[str, int]:
    """Ensembl gene id -> Entrez id, for the ids mygene resolves. One batched POST.

    Returns only the ids that resolved to a single integer Entrez id. A gene mygene does not
    know, or maps ambiguously (no scalar entrezgene), is omitted -- never forced to a wrong id.
    A total failure (network, non-200, malformed body) returns {} and is logged: every gene
    then falls through to NOT_MEASURED, which the caller renders distinctly from a real zero.
    """
    ids = [e for e in dict.fromkeys(ensembl_ids) if e]  # de-dupe, preserve order, drop blanks
    if not ids:
        return {}
    try:
        r = await client.post(
            MYGENE_URL,
            json={"q": ids, "scopes": "ensembl.gene", "fields": "entrezgene"},
        )
        r.raise_for_status()
        body = r.json()
    except Exception as exc:
        logger.warning("mygene Ensembl->Entrez batch failed: %s", exc)
        return {}
    if not isinstance(body, list):
        logger.warning("mygene returned an unexpected shape: %r", type(body).__name__)
        return {}
    out: dict[str, int] = {}
    for hit in body:
        # mygene echoes the queried id back as `query`; match on it, never on position, so a
        # reordered or notfound entry cannot misassign. An id with several hits appears several
        # times -- the first scalar entrezgene wins deterministically (input order is preserved).
        if not isinstance(hit, dict) or hit.get("notfound"):
            continue
        q = hit.get("query")
        entrez = hit.get("entrezgene")
        if not q or entrez is None or q in out:
            continue
        try:
            out[str(q)] = int(entrez)
        except (TypeError, ValueError):
            continue
    return out
