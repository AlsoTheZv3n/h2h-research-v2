"""The grounding contract, against adversarial models.

Real models are not used here on purpose. These tests are not asking "is Claude
good?" -- they are asking "when a model misbehaves in the specific way models
misbehave, does this pipeline catch it?", and the only way to ask that reliably is
to write the misbehaviour yourself. A real model would pass these on a good day and
tell you nothing about the bad one.

`backend/eval/` is the other half: it runs a real model against real evidence and
reports how often it actually does these things. Neither replaces the other. This
file proves the guard works; the eval measures whether the guard ever fires.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import SourceRecord, fact, failed, utcnow
from backend.ingestion.literature import Article, LiteratureRecord
from backend.models import Drug
from backend.repositories import DrugRepository
from backend.repositories.literature import LiteratureRepository
from backend.services.chat import AnswerState, answer_question
from backend.services.chat_providers import ChatUnavailable

CID = "CHEMBL_CHAT"
REAL_PMID = "40000001"


class Spy:
    """Records what it was asked, answers what it was told to."""

    name = "spy"

    def __init__(self, reply: str = "An answer.") -> None:
        self.reply = reply
        self.calls: list[str] = []
        self.system: str | None = None

    async def complete(self, system: str, question: str) -> str:
        self.system = system
        self.calls.append(question)
        return self.reply


class Dead:
    name = "dead"

    async def complete(self, system: str, question: str) -> str:
        raise ChatUnavailable("the model API returned 503")


@pytest.fixture
async def drug(session: AsyncSession) -> Drug:
    repo = DrugRepository(session)
    d = await repo.upsert_drug(CID, pref_name="testinib", last_enriched_at=utcnow())
    await repo.save_record(
        CID,
        SourceRecord(
            "chembl",
            "testinib",
            ok=True,
            facts={
                "smiles": fact("CCO", "chembl"),
                "n_trials": fact(0, "chembl"),
                # The state that matters: ChEMBL was down for the mechanism.
                "moa": failed("chembl", "mechanism: 500 Internal Server Error"),
            },
        ),
    )
    await LiteratureRepository(session).save(
        CID,
        LiteratureRecord(
            query="testinib",
            articles=(
                Article(
                    pmid=REAL_PMID,
                    title="Testinib in advanced disease",
                    text="Testinib produced a response rate of 41% in the phase 2 cohort.",
                    journal="J Test",
                    year=2024,
                    rank=0,
                ),
            ),
            retrieved_at=utcnow(),
        ),
    )
    await session.commit()
    return d


class TestFabricatedCitations:
    async def test_an_invented_pmid_withholds_the_whole_answer(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """The worst output this tool can produce, and the guard that stops it.

        The model answers fluently, on topic, and cites a paper that does not exist.
        Nothing about the prose distinguishes it from a grounded answer -- that is
        the entire problem, and why the check is mechanical rather than editorial.
        """
        liar = Spy("Testinib inhibits EGFR with high selectivity [PMID 12345678].")

        answer = await answer_question(session, drug, "How does it work?", provider=liar)

        assert answer.state is AnswerState.UNGROUNDED
        assert answer.text == ""
        assert answer.citations == []
        assert answer.detail is not None and "invented" in answer.detail

    async def test_a_real_pmid_passes(self, session: AsyncSession, drug: Drug) -> None:
        """The guard must not eat good answers -- otherwise it is just an off switch."""
        honest = Spy(f"The response rate was 41% [PMID {REAL_PMID}].")

        answer = await answer_question(
            session, drug, "What was the response rate?", provider=honest
        )

        assert answer.state is AnswerState.OK
        assert "41%" in answer.text
        assert [c.pmid for c in answer.citations] == [REAL_PMID]

    async def test_one_bad_citation_poisons_the_answer_even_beside_a_good_one(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """A half-fabricated answer is not half-trustworthy.

        This is the realistic shape of the failure: the model cites the paper it was
        given *and* one it remembers. Keeping the answer and dropping the bad
        citation would leave the invented claim in the prose with nothing marking it.
        """
        mixed = Spy(
            f"The response rate was 41% [PMID {REAL_PMID}], confirmed in a larger "
            "trial [PMID 87654321]."
        )

        answer = await answer_question(session, drug, "What was the response rate?", provider=mixed)

        assert answer.state is AnswerState.UNGROUNDED

    @pytest.mark.parametrize(
        "reply",
        [
            "See [PMID: 12345678].",
            "see pmid 12345678 for details",
            "As shown in PMID12345678.",
        ],
    )
    async def test_the_check_is_not_fooled_by_formatting(
        self, session: AsyncSession, drug: Drug, reply: str
    ) -> None:
        """A guard that only catches one spelling is a guard with a hole in it."""
        answer = await answer_question(session, drug, "q?", provider=Spy(reply))
        assert answer.state is AnswerState.UNGROUNDED

    @pytest.mark.parametrize(
        "reply",
        [
            # The exact shapes the pre-release audit found leaking. Each mixes the one
            # real retrieved PMID with a fabricated one, which is the realistic case: a
            # model cites the paper it was given AND one it remembers.
            f"Confirmed in two studies [PMID {REAL_PMID}, 99999999].",
            f"See PMIDs {REAL_PMID}, 99999999 for the trial data.",
            f"Reported in [PMID: {REAL_PMID}; 99999999].",
            "As shown at pubmed.ncbi.nlm.nih.gov/99999999.",
        ],
    )
    async def test_a_fabricated_id_in_a_list_plural_or_url_is_caught(
        self, session: AsyncSession, drug: Drug, reply: str
    ) -> None:
        """The audit's blocker, pinned. The old anchor matched one id right after the
        literal "PMID": the plural "s" broke it entirely and a comma-listed second id
        escaped, so a fabricated citation shipped as state=ok -- the one runtime lie
        the whole phase exists to prevent."""
        answer = await answer_question(session, drug, "q?", provider=Spy(reply))
        assert answer.state is AnswerState.UNGROUNDED

    async def test_a_number_that_is_not_a_citation_is_left_alone(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """Precision matters as much as recall: false alarms train people to ignore it."""
        answer = await answer_question(
            session, drug, "q?", provider=Spy("A response rate of 41% across 128 patients.")
        )
        assert answer.state is AnswerState.OK


class TestTheOutputBoundary:
    """NOTICE.md promises no abstract text is ever served. This is what makes it true.

    Every other check in this suite guards against the model saying something *false*.
    These guard against it saying something *true that is not ours to publish* -- and
    they were missing until review pointed out that the promise was enforced against
    the response schema, which has no field for abstract text, and not against the
    model, which can simply quote.
    """

    async def test_a_verbatim_quote_withholds_the_answer(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """The hole review found. Real PMID, valid citation, copied text.

        `The paper states: "<the abstract>" [PMID 40000001]` passed every guard:
        nothing is fabricated, the citation is real, the claim is accurate. And
        someone else's copyrighted abstract went out in the response body.
        """
        plagiarist = Spy(
            'The paper states: "Testinib produced a response rate of 41% in the phase 2 '
            f'cohort." [PMID {REAL_PMID}]'
        )

        answer = await answer_question(session, drug, "What did it show?", provider=plagiarist)

        assert answer.state is AnswerState.WITHHELD
        assert answer.text == ""
        assert answer.detail is not None and "republish" in answer.detail

    async def test_a_paraphrase_passes(self, session: AsyncSession, drug: Drug) -> None:
        """The guard must not eat the thing the feature is for.

        Same facts, same citation, the model's own words. This is exactly what a
        grounded answer looks like and it has to survive.
        """
        honest = Spy(f"Four in ten patients responded during the phase 2 study [PMID {REAL_PMID}].")

        answer = await answer_question(session, drug, "What did it show?", provider=honest)

        assert answer.state is AnswerState.OK

    async def test_a_short_shared_phrase_is_not_a_quote(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """Technical writing shares phrases. Twelve consecutive words does not.

        "response rate of 41%" appears in both because it is the finding, not because
        anything was copied. A guard that fires on this is one people learn to
        ignore.
        """
        answer = await answer_question(
            session,
            drug,
            "q?",
            provider=Spy(f"The response rate of 41% is the headline number [PMID {REAL_PMID}]."),
        )
        assert answer.state is AnswerState.OK


class TestTheStatesReachTheModel:
    async def test_a_failed_source_is_named_in_the_context(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """The founding rule, at the last layer it can break.

        ChEMBL's mechanism fetch failed. If the prompt simply lacks a mechanism, the
        model says "no mechanism is reported" -- fluent, grounded in what it was
        given, and false: it *is* reported, we just could not fetch it. The outage
        has to arrive as a fact about our pipeline, or the model cannot tell the
        reader the truth.
        """
        spy = Spy()
        await answer_question(session, drug, "What is the mechanism?", provider=spy)

        prompt = spy.calls[0]
        assert "SOURCE UNAVAILABLE" in prompt
        assert "moa" in prompt
        # And the instruction that tells it what to do with that.
        assert spy.system is not None
        assert "could not retrieve" in spy.system

    async def test_a_measured_zero_reads_differently_from_an_outage(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        """n_trials=0 is a finding. moa-unavailable is not. Both are in the prompt,
        and they must not look the same when they get there."""
        spy = Spy()
        await answer_question(session, drug, "How many trials?", provider=spy)

        prompt = spy.calls[0]
        assert "MEASURED, NONE FOUND" in prompt
        assert prompt.index("MEASURED, NONE FOUND") != prompt.index("SOURCE UNAVAILABLE")

    async def test_the_abstract_reaches_the_model(self, session: AsyncSession, drug: Drug) -> None:
        """Retrieval is not decoration: if this fails, every other test here passes
        while the model answers from nothing."""
        spy = Spy()
        await answer_question(session, drug, "What was the response rate?", provider=spy)

        assert "response rate of 41%" in spy.calls[0]
        assert f"PMID {REAL_PMID}" in spy.calls[0]


class TestRefusingToAnswer:
    async def test_no_model_is_a_stated_gap_not_an_error(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        answer = await answer_question(session, drug, "anything?", provider=None)

        assert answer.state is AnswerState.NOT_CONFIGURED
        assert answer.detail is not None
        # Actionable: it says what to do, because the reader can actually do it.
        assert "ANTHROPIC_API_KEY" in answer.detail

    async def test_a_drug_nobody_looked_at_never_reaches_the_model(
        self, session: AsyncSession
    ) -> None:
        """The check that makes the prompt's "no knowledge outside EVIDENCE" true.

        Handed an empty context, a model answers from training -- fluently, and with
        nothing to mark it. The prompt forbids it; *not making the call* is what
        enforces it. Asserting the spy was never called is the only way to know the
        enforcement is real rather than aspirational.
        """
        blank = await DrugRepository(session).upsert_drug("CHEMBL_BLANK", pref_name="nobodyol")
        await session.commit()
        spy = Spy("Nobodyol is a well-known kinase inhibitor.")

        answer = await answer_question(session, blank, "What is it?", provider=spy)

        assert answer.state is AnswerState.NO_EVIDENCE
        assert spy.calls == [], "the model was asked despite there being no evidence"
        assert answer.text == ""

    async def test_a_dead_model_says_so_rather_than_inventing_an_answer(
        self, session: AsyncSession, drug: Drug
    ) -> None:
        answer = await answer_question(session, drug, "q?", provider=Dead())

        assert answer.state is AnswerState.UNAVAILABLE
        assert answer.text == ""
        assert answer.detail is not None and "503" in answer.detail
