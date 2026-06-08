import importlib

from fastapi.testclient import TestClient


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
