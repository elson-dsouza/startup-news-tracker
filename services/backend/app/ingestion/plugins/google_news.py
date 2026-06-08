from datetime import datetime
from typing import List

import feedparser
import httpx

from app.domain.raw_article import RawArticle
from app.ingestion.plugins.source_plugin import SourcePlugin


class GoogleNewsFundingPlugin(SourcePlugin):
    FEED_URL = "https://news.google.com/rss/search?q=india+startup+funding&hl=en-IN&gl=IN&ceid=IN:en"

    async def fetch(self) -> List[RawArticle]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(self.FEED_URL)
            response.raise_for_status()
            feed = feedparser.parse(response.text)

        articles: List[RawArticle] = []
        for entry in feed.entries:
            articles.append(
                RawArticle(
                    source="google_news",
                    title=entry.get("title", "").strip(),
                    url=entry.get("link", "").strip(),
                    published_at=self._parse_published(entry),
                    content=self._extract_content(entry),
                )
            )

        return articles

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
