from datetime import datetime

from app.domain.raw_article import RawArticle
from app.messaging.articles import raw_article_from_message, raw_article_to_message


def test_raw_article_message_round_trip_preserves_fields() -> None:
    article = RawArticle(
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://example.com/acme",
        published_at=datetime(2026, 6, 10, 8, 30),
        content="Acme raised funding.",
        external_id="external-1",
        source_url="https://publisher.example.com/acme",
    )

    payload = raw_article_to_message(article)
    restored = raw_article_from_message(payload)

    assert restored == article
