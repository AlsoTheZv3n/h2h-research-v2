"""On-demand enrichment of a cancer's evidence brief.

The disease-side twin of enrich.py, and the same reason for it: the catalog holds index
columns only, and a cancer's real evidence -- its target landscape today, its pipeline
and trial reality as later increments land -- is fetched the first time someone opens it
and served from Postgres after.

Each source is a self-contained async function returning a SourceRecord, so adding the
next block is adding a function to build_cancer_sources(), not touching the loop.
`commit_each` persists each source as it returns, so a polling page fills card by card.

Run:  uv run python -m backend.ingestion.enrich_cancer --disease MONDO_0005233
      uv run python -m backend.ingestion.enrich_cancer --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion import cbioportal, ctgov_cancer, eurostat, seer
from backend.ingestion.base import Fact, SourceRecord, fact, failed, utcnow
from backend.ingestion.gene_ids import resolve_entrez
from backend.ingestion.http import build_client
from backend.models import Cancer
from backend.repositories.cancers import CancerRepository
from backend.services.cbioportal_map import StudyMap, load_study_map
from backend.services.disease_map import (
    MatchType,
    Resolution,
    SourceMap,
    load_source_maps,
    resolve,
)

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

# How many top associated targets the landscape card DISPLAYS: enough to show the
# established drivers plus a few less-obvious ones, not the ~12,000 Open Targets lists.
_TOP_TARGETS = 15

# How many to SCAN when counting strong associations. Open Targets returns associations
# sorted by score descending, so the strong ones (>= _STRONG_SCORE) are all within the
# first few hundred; 600 covers every cancer measured (the busiest, breast, has ~293
# above the threshold) with headroom.
_SCAN_TARGETS = 600

# The "strong association" cut, chosen from the real score distribution rather than a
# guess: Open Targets returns everything with ANY evidence (12,000-18,000 targets per
# cancer -- nearly the whole genome), which makes the raw total a threshold artifact, not
# a finding. At >= 0.5 (the midpoint of the 0-1 score) the count drops to the low hundreds
# -- NSCLC 117, breast 293 -- the targets with real, converging evidence. The number is
# never shown without this threshold beside it (the metric would mislead otherwise).
_STRONG_SCORE = 0.5

_TARGET_LANDSCAPE_QUERY = """
query TargetLandscape($id: String!, $n: Int!) {
  disease(efoId: $id) {
    id
    associatedTargets(page: {index: 0, size: $n}) {
      count
      rows {
        score
        datatypeScores { id score }
        target { id approvedSymbol tractability { label modality value } }
      }
    }
  }
}
"""

# The drugged/unexploited status of a target is a property of the target IN THE WORLD, not
# of our catalog -- so it comes from Open Targets, batched for the whole displayed set in one
# call via the plural `targets(ensemblIds:)`. NB: `Target.knownDrugs` does NOT exist (the
# query errors); `drugAndClinicalCandidates` is the field, the same one the disease pipeline
# uses, and `maxClinicalStage` (not a non-existent `Drug.isApproved`) carries the stage.
# maxClinicalStage is the drug's OVERALL stage against this target across ALL indications --
# indication-agnostic, target-level. It is NOT "approved for this cancer"; the UI must say so.
_TARGET_DRUG_STATUS_QUERY = """
query TargetDrugStatus($ids: [String!]!) {
  targets(ensemblIds: $ids) {
    id
    drugAndClinicalCandidates {
      count
      rows { maxClinicalStage }
    }
  }
}
"""

# maxClinicalStage values that mean an approved drug exists (APPROVAL, or PHASE_4 = post-
# marketing, which only happens after approval). Anything else with candidates is "clinical".
_APPROVED_STAGES = frozenset({"APPROVAL", "PHASE_4"})

_PIPELINE_QUERY = """
query Pipeline($id: String!) {
  disease(efoId: $id) {
    id
    drugAndClinicalCandidates {
      count
      rows {
        maxClinicalStage
        drug {
          id
          name
          drugType
          mechanismsOfAction { rows { mechanismOfAction } }
        }
      }
    }
  }
}
"""

# Clinical stages in descending order, most advanced first -- how the pipeline card
# reads top to bottom. Open Targets' maxClinicalStage enum (verified live: APPROVAL,
# PHASE_4, PREAPPROVAL, PHASE_3, PHASE_2_3, PHASE_2, PHASE_1_2, PHASE_1, EARLY_PHASE_1,
# PHASE_0, PRECLINICAL all occur). PREAPPROVAL (submitted, awaiting approval) is a genuinely
# advanced stage and must rank near the top, not fall into the alphabetical tail -- so the
# enum is listed in full. Only a truly-unknown value sorts to the end.
_PHASE_ORDER = (
    "APPROVAL",
    "PHASE_4",
    "PREAPPROVAL",
    "PHASE_3",
    "PHASE_2_3",
    "PHASE_2",
    "PHASE_1_2",
    "PHASE_1",
    "EARLY_PHASE_1",
    "PHASE_0",
    "PRECLINICAL",
)
_STAGE_RANK = {stage: i for i, stage in enumerate(_PHASE_ORDER)}


def _stage_rank(stage: str) -> int:
    """Advancement rank -- lower is more advanced; unknown stages sort to the end."""
    return _STAGE_RANK.get(stage, len(_PHASE_ORDER))


# A source: one function, one SourceRecord for one cancer.
CancerSource = Callable[[httpx.AsyncClient, Cancer], Awaitable[SourceRecord]]

_CONCURRENCY = 3


@dataclass
class CancerEnrichStats:
    cancers: int = 0
    enriched: int = 0
    records_ok: int = 0
    records_failed: int = 0
    facts_written: int = 0
    facts_source_failed: int = 0

    def report(self) -> str:
        return "\n".join(
            [
                f"  cancers enriched      : {self.enriched}",
                f"  source records ok     : {self.records_ok}",
                f"  source records failed : {self.records_failed}",
                f"  facts written         : {self.facts_written}",
                f"  facts marked failed   : {self.facts_source_failed}",
            ]
        )


async def _gql(client: httpx.AsyncClient, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """POST a GraphQL query, surfacing the `errors` array (see the OT adapter's _gql)."""
    r = await client.post(ENDPOINT, json={"query": query, "variables": variables})
    body: dict[str, Any] | None = None
    try:
        body = r.json()
    except ValueError:
        body = None
    if body and body.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "") for e in body["errors"]))
    r.raise_for_status()
    return (body or {}).get("data") or {}


def _target_row(row: dict[str, Any]) -> dict[str, Any]:
    """One associated target, reduced to what the landscape card shows."""
    target = row.get("target") or {}
    tractability = target.get("tractability") or []
    return {
        "symbol": target.get("approvedSymbol"),
        # The stable Ensembl gene id (ENSG...), carried so the drugged/unexploited flag and
        # the catalog link both join on it, never on the alias-prone approvedSymbol.
        "ensembl_id": target.get("id"),
        "score": round(row.get("score") or 0.0, 3),
        # The typed evidence channels behind the association ("clinical",
        # "somatic_mutation", ...), so a reader sees whether it rests on trials or on
        # literature alone.
        "evidence_types": [e["id"] for e in (row.get("datatypeScores") or []) if e.get("id")],
        # The drugged/undrugged story starts here: is there a tractable modality at all?
        "sm_tractable": any(t.get("modality") == "SM" and t.get("value") for t in tractability),
        "ab_tractable": any(t.get("modality") == "AB" and t.get("value") for t in tractability),
        # Filled in by the drug-status batch below; "unknown" until then, never "unexploited"
        # -- absence of a measurement is not a measurement of absence.
        "drug_status": "unknown",
    }


def _classify_drug_status(dcc: dict[str, Any] | None) -> str:
    """A target's drugged status from its drugAndClinicalCandidates, indication-agnostic.

    Three measured states; the caller supplies "unknown" for a target OT never resolved.
      approved     -- an approved drug hits this target (APPROVAL / PHASE_4)
      clinical     -- candidates exist against it, none approved
      unexploited  -- OT resolved the target and it has NO drugs at all (a real finding)
    """
    dcc = dcc or {}
    rows = dcc.get("rows") or []
    # "Unexploited" keys on the authoritative count, not len(rows): Open Targets returns
    # every candidate today (verified: count == len(rows), APPROVAL always present), so the
    # two agree -- but keying the "no drugs anywhere" call on count keeps it correct even if
    # a future release paginates rows. Approved-vs-clinical still reads the rows' stages.
    if not (dcc.get("count") or rows):
        return "unexploited"
    stages = {r.get("maxClinicalStage") for r in rows}
    if stages & _APPROVED_STAGES:
        return "approved"
    return "clinical"


async def _fetch_drug_status(client: httpx.AsyncClient, ensembl_ids: list[str]) -> dict[str, str]:
    """Batch the drugged status for a set of targets: one OT call, keyed by Ensembl id.

    Returns a status ONLY for targets Open Targets actually resolved. A total failure
    returns {} (every target falls through to "unknown"); a partial response omits the
    unresolved targets (they too fall through to "unknown") -- so a fetch that half-worked
    marks only the missing targets unknown, never contaminating the ones that resolved, and
    never letting an unresolved target read as "unexploited".
    """
    if not ensembl_ids:
        return {}
    try:
        data = await _gql(client, _TARGET_DRUG_STATUS_QUERY, {"ids": ensembl_ids})
    except Exception as exc:
        # The flag sub-query is down; the landscape itself still stands. Every target
        # becomes "unknown", which the card renders distinctly from "unexploited".
        logger.warning("target drug-status batch failed: %s", exc)
        return {}
    status: dict[str, str] = {}
    for t in data.get("targets") or []:
        # OT returns a null entry (or omits) an unresolved id; match by the id it echoes
        # back, not by position, so nulls and reordering cannot misassign a status.
        if not t or not t.get("id"):
            continue
        status[t["id"]] = _classify_drug_status(t.get("drugAndClinicalCandidates"))
    return status


async def opentargets_target_landscape(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
    """The disease's top associated targets, with score, evidence channels and tractability."""
    source, key = "opentargets", "target_landscape"
    url = f"https://platform.opentargets.org/disease/{cancer.disease_id}"
    retrieved_at = utcnow()
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    try:
        data = await _gql(
            client, _TARGET_LANDSCAPE_QUERY, {"id": cancer.disease_id, "n": _SCAN_TARGETS}
        )
    except Exception as exc:
        # An outage (network, 5xx, 200-with-errors), recorded as a source_failed fact so
        # the card reads "Open Targets unavailable" -- never "no targets".
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )

    disease = data.get("disease")
    if disease is None:
        # Open Targets answered but does not resolve this disease id (deprecated or
        # remapped across releases -- the same EFO->MONDO drift the catalog guards). That
        # is a lookup failure, NOT "this cancer has no targets": write no fact for the
        # key, mirroring the drug adapter's no-hit branch, so it never becomes a measured
        # EMPTY that claims zero druggable biology for a disease we could not look up.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            error="Open Targets did not resolve this disease id",
        )

    rows = (disease.get("associatedTargets") or {}).get("rows") or []
    if not rows:
        # Resolved, but Open Targets lists no associated targets. A measured EMPTY ("we
        # looked, nothing there"), distinct from the not-found and outage cases above --
        # the same empty-dict branch the pipeline uses, so the status layer keeps saying
        # what it means rather than dressing an empty result as OK.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            facts={key: fact({}, source, source_url=url, retrieved_at=retrieved_at)},
            provenance=prov,
        )
    # Open Targets returns associations score-descending, but sort defensively so the "top"
    # slice and the saturation check below hold on the fetched set even if a future release
    # changes the within-page ordering (the count itself still assumes OT returned the
    # top-scored page -- there is no client-side fix for that short of fetching everything).
    rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    # Count the strong associations across the whole scanned page (not just the 15
    # displayed): this is the headline metric, and it must be over the strong set, not
    # the ~12,000-with-any-evidence total that would read as "the whole genome". Require an
    # approvedSymbol -- the same basis the displayed list uses -- so the headline count and
    # the card can never contradict each other (a strong but un-symboled row would inflate
    # the number while the card, which needs a symbol to render a target, shows nothing).
    n_strong = sum(
        1
        for r in rows
        if (r.get("score") or 0.0) >= _STRONG_SCORE
        and (r.get("target") or {}).get("approvedSymbol")
    )
    if len(rows) >= _SCAN_TARGETS and (rows[-1].get("score") or 0.0) >= _STRONG_SCORE:
        # The scan filled up and even its weakest (last, since rows are score-descending)
        # row is still strong: the strong set may run past the scanned page, so n_strong is
        # a floor. Never observed -- breast, the busiest, is ~322 of a 600-row scan -- but
        # logged rather than silently undercounted if a future release ever crosses it.
        logger.warning(
            "target_landscape scan saturated for %s: n_strong>=%d may undercount; "
            "raise _SCAN_TARGETS",
            cancer.disease_id,
            n_strong,
        )
    display = [
        _target_row(r) for r in rows[:_TOP_TARGETS] if (r.get("target") or {}).get("approvedSymbol")
    ]
    # The drugged/unexploited flag: one batched OT call for the displayed targets, joined
    # back on Ensembl id. A failed or partial batch leaves the affected targets at their
    # "unknown" default (set in _target_row) -- never "unexploited".
    drug_status = await _fetch_drug_status(
        client, [t["ensembl_id"] for t in display if t["ensembl_id"]]
    )
    for t in display:
        if t["ensembl_id"] in drug_status:
            t["drug_status"] = drug_status[t["ensembl_id"]]
    # The value carries the threshold beside the count, so the number is never shown
    # without saying what it counts.
    value = {"threshold": _STRONG_SCORE, "n_strong": n_strong, "targets": display}
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        facts={key: fact(value, source, source_url=url, retrieved_at=retrieved_at)},
        provenance=prov,
    )


def _group_pipeline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten the disease's drugs/candidates for the pipeline card.

    Deduped globally on the drug's ChEMBL id, keeping its most advanced stage (Open
    Targets can list a drug under several stages via different indications). Returns the
    flat drug list -- each with its stage, modality and mechanism -- for the table, plus a
    per-stage distribution (stage + true count) for the summary bars. No cap: the table
    pages client-side, so the whole pipeline is stored.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        drug = row.get("drug") or {}
        cid = drug.get("id")
        if not cid:
            continue
        stage = row.get("maxClinicalStage") or "UNKNOWN"
        prior = best.get(cid)
        if prior is not None and _stage_rank(prior["stage"]) <= _stage_rank(stage):
            continue  # already seen at an equal-or-more-advanced stage
        moas = [
            m["mechanismOfAction"]
            # `.get("rows") or []`, not `.get("rows", [])`: Open Targets returns rows as
            # JSON null (not absent), and the default only fires on an absent key -- so
            # the [] default would leave None and `for m in None` would crash out of the
            # source uncaught, writing no source_failed fact. Same guard as line 204.
            for m in (drug.get("mechanismsOfAction") or {}).get("rows") or []
            if m.get("mechanismOfAction")
        ]
        best[cid] = {
            "chembl_id": cid,
            "name": drug.get("name") or cid,
            "stage": stage,
            # Missing modality/mechanism stay null -> the UI renders an honest "—", never
            # a guessed value.
            "modality": drug.get("drugType"),
            "mechanism": moas[0] if moas else None,
        }

    if not best:
        return {}

    drugs = sorted(best.values(), key=lambda d: (_stage_rank(d["stage"]), d["name"] or ""))
    counts: dict[str, int] = defaultdict(int)
    for d in drugs:
        counts[d["stage"]] += 1
    order = [*_PHASE_ORDER, *sorted(s for s in counts if s not in _PHASE_ORDER)]
    by_phase = [{"stage": stage, "count": counts[stage]} for stage in order if stage in counts]
    return {"total": len(drugs), "by_phase": by_phase, "drugs": drugs}


async def opentargets_pipeline(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
    """The drugs and clinical candidates for this cancer, grouped by clinical stage.

    Open Targets' disease->drugs list already rolls the disease ontology up, so a drug
    indicated for a subtype (osimertinib for lung adenocarcinoma) is counted for the
    parent (NSCLC) -- which an exact disease-id match over stored drug indications would
    miss. The join is on the disease ID and the drilldown is on the ChEMBL ID; no name
    matching anywhere (the weave's hard rule).
    """
    source, key = "opentargets", "pipeline"
    url = f"https://platform.opentargets.org/disease/{cancer.disease_id}"
    retrieved_at = utcnow()
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    try:
        data = await _gql(client, _PIPELINE_QUERY, {"id": cancer.disease_id})
    except Exception as exc:
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )
    disease = data.get("disease")
    if disease is None:
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            error="Open Targets did not resolve this disease id",
        )
    rows = (disease.get("drugAndClinicalCandidates") or {}).get("rows") or []
    pipeline = _group_pipeline(rows)
    # fact() classifies an empty dict as EMPTY -- "resolved, no drug programmes" --
    # distinct from the not-found and outage cases above.
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        facts={key: fact(pipeline, source, source_url=url, retrieved_at=retrieved_at)},
        provenance=prov,
    )


# -- Disease-map-resolved sources (epidemiology, survival) -------------------------------------
#
# These attach an external source (Eurostat mortality, SEER survival) to a cancer by crossing
# the vocabulary in the Gate-1 disease map: resolve() says whether the cancer IS a mapped
# category (exact), rolls up to a broader one (rollup -- which the value NAMES so a specific
# page never passes off broader figures as its own), or has no path at all (unmapped -- the
# honest "not available for this cancer", distinct from empty/source_failed). Only then is the
# external source fetched, keyed by the resolved source_code, never by name.

_ANCESTORS_QUERY = "query A($id: String!) { disease(efoId: $id) { id ancestors } }"


class _DiseaseNotResolved(Exception):
    """Open Targets answered but does not resolve this disease id (deprecated / remapped across
    releases). NOT an outage, and NOT "unmapped": a lookup miss the sources must skip, exactly as
    opentargets_target_landscape and opentargets_pipeline do -- never a settled "not available"."""


async def _fetch_ancestors(client: httpx.AsyncClient, disease_id: str) -> list[str]:
    """The cancer's MONDO ancestors from Open Targets -- the ontology path resolve() walks.

    A disease OT cannot resolve raises _DiseaseNotResolved: its empty ancestry must not be read
    as "no mapped category" (UNMAPPED), which would assert availability we never determined."""
    data = await _gql(client, _ANCESTORS_QUERY, {"id": disease_id})
    disease = data.get("disease")
    if disease is None:
        raise _DiseaseNotResolved(disease_id)
    return disease.get("ancestors") or []


async def _fetch_mapped_ancestors(
    client: httpx.AsyncClient, hits: list[str], source_map: SourceMap
) -> dict[str, frozenset[str]]:
    """For each hit (a mapped id that is the cancer's ancestor), the mapped ids among ITS
    ancestors -- what closest-wins needs to drop a broader hit when a narrower one is present
    (SEER leukaemia when AML is also a hit). Fetched only when there are >= 2 hits to compare."""
    parts = [f'h{i}: disease(efoId: "{h}") {{ id ancestors }}' for i, h in enumerate(hits)]
    data = await _gql(client, "{ " + " ".join(parts) + " }", {})
    out: dict[str, frozenset[str]] = {}
    for i, h in enumerate(hits):
        anc = set(((data.get(f"h{i}") or {}).get("ancestors")) or [])
        out[h] = frozenset(a for a in anc if a in source_map)
    return out


async def _resolve_cancer(
    client: httpx.AsyncClient,
    disease_id: str,
    source_map: SourceMap,
    ancestors_cache: dict[str, list[str]],
) -> Resolution:
    """Resolve one cancer against one source's map, fetching only the ontology it needs: nothing
    for an exact match, the cancer's ancestors otherwise, and the hits' ancestors only when two
    or more mapped ancestors must be disambiguated. resolve() remains the single decision point.

    `ancestors_cache` is shared across the sources of one enrichment run, so a cancer's ancestors
    are fetched from Open Targets ONCE even though both the epidemiology and survival sources
    resolve it (against different maps)."""
    if disease_id in source_map:
        code, label = source_map[disease_id]
        return Resolution(MatchType.EXACT, disease_id, code, label)
    ancestors = ancestors_cache.get(disease_id)
    if ancestors is None:
        ancestors = await _fetch_ancestors(client, disease_id)
        ancestors_cache[disease_id] = ancestors
    hits = [a for a in ancestors if a in source_map]
    mapped_ancestors: dict[str, frozenset[str]] = {}
    if len(hits) >= 2:
        mapped_ancestors = await _fetch_mapped_ancestors(client, hits, source_map)
    return resolve(disease_id, ancestors, source_map, mapped_ancestors)


def _resolved_value(resolution: Resolution, data: dict[str, Any]) -> dict[str, Any]:
    """The fact value for a resolved source: the match type + the entity the figures describe
    (so a rollup can be labelled "broader than X"), merged with the source's own data."""
    return {
        "match_type": resolution.match_type.value,
        "source_code": resolution.source_code,
        "source_label": resolution.source_label,
        "target_mondo": resolution.target_mondo,
        **data,
    }


def _unmapped_fact(source: str, retrieved_at: datetime) -> Fact:
    """The honest UNMAPPED state as a fact: an OK fact whose value says only that no source
    category applies -- kept distinct from empty (the source had nothing) and source_failed
    (an outage), so the UI can render "not available for this cancer" as its own answer."""
    return fact({"match_type": MatchType.UNMAPPED.value}, source, retrieved_at=retrieved_at)


def _not_resolved_record(source: str, disease_id: str, prov: dict[str, Any]) -> SourceRecord:
    """A cancer whose id Open Targets does not resolve: a lookup miss, so NO fact is written --
    the same skip opentargets_target_landscape / opentargets_pipeline make -- never a settled
    "not available for this cancer" (which UNMAPPED asserts) for an id we could not look up."""
    return SourceRecord(
        source,
        disease_id,
        ok=False,
        provenance=prov,
        error="Open Targets did not resolve this disease id",
    )


_EUROSTAT_URL = "https://ec.europa.eu/eurostat/databrowser/view/hlth_cd_asdr2/default/table"


def make_epidemiology_source(
    source_map: SourceMap, ancestors_cache: dict[str, list[str]]
) -> CancerSource:
    """Block A: European mortality (Eurostat), attached via the disease map's eurostat vocab."""

    async def cancer_epidemiology(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
        source, key = "eurostat", "epidemiology"
        retrieved_at = utcnow()
        prov: dict[str, Any] = {"source_url": _EUROSTAT_URL, "retrieved_at": retrieved_at}
        try:
            resolution = await _resolve_cancer(
                client, cancer.disease_id, source_map, ancestors_cache
            )
        except _DiseaseNotResolved:
            return _not_resolved_record(source, cancer.disease_id, prov)
        except Exception as exc:
            # We could not even resolve the cancer (Open Targets ancestry fetch failed): an
            # outage, so an amber source_failed fact -- never a silent "not available".
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, f"disease resolution failed: {exc}")},
                error=str(exc),
                outage=True,
            )
        if not resolution.available:
            # UNMAPPED: no European mortality category applies to this cancer. An honest,
            # measured answer about the mapping -- kept distinct from empty and source_failed.
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=True,
                provenance=prov,
                facts={key: _unmapped_fact(source, retrieved_at)},
            )
        try:
            data = await eurostat.fetch_epidemiology(client, resolution.source_code or "")
        except Exception as exc:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, str(exc), source_url=_EUROSTAT_URL)},
                error=str(exc),
                outage=True,
            )
        if data is None:
            # The category resolved but Eurostat reports no rate for it -- a measured EMPTY.
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=True,
                provenance=prov,
                facts={
                    key: fact(None, source, source_url=_EUROSTAT_URL, retrieved_at=retrieved_at)
                },
            )
        value = _resolved_value(resolution, data)
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            provenance=prov,
            facts={key: fact(value, source, source_url=_EUROSTAT_URL, retrieved_at=retrieved_at)},
        )

    return cancer_epidemiology


def _seer_url(site: int) -> str:
    return (
        "https://seer.cancer.gov/statistics-network/explorer/application.html"
        f"?site={site}&data_type=4&graph_type=5&compareBy=stage"
    )


def make_survival_source(
    source_map: SourceMap, ancestors_cache: dict[str, list[str]]
) -> CancerSource:
    """Block B: SEER 5-year relative survival, attached via the disease map's seer vocab."""

    async def cancer_survival(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
        source, key = "seer", "survival"
        retrieved_at = utcnow()
        prov: dict[str, Any] = {"retrieved_at": retrieved_at}
        try:
            resolution = await _resolve_cancer(
                client, cancer.disease_id, source_map, ancestors_cache
            )
        except _DiseaseNotResolved:
            return _not_resolved_record(source, cancer.disease_id, prov)
        except Exception as exc:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, f"disease resolution failed: {exc}")},
                error=str(exc),
                outage=True,
            )
        if not resolution.available:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=True,
                provenance=prov,
                facts={key: _unmapped_fact(source, retrieved_at)},
            )
        # SEER site codes are numeric; a non-numeric mapped code is a data error, not an outage.
        try:
            site = int(resolution.source_code or "")
        except ValueError:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                error=f"non-numeric SEER site code {resolution.source_code!r}",
            )
        url = _seer_url(site)
        prov["source_url"] = url
        try:
            data = await seer.fetch_survival(client, site)
        except Exception as exc:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, str(exc), source_url=url)},
                error=str(exc),
                outage=True,
            )
        if data is None:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=True,
                provenance=prov,
                facts={key: fact(None, source, source_url=url, retrieved_at=retrieved_at)},
            )
        value = _resolved_value(resolution, data)
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            provenance=prov,
            facts={key: fact(value, source, source_url=url, retrieved_at=retrieved_at)},
        )

    return cancer_survival


async def cancer_trial_reality(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
    """Block D: the real registered-trial landscape from ClinicalTrials.gov v2, by condition.

    Distinct from the pipeline block (an Open Targets drug roll-up): pipeline says which drugs are
    in development for this cancer; trial reality says what trials actually exist and their state.
    Queried by the cancer's NAME as condition text -- CT.gov keys diseases by condition string, not
    MONDO -- so the match is soft, which the value owns via its `condition` field. Field paths and
    the count/DACH design were verified live in the P1-T4.0 gate (issue #20); see ctgov_cancer.
    """
    source, key = "clinicaltrials", "trial_reality"
    retrieved_at = utcnow()
    condition = (cancer.name or "").strip()
    url = f"https://clinicaltrials.gov/search?cond={quote(condition)}"
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    if not condition:
        # A catalog row with no name -- nothing to query by. Skip (write no fact), the same
        # lookup-miss branch the OT sources take: never a measured EMPTY ("no trials") for a
        # cancer we could not even query.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            error="cancer has no name to query ClinicalTrials.gov by",
        )
    try:
        data = await ctgov_cancer.fetch_trial_reality(client, condition)
    except Exception as exc:
        # Outage (network, 5xx, absent-count handled inside): the source failed, so its answer is
        # unknown -- an amber source_failed fact, never "no trials".
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )
    if data is None:
        # Resolved, zero registered trials -- a measured EMPTY, distinct from an outage.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            provenance=prov,
            facts={key: fact(None, source, source_url=url, retrieved_at=retrieved_at)},
        )
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        provenance=prov,
        facts={key: fact(data, source, source_url=url, retrieved_at=retrieved_at)},
    )


# -- Block E: cBioPortal somatic-mutation frequency (issue #43) -----------------------------------
#
# For each of the cancer's top landscape genes, how often it is mutated in a matched tumour cohort
# -- an orthogonal, quantitative signal beside the Open Targets association score. A curated,
# licence-whitelisted MONDO -> cBioPortal-study crosswalk (exact match, never rollup: a molecular
# profile is subtype-specific) picks the cohort; mygene maps our Ensembl ids to cBioPortal's Entrez
# keys (ID -> ID). SCOPE is mutation-only (SNV/indel), stated on the fact so it is never read as the
# full alteration frequency. Honest states, distinct: no cohort mapped (unmapped) / a gene we could
# not join (gene_unmapped) / profiled-never-mutated (measured_zero) / an outage (source_failed).

_CBIOPORTAL_HOME = "https://www.cbioportal.org/"

# Lean twin of _TARGET_LANDSCAPE_QUERY: just the top genes' Ensembl id + symbol, in score order.
# Same size + score-desc + require-approvedSymbol selection as the landscape card's displayed set,
# so the two cards name the SAME genes -- frequency reads beside the target being looked at.
_LANDSCAPE_GENES_QUERY = """
query LandscapeGenes($id: String!, $n: Int!) {
  disease(efoId: $id) {
    id
    associatedTargets(page: {index: 0, size: $n}) {
      rows { score target { id approvedSymbol } }
    }
  }
}
"""


async def _fetch_landscape_genes(client: httpx.AsyncClient, cancer: Cancer) -> list[dict[str, str]]:
    """The cancer's top landscape genes (Ensembl id + symbol), matching the displayed set. Returns
    [] when Open Targets does not resolve the disease -- a lookup miss the caller skips, never a
    measured "no genes". Raises on an OT outage, which the caller records as source_failed."""
    data = await _gql(client, _LANDSCAPE_GENES_QUERY, {"id": cancer.disease_id, "n": _TOP_TARGETS})
    disease = data.get("disease")
    if disease is None:
        return []
    rows = (disease.get("associatedTargets") or {}).get("rows") or []
    rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    out: list[dict[str, str]] = []
    for r in rows[:_TOP_TARGETS]:
        target = r.get("target") or {}
        if target.get("approvedSymbol") and target.get("id"):
            out.append({"ensembl_id": target["id"], "symbol": target["approvedSymbol"]})
    return out


def _study_url(study_id: str) -> str:
    return f"https://www.cbioportal.org/study/summary?id={study_id}"


def make_alteration_frequency_source(study_map: StudyMap) -> CancerSource:
    """Block E: cBioPortal mutation frequency, attached via the curated MONDO->study crosswalk."""

    async def cancer_alteration_frequency(
        client: httpx.AsyncClient, cancer: Cancer
    ) -> SourceRecord:
        source, key = "cbioportal", "alteration_frequency"
        retrieved_at = utcnow()
        mapped = study_map.get(cancer.disease_id)  # EXACT MONDO match only -- no rollup
        if mapped is None:
            # NOT_MEASURED: no cBioPortal cohort is mapped to this cancer. An honest, measured
            # answer about coverage (most of the 1324-entity catalog), kept distinct from empty
            # and source_failed -- the UI says "no matched cohort", never "0% altered".
            prov: dict[str, Any] = {"source_url": _CBIOPORTAL_HOME, "retrieved_at": retrieved_at}
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=True,
                provenance=prov,
                facts={
                    key: fact(
                        {"state": "unmapped"},
                        source,
                        source_url=_CBIOPORTAL_HOME,
                        retrieved_at=retrieved_at,
                    )
                },
            )
        study_id, study_label = mapped
        url = _study_url(study_id)
        prov = {"source_url": url, "retrieved_at": retrieved_at}

        try:
            genes = await _fetch_landscape_genes(client, cancer)
        except Exception as exc:
            # OT outage while getting the gene set -> unknown, an amber source_failed fact.
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, f"landscape gene fetch failed: {exc}", source_url=url)},
                error=str(exc),
                outage=True,
            )
        if not genes:
            # A cohort is mapped but OT resolves no landscape genes (deprecated disease id, or an
            # empty landscape): nothing to measure frequency FOR. A lookup miss -> write no fact,
            # like the not-resolved branches above, never a measured "no genes altered".
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                error="no landscape genes to measure alteration frequency for",
            )

        # Ensembl -> Entrez (ID -> ID). A gene mygene cannot resolve is omitted here and marked
        # gene_unmapped below -- never joined by symbol, never dropped silently.
        entrez_by_ensembl = await resolve_entrez(
            client, [g["ensembl_id"] for g in genes if g.get("ensembl_id")]
        )
        want = sorted({e for e in entrez_by_ensembl.values()})
        if not want:
            # No landscape gene resolved to an Entrez id. resolve_entrez returns {} both on a
            # mygene OUTAGE and (unreachably, for real driver symbols) on a genuine no-match, so
            # the safe honest reading is source_failed with the accurate cause -- NOT a cBioPortal
            # outage (which fetch_mutation_frequencies would raise on an empty gene list), and never
            # a measured "0% everywhere".
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={
                    key: failed(
                        source,
                        "gene-id lookup resolved no Entrez ids (mygene unavailable)",
                        source_url=url,
                    )
                },
                error="no landscape gene resolved to an Entrez id",
                outage=True,
            )
        try:
            freqs = await cbioportal.fetch_mutation_frequencies(client, study_id, want)
        except cbioportal.CBioPortalError as exc:
            return SourceRecord(
                source,
                cancer.disease_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, str(exc), source_url=url)},
                error=str(exc),
                outage=True,
            )

        gene_rows: list[dict[str, Any]] = []
        for g in genes:
            ensembl_id, symbol = g.get("ensembl_id"), g.get("symbol")
            entrez = entrez_by_ensembl.get(ensembl_id) if ensembl_id else None
            altered = freqs.altered_by_entrez.get(entrez) if entrez is not None else None
            if entrez is None or altered is None:
                # Could not join this gene to an Entrez id (or, defensively, it was not in the
                # fetched set): NOT measured for this gene -- distinct from a 0% frequency.
                gene_rows.append(
                    {
                        "symbol": symbol,
                        "ensembl_id": ensembl_id,
                        "entrez_id": entrez,
                        "state": "gene_unmapped",
                    }
                )
                continue
            pct = round(100.0 * altered / freqs.denominator, 1)
            gene_rows.append(
                {
                    "symbol": symbol,
                    "ensembl_id": ensembl_id,
                    "entrez_id": entrez,
                    # A whole-exome cohort profiles every gene, so altered == 0 is a MEASURED zero
                    # (profiled, never mutated) -- not "not measured". The two states never merge.
                    "state": "measured_zero" if altered == 0 else "measured",
                    "altered_n": altered,
                    "pct": pct,
                }
            )

        value = {
            "state": "measured",
            "study_id": study_id,
            "study_label": study_label,
            "study_name": freqs.study_name,
            "alteration_scope": cbioportal.ALTERATION_SCOPE,
            "denominator_type": cbioportal.DENOMINATOR_TYPE,
            "denominator_n": freqs.denominator,
            "genes": gene_rows,
            # The ODbL grant condition: the portal citations PLUS the specific source study.
            "attribution": {
                "portal": list(cbioportal.CBIOPORTAL_CITATIONS),
                "study_citation": freqs.study_citation,
                "study_pmid": freqs.study_pmid,
            },
        }
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            provenance=prov,
            facts={key: fact(value, source, source_url=url, retrieved_at=retrieved_at)},
        )

    return cancer_alteration_frequency


async def build_cancer_sources(session: AsyncSession) -> list[CancerSource]:
    """The cancer evidence sources, assembled. The disease-map-resolved sources (epidemiology,
    survival) capture their source's crosswalk, loaded once from the DB here; the cBioPortal
    alteration-frequency source captures its own MONDO->study crosswalk the same way."""
    source_maps = await load_source_maps(session)
    study_map = await load_study_map(session)
    # One ancestor cache shared by the two disease-map sources, so a cancer's Open Targets
    # ancestors are fetched once even though epidemiology and survival both resolve it.
    ancestors_cache: dict[str, list[str]] = {}
    return [
        opentargets_target_landscape,
        opentargets_pipeline,
        make_alteration_frequency_source(study_map),
        make_epidemiology_source(source_maps.get("eurostat", {}), ancestors_cache),
        make_survival_source(source_maps.get("seer", {}), ancestors_cache),
        cancer_trial_reality,
    ]


async def _save_source_record(
    repo: CancerRepository, disease_id: str, record: SourceRecord, stats: CancerEnrichStats
) -> None:
    if record.error and not record.facts:
        # The source answered with no data for this entity and it is not an outage (e.g.
        # Open Targets does not resolve the disease id): nothing to record. Writing an
        # empty fact would claim "no targets" for a disease we could not look up -- the
        # same lie the outage path is guarded against, pointed the other way.
        stats.records_failed += 1
        return
    await repo.save_record(disease_id, record)
    stats.facts_written += len(record.facts)
    failed_here = len(record.failed_facts)
    stats.facts_source_failed += failed_here
    if failed_here:
        stats.records_failed += 1
    else:
        stats.records_ok += 1


async def enrich_cancer(
    session: AsyncSession,
    cancer: Cancer,
    client: httpx.AsyncClient,
    sources: list[CancerSource],
    stats: CancerEnrichStats,
    *,
    commit_each: bool = False,
) -> None:
    """Fetch every source for one cancer and persist the result.

    `commit_each` persists each source as it returns, so a polling page fills card by
    card. last_enriched_at is set at the end, so the brief stays "enriching" -- not
    "ready" -- until every source has had its chance.
    """
    repo = CancerRepository(session)
    for source_fn in sources:
        record = await source_fn(client, cancer)
        await _save_source_record(repo, cancer.disease_id, record, stats)
        if commit_each:
            await session.commit()

    # Stamped even when every source failed: it records that we *looked*, which a brief
    # full of source_failed facts is -- distinct from a never-analyzed cancer with no
    # facts at all. The same last_enriched_at semantics the drug side carries. A plain
    # UPDATE (mark_enriched), not an upsert -- see the method for why NOT NULL forces it.
    await repo.mark_enriched(cancer.disease_id, utcnow())
    stats.enriched += 1


async def enrich_cancer_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    disease_id: str | None = None,
    only_unenriched: bool = False,
    stale_before: datetime | None = None,
) -> CancerEnrichStats:
    """Bulk-enrich cancers (manual runs and, later, the refresh cron).

    last_enriched_at is both the never-touched marker and the freshness clock, so
    only_unenriched (fill) and stale_before (refresh) select over the one column, like
    enrich_catalog.
    """
    if client is None:
        async with build_client() as owned:
            return await enrich_cancer_catalog(
                session,
                client=owned,
                limit=limit,
                disease_id=disease_id,
                only_unenriched=only_unenriched,
                stale_before=stale_before,
            )

    stats = CancerEnrichStats()
    sources = await build_cancer_sources(session)

    query = select(Cancer).order_by(Cancer.n_drugs.desc(), Cancer.disease_id)
    if disease_id:
        query = select(Cancer).where(Cancer.disease_id == disease_id)
    else:
        conds: list[ColumnElement[bool]] = []
        if only_unenriched:
            conds.append(Cancer.last_enriched_at.is_(None))
        if stale_before is not None:
            conds.append(Cancer.last_enriched_at < stale_before)
        if conds:
            query = query.where(or_(*conds))
        if limit:
            query = query.limit(limit)

    cancers = list((await session.execute(query)).scalars().all())
    stats.cancers = len(cancers)
    logger.info("enriching %d cancers", len(cancers))

    for i in range(0, len(cancers), _CONCURRENCY):
        wave = cancers[i : i + _CONCURRENCY]
        for cancer in wave:
            await enrich_cancer(session, cancer, client, sources, stats)
        await session.commit()
        logger.info("committed: %d/%d cancers enriched", stats.enriched, len(cancers))

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich cancers with their evidence blocks.")
    parser.add_argument("--limit", type=int, help="only the first N cancers (most-drugged first)")
    parser.add_argument(
        "--disease", dest="disease_id", help="a single disease id, e.g. MONDO_0005233"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await enrich_cancer_catalog(session, limit=args.limit, disease_id=args.disease_id)

    print("\n=== cancer enrichment ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
