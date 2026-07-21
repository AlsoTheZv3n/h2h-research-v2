"""Fetching somatic-mutation alteration frequency per gene per tumour cohort from cBioPortal.

cBioPortal's public REST API (no key) over TCGA PanCancer Atlas studies. For a study and a set of
Entrez gene ids this returns, per gene, how many sequenced samples carry >= 1 mutation in it, and
the denominator (samples with mutation data) -- the raw numbers the alteration-frequency fact is
built from. Gate-0 (issue #43) established the licence: cBioPortal data is ODC-ODbL, redistributable
with attribution; some studies carry a commercial-use restriction, so only whitelisted studies are
fetched and a runtime guard refuses any study that reports a restriction.

SCOPE, stated so it is never overstated: this counts SOMATIC MUTATIONS (SNV/indel) only. It does
NOT fold in copy-number (CNA) or fusions -- so it is a MUTATION frequency, a floor on the true
"alteration" frequency, and every surface must say "mutation", not "alteration". The denominator is
the study's `_sequenced` sample list (samples with mutation data); numerator and denominator come
from the same sample set, so the percentage is honest. TCGA PanCancer cohorts are whole-exome, so a
queried gene with zero mutation records is a real 0% (profiled, never mutated) -- a MEASURED zero,
distinct from a gene we could not join or a study we could not reach.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

CBIOPORTAL_API = "https://www.cbioportal.org/api"

# The mandatory attribution (ODbL grant condition). Verified against PubMed (#43): Cerami 2012
# PMID 22588877 / DOI 10.1158/2159-8290.CD-12-0095; Gao 2013 PMID 23550210 / DOI
# 10.1126/scisignal.2004088; de Bruijn 2023 PMID 37668528 / DOI 10.1158/0008-5472.CAN-23-0816.
# Carried on every surface, ALONGSIDE the specific source-study citation (study.citation), which
# the fetch reads live so it is never hardcoded stale.
CBIOPORTAL_CITATIONS: tuple[str, ...] = (
    "Cerami E, et al. The cBio Cancer Genomics Portal. Cancer Discov. 2012;2(5):401-404.",
    "Gao J, et al. Integrative analysis of complex cancer genomics and clinical profiles using "
    "the cBioPortal. Sci Signal. 2013;6(269):pl1.",
    "de Bruijn I, et al. Analysis and Visualization of Longitudinal Genomic and Clinical Data "
    "from the AACR Project GENIE Biopharma Collaborative in cBioPortal. Cancer Res. "
    "2023;83(23):3861-3867.",
)

# What we count and over what denominator -- carried in the fact so the number is never bare.
ALTERATION_SCOPE = "somatic mutation (SNV/indel); excludes copy-number & fusions"
DENOMINATOR_TYPE = "samples with mutation data (sequenced)"


class CBioPortalError(Exception):
    """A cBioPortal fetch could not be completed -- an outage, a missing study/profile, or a
    study that fails the redistributability guard. The caller turns it into a source_failed fact
    (an amber "unavailable"), never a measured zero."""


@dataclass(frozen=True, slots=True)
class MutationFrequencies:
    """Per-gene mutation counts for one study, plus the attribution the surface must show."""

    study_id: str
    study_name: str | None
    # The study's own citation string (e.g. "TCGA, Cell 2018") and first PMID, read live from the
    # study object -- the specific-source-study attribution ODbL requires beside the portal cites.
    study_citation: str | None
    study_pmid: str | None
    # Samples with mutation data -- the honest denominator (numerator is drawn from the same set).
    denominator: int
    # Every queried Entrez id -> distinct samples carrying >= 1 mutation. A queried gene with no
    # records is present with 0 (a measured zero in a whole-exome cohort), NOT omitted.
    altered_by_entrez: dict[int, int]


def study_is_redistributable(study: dict[str, object]) -> bool:
    """Whether a study object may be fetched. Belt-and-suspenders on the CSV whitelist -- if a
    curated study ever flips to restricted upstream, this refuses it at fetch time so restricted
    data cannot leak. `publicStudy` is the authoritative flag: it must be exactly True, so an
    absent/None value fails closed. `readPermission` is a secondary veto -- it refuses only when
    EXPLICITLY False, so a public study that simply omits the field is not over-refused."""
    return study.get("publicStudy") is True and study.get("readPermission", True) is not False


async def _get(client: httpx.AsyncClient, path: str) -> object:
    try:
        r = await client.get(f"{CBIOPORTAL_API}{path}")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise CBioPortalError(f"GET {path} failed: {exc}") from exc
    except ValueError as exc:  # non-JSON body (an error page behind a 200)
        raise CBioPortalError(f"GET {path} returned non-JSON: {exc}") from exc


async def fetch_mutation_frequencies(
    client: httpx.AsyncClient, study_id: str, entrez_ids: Sequence[int]
) -> MutationFrequencies:
    """The mutation frequency of each Entrez gene in one cBioPortal study.

    Three calls: the study (for attribution + the redistributability guard), its `_sequenced`
    sample list (the denominator), and one `mutations/fetch` POST for all genes at once. Raises
    CBioPortalError on any outage, a missing study/profile, a non-redistributable study, or an
    empty denominator -- all of which are "unknown", never "zero".
    """
    queried = [g for g in dict.fromkeys(entrez_ids) if g]
    if not queried:
        raise CBioPortalError("no Entrez gene ids to query")

    study = await _get(client, f"/studies/{study_id}")
    if not isinstance(study, dict):
        raise CBioPortalError(f"study {study_id} returned an unexpected shape")
    if not study_is_redistributable(study):
        raise CBioPortalError(f"study {study_id} is not redistributable (public/read guard)")

    sample_list = await _get(client, f"/sample-lists/{study_id}_sequenced")
    sample_ids = sample_list.get("sampleIds") if isinstance(sample_list, dict) else None
    denominator = len(sample_ids) if isinstance(sample_ids, list) else 0
    if denominator == 0:
        raise CBioPortalError(f"study {study_id} has no sequenced samples")

    try:
        r = await client.post(
            f"{CBIOPORTAL_API}/molecular-profiles/{study_id}_mutations/mutations/fetch",
            json={"sampleListId": f"{study_id}_sequenced", "entrezGeneIds": list(queried)},
        )
        r.raise_for_status()
        muts = r.json()
    except httpx.HTTPError as exc:
        raise CBioPortalError(f"mutations/fetch for {study_id} failed: {exc}") from exc
    except ValueError as exc:
        raise CBioPortalError(f"mutations/fetch for {study_id} returned non-JSON: {exc}") from exc
    if not isinstance(muts, list):
        raise CBioPortalError(f"mutations/fetch for {study_id} returned an unexpected shape")

    # Distinct samples per gene. Start every queried gene at 0: a whole-exome cohort profiles the
    # whole gene set, so a gene with no records is a measured zero, not a missing measurement.
    samples_by_gene: dict[int, set[str]] = {g: set() for g in queried}
    for m in muts:
        if not isinstance(m, dict):
            continue
        gene = m.get("entrezGeneId")
        sample = m.get("sampleId")
        if gene in samples_by_gene and sample:
            samples_by_gene[gene].add(sample)

    pmids = str(study.get("pmid") or "")
    return MutationFrequencies(
        study_id=study_id,
        study_name=study.get("name"),
        study_citation=study.get("citation") or None,
        # study.pmid can be a comma-separated list; the first is the primary source study.
        study_pmid=(pmids.split(",")[0].strip() or None) if pmids else None,
        denominator=denominator,
        altered_by_entrez={g: len(s) for g, s in samples_by_gene.items()},
    )
