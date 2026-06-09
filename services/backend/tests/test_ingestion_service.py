from datetime import datetime

import pytest

from app.domain.raw_article import RawArticle
from app.ingestion.services.ingestion_service import IngestionService


def test_deduplicate_by_url_keeps_first_article() -> None:
    first = RawArticle(
        source="google_news",
        title="First",
        url="https://example.com/article",
        published_at=datetime(2026, 6, 8),
        content="first",
    )
    duplicate = RawArticle(
        source="google_news",
        title="Duplicate",
        url="https://example.com/article",
        published_at=datetime(2026, 6, 8),
        content="duplicate",
    )

    result = IngestionService._deduplicate_by_url([first, duplicate])

    assert result == [first]


def test_prepare_articles_skips_malformed_and_normalizes_urls() -> None:
    articles = [
        RawArticle(
            source="google_news_funding",
            title=" Funding story ",
            url="HTTPS://Example.com/story/?utm_source=newsletter&keep=1#section",
            published_at=datetime(2026, 6, 8),
            content=None,
        ),
        RawArticle(
            source="google_news_funding",
            title="",
            url="https://example.com/missing-title",
            published_at=None,
            content=None,
        ),
    ]

    result = IngestionService._prepare_articles(articles)

    assert len(result) == 1
    assert result[0].title == "Funding story"
    assert result[0].url == "https://example.com/story?keep=1"
    assert result[0].source_url == articles[0].url


def test_prepare_articles_truncates_database_bounded_fields() -> None:
    article = RawArticle(
        source="x" * 300,
        title="T" * 1200,
        url=f"https://example.com/{'path' * 600}",
        published_at=datetime(2026, 6, 8),
        content=None,
        external_id="e" * 700,
        source_url=f"https://source.example.com/{'path' * 600}",
    )

    result = IngestionService._prepare_articles([article])

    assert len(result) == 1
    assert len(result[0].source) == 255
    assert len(result[0].title) == 1024
    assert len(result[0].url) == 2048
    assert len(result[0].external_id or "") == 512
    assert len(result[0].source_url or "") == 2048


@pytest.mark.asyncio
async def test_ingest_continues_when_one_source_fails(monkeypatch) -> None:
    class WorkingPlugin:
        source_id = "working_source"
        display_name = "Working Source"

        @classmethod
        def is_enabled(cls, enabled_sources: set[str]) -> bool:
            return True

        async def fetch(self) -> list[RawArticle]:
            return [
                RawArticle(
                    source=self.source_id,
                    title="Startup raises funding",
                    url="https://example.com/funding?utm_medium=social",
                    published_at=datetime(2026, 6, 8),
                    content="summary",
                )
            ]

    class FailingPlugin:
        source_id = "failing_source"
        display_name = "Failing Source"

        @classmethod
        def is_enabled(cls, enabled_sources: set[str]) -> bool:
            return True

        async def fetch(self) -> list[RawArticle]:
            raise RuntimeError("source down")

    class FakeResult:
        def fetchall(self) -> list[tuple[str]]:
            return []

    class FakeSession:
        def __init__(self) -> None:
            self.articles = []

        async def execute(self, statement) -> FakeResult:
            return FakeResult()

        def add_all(self, articles) -> None:
            self.articles.extend(articles)

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    session = FakeSession()
    monkeypatch.setattr(
        "app.ingestion.services.ingestion_service.load_plugins", lambda: None
    )
    monkeypatch.setattr(
        "app.ingestion.services.ingestion_service.SourcePlugin.get_plugins",
        lambda: [FailingPlugin, WorkingPlugin],
    )

    created_count, fetched_count = await IngestionService(session).ingest()

    assert created_count == 1
    assert fetched_count == 1
    assert session.articles[0].source == "working_source"
    assert session.articles[0].url == "https://example.com/funding"
