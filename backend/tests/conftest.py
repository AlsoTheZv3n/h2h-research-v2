"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager

from backend.main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with the app's lifespan actually run (startup/shutdown included)."""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
