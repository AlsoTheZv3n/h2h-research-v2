"""Where the synthesis happens, and the fifth honest state.

The project has four states for a fact. This adds one for the chat itself:

    not_configured   no model is available, so no answer can be composed

That is not an error and must not read as one. `docker compose up` on a fresh
clone has no API key and no local model, and the honest thing to tell that reader
is "the chat needs a model, here is how to give it one" -- not a 500, and
emphatically not a chat box that silently does nothing. Same rule as
`source_failed`: name the gap rather than presenting it as an absence.

Two providers, because the two halves of this feature have different needs.
Embeddings run locally with no key (see backend/embeddings.py) so retrieval always
works. Synthesis is the half where model quality is the product: a small model that
invents a citation is the exact failure this project exists to prevent, so Claude is
the default when a key is present, and Ollama is the keyless fallback for anyone who
would rather run it locally.
"""

from __future__ import annotations

import logging
from typing import Literal, Protocol

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Thinking tokens count against max_tokens, so this is not "how long may the answer
# be" -- it is thinking plus answer. Budget for both: too tight and the model
# reasons its way to a correct answer and then gets cut off mid-sentence, which
# looks like a bug in the prompt rather than a bug in this constant.
_MAX_TOKENS = 8000

# Adaptive thinking, medium effort. Grounding an answer in five abstracts is not a
# hard reasoning problem, but it is one where being careful about what the sources
# actually say is the entire job -- and that is what the thinking is for.
#
# Literal, not str: the SDK types `effort` as a closed set, so a typo here is a type
# error rather than a 400 discovered on the first real question.
_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"


class ChatUnavailable(RuntimeError):
    """The provider exists but could not answer. Distinct from not_configured."""


class ChatProvider(Protocol):
    name: str

    async def complete(self, system: str, question: str) -> str: ...


class AnthropicProvider:
    """Claude. The default when ANTHROPIC_API_KEY is set."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, question: str) -> str:
        import anthropic

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": _EFFORT},
                messages=[{"role": "user", "content": question}],
            )
        except anthropic.APIStatusError as exc:
            # The status, never the message: an SDK error string can carry request
            # detail, and this text reaches a user-facing response. Same rule as the
            # NCBI adapter, which leaked an API key into a served tooltip exactly
            # this way.
            raise ChatUnavailable(f"the model API returned {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise ChatUnavailable("could not reach the model API") from exc

        # Never index content[0] blind: with thinking on, the first block is a
        # thinking block, and on a refusal the list can be empty entirely.
        if response.stop_reason == "refusal":
            raise ChatUnavailable("the model declined to answer this question")
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            raise ChatUnavailable("the model returned no answer")
        return text


class OllamaProvider:
    """A local model. Keyless, free, offline.

    This was written as the fallback on the assumption that a small local model
    would invent citations -- the one failure this project cannot ship. Then the
    assumption got measured, and it did not hold: on the five questions in
    `backend/eval/grounding.py` that are built to tempt exactly that, llama3.1:8b
    fabricated nothing, correctly reported a failed source as unretrieved rather
    than absent, and declined to supply a dose it certainly knows. 5/5.

    So the ordering here is not evidence-backed, and the comment that claimed it was
    has been removed rather than left to sound authoritative. Claude stays the
    default on general capability grounds; that is a judgement, not a measurement,
    and five questions on one drug is not a benchmark. If you run this locally, run
    the eval -- it is the thing that would actually tell you.
    """

    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    # 120s was not enough, measured against a real cold Ollama: the first request
    # after a restart pays for loading the weights off disk (llama3.1:8b is ~4.9 GB)
    # before it generates a token, and it timed out. The reader sees "the model could
    # not answer", asks again, and it works -- which reads as a flaky tool rather
    # than a one-off warm-up. Generous here, because the cost of being wrong is a
    # false failure and the cost of waiting is one slow first question.
    _TIMEOUT = 300.0

    async def complete(self, system: str, question: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                r = await client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "stream": False,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": question},
                        ],
                        # Low temperature: this is a grounding task, not a writing
                        # task. Nothing here should be invented, so nothing here
                        # benefits from sampling variety.
                        "options": {"temperature": 0.1},
                    },
                )
                r.raise_for_status()
                text: str = (r.json().get("message") or {}).get("content", "")
        except httpx.HTTPStatusError as exc:
            raise ChatUnavailable(f"ollama returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ChatUnavailable(f"could not reach ollama: {type(exc).__name__}") from exc

        if not text.strip():
            raise ChatUnavailable("ollama returned no answer")
        return text


def build_provider() -> ChatProvider | None:
    """The configured provider, or None -- which means not_configured, not broken.

    Claude first when a key is present, Ollama when it is not. Returning None rather
    than raising is the whole point: the caller turns it into a stated, actionable
    gap on the page instead of an error the reader cannot act on.
    """
    settings = get_settings()

    if settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.chat_model)
    if settings.ollama_url:
        return OllamaProvider(settings.ollama_url, settings.ollama_model)
    return None
