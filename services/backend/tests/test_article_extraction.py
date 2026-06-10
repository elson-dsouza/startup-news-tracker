import pytest

from app.enrichment.extraction import ArticleExtractor


class FakeResponse:
    text = "<html><article>Readable story</article></html>"
    url = "https://publisher.example/story"

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url: str) -> FakeResponse:
        return FakeResponse()


@pytest.mark.asyncio
async def test_article_extractor_returns_readable_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.enrichment.extraction.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "app.enrichment.extraction._extract_readable_text",
        lambda *args, **kwargs: "Readable story",
    )

    result = await ArticleExtractor().extract("https://news.google.com/rss/article")

    assert result.status == "extracted"
    assert result.final_url == "https://publisher.example/story"
    assert result.text == "Readable story"


@pytest.mark.asyncio
async def test_article_extractor_marks_empty_text_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.enrichment.extraction.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "app.enrichment.extraction._extract_readable_text",
        lambda *args, **kwargs: None,
    )

    result = await ArticleExtractor().extract("https://example.com/empty")

    assert result.status == "failed"
    assert result.error == "No readable article text extracted."
