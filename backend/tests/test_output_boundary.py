"""No abstract text leaves this process. Asserted, not promised.

NOTICE.md draws the line at the output boundary, and this is where that line is
enforced. The research behind that decision put it plainly: the database is not the
exposure, the response body is. NLM does not own these abstracts and cannot license
them onward, so storing them locally is defensible and serving them is not.

Two things make this worth a whole file rather than one assertion:

1. **The UI is not the boundary.** A page that renders 50 words is cosmetic if the
   JSON behind it carried all 250 -- the response is what was published, not the
   pixels. So these tests read the raw body.
2. **The leak will come from a route nobody thought about.** A debug endpoint, an
   export, a `response_model` widened by one field. So this walks *every* route the
   app declares rather than the two that exist today, and a new route that serves
   abstract text fails here without anyone remembering to come back.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import utcnow
from backend.ingestion.literature import Article, LiteratureRecord
from backend.models import Drug
from backend.repositories.literature import LiteratureRepository

CHEMBL_ID = "CHEMBL_BOUNDARY"

# A sentence that exists nowhere else in this codebase, so finding it in a response
# body can only mean it came out of the abstract table.
SECRET = "Pembrolizumab demonstrated a hazard ratio of 0.62 in the canary cohort."
TITLE = "A canary title, which is metadata and may be shown"


@pytest.fixture
async def indexed_drug(session: AsyncSession) -> Drug:
    drug = Drug(chembl_id=CHEMBL_ID, pref_name="canarylimab", last_enriched_at=utcnow())
    session.add(drug)
    await session.commit()

    await LiteratureRepository(session).save(
        CHEMBL_ID,
        LiteratureRecord(
            query="canarylimab",
            articles=(
                Article(
                    pmid="99999999",
                    title=TITLE,
                    text=SECRET,
                    journal="J Canary",
                    year=2024,
                    rank=0,
                ),
            ),
            retrieved_at=utcnow(),
        ),
    )
    return drug


class TestNoAbstractTextIsServed:
    async def test_the_brief_does_not_carry_it(
        self, api: httpx.AsyncClient, indexed_drug: Drug
    ) -> None:
        r = await api.get(f"/drugs/{CHEMBL_ID}")
        assert r.status_code == 200
        assert SECRET not in r.text

    async def test_the_overview_does_not_carry_it(
        self, api: httpx.AsyncClient, indexed_drug: Drug
    ) -> None:
        r = await api.get("/drugs?q=canarylimab")
        assert SECRET not in r.text

    async def test_no_get_route_carries_it(
        self, api: httpx.AsyncClient, indexed_drug: Drug
    ) -> None:
        """Every GET route the app declares, not just the ones I remembered.

        The whole risk is a route added later by someone who never read NOTICE.md.
        Enumerating the app's own router means that route is covered on the day it
        is written.
        """
        from backend.main import app

        checked = 0
        for route in app.routes:
            path = getattr(route, "path", "")
            methods: set[str] = getattr(route, "methods", set()) or set()
            if "GET" not in methods or ("{" in path and "chembl_id" not in path):
                continue
            url = path.replace("{chembl_id}", CHEMBL_ID)
            try:
                r = await api.get(url)
            except Exception:  # a route needing params we cannot guess
                continue
            checked += 1
            assert SECRET not in r.text, f"{url} served abstract text"

        # Guard the guard: if the loop matched nothing, this file would pass forever
        # while testing nothing -- the vacuous-test failure this project has already
        # shipped twice.
        assert checked >= 2, f"the route sweep only reached {checked} routes"

    async def test_the_answer_carries_the_synthesis_and_never_the_source(
        self, api: httpx.AsyncClient, indexed_drug: Drug
    ) -> None:
        """The riskiest route: the one that puts abstracts in front of a model.

        The model reads the abstract. What comes back must be the model's words plus
        a citation -- never the source text. Here the "model" echoes a fixed answer,
        because the claim under test is about what the *endpoint* serializes, not
        about what a real model writes.
        """
        from backend.api.chat import get_chat_provider
        from backend.main import app

        class Echo:
            name = "echo"

            async def complete(self, system: str, question: str) -> str:
                # The abstract really is in the prompt -- that is the point of RAG,
                # and it is allowed. Assert it, so this test cannot pass by the
                # retrieval quietly having failed and there being nothing to leak.
                assert SECRET in question, "the model was never given the abstract"
                return "Survival improved in that trial [PMID 99999999]."

        app.dependency_overrides[get_chat_provider] = lambda: Echo()
        try:
            r = await api.post(
                f"/drugs/{CHEMBL_ID}/ask", json={"question": "Did survival improve?"}
            )
        finally:
            app.dependency_overrides.pop(get_chat_provider, None)

        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "ok"
        assert "[PMID 99999999]" in body["text"]
        # The citation is metadata: pmid, title, link. Never the body.
        assert body["citations"][0]["pmid"] == "99999999"
        assert body["citations"][0]["title"] == TITLE
        assert SECRET not in r.text


class TestFixturesStayClean:
    def test_no_abstract_text_is_committed(self) -> None:
        """The one clearly-uncleared act: publishing them.

        A demo fixture is the likeliest way abstracts end up in the repository --
        someone captures a real ingest to make CI green and ships 200 abstracts with
        it. The fixture is committed; the abstracts must not be in it.
        """
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for fixture in (root / "backend" / "fixtures").glob("*.json"):
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            blob = json.dumps(payload)
            assert '"abstract"' not in blob, f"{fixture.name} carries an abstract table"
            assert '"drug_abstract"' not in blob, f"{fixture.name} carries abstract links"
