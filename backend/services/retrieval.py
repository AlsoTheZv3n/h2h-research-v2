"""Assembling what the model is allowed to know about one drug.

Two layers, deliberately unequal:

    facts      structured, exact, already carrying source and date. Retrieved by
               *lookup*, not by similarity -- when the question is about this drug,
               the mechanism ChEMBL asserts for it is not a thing to rank.
    abstracts  unstructured, fuzzy. This is where vectors earn their place: which of
               this drug's twenty papers speak to *this* question.

The third thing in the context is the one that matters most, and it is the reason
this file exists rather than a `select` inside the chat endpoint: the honest states
come with. A retriever that silently omits a source that failed lets the model say
"there is no information on the mechanism" -- fluent, well-grounded in the context it
was given, and a lie. It is `unavailable: []` again, one layer up: the absence of
evidence rendered as evidence of absence, this time in prose that sounds like an
answer. So `unavailable` and `not_analyzed` are part of the context, and the prompt
tells the model what to do with them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.embeddings import embed_query
from backend.ingestion.base import FactStatus
from backend.models import Drug
from backend.repositories.drugs import DrugRepository
from backend.repositories.literature import LiteratureRepository, RetrievedAbstract

# Five abstracts is roughly 1,200 words of context -- enough for a question to find
# its answer, short enough that the facts above them are not buried.
DEFAULT_ABSTRACTS = 5


@dataclass(frozen=True, slots=True)
class GroundedFact:
    """A fact as the model sees it: never a bare value."""

    key: str
    source: str
    status: FactStatus
    value: object | None
    source_url: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class Evidence:
    """Everything the answer may rest on, and everything it must admit to."""

    chembl_id: str
    drug_name: str
    facts: list[GroundedFact] = field(default_factory=list)
    abstracts: list[RetrievedAbstract] = field(default_factory=list)

    unavailable: list[str] = field(default_factory=list)
    """Keys where *every* source failed. Not the same as having no value."""

    never_analyzed: bool = False
    """Nobody has ever asked the sources about this drug."""

    literature_searched: bool = False
    """Whether PubMed has ever been asked about this drug.

    Three literature states, not two, and this flag plus `abstracts` distinguishes
    all three:

        not searched              nobody has asked PubMed about this drug
        searched, none stored     we asked; PubMed has nothing on it
        searched, none relevant   we asked, it has papers, none answer this question

    The first version had a `literature_indexed` flag derived from whether any link
    rows existed, which silently merged the first two -- the founding bug again, in
    the layer whose job is telling the model what it does not know.
    """

    @property
    def is_empty(self) -> bool:
        return not self.facts and not self.abstracts


async def gather_evidence(
    session: AsyncSession,
    drug: Drug,
    question: str,
    *,
    limit: int = DEFAULT_ABSTRACTS,
) -> Evidence:
    """Facts by lookup, abstracts by similarity, gaps by name."""
    drugs = DrugRepository(session)
    rows = list(await drugs.facts_for(drug.chembl_id))

    facts = [
        GroundedFact(
            key=row.key,
            source=row.source,
            status=row.status,
            value=row.value,
            source_url=row.source_url,
            error=row.error,
        )
        for row in rows
    ]

    # Same rule as the API's brief, and for the same reason: a key is only
    # unavailable when every source for it failed. ChEMBL down but Open Targets
    # answering still leaves us with a mechanism, and calling that missing would be
    # its own kind of lie.
    by_key: dict[str, list[GroundedFact]] = {}
    for f in facts:
        by_key.setdefault(f.key, []).append(f)
    unavailable = sorted(
        key
        for key, entries in by_key.items()
        if entries and all(f.status is FactStatus.SOURCE_FAILED for f in entries)
    )

    literature = LiteratureRepository(session)
    searched = await literature.was_searched(drug.chembl_id)
    abstracts = (
        await literature.search(drug.chembl_id, await embed_query(question), limit=limit)
        if searched
        else []
    )

    return Evidence(
        chembl_id=drug.chembl_id,
        drug_name=drug.pref_name or drug.chembl_id,
        facts=facts,
        abstracts=abstracts,
        unavailable=unavailable,
        never_analyzed=drug.last_enriched_at is None,
        literature_searched=searched,
    )


def _render_fact(f: GroundedFact) -> str:
    """One fact, with its status spelled out rather than implied by absence."""
    if f.status is FactStatus.SOURCE_FAILED:
        return f"- {f.key}: SOURCE UNAVAILABLE ({f.source} failed: {f.error or 'no reason given'})"
    if f.status is FactStatus.EMPTY:
        return f"- {f.key}: MEASURED, NONE FOUND (source: {f.source})"
    return f"- {f.key}: {f.value!r} (source: {f.source})"


def render_context(evidence: Evidence) -> str:
    """The evidence, as the text the model reads.

    Written out longhand rather than dumped as JSON: the states are the point, and
    "SOURCE UNAVAILABLE" survives being skimmed by a model in a way that
    `{"status": "source_failed"}` next to forty other keys does not.
    """
    parts: list[str] = [f"DRUG: {evidence.drug_name} ({evidence.chembl_id})", ""]

    if evidence.never_analyzed:
        parts += [
            "NOTE: no source has ever been queried about this drug. Nothing below is",
            "an absence of evidence -- there is simply no evidence gathered yet.",
            "",
        ]

    parts.append("STRUCTURED FACTS")
    parts += [_render_fact(f) for f in evidence.facts] if evidence.facts else ["(none stored)"]
    parts.append("")

    if evidence.unavailable:
        parts += [
            "SOURCES THAT FAILED FOR THIS DRUG",
            "Every source for these was down when we looked. You do not know these",
            "values. Do not say they are absent, zero, or unknown to science -- say we",
            "could not retrieve them:",
            *(f"- {key}" for key in evidence.unavailable),
            "",
        ]

    parts.append("LITERATURE")
    if not evidence.literature_searched:
        # Three wordings, because there are three states and the model has to be able
        # to tell the reader which one it is in.
        parts += ["(PubMed has never been searched for this drug -- nobody has looked)", ""]
    elif not evidence.abstracts:
        parts += [
            "(PubMed was searched for this drug. Either it has no papers on it, or",
            "none of the ones it has speak to this question. Do not claim the",
            "literature is silent on the topic -- say the search returned nothing",
            "relevant.)",
            "",
        ]
    else:
        for a in evidence.abstracts:
            head = f"[PMID {a.pmid}]"
            if a.title:
                head += f" {a.title}"
            if a.journal or a.year:
                head += f" ({a.journal or '?'} {a.year or '?'})"
            parts += [head, a.text, ""]

    return "\n".join(parts)
