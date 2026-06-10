from datetime import datetime
from types import SimpleNamespace

from app.domain.raw_article import RawArticle
from app.messaging.articles import (
    ArticleQueue,
    _message_attempts,
    raw_article_from_message,
    raw_article_to_message,
)


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


def test_article_queue_copies_failed_message_with_incremented_attempts() -> None:
    message = SimpleNamespace(
        body=b'{"title":"Story"}',
        content_type="application/json",
        delivery_mode=None,
        priority=42,
        headers={"attempts": "1", "source": "test"},
    )

    copied = ArticleQueue._copy_message(message, attempts=2)

    assert _message_attempts(message) == 1
    assert copied.body == message.body
    assert copied.priority == 42
    assert copied.headers == {"attempts": 2, "source": "test"}


def test_article_queue_treats_invalid_attempt_header_as_zero() -> None:
    message = SimpleNamespace(headers={"attempts": "not-a-number"})

    assert _message_attempts(message) == 0
