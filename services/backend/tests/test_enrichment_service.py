from datetime import datetime
from uuid import uuid4

import pytest

from app.enrichment.extraction import ExtractionResult
from app.enrichment.llama_cpp import EnrichedEntity, EnrichmentPayload, LlamaCppResult
from app.enrichment.service import (
    EnrichmentService,
    clean_feed_content,
    normalize_entity_name,
)
from app.domain.raw_article import RawArticle
from app.models.article import Article, ArticleEnrichment


def test_normalize_entity_name_collapses_whitespace() -> None:
    assert normalize_entity_name("  Acme   Capital  ") == "acme capital"


def test_clean_feed_content_strips_markup() -> None:
    assert clean_feed_content("<p>Acme&nbsp; raised <b>$5M</b></p>") == (
        "Acme&nbsp; raised $5M"
    )


def test_enrichment_service_applies_ai_result_idempotently() -> None:
    article = Article(
        id=uuid4(),
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://example.com/acme",
        published_at=datetime(2026, 6, 9),
        content="feed summary",
    )
    enrichment = article.enrichment
    if enrichment is None:
        from app.models.article import ArticleEnrichment

        enrichment = ArticleEnrichment(article_id=article.id)
        article.enrichment = enrichment

    payload = EnrichmentPayload(
        summary="Acme raised a seed round.",
        entities=[
            EnrichedEntity(entity_type="startup", name="Acme"),
            EnrichedEntity(entity_type="startup", name=" Acme "),
            EnrichedEntity(entity_type="investor", name="First Fund"),
        ],
        startup_country="India",
        publisher_country="India",
        mentioned_countries=["India"],
        funding_amount_original="$5 million",
        funding_currency_original="USD",
        funding_amount_usd="$5,000,000",
        funding_round="Seed",
    )
    result = LlamaCppResult(status="enriched", model_name="qwen3-1.7b", payload=payload)

    service = EnrichmentService.__new__(EnrichmentService)
    EnrichmentService._apply_ai_result(service, article, enrichment, result)
    EnrichmentService._apply_ai_result(service, article, enrichment, result)

    assert enrichment.enrichment_status == "enriched"
    assert enrichment.funding_amount_usd == 5000000
    assert [entity.normalized_name for entity in article.entities] == [
        "acme",
        "first fund",
    ]


@pytest.mark.asyncio
async def test_enrichment_service_uses_feed_content_when_extraction_fails() -> None:
    article = Article(
        id=uuid4(),
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://news.google.com/rss/articles/story",
        published_at=datetime(2026, 6, 9),
        content="<p>Acme raised seed funding from First Fund.</p>",
    )
    enrichment = ArticleEnrichment(article_id=article.id)
    article.enrichment = enrichment

    class FakeExtractor:
        async def extract(self, url: str) -> ExtractionResult:
            return ExtractionResult(
                status="failed",
                final_url=url,
                error="No readable article text extracted.",
            )

    class FakeLlmClient:
        async def enrich_article(self, **kwargs) -> LlamaCppResult:
            assert kwargs["full_text"] == "Acme raised seed funding from First Fund."
            payload = EnrichmentPayload(
                summary="Acme raised seed funding.",
                entities=[],
                startup_country=None,
                publisher_country=None,
                mentioned_countries=[],
                funding_amount_original=None,
                funding_currency_original=None,
                funding_amount_usd=None,
                funding_round=None,
            )
            return LlamaCppResult(
                status="enriched",
                model_name="qwen3-1.7b",
                payload=payload,
            )

    service = EnrichmentService.__new__(EnrichmentService)
    service.extractor = FakeExtractor()
    service.llm_client = FakeLlmClient()
    service.session = type(
        "FakeSession",
        (),
        {"commit": lambda self: _async_none()},
    )()

    result = await EnrichmentService._enrich_article(service, article)

    assert result is True
    assert enrichment.extraction_status == "feed_fallback"
    assert enrichment.extraction_error is None
    assert enrichment.enrichment_status == "enriched"


@pytest.mark.asyncio
async def test_enrichment_service_prefers_source_url_for_extraction() -> None:
    article = Article(
        id=uuid4(),
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://news.google.com/rss/articles/story",
        source_url="https://example.com/acme-raises-seed-funding",
        published_at=datetime(2026, 6, 9),
        content="<p>Acme raised seed funding from First Fund.</p>",
    )
    enrichment = ArticleEnrichment(article_id=article.id)
    article.enrichment = enrichment

    class FakeExtractor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def extract(self, url: str) -> ExtractionResult:
            self.calls.append(url)
            assert url == article.source_url
            return ExtractionResult(
                status="extracted",
                final_url=url,
                text="Acme raised seed funding from First Fund.",
            )

    class FakeLlmClient:
        async def enrich_article(self, **kwargs) -> LlamaCppResult:
            assert kwargs["url"] == article.source_url
            assert kwargs["full_text"] == "Acme raised seed funding from First Fund."
            payload = EnrichmentPayload(
                summary="Acme raised seed funding.",
                entities=[],
                startup_country=None,
                publisher_country=None,
                mentioned_countries=[],
                funding_amount_original=None,
                funding_currency_original=None,
                funding_amount_usd=None,
                funding_round=None,
            )
            return LlamaCppResult(
                status="enriched",
                model_name="qwen3-1.7b",
                payload=payload,
            )

    extractor = FakeExtractor()
    service = EnrichmentService.__new__(EnrichmentService)
    service.extractor = extractor
    service.llm_client = FakeLlmClient()
    service.session = type(
        "FakeSession",
        (),
        {"commit": lambda self: _async_none()},
    )()

    result = await EnrichmentService._enrich_article(service, article)

    assert result is True
    assert extractor.calls == [article.source_url]
    assert enrichment.extraction_status == "extracted"
    assert enrichment.enrichment_status == "enriched"


@pytest.mark.asyncio
async def test_enrichment_service_skips_when_no_text_is_available() -> None:
    article = Article(
        id=uuid4(),
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://news.google.com/rss/articles/story",
        published_at=datetime(2026, 6, 9),
        content=None,
    )
    enrichment = ArticleEnrichment(article_id=article.id)
    article.enrichment = enrichment

    class FakeExtractor:
        async def extract(self, url: str) -> ExtractionResult:
            return ExtractionResult(
                status="failed",
                final_url=url,
                error="No readable article text extracted.",
            )

    service = EnrichmentService.__new__(EnrichmentService)
    service.extractor = FakeExtractor()
    service.session = type(
        "FakeSession",
        (),
        {"commit": lambda self: _async_none()},
    )()

    result = await EnrichmentService._enrich_article(service, article)

    assert result is False
    assert enrichment.extraction_status == "failed"
    assert enrichment.enrichment_status == "skipped"


@pytest.mark.asyncio
async def test_enrich_raw_article_does_not_persist_when_ai_fails() -> None:
    raw_article = RawArticle(
        source="google_news_funding",
        title="Acme raises seed funding",
        url="https://example.com/acme",
        published_at=datetime(2026, 6, 9),
        content="Acme raised seed funding.",
    )

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.added = []
            self.committed = False
            self.rolled_back = False

        async def execute(self, statement):
            return FakeScalarResult()

        def add(self, value) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

    class FakeExtractor:
        async def extract(self, url: str) -> ExtractionResult:
            return ExtractionResult(
                status="extracted",
                final_url=url,
                text="Acme raised seed funding.",
            )

    class FakeLlmClient:
        async def enrich_article(self, **kwargs) -> LlamaCppResult:
            return LlamaCppResult(
                status="failed",
                model_name="qwen3-1.7b",
                error="invalid JSON",
            )

    session = FakeSession()
    service = EnrichmentService.__new__(EnrichmentService)
    service.session = session
    service.extractor = FakeExtractor()
    service.llm_client = FakeLlmClient()

    result = await EnrichmentService.enrich_raw_article(service, raw_article)

    assert result is False
    assert session.added == []
    assert session.committed is False
    assert session.rolled_back is True


async def _async_none() -> None:
    return None
