"""HTTP routes."""

from __future__ import annotations

from backend.api.cancers import router as cancers_router
from backend.api.chat import router as chat_router
from backend.api.drugs import router as drugs_router
from backend.api.targets import router as targets_router

__all__ = ["cancers_router", "chat_router", "drugs_router", "targets_router"]
