"""The full RAG loop, proven through the production entrypoint on an unseeded drug.

This is the test kind -- not the test count -- that catches "nobody wired it". The
pre-release audit found the founding bug restaged: LiteratureFetcher and
LiteratureRepository.save had no production caller, so the chat's abstract retrieval
was inert on every real drug, and a full green suite said nothing because every
literature test called the fetcher directly. A unit test that calls the fetcher is
worthless here: it passes whether or not enrichment wires it.

So this seeds nothing but a catalog row, opens the drug through the SAME entrypoint
the UI uses (get_or_start_brief -> the background enrich job), and asserts the whole
chain end to end:

    fetch -> persist + embed -> retrieve -> cite

Only the external HTTP is mocked (respx), exactly as every adapter test mocks it --
the wiring, the parse, the embedding, the vector search and the citation are all
real. Remove the literature step from enrich_drug and this goes red; that was
verified by hand.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.models import Abstract, Drug, DrugAbstract
from backend.repositories import DrugRepository
from backend.services import briefs
from backend.services.briefs import BriefState, get_or_start_brief
from backend.services.chat import AnswerState, answer_question
from backend.services.retrieval import gather_evidence

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

CID = "CHEMBL_LIT"
PMID = "40000001"

# A distinctive abstract, returned by the mocked efetch. Nothing else in the codebase
# contains this sentence, so finding it retrieved can only mean the chain ran.
ABSTRACT = (
    "RESULTS: Acquired resistance emerged through MUC1-C upregulation in every "
    "resistant model, and its suppression restored sensitivity to the drug."
)

EFETCH_XML = f"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>{PMID}</PMID>
<Article><Journal><ISOAbbreviation>J Test Oncol</ISOAbbreviation>
<JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
<ArticleTitle>MUC1-C drives acquired resistance.</ArticleTitle>
<Abstract><AbstractText>{ABSTRACT}</AbstractText></Abstract>
</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


@pytest.fixture(autouse=True)
def clear_in_flight() -> Iterator[None]:
    briefs._in_flight.clear()
    yield
    briefs._in_flight.clear()


def _mock_all_sources() -> None:
    """Every external endpoint the enrich job touches -- facts and literature both.

    esearch is shared by the PubMed fact adapter (count + titles) and the literature
    fetcher (the id list to efetch). One mock satisfies both.
    """
    respx.get(f"{CHEMBL}/molecule/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "molecules": [
                    {
                        "molecule_chembl_id": CID,
                        "pref_name": "LITDRUG",
                        "molecule_synonyms": [],
                        "molecule_structures": {"canonical_smiles": "CCO"},
                        "molecule_properties": {"full_mwt": "100.0"},
                        "max_phase": "2",
                    }
                ]
            },
        )
    )
    respx.get(f"{CHEMBL}/mechanism.json").mock(
        return_value=httpx.Response(200, json={"mechanisms": []})
    )
    respx.get(f"{CHEMBL}/activity.json").mock(
        return_value=httpx.Response(200, json={"page_meta": {"total_count": 0}, "activities": []})
    )
    respx.get(CT).mock(return_value=httpx.Response(200, json={"totalCount": 3, "studies": []}))
    respx.post(OT).mock(
        side_effect=[
            httpx.Response(200, json={"data": {"search": {"hits": [{"id": CID}]}}}),
            httpx.Response(
                200,
                json={
                    "data": {
                        "drug": {
                            "id": CID,
                            "drugType": "Small molecule",
                            "maximumClinicalStage": "PHASE_2",
                            "mechanismsOfAction": {"rows": []},
                            "indications": {"count": 0, "rows": []},
                        }
                    }
                },
            ),
        ]
    )
    respx.get(f"{EUTILS}/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"count": "1", "idlist": [PMID]}})
    )
    respx.get(f"{EUTILS}/esummary.fcgi").mock(
        return_value=httpx.Response(
            200, json={"result": {"uids": [PMID], PMID: {"title": "MUC1-C drives resistance"}}}
        )
    )
    respx.get(f"{EUTILS}/efetch.fcgi").mock(return_value=httpx.Response(200, text=EFETCH_XML))


class _Spy:
    """A stand-in model. Cites the PMID it is told to -- the test supplies the one it
    read back from retrieval, so this proves the retrieve->cite plumbing, not the
    model."""

    name = "spy"

    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def complete(self, system: str, question: str) -> str:
        return self.reply


@pytest.fixture
async def catalogued(session: AsyncSession) -> None:
    """A catalog row and nothing else: never enriched, no facts, no abstracts."""
    await DrugRepository(session).upsert_drug(
        CID, pref_name="LITDRUG", drug_type="Small molecule", max_phase=2
    )
    await session.commit()


@respx.mock
async def test_the_whole_rag_loop_runs_through_the_production_entrypoint(
    session: AsyncSession, catalogued: None, db_engine: AsyncEngine
) -> None:
    _mock_all_sources()
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    # The production entrypoint: open the drug. Not a direct fetcher call.
    state = await get_or_start_brief(session, CID, maker=maker)
    assert state is BriefState.ENRICHING

    task = briefs._in_flight.get(CID)
    assert task is not None
    await task  # let the background enrich job finish

    async with maker() as fresh:
        # 1. Abstracts landed in Postgres for this drug, with provenance.
        abstract = await fresh.get(Abstract, PMID)
        assert abstract is not None, "the enrich job never persisted an abstract"
        assert ABSTRACT in (abstract.text or "")
        assert abstract.retrieved_at is not None
        link = (
            await fresh.execute(select(DrugAbstract).where(DrugAbstract.drug_chembl_id == CID))
        ).scalar_one_or_none()
        assert link is not None and link.pmid == PMID

        # 2. It was embedded -- persist-without-embed is the hidden other end of the
        # same bug: an abstract that can never be retrieved.
        assert abstract.embedding is not None

        # 3. Retrieval RETURNS it -- asserted on the retrieval result, not just DB rows.
        drug = await fresh.get(Drug, CID)
        assert drug is not None
        evidence = await gather_evidence(fresh, drug, "why does the drug stop working?")
        assert [a.pmid for a in evidence.abstracts] == [PMID], (
            "retrieval returned no abstract -- the fetch/embed/search chain is broken"
        )

        # 4. The answer cites the real abstract. The Spy cites the PMID the test just
        # read back from retrieval; answer_question must surface it as a citation.
        answer = await answer_question(
            fresh,
            drug,
            "why does the drug stop working?",
            provider=_Spy(f"Resistance is driven by MUC1-C upregulation [PMID {PMID}]."),
        )
        assert answer.state is AnswerState.OK
        assert [c.pmid for c in answer.citations] == [PMID]


@respx.mock
async def test_a_failed_literature_fetch_does_not_sink_the_brief(
    session: AsyncSession, catalogued: None, db_engine: AsyncEngine
) -> None:
    """Literature is a source among sources: if NCBI is down, the facts still land and
    the drug is enriched. The abstract index simply stays empty and retries next time
    -- an index is not a claim, so a fetch outage records nothing."""
    _mock_all_sources()
    respx.get(f"{EUTILS}/efetch.fcgi").mock(return_value=httpx.Response(500))
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    await get_or_start_brief(session, CID, maker=maker)
    task = briefs._in_flight.get(CID)
    assert task is not None
    await task

    async with maker() as fresh:
        drug = await fresh.get(Drug, CID)
        assert drug is not None
        # The brief still finished -- facts landed, drug stamped.
        assert drug.last_enriched_at is not None
        assert list(await DrugRepository(fresh).facts_for(CID))
        # But literature was not searched successfully, so no abstracts and no
        # false "searched" stamp: the next open retries.
        assert drug.literature_fetched_at is None
