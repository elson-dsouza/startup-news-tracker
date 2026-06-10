import importlib

from fastapi.testclient import TestClient
import pytest

from app.api.routes import list_articles
from app.db.deps import get_session


def test_health_endpoint(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/startup_news",
    )
    main = importlib.import_module("app.main")

    client = TestClient(main.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_article_sources_endpoint(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/startup_news",
    )
    main = importlib.import_module("app.main")

    class FakeResult:
        def fetchall(self) -> list[tuple[str, None]]:
            return [("google_news_funding", None)]

    class FakeSession:
        async def execute(self, statement) -> FakeResult:
            return FakeResult()

    async def override_session():
        yield FakeSession()

    main.app.dependency_overrides[get_session] = override_session
    client = TestClient(main.app)

    response = client.get("/articles/sources")

    main.app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert any(item["id"] == "google_news_funding" for item in payload)
    assert all("display_name" in item for item in payload)


def test_article_sources_endpoint_includes_database_sources(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/startup_news",
    )
    main = importlib.import_module("app.main")

    class FakeResult:
        def fetchall(self) -> list[tuple[str, None]]:
            return [("the_economic_times", None)]

    class FakeSession:
        async def execute(self, statement) -> FakeResult:
            return FakeResult()

    async def override_session():
        yield FakeSession()

    main.app.dependency_overrides[get_session] = override_session
    client = TestClient(main.app)

    response = client.get("/articles/sources")

    main.app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert any(
        item["id"] == "the_economic_times"
        and item["display_name"] == "The Economic Times"
        and item["enabled"]
        for item in payload
    )


@pytest.mark.asyncio
async def test_list_articles_accepts_multiple_sources() -> None:
    class FakeScalars:
        def unique(self):
            return self

        def all(self) -> list[object]:
            return []

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeSession:
        def __init__(self) -> None:
            self.statement = None

        async def execute(self, statement) -> FakeResult:
            self.statement = statement
            return FakeResult()

    session = FakeSession()

    await list_articles(
        limit=20,
        offset=0,
        source=["expresshealthcare_in", "un_news"],
        q=None,
        entity=None,
        entity_type=None,
        funding_min_usd=None,
        funding_max_usd=None,
        startup_country=None,
        publisher_country=None,
        mentioned_country=None,
        published_after=None,
        published_before=None,
        session=session,
    )

    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "expresshealthcare_in" in compiled
    assert "un_news" in compiled


@pytest.mark.asyncio
async def test_list_articles_accepts_enrichment_filters() -> None:
    class FakeScalars:
        def unique(self):
            return self

        def all(self) -> list[object]:
            return []

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeSession:
        def __init__(self) -> None:
            self.statement = None

        async def execute(self, statement) -> FakeResult:
            self.statement = statement
            return FakeResult()

    session = FakeSession()

    await list_articles(
        limit=20,
        offset=0,
        source=None,
        q="fintech",
        entity=["Acme Capital"],
        entity_type=["investor"],
        funding_min_usd=1000000,
        funding_max_usd=5000000,
        startup_country=["India"],
        publisher_country=["United States"],
        mentioned_country=None,
        published_after=None,
        published_before=None,
        session=session,
    )

    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "article_enrichments" in compiled
    assert "article_entities" in compiled
    assert "funding_amount_usd" in compiled
    assert "startup_country" in compiled
    assert "publisher_country" in compiled
