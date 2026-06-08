from datetime import datetime

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
