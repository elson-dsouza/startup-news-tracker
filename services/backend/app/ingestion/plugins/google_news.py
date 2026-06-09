from datetime import datetime
from typing import ClassVar, List
from urllib.parse import quote_plus

import feedparser
import httpx

from app.core.config import settings
from app.domain.raw_article import RawArticle
from app.ingestion.plugins.source_plugin import SourcePlugin


class GoogleNewsSearchPlugin(SourcePlugin):
    queries: ClassVar[tuple[str, ...]]
    source_id: ClassVar[str]
    display_name: ClassVar[str]

    async def fetch(self) -> List[RawArticle]:
        articles: list[RawArticle] = []
        headers = {"User-Agent": settings.source_user_agent}
        async with httpx.AsyncClient(
            timeout=settings.source_timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for feed_url in self.feed_urls:
                response = await client.get(feed_url)
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                for entry in feed.entries:
                    title = entry.get("title", "").strip()
                    url = entry.get("link", "").strip()
                    if not title or not url:
                        continue

                    articles.append(
                        RawArticle(
                            source=self.source_id,
                            title=title,
                            url=url,
                            published_at=self._parse_published(entry),
                            content=self._extract_content(entry),
                            external_id=entry.get("id") or entry.get("guid"),
                            source_url=url,
                        )
                    )

        return articles

    @property
    def feed_urls(self) -> tuple[str, ...]:
        return tuple(self._feed_url_for_query(query) for query in self.queries)

    @staticmethod
    def _feed_url_for_query(query: str) -> str:
        encoded_query = quote_plus(query)
        return (
            "https://news.google.com/rss/search?"
            f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        )

    @staticmethod
    def _parse_published(entry: dict) -> datetime | None:
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not published_parsed:
            return None

        return datetime(
            published_parsed.tm_year,
            published_parsed.tm_mon,
            published_parsed.tm_mday,
            published_parsed.tm_hour,
            published_parsed.tm_min,
            published_parsed.tm_sec,
        )

    @staticmethod
    def _extract_content(entry: dict) -> str | None:
        if summary := entry.get("summary"):
            return summary

        content = entry.get("content")
        if isinstance(content, list) and content:
            return content[0].get("value")

        return None


class GoogleNewsFundingPlugin(GoogleNewsSearchPlugin):
    source_id = "google_news_funding"
    display_name = "Google News Funding"
    queries = (
        "india startup funding",
        "indian startup raises funding",
        "series a funding india",
        "seed funding india",
    )


class GoogleNewsVentureCapitalPlugin(GoogleNewsSearchPlugin):
    source_id = "google_news_venture_capital"
    display_name = "Google News Venture Capital"
    queries = (
        "india startup venture funding",
        "seed fund india",
        "venture fund india",
        "venture capital india",
    )
