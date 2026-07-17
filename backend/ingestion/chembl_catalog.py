"""Bulk-load the oncology drug catalog from ChEMBL.

Why bulk, and not on demand: ChEMBL is the least reliable of the four sources --
broad 500s (its own /status.json included) and 30-60s latencies, observed
repeatedly. A product that resolved drugs live at query time would inherit that.
So the catalog is pulled once, ahead of time, and served from Postgres.

Which means this command must survive ChEMBL misbehaving *while it runs*:

  idempotent  every write is an upsert keyed by chembl_id, so a re-run is safe
  resumable   per-record failures are logged and skipped, never fatal; re-running
              fills the gaps, and `--only-missing` fetches just those

Run:  uv run python -m backend.ingestion.chembl_catalog
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.chembl import _as_float, _as_int, pick_molecule
from backend.ingestion.http import build_client
from backend.models import Drug
from backend.repositories.drugs import DrugRepository, classify_maturity

logger = logging.getLogger(__name__)

BASE = "https://www.ebi.ac.uk/chembl/api/data"

# How we define "oncology". ChEMBL has no cancer flag, so we go through
# drug_indication and match the disease term.
#
# Matched against BOTH mesh_heading and efo_term, because neither alone is
# sufficient: MeSH names organ cancers "<Organ> Neoplasms" (so "neoplasm" catches
# them) but calls others "Carcinoma, Non-Small-Cell Lung" (which it does not).
# Substring matching is blunt and will pull in the odd benign neoplasm -- the
# alternative is vendoring a MeSH/EFO ontology, which is a Phase-2-sized problem.
# Kept as one visible list rather than buried in a query string, so the definition
# can be argued with.
CANCER_TERMS = (
    "neoplasm",
    "carcinoma",
    "sarcoma",
    "lymphoma",
    "leukemia",
    "leukaemia",
    "myeloma",
    "melanoma",
    "glioma",
    "glioblastoma",
    "blastoma",
    "mesothelioma",
    "cancer",
    "tumor",
    "tumour",
)

# Only drugs that reached a patient. max_phase >= 1 per the brief: preclinical
# compounds are a different product.
MIN_PHASE = 1

_PAGE = 1000
# Small batches: ChEMBL 500s on long __in lists, and a failed batch costs a retry
# of everything in it.
_BATCH = 20
# ChEMBL answers a batch in tens of seconds, so serially this ran for hours. Six is
# deliberately modest: this is a public, already-struggling service, and the point
# is to finish in a sitting, not to squeeze it.
_CONCURRENCY = 6


@dataclass
class LoadStats:
    indications_scanned: int = 0
    candidates: int = 0
    loaded: int = 0
    skipped_phase: int = 0
    unknown_phase: int = 0
    failed: list[str] = field(default_factory=list)
    pages_failed: int = 0
    terms_seen: set[str] = field(default_factory=set)

    def report(self) -> str:
        lines = [
            f"  indication rows scanned : {self.indications_scanned}",
            f"  oncology candidates     : {self.candidates}",
            f"  loaded into `drug`      : {self.loaded}",
            f"  skipped (phase < {MIN_PHASE})    : {self.skipped_phase}",
        ]
        if self.unknown_phase:
            # Its own line, never folded into skipped_phase: "no phase annotated on
            # the indication" is not "measured below phase 1".
            lines.append(f"  indication phase unknown: {self.unknown_phase} (molecule decided)")
        if self.pages_failed:
            lines.append(f"  !! discovery pages lost : {self.pages_failed} (catalog is incomplete)")
        if self.failed:
            lines.append(f"  !! molecules failed     : {len(self.failed)} -- re-run to fill")
            lines.append(f"     first few: {self.failed[:5]}")
        if self.pages_failed or self.failed:
            # Never let a partial load read as a complete one.
            lines.append("  NOTE: this run is a FLOOR, not the catalog size. Re-run to fill gaps.")
        return "\n".join(lines)


# Sentinel for "this molecule has not been seen yet", distinct from "seen, with an
# unknown phase" (None). Two different absences, and collapsing them is the bug this
# whole codebase is built to avoid.
_MISSING = object()


def _merge_phase(existing: Any, phase: int | None) -> int | None:
    """Highest known phase across a molecule's indication rows; None if none is known.

    `max_phase_for_ind` is routinely null -- "no phase annotated for this indication",
    not "phase 0". The old `or 0` turned that into a measured zero, which the shortlist
    filter then dropped, so an approved drug whose cancer rows all lack a phase never
    reached the authoritative molecule-level check. Worse, the run positively reported
    it as "skipped (phase < 1)". A known phase always wins over an unknown one.
    """
    if existing is _MISSING:
        return phase
    if existing is None:
        return phase
    if phase is None:
        return existing  # type: ignore[no-any-return]
    return max(existing, phase)  # type: ignore[no-any-return]


def is_cancer_indication(row: dict[str, Any]) -> bool:
    """Does this indication row describe a cancer?"""
    haystack = f"{row.get('mesh_heading') or ''} {row.get('efo_term') or ''}".lower()
    return any(term in haystack for term in CANCER_TERMS)


# The blunt terms: they match cancer, but also benign neoplasms and incidental "tumor"
# mentions. A drug matched ONLY by these is not yet established as oncology. The rest of
# CANCER_TERMS name a specific malignancy -- a drug indicated against one of those is
# doing oncology whatever its phase.
_BLUNT_TERMS = frozenset({"neoplasm", "tumor", "tumour", "cancer"})
_SPECIFIC_CANCER = frozenset(CANCER_TERMS) - _BLUNT_TERMS


def is_out_of_scope(rows: list[dict[str, Any]], molecule_max_phase: int | None) -> bool:
    """Is this drug outside the oncology scope -- in the catalog only by a blunt match?

    The catalog is built by substring-matching disease terms, which pulls in drugs whose
    cancer link is incidental: an approved statin or contrast agent with a single
    exploratory "Neoplasms" trial. This separates those from real oncology programs, and
    is deliberately conservative -- it biases toward keeping, because losing a real
    oncology drug is the expensive error and the exclusion is reversible anyway.

    A drug is OUT of scope when:
      - it has no cancer indication at all (nothing anchors it here), or
      - its cancer indications match only the blunt terms AND the drug has reached phase
        3+ on a programme its cancer work trails -- an approved (or near-approved)
        non-oncology drug with an incidental cancer study.

    It stays IN scope when a specific malignancy is named (at any phase), when its cancer
    work reaches its overall max_phase, whenever the phases are unknown, and -- crucially
    -- for any experimental compound below phase 3: an early oncology drug's overall
    phase IS its cancer phase, so the phase-3 gate never hides one. Ignorance and youth
    both keep a drug; only a clearly-advanced non-cancer programme excludes it.
    """
    cancer = [r for r in rows if is_cancer_indication(r)]
    if not cancer:
        return True

    haystack = " ".join(
        f"{r.get('mesh_heading') or ''} {r.get('efo_term') or ''}" for r in cancer
    ).lower()
    if any(term in haystack for term in _SPECIFIC_CANCER):
        return False

    # Blunt-only. Exclude only a drug developed to phase 3+ on a lead programme its
    # cancer work trails -- never an experimental (phase 1-2) compound, whose overall
    # phase is its cancer phase and which the phase-3 gate deliberately protects.
    phases = [_as_int(r.get("max_phase_for_ind")) for r in cancer]
    best = max((p for p in phases if p is not None), default=None)
    if molecule_max_phase is None or best is None:
        return False  # unknown phase -> keep; do not exclude on missing data
    return molecule_max_phase >= 3 and best < molecule_max_phase


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """GET returning parsed JSON, or None when ChEMBL misbehaves.

    ChEMBL answers a 500 with an HTML page, so .json() raises rather than returning
    an error body -- both failure shapes have to collapse to the same None here.
    """
    try:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except Exception as exc:
        logger.warning("chembl request failed (%s): %s", url, str(exc)[:120])
        return None


async def _walk_term(
    client: httpx.AsyncClient, field_name: str, term: str, stats: LoadStats
) -> dict[str, int | None]:
    """Paginate one (field, term) query. Returns chembl_id -> max_phase_for_ind.

    None means the indication row carries no phase -- not phase 0. See _merge_phase.
    """
    found: dict[str, int | None] = {}
    url: str | None = f"{BASE}/drug_indication.json"
    params: dict[str, Any] | None = {field_name: term, "limit": _PAGE}

    while url:
        body = await _get_json(client, url, params)
        if body is None:
            stats.pages_failed += 1
            break  # lost this page: recorded, and the run says so at the end
        # Note the plural: the path is drug_indication, the payload key is
        # drug_indications.
        rows = body.get("drug_indications", [])
        stats.indications_scanned += len(rows)
        for row in rows:
            if not is_cancer_indication(row):
                continue
            cid = row.get("molecule_chembl_id")
            if not cid:
                continue
            phase = _as_int(row.get("max_phase_for_ind"))
            found[cid] = _merge_phase(found.get(cid, _MISSING), phase)
            stats.terms_seen.add((row.get("mesh_heading") or row.get("efo_term") or "")[:60])

        nxt = (body.get("page_meta") or {}).get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None
        params = None  # `next` already carries the query string

    logger.info("%s=%s -> %d molecules", field_name, term, len(found))
    return found


async def discover_oncology_ids(
    client: httpx.AsyncClient, stats: LoadStats
) -> dict[str, int | None]:
    """Walk drug_indication and collect the molecules with a cancer indication.

    Returns chembl_id -> highest known max_phase_for_ind, or None where no row
    annotated one. The queries overlap heavily (a breast carcinoma row matches both
    "carcinoma" and "neoplasm"), which is fine: the union is what we want.
    """
    queries = [
        (field_name, term)
        for term in CANCER_TERMS
        for field_name in ("mesh_heading__icontains", "efo_term__icontains")
    ]

    found: dict[str, int | None] = {}
    for i in range(0, len(queries), _CONCURRENCY):
        wave = queries[i : i + _CONCURRENCY]
        results = await asyncio.gather(
            *(_walk_term(client, field_name, term, stats) for field_name, term in wave)
        )
        for result in results:
            for cid, phase in result.items():
                found[cid] = _merge_phase(found.get(cid, _MISSING), phase)
        logger.info(
            "discovery: %d molecules after %d/%d queries", len(found), i + len(wave), len(queries)
        )

    stats.candidates = len(found)
    logger.info(
        "discovery done: %d candidate molecules across %d distinct terms",
        len(found),
        len(stats.terms_seen),
    )
    return found


async def _fetch_batch(
    client: httpx.AsyncClient, chunk: list[str], stats: LoadStats
) -> list[dict[str, Any]]:
    """One batch, degrading to single fetches so one bad record cannot cost the rest."""
    body = await _get_json(
        client,
        f"{BASE}/molecule.json",
        {"molecule_chembl_id__in": ",".join(chunk), "limit": _BATCH},
    )
    if body is not None and body.get("molecules"):
        return list(body["molecules"])

    logger.info("batch of %d failed; falling back to single fetches", len(chunk))
    out: list[dict[str, Any]] = []
    for cid in chunk:
        single = await _get_json(client, f"{BASE}/molecule/{cid}.json")
        if single is None:
            stats.failed.append(cid)
        else:
            out.append(single)
    return out


async def fetch_molecules(
    client: httpx.AsyncClient, ids: list[str], stats: LoadStats
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield molecules a wave at a time.

    Concurrent, and a generator rather than one big list, for the same reason:
    ChEMBL answers a batch in tens of seconds, so serially this ran for hours --
    and the caller could not persist anything until all of it was in memory. Waves
    let the caller commit as it goes, which is what makes the run resumable rather
    than all-or-nothing.
    """
    chunks = [ids[i : i + _BATCH] for i in range(0, len(ids), _BATCH)]
    for i in range(0, len(chunks), _CONCURRENCY):
        wave = chunks[i : i + _CONCURRENCY]
        results = await asyncio.gather(*(_fetch_batch(client, c, stats) for c in wave))
        done = min(i + _CONCURRENCY, len(chunks))
        logger.info("fetched wave %d-%d of %d batches", i + 1, done, len(chunks))
        yield [mol for batch in results for mol in batch]


def to_columns(mol: dict[str, Any]) -> dict[str, Any]:
    """Map a ChEMBL molecule onto the catalog's index columns."""
    structures = mol.get("molecule_structures") or {}
    props = mol.get("molecule_properties") or {}
    smiles = structures.get("canonical_smiles")
    return {
        "pref_name": mol.get("pref_name"),
        "smiles": smiles,
        "mw": _as_float(props.get("full_mwt")),
        "alogp": _as_float(props.get("alogp")),
        "hbd": _as_int(props.get("hbd")),
        "hba": _as_int(props.get("hba")),
        "psa": _as_float(props.get("psa")),
        "ro5_violations": _as_int(props.get("num_ro5_violations")),
        # ChEMBL's own modality label ("Small molecule", "Antibody", ...). Open
        # Targets phrases it differently ("Antibody drug conjugate"); T6 reconciles.
        "drug_type": mol.get("molecule_type"),
        "max_phase": _as_int(mol.get("max_phase")),
        # No potency yet -- that is T5's job, and it upgrades the row afterwards.
        "maturity": classify_maturity(mol.get("molecule_type"), smiles, has_potency=False),
    }


async def resolve_query(client: httpx.AsyncClient, query: str) -> str | None:
    """A ChEMBL id passes through; a name is resolved to one.

    Name resolution goes through pick_molecule, so it obeys the same rule as the
    adapter: a relevance-ranked search does not get to pick the molecule for us.
    """
    if query.upper().startswith("CHEMBL") and query[6:].isdigit():
        return query.upper()

    body = await _get_json(client, f"{BASE}/molecule/search.json", {"q": query})
    if body is None:
        logger.warning("could not search for %r", query)
        return None
    mol = pick_molecule(body.get("molecules", []), query)
    if mol is None:
        logger.warning("no ChEMBL molecule named %r", query)
        return None
    cid: str | None = mol.get("molecule_chembl_id")
    return cid


async def seed_catalog(
    session: AsyncSession,
    queries: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> LoadStats:
    """Load specific molecules by id or name, skipping discovery.

    Discovery walks tens of thousands of indication rows against a source that 500s
    a third of the time -- an hour or more before it reaches any given drug. That is
    the right shape for building the whole catalog and the wrong one for putting a
    known handful of drugs in front of a developer. Same upserts, so it composes
    with a full load rather than competing with it.

    Deliberately does NOT apply the oncology or phase filters: if you asked for this
    molecule by name, you meant it.
    """
    if client is None:
        async with build_client() as owned:
            return await seed_catalog(session, queries, client=owned)

    stats = LoadStats()
    repo = DrugRepository(session)

    ids: list[str] = []
    for query in queries:
        cid = await resolve_query(client, query)
        if cid is None:
            stats.failed.append(query)
        else:
            ids.append(cid)
    stats.candidates = len(ids)

    async for molecules in fetch_molecules(client, ids, stats):
        for mol in molecules:
            cid = mol.get("molecule_chembl_id")
            if not cid:
                continue
            await repo.upsert_drug(cid, **to_columns(mol))
            stats.loaded += 1
        await session.commit()

    return stats


async def load_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    only_missing: bool = False,
) -> LoadStats:
    """Load the catalog. Pass a client to control timeouts/retries; otherwise one
    is built with the production settings."""
    if client is None:
        async with build_client() as owned:
            return await load_catalog(session, client=owned, only_missing=only_missing)

    stats = LoadStats()
    repo = DrugRepository(session)

    candidates = await discover_oncology_ids(client, stats)

    # An unknown indication phase shortlists the molecule rather than dropping it:
    # the molecule record's own max_phase is the authority (checked below), and this
    # filter exists only to keep the fetch volume down. Measured-low rows are still
    # dropped here -- it is specifically *not knowing* that must not decide.
    wanted = [cid for cid, phase in candidates.items() if phase is None or phase >= MIN_PHASE]
    stats.skipped_phase = sum(
        1 for phase in candidates.values() if phase is not None and phase < MIN_PHASE
    )
    stats.unknown_phase = sum(1 for phase in candidates.values() if phase is None)

    if only_missing:
        existing = set((await session.execute(select(Drug.chembl_id))).scalars().all())
        wanted = [c for c in wanted if c not in existing]
        logger.info("only-missing: %d of %d still to fetch", len(wanted), len(candidates))

    # Commit per wave, not once at the end. The docstring above promises resumable,
    # and a single commit after an hours-long run would make that a lie: any crash
    # (or a Ctrl-C during a ChEMBL stall) would roll back everything, leaving
    # --only-missing nothing to skip. Committing as we go is what makes the promise
    # true -- each wave that lands, stays landed.
    async for molecules in fetch_molecules(client, wanted, stats):
        for mol in molecules:
            cid = mol.get("molecule_chembl_id")
            if not cid:
                continue
            columns = to_columns(mol)
            # max_phase from the molecule record is authoritative; the indication's
            # phase is per-indication and only used to shortlist.
            if (columns["max_phase"] or 0) < MIN_PHASE:
                stats.skipped_phase += 1
                continue
            await repo.upsert_drug(cid, **columns)
            stats.loaded += 1
        await session.commit()
        logger.info("committed: %d loaded so far", stats.loaded)

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="fetch only molecules not already in the catalog (fills gaps after an outage)",
    )
    parser.add_argument(
        "--ids",
        help=(
            "comma-separated ChEMBL ids or drug names to load directly, skipping"
            " discovery (e.g. 'sotorasib,CHEMBL4594350'). Ignores the oncology and"
            " phase filters -- you asked for these by name."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        if args.ids:
            queries = [q.strip() for q in args.ids.split(",") if q.strip()]
            stats = await seed_catalog(session, queries)
        else:
            stats = await load_catalog(session, only_missing=args.only_missing)

    print("\n=== ChEMBL oncology catalog ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
