"""Ask a question about one drug, answered only from that drug's evidence.

Scoped to a single drug by URL, deliberately. A cross-catalog "ask anything" box
would need retrieval to pick the drug from the question, and picking wrong means
answering confidently about a molecule the reader never asked about -- the failure
the drug filter in the retriever exists to prevent, reintroduced one layer up.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.repositories import DrugRepository
from backend.services.chat import AnswerState, answer_question
from backend.services.chat_providers import ChatProvider, build_provider

router = APIRouter(prefix="/drugs", tags=["chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_chat_provider() -> ChatProvider | None:
    """The model, as a dependency -- so a test can swap it without patching a module.

    Returns None when nothing is configured, and that is not an error: the route
    turns it into the not_configured state. A dependency that raised here would make
    "no key set" indistinguishable from "the model is broken", which is the same
    collapse this project spends the rest of its code preventing.
    """
    return build_provider()


ProviderDep = Annotated[ChatProvider | None, Depends(get_chat_provider)]


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class CitationOut(BaseModel):
    pmid: str
    title: str | None
    url: str


class AnswerOut(BaseModel):
    """The answer, and never the evidence it was made from.

    There is deliberately no field carrying abstract text. The model reads abstracts;
    what leaves this process is a synthesis plus citations. See NOTICE.md -- and
    `test_output_boundary.py`, which asserts it against every route rather than
    trusting this comment.
    """

    state: AnswerState
    text: str
    citations: list[CitationOut]
    detail: str | None = Field(
        default=None,
        description=(
            "Why there is no answer, when state is not ok. Written for the reader:"
            " not_configured means nobody has set up a model, which is a gap to fill,"
            " not a failure to retry."
        ),
    )


@router.post("/{chembl_id}/ask", response_model=AnswerOut, summary="Ask about this drug")
async def ask(
    chembl_id: str, body: Question, session: SessionDep, provider: ProviderDep
) -> AnswerOut:
    drug = await DrugRepository(session).get(chembl_id)
    if drug is None:
        raise HTTPException(status_code=404, detail=f"{chembl_id} is not in the catalog")

    answer = await answer_question(session, drug, body.question, provider=provider)

    return AnswerOut(
        state=answer.state,
        text=answer.text,
        citations=[CitationOut(pmid=c.pmid, title=c.title, url=c.url) for c in answer.citations],
        detail=answer.detail,
    )
