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
from backend.models import Cancer, Drug
from backend.repositories.literature import LiteratureRepository

CHEMBL_ID = "CHEMBL_BOUNDARY"
# A cancer for the route sweep to reach: /cancers/{disease_id} takes a path param the
# sweep must be able to fill, or it fails loudly (by design). The cancer detail carries
# no abstract text today, but the sweep must cover it so it still does the day it might.
DISEASE_ID = "MONDO_BOUNDARY"

# A sentence that exists nowhere else in this codebase, so finding it in a response
# body can only mean it came out of the abstract table.
SECRET = "Pembrolizumab demonstrated a hazard ratio of 0.62 in the canary cohort."
TITLE = "A canary title, which is metadata and may be shown"


@pytest.fixture
async def indexed_drug(session: AsyncSession) -> Drug:
    drug = Drug(chembl_id=CHEMBL_ID, pref_name="canarylimab", last_enriched_at=utcnow())
    session.add(drug)
    # A catalog cancer so /cancers/{disease_id} is reachable by the route sweep below.
    session.add(Cancer(disease_id=DISEASE_ID, name="canary carcinoma", n_drugs=0, n_targets=0))
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
        Enumerating the app's routes means that route is covered on the day it is
        written.
        """
        from backend.main import app

        # Enumerate from the OpenAPI schema, NOT app.routes. The pre-release audit ran
        # the old version and caught it walking ZERO data routes: under FastAPI
        # 0.139.1 the included routers appear in app.routes as `_IncludedRouter`
        # objects with methods=None, so `if "GET" not in methods: continue` skipped
        # every /drugs and /ask route, and the two /health routes satisfied the
        # `checked >= 2` guard. The boundary test -- NOTICE.md's central proof that no
        # abstract text is served -- passed while checking nothing that could leak.
        #
        # app.openapi()["paths"] lists the real declared paths, and by construction
        # excludes the doc routes (/openapi.json, /docs, /redoc) -- so no allowlist is
        # needed for them.
        schema = app.openapi()

        checked, skipped, reached_drugs = 0, [], False
        for path, operations in schema["paths"].items():
            if "get" not in operations:
                continue
            url = path.replace("{chembl_id}", CHEMBL_ID).replace("{disease_id}", DISEASE_ID)
            if "{" in url:
                # A path param this sweep cannot fill. A FAILURE, not a silent skip:
                # a future /abstracts/{pmid} must not slip through unchecked while the
                # file claims full coverage.
                skipped.append(path)
                continue
            r = await api.get(url)
            checked += 1
            if "/drugs" in path:
                reached_drugs = True
            assert SECRET not in r.text, f"{url} served abstract text"

        assert not skipped, (
            f"these routes take a path param this sweep cannot fill: {skipped}. "
            "Teach it to fill them -- do not let the boundary go unchecked silently."
        )
        # The guard the old `checked >= 2` only pretended to be. It reached the two
        # health routes and passed; this requires the sweep to actually reach a data
        # route -- the only kind that could carry abstract text.
        assert reached_drugs, f"the sweep reached no /drugs route -- vacuous ({checked} checked)"

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

        A demo fixture is the likeliest way abstracts end up in this repository --
        someone captures a real ingest to make CI green and ships 200 abstracts with
        it. The fixture is committed; the abstracts must not be in it.

        Checked structurally, not by table name. The first version looked for the
        strings "abstract" and "drug_abstract", which is a check on the shape I
        happened to imagine: a fixture written as `{"articles": [{"text": "..."}]}`
        carries every abstract and passes cleanly. So this walks the JSON and looks
        for what actually matters -- a long free-text field sitting next to a PMID,
        which is what an abstract *is* regardless of what the key is called.
        """
        import json
        from pathlib import Path
        from typing import Any

        # Long enough that a title, a mechanism string or a drug name cannot trip it;
        # short enough that no real abstract slips under. Real abstracts run 1000+
        # characters; the longest legitimate string in the current fixture is a
        # sample title at ~120.
        ABSTRACT_LENGTH = 400

        def offenders(node: Any, path: str = "$") -> list[str]:
            found: list[str] = []
            if isinstance(node, dict):
                looks_like_a_record = any(k.lower() in {"pmid", "pmids", "doi"} for k in node)
                for key, value in node.items():
                    if isinstance(value, str) and len(value) > ABSTRACT_LENGTH:
                        found.append(f"{path}.{key} ({len(value)} chars)")
                    elif looks_like_a_record and key.lower() in {"abstract", "text", "body"}:
                        found.append(f"{path}.{key} (an abstract-shaped field beside a PMID)")
                    else:
                        found += offenders(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    found += offenders(item, f"{path}[{i}]")
            return found

        root = Path(__file__).resolve().parents[2]
        fixtures = list((root / "backend" / "fixtures").glob("*.json"))
        assert fixtures, "no fixtures found -- this test would pass by checking nothing"

        for fixture in fixtures:
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            assert not (bad := offenders(payload)), (
                f"{fixture.name} looks like it carries abstract text: {bad}. "
                "NOTICE.md says abstracts are never committed; see NLM's position on "
                "who owns them."
            )
