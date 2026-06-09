import importlib

from fastapi.testclient import TestClient

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
