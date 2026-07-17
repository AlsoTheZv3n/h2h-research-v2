"""Turning text into vectors, locally.

Anthropic has no embeddings API, so the chat provider and this cannot be the same
service. That is a feature rather than an awkwardness: embeddings must work on a
laptop with no key and no network egress budget, because `docker compose up` is the
first thing a stranger runs and it has to produce a working system. fastembed runs
bge-small on ONNX Runtime -- CPU-only, ~130 MB, no torch -- so the vector half of
retrieval has no external dependency at all. Only the *synthesis* half needs a key,
and it degrades honestly without one.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

# Both halves of this pair are load-bearing and they must not drift: the column is
# `vector(384)` and Postgres rejects anything else, but it rejects it at write time,
# deep inside an ingest, long after the mistake. `verify_dimension()` below checks
# the model against this number at startup instead.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# bge wants an instruction prefix on the *query* but not on the documents; without
# it, retrieval quality drops measurably. The asymmetry is easy to miss and silent
# when wrong -- searches simply get worse -- so both sides live here rather than at
# the two call sites that would eventually disagree.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    """Loaded once, lazily. ~2.7s the first time, then free."""
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME)


def verify_dimension() -> None:
    """Fail at startup if the model stopped agreeing with the schema.

    A model swap that changes the width is otherwise invisible until the first
    INSERT, which is a crash in the middle of an ingest rather than a refusal to
    start. Cheap to check, and it runs once.
    """
    actual = len(next(iter(_model().embed(["dimension probe"]))))
    if actual != EMBEDDING_DIM:
        raise RuntimeError(
            f"{MODEL_NAME} emits {actual}-d vectors but the schema declares "
            f"{EMBEDDING_DIM}. Changing the model means a migration, not a constant."
        )


def _embed_sync(texts: list[str], *, is_query: bool) -> list[list[float]]:
    if not texts:
        return []
    prepared = [_QUERY_PREFIX + t for t in texts] if is_query else texts
    return [v.tolist() for v in _model().embed(prepared)]


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Vectors for text being stored. Off the event loop: ONNX blocks."""
    return await asyncio.to_thread(_embed_sync, texts, is_query=False)


async def embed_query(text: str) -> list[float]:
    """A vector for text being searched with -- prefixed, as bge expects."""
    vectors = await asyncio.to_thread(_embed_sync, [text], is_query=True)
    return vectors[0]
