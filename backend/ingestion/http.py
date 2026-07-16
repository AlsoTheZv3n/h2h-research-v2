"""The shared HTTP client every adapter is handed.

Both fixes here were found by running the spike against the live APIs, not by
reading the code. They live in the client rather than the adapters so that each
adapter stays a thin, replaceable mapping of one source's payload.
"""

from __future__ import annotations

import asyncio

import httpx

# ClinicalTrials.gov sits behind a WAF that allowlists known client tokens and 403s
# everything else. Measured against the live API: a bare "h2h/0.1 (research)" is
# rejected, and so are "Mozilla/5.0" and "curl/8.0.1"; a UA carrying the
# python-httpx token passes in any position. So keep the token and identify
# ourselves in the comment field -- which the other three sources ask for anyway.
#
# Built from httpx.__version__ rather than hardcoded, so a dependency bump cannot
# silently turn every ClinicalTrials.gov call into a 403.
USER_AGENT = f"python-httpx/{httpx.__version__} (h2h/0.1; research)"

# ChEMBL's /activity legitimately takes 30-60s for a well-studied molecule. At a
# 30s timeout it fails, and a timeout is indistinguishable from "this drug has no
# IC50s" -- the exact confusion the fact model exists to prevent.
DEFAULT_TIMEOUT = 120.0


class RetryTransport(httpx.AsyncHTTPTransport):
    """Retry transient upstream failures with exponential backoff.

    ChEMBL is the least reliable of the four: broad 500s (its own /status.json
    included) and stalls. Retrying here keeps that noise out of every adapter.

    Note this is a floor, not a fix: retries cannot ride out a multi-minute ChEMBL
    outage, which is why the catalog is bulk-loaded and cached rather than queried
    live per request.
    """

    # 403 is deliberately absent. ClinicalTrials.gov's 403 is a deterministic verdict
    # on the User-Agent, not a transient fault: retrying it burns backoff, delays the
    # real error, and buries the cause.
    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, *args: object, attempts: int = 4, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.attempts = attempts

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(self.attempts):
            last_exc, response = None, None
            try:
                response = await super().handle_async_request(request)
                if response.status_code not in self.RETRY_STATUS:
                    return response
                await response.aread()
                await response.aclose()
            except httpx.TimeoutException as exc:
                last_exc = exc
            if attempt < self.attempts - 1:
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s
        if last_exc is not None:
            raise last_exc
        assert response is not None
        return response  # retries exhausted: hand back the last failing response


def build_client(*, timeout: float = DEFAULT_TIMEOUT, attempts: int = 4) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        transport=RetryTransport(attempts=attempts),
        headers={"User-Agent": USER_AGENT},
    )
