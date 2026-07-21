"""Machine-EXTRACTED gene relations from the literature, via the PubTator3 API (#44).

PubTator3 runs NLP over PubMed and surfaces entity relations -- gene<->disease, gene<->chemical --
each with a co-mention count. This is powerful and at scale, but it is EXTRACTED, NOT CURATED: a
relation is a statistical co-occurrence the model found, not a fact a human verified. Presenting it
as settled would repeat the "generated critique != validated defect" error the usability harness
guards against, one rung up. So everything this adapter produces is stamped `EXTRACTED_PROVENANCE`
and the co-mention count is labelled as VOLUME, never as curated weight.

Gate-0 (the spike) settled access + licence: the API is open (no key); PubTator is an NLM resource,
and NLM-produced data (the relations -- entities + type + count, not the copyrighted abstract text,
which we never store) is US-government public domain, redistributable with a courtesy attribution +
the citation below.

Joins are by ID. Genes: PubTator keys relations by an @GENE_<symbol> entity whose db_id is the
Entrez id -- so our target's symbol proposes the entity and its Entrez (from #43) CONFIRMS it (an
@GENE with the wrong Entrez is rejected). Diseases: keyed by MeSH; a per-disease resolve gets the
MeSH id, bridged to our catalog MONDO via mesh_disease_map (else an unlinked extracted mention).
Chemicals: MeSH names, shown as-is (not joined to ChEMBL) -- per the roadmap.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

PUBTATOR_API = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"

# The NLM courtesy attribution + the PubTator3 paper (verified: PMID 38572754,
# DOI 10.1093/nar/gkae235).
PUBTATOR_CITATION = (
    "Extracted relations via PubTator3, courtesy of the U.S. National Library of Medicine. "
    "Wei C-H, et al. PubTator 3.0: an AI-powered literature resource for unlocking biomedical "
    "knowledge. Nucleic Acids Res. 2024;52(W1):W540-W546."
)

# The non-negotiable provenance stamp: NLP-extracted, not curated. Carried on every fact.
EXTRACTED_PROVENANCE = "extracted, not curated — PubTator3, NLP over the literature"


class PubtatorError(Exception):
    """A PubTator fetch could not be completed (an outage). The caller records source_failed."""


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    """One machine-extracted relation between the queried gene and another entity."""

    kind: str  # "disease" | "chemical"
    name: str  # human-readable entity name (from the @KIND_<name> id)
    rel_type: str  # associate / positive_correlate / negative_correlate / inhibit / stimulate / ...
    co_mentions: int  # the `publications` count -- co-mention VOLUME, never curated weight
    mesh_id: str | None = None  # diseases: the resolved MeSH id (for the catalog link)
    mondo_id: str | None = None  # diseases: linked catalog entity, if the MeSH bridges
    mondo_label: str | None = None


def _humanise(entity_id: str) -> str:
    """@DISEASE_Carcinoma_Non_Small_Cell_Lung -> 'Carcinoma Non Small Cell Lung'."""
    body = entity_id.split("_", 1)[1] if "_" in entity_id else entity_id
    return body.replace("_", " ").strip()


async def _get_json(client: httpx.AsyncClient, path: str) -> object:
    try:
        r = await client.get(f"{PUBTATOR_API}{path}")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise PubtatorError(f"GET {path} failed: {exc}") from exc
    except ValueError as exc:
        raise PubtatorError(f"GET {path} returned non-JSON: {exc}") from exc


async def _autocomplete(client: httpx.AsyncClient, query: str) -> list[dict[str, object]]:
    body = await _get_json(client, f"/entity/autocomplete/?query={quote(query)}")
    return [e for e in body if isinstance(e, dict)] if isinstance(body, list) else []


async def resolve_gene_entity(client: httpx.AsyncClient, symbol: str, entrez: int) -> str | None:
    """The @GENE_ entity id PubTator keys relations by, CONFIRMED against our Entrez id.

    The symbol proposes candidates; the one whose db_id equals our Entrez is the join (an @GENE with
    a different Entrez -- a paralog, another species -- is rejected). Returns None when no candidate
    confirms, so a gene PubTator cannot resolve becomes an honest "not found", never a wrong match.
    """
    if not symbol:
        return None
    for e in await _autocomplete(client, symbol):
        if e.get("biotype") == "gene" and str(e.get("db_id")) == str(entrez):
            entity = e.get("_id")
            return entity if isinstance(entity, str) else None
    return None


async def _resolve_disease_mesh(client: httpx.AsyncClient, disease_entity_id: str) -> str | None:
    """The MeSH id for an @DISEASE_ entity, via autocomplete on its name (matched back on the exact
    entity id, so a fuzzy hit cannot misassign). None when it does not resolve -> the disease shows
    unlinked, never mislinked."""
    for e in await _autocomplete(client, _humanise(disease_entity_id)):
        if e.get("_id") == disease_entity_id and e.get("db") == "ncbi_mesh":
            mesh = e.get("db_id")
            return mesh if isinstance(mesh, str) and mesh else None
    return None


async def fetch_gene_relations(
    client: httpx.AsyncClient,
    symbol: str,
    entrez: int,
    mesh_map: Mapping[str, tuple[str, str]],
    *,
    top: int = 10,
) -> dict[str, object] | None:
    """This gene's extracted relations: the top diseases + chemicals by co-mention volume.

    Returns None when PubTator does not resolve the gene (a lookup miss -> the caller writes no
    fact). Raises PubtatorError on an outage. Every returned relation is EXTRACTED, not curated.
    """
    gene = await resolve_gene_entity(client, symbol, entrez)
    if gene is None:
        return None

    raw = await _get_json(client, f"/relations?e1={gene}")
    if not isinstance(raw, list):
        raise PubtatorError("relations response was not a list")

    diseases: list[ExtractedRelation] = []
    chemicals: list[ExtractedRelation] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        source, target = r.get("source"), r.get("target")
        other = target if source == gene else source
        if not isinstance(other, str):
            continue
        rel_type = str(r.get("type") or "")
        pubs = r.get("publications")
        co = int(pubs) if isinstance(pubs, int) else 0
        if other.startswith("@DISEASE_"):
            diseases.append(ExtractedRelation("disease", _humanise(other), rel_type, co))
        elif other.startswith("@CHEMICAL_"):
            chemicals.append(ExtractedRelation("chemical", _humanise(other), rel_type, co))

    diseases.sort(key=lambda x: x.co_mentions, reverse=True)
    chemicals.sort(key=lambda x: x.co_mentions, reverse=True)
    top_diseases = diseases[:top]
    top_chemicals = chemicals[:top]

    # Only the shown diseases pay the per-disease MeSH resolve, and only they get a catalog link.
    linked_diseases: list[ExtractedRelation] = []
    for d in top_diseases:
        mesh = await _resolve_disease_mesh(client, f"@DISEASE_{d.name.replace(' ', '_')}")
        bridge = mesh_map.get(mesh) if mesh else None
        linked_diseases.append(
            ExtractedRelation(
                d.kind,
                d.name,
                d.rel_type,
                d.co_mentions,
                mesh_id=mesh,
                mondo_id=bridge[0] if bridge else None,
                mondo_label=bridge[1] if bridge else None,
            )
        )

    return {
        "gene_entity": gene,
        "n_disease_relations": len(diseases),
        "n_chemical_relations": len(chemicals),
        "diseases": [_as_dict(d) for d in linked_diseases],
        "chemicals": [_as_dict(c) for c in top_chemicals],
    }


def _as_dict(r: ExtractedRelation) -> dict[str, object]:
    out: dict[str, object] = {
        "name": r.name,
        "rel_type": r.rel_type,
        "co_mentions": r.co_mentions,
    }
    if r.kind == "disease":
        out["mondo_id"] = r.mondo_id
        out["mondo_label"] = r.mondo_label
    return out
