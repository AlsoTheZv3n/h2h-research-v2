"""Grounded synthesis: an answer that can only be made of retrieved evidence.

The prompt below is the product, in the same way `Fact.tsx` is. Everything else in
this pipeline exists to put the right evidence in front of a model; this is where
the project's founding rule either survives or quietly stops being true, because a
model that pads a gap with a plausible sentence produces output indistinguishable
from a grounded one -- fluent, cited, and wrong.

So the prompt does not just say "do not make things up". It says what to do with
each of the states the retriever hands it, because "the source was down" and "the
literature does not address this" are different answers and the difference is the
entire point of this project.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Drug
from backend.services.chat_providers import ChatProvider, ChatUnavailable
from backend.services.retrieval import Evidence, gather_evidence, render_context

logger = logging.getLogger(__name__)


class AnswerState(StrEnum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    """No model available. A stated gap, not an error -- see chat_providers.py."""
    NO_EVIDENCE = "no_evidence"
    """Nothing retrieved. Answering anyway would be answering from the model's own
    memory, which is exactly the thing this project refuses to do."""
    UNAVAILABLE = "unavailable"
    """A model exists but could not answer. Transient; try again."""


@dataclass(frozen=True, slots=True)
class Citation:
    pmid: str
    title: str | None
    url: str


@dataclass(frozen=True, slots=True)
class Answer:
    state: AnswerState
    text: str
    citations: list[Citation]
    detail: str | None = None


SYSTEM_PROMPT = """\
You answer questions about one oncology drug, using only the evidence supplied in \
the EVIDENCE block of the user's message. You are part of a tool whose entire \
purpose is to never overstate what is known.

THE ONE RULE
Every claim you make must be traceable to a line in EVIDENCE. If EVIDENCE does not \
support an answer, say so. Do not fill a gap with what you know about this drug from \
training -- a fluent unsupported sentence is worse than no sentence here, because \
the reader cannot tell the two apart. You have no knowledge of this drug outside \
EVIDENCE. Act accordingly.

THE STATES, AND WHAT EACH ONE MEANS
EVIDENCE distinguishes several kinds of not-knowing. Never collapse them:

- "SOURCE UNAVAILABLE" -- the database was down when we looked. You do not know this \
value, and neither does anyone reading. Say "we could not retrieve this; the source \
was unavailable". NEVER say it is absent, zero, unknown to science, or not reported. \
An outage is a fact about our pipeline, not a finding about the drug.
- "MEASURED, NONE FOUND" -- we asked and the answer is genuinely nothing. This IS a \
finding and you may report it as one: no trials, no annotated mechanism.
- A value -- report it, with its source.
- No abstracts fetched -- nobody has looked at the literature yet. Not the same as \
the literature being silent.
- Abstracts indexed but none relevant -- we looked and none of this drug's papers \
speak to the question.

CITATIONS
Cite the PMID inline as [PMID 12345678] for any claim drawn from an abstract. Facts \
from the structured databases carry their source name -- attribute them to it \
("ChEMBL reports..."). Never invent a PMID, and never cite a PMID that is not in \
EVIDENCE: a fabricated citation is the single worst output this tool can produce, \
because it looks exactly like a real one.

Do not quote abstracts at length. Two sentences of anyone's abstract is a large \
fraction of it. Summarise in your own words and cite.

STYLE
Answer the question directly, in prose, then support it. Do not open with a summary \
of what you were given or a restatement of the question. Be brief -- a few sentences \
is usually right. Do not hedge on things EVIDENCE states plainly; do not assert \
things it does not.\
"""


def _user_message(evidence: Evidence, question: str) -> str:
    return f"EVIDENCE\n{'=' * 60}\n{render_context(evidence)}\n{'=' * 60}\n\nQUESTION: {question}"


def _citations_for(evidence: Evidence, answer: str) -> list[Citation]:
    """Only the abstracts the answer actually cited.

    Listing everything retrieved would attach sources to an answer that never used
    them -- the appearance of grounding rather than grounding. If the model cited
    nothing, this is empty, and that is a true statement about the answer.
    """
    return [
        Citation(pmid=a.pmid, title=a.title, url=a.url)
        for a in evidence.abstracts
        if a.pmid in answer
    ]


async def answer_question(
    session: AsyncSession,
    drug: Drug,
    question: str,
    *,
    provider: ChatProvider | None,
) -> Answer:
    """Retrieve, ground, answer.

    `provider` is required and has no default, though it accepts None. That is
    deliberate: with a default of None, the same value would mean both "nothing is
    configured" and "go build one yourself", and a caller who forgot to pass it
    would silently get whichever the environment happened to have. One value, two
    meanings, decided by an omission -- the exact collapse the rest of this codebase
    exists to prevent. Composition root builds it (api/chat.py); here None means
    not_configured and nothing else.
    """
    chat = provider
    if chat is None:
        return Answer(
            state=AnswerState.NOT_CONFIGURED,
            text="",
            citations=[],
            detail=(
                "No language model is configured, so questions cannot be answered yet. "
                "Set ANTHROPIC_API_KEY, or point OLLAMA_URL at a local model. Browsing "
                "and the sourced briefs work without either."
            ),
        )

    evidence = await gather_evidence(session, drug, question)

    # Refusing to call the model on empty evidence is not an optimisation. Handed no
    # context, a model answers from training -- fluently, plausibly, and with no way
    # for the reader to tell it apart from a grounded answer. The prompt forbids it;
    # not making the call is what enforces it.
    if evidence.is_empty:
        return Answer(
            state=AnswerState.NO_EVIDENCE,
            text="",
            citations=[],
            detail=(
                f"Nothing has been gathered about {evidence.drug_name} yet, so there is "
                "nothing to answer from. Open its brief first -- that fetches the facts "
                "and the literature."
            ),
        )

    try:
        text = await chat.complete(SYSTEM_PROMPT, _user_message(evidence, question))
    except ChatUnavailable as exc:
        logger.warning("chat provider %s failed: %s", chat.name, exc)
        return Answer(state=AnswerState.UNAVAILABLE, text="", citations=[], detail=str(exc))

    return Answer(state=AnswerState.OK, text=text, citations=_citations_for(evidence, text))
