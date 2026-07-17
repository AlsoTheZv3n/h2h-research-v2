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
import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Drug
from backend.services.briefs import is_enriching
from backend.services.chat_providers import ChatProvider, ChatUnavailable
from backend.services.retrieval import Evidence, gather_evidence, render_context

logger = logging.getLogger(__name__)


class AnswerState(StrEnum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    """No model available. A stated gap, not an error -- see chat_providers.py."""
    NO_EVIDENCE = "no_evidence"
    """Nothing retrieved, and enrichment is not running. Answering anyway would be
    answering from the model's own memory, which is exactly the thing this project
    refuses to do."""
    ENRICHING = "enriching"
    """Nothing retrieved YET -- a background enrich job is in flight. Async empty is
    not the same as empty: "still gathering" and "we looked and found nothing" are
    different answers, the same enriching-vs-empty distinction the brief draws, at the
    chat level."""
    UNAVAILABLE = "unavailable"
    """A model exists but could not answer. Transient; try again."""
    UNGROUNDED = "ungrounded"
    """The model cited a PMID we never gave it. The answer is withheld -- see
    `_fabricated_pmids`. This is the state the whole phase exists to be able to
    reach."""
    WITHHELD = "withheld"
    """The answer quoted an abstract verbatim, so it is not ours to publish. Not the
    model's fault and not a gap in the evidence -- a licensing boundary. See
    `_copies_source_text` and NOTICE.md."""


# Extracting every PMID an answer cites, in every shape a model actually writes it.
#
# The first cut was `PMID[:\s]*(\d{4,9})` -- one digit run immediately after the
# literal "PMID". The audit ran it and it leaked: "PMIDs 12345678, 99999999" matched
# NOTHING (the plural "s" sits between "PMID" and the space, so `[:\s]*` matches zero
# and the anchor fails), and "[PMID 12345678, 99999999]" matched only the first id.
# Either way a fabricated identifier shipped as state=ok -- the one runtime lie the
# whole phase exists to prevent, defeated by the commonest citation format.
#
# So: anchor on PMID or PMIDs, then take EVERY id in the comma/semicolon/space list
# that follows -- and also catch a bare PubMed URL. Erring toward capturing (a stray
# year in a list read as a PMID) is the safe direction: a false positive withholds an
# answer; a false negative serves a fabrication.
#
# No `\b` after PMIDs?: it would reject the no-separator form "PMID12345678" (D and 1
# are both word chars, so there is no boundary between them) -- which the old regex
# caught and a test pins. `s?` still absorbs the plural.
_PMID_ANCHOR = re.compile(r"PMIDs?[:\s]*([\d,;\s]*\d{4,9})", re.IGNORECASE)
_PMID_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{4,9})", re.IGNORECASE)
_PMID_DIGITS = re.compile(r"\d{4,9}")

# Word characters only: see _copies_source_text.
_WORD = re.compile(r"\w+")


def _cited_pmids(answer: str) -> set[str]:
    """Every PMID the answer cites, across list forms, plurals and URLs."""
    ids: set[str] = set()
    for match in _PMID_ANCHOR.finditer(answer):
        ids.update(_PMID_DIGITS.findall(match.group(1)))
    ids.update(_PMID_URL.findall(answer))
    return ids


def _fabricated_pmids(evidence: Evidence, answer: str) -> set[str]:
    """PMIDs the answer cites that were never in the evidence.

    This is the guard that makes the rest of the pipeline worth building. Everything
    upstream -- the drug filter, the state-aware prompt, refusing to call the model
    on empty evidence -- reduces the *chance* of a fabricated citation. None of it
    can rule one out, because a model under pressure to be helpful will produce a
    citation-shaped string, and a citation-shaped string is indistinguishable from a
    citation to every reader who does not click it. Nobody clicks it.

    So: check. Any identifier in the answer that we did not put there is proof the
    model invented something, and an answer with one invented citation in it has no
    claim on the reader's trust for the rest.

    **What this does not catch, and it is the bigger half.** This verifies that a
    citation *exists* in the evidence, not that it *supports the claim attached to
    it*. A model that writes "the hazard ratio was 0.46 [PMID 34543864]" against a
    real retrieved abstract that says nothing about hazard ratios sails straight
    through -- the PMID is real, so nothing here fires, and the sentence is a
    fabrication wearing a valid citation. That is a harder problem (it needs a
    second model checking each claim against its source, which is its own eval and
    its own failure modes), and it is not solved. It is written down here and in the
    README rather than left for a reader to discover, because a guard whose limits
    are not stated is worse than no guard: it buys trust it has not earned.
    """
    given = {a.pmid for a in evidence.abstracts}
    return _cited_pmids(answer) - given


# Twelve consecutive words from a source document is not paraphrase and not
# coincidence -- it is copying. Short enough to catch a lifted sentence, long enough
# that shared technical phrasing ("acquired resistance to osimertinib in patients
# with EGFR-mutant non-small cell lung cancer") does not trip it.
_VERBATIM_WORDS = 12


def _copies_source_text(evidence: Evidence, answer: str) -> bool:
    """Whether the answer lifts a run of words straight out of an abstract.

    NOTICE.md promises "no abstract text is ever served". Until this existed, that
    promise was enforced against the *schema* -- no response model has a field for
    it -- and not against the model, which can simply quote. `"The paper states:
    '<200 characters of abstract>'"` passed every check in this file: the PMID is
    real, the citation is valid, and 200 words of someone's copyrighted abstract
    went out in the response body.

    Caught in review, and it is the right kind of finding: the guarantee was true
    about the code I wrote and false about the system I built. The prompt does say
    not to quote at length -- but a prompt is a request, and NOTICE.md makes a
    promise. A promise needs a check.
    """

    def words(text: str) -> list[str]:
        # Word characters only, so punctuation cannot smuggle a quote past this. A
        # plain .split() compares `"testinib` against `testinib` and finds them
        # different -- meaning the check missed every quotation that was *marked as
        # one*, which is the commonest form by far and the exact case the test was
        # written around. It failed, correctly, on the first run.
        return _WORD.findall(text.lower())

    answer_words = words(answer)
    if len(answer_words) < _VERBATIM_WORDS:
        return False
    answer_grams = {
        " ".join(answer_words[i : i + _VERBATIM_WORDS])
        for i in range(len(answer_words) - _VERBATIM_WORDS + 1)
    }

    for abstract in evidence.abstracts:
        source = words(abstract.text)
        for i in range(len(source) - _VERBATIM_WORDS + 1):
            if " ".join(source[i : i + _VERBATIM_WORDS]) in answer_grams:
                return True
    return False


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
        # Async empty is not empty. A drug whose enrich job is in flight has no facts
        # YET; telling the reader "nothing gathered" would collapse enriching into
        # empty at the chat level -- the same lie the brief's states exist to prevent.
        if is_enriching(drug.chembl_id):
            return Answer(
                state=AnswerState.ENRICHING,
                text="",
                citations=[],
                detail=(
                    f"The evidence for {evidence.drug_name} is still being gathered. "
                    "Give it a moment and ask again."
                ),
            )
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

    # The last gate, and the only one that can catch a fabrication after the fact.
    # Withholding the whole answer over one bad identifier is the right trade: a
    # confident answer with an invented source is the worst thing this tool could
    # hand a reader, and it is worse than no answer precisely because it does not
    # look like one.
    if fabricated := _fabricated_pmids(evidence, text):
        logger.warning(
            "provider %s cited PMIDs not in evidence for %s: %s",
            chat.name,
            evidence.chembl_id,
            sorted(fabricated),
        )
        return Answer(
            state=AnswerState.UNGROUNDED,
            text="",
            citations=[],
            detail=(
                "The answer was withheld: the model cited "
                f"{'a source' if len(fabricated) == 1 else 'sources'} that was not in "
                "the retrieved evidence, which means it invented it. Rather than show "
                "you an answer we cannot stand behind, we are telling you it happened."
            ),
        )

    # The output boundary, enforced rather than requested. The prompt asks the model
    # not to quote at length; NOTICE.md *promises* no abstract text is ever served,
    # and only this makes the promise true.
    if _copies_source_text(evidence, text):
        logger.warning(
            "provider %s reproduced source text for %s; answer withheld",
            chat.name,
            evidence.chembl_id,
        )
        return Answer(
            state=AnswerState.WITHHELD,
            text="",
            citations=[],
            detail=(
                "The answer quoted a paper's abstract directly, and that text is not "
                "ours to republish — NLM does not own these abstracts and neither do "
                "we. Ask again, or follow the citations on this page to read the "
                "papers at the source."
            ),
        )

    return Answer(state=AnswerState.OK, text=text, citations=_citations_for(evidence, text))
