from datetime import datetime
from functools import lru_cache
from pathlib import Path
import re
from typing import ClassVar, List
from urllib.parse import quote_plus

import feedparser
import httpx
import yaml  # type: ignore[import-untyped]

from app.core.config import settings
from app.domain.raw_article import RawArticle
from app.ingestion.plugins.source_plugin import SourcePlugin


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "google_news.yaml"


def _configured_google_news_path() -> Path:
    configured_path = Path(settings.google_news_queries_path)
    if configured_path.is_absolute():
        return configured_path

    cwd_path = Path.cwd() / configured_path
    if cwd_path.exists():
        return cwd_path

    return _default_config_path()


@lru_cache(maxsize=1)
def load_google_news_queries() -> dict[str, tuple[str, ...]]:
    config_path = _configured_google_news_path()
    if not config_path.exists():
        return {}

    with config_path.open(encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"Google News query config must be a mapping: {config_path}")

    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError(
            f"Google News query config 'sources' must be a mapping: {config_path}"
        )

    query_map: dict[str, tuple[str, ...]] = {}
    for source_id, source_config in sources.items():
        if not isinstance(source_id, str) or not isinstance(source_config, dict):
            continue

        queries = source_config.get("queries", [])
        if not isinstance(queries, list):
            raise ValueError(
                f"Google News queries for '{source_id}' must be a list: {config_path}"
            )

        cleaned_queries = tuple(
            query.strip()
            for query in queries
            if isinstance(query, str) and query.strip()
        )
        if cleaned_queries:
            query_map[source_id] = cleaned_queries

    return query_map


class GoogleNewsSearchPlugin(SourcePlugin):
    default_queries: ClassVar[tuple[str, ...]]
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
                            source=self._extract_source_id(entry),
                            title=title,
                            url=url,
                            published_at=self._parse_published(entry),
                            content=self._extract_content(entry),
                            external_id=entry.get("id") or entry.get("guid"),
                            source_url=self._extract_source_url(entry) or url,
                        )
                    )

        return articles

    @property
    def feed_urls(self) -> tuple[str, ...]:
        return tuple(self._feed_url_for_query(query) for query in self.queries)

    @property
    def queries(self) -> tuple[str, ...]:
        return load_google_news_queries().get(self.source_id, self.default_queries)

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

    def _extract_source_id(self, entry: dict) -> str:
        source_name = self._extract_source_name(entry)
        if not source_name:
            return self.source_id

        return self._normalize_source_id(source_name)

    @staticmethod
    def _extract_source_name(entry: dict) -> str | None:
        source = entry.get("source")
        if isinstance(source, dict):
            title = source.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()

        return None

    @staticmethod
    def _extract_source_url(entry: dict) -> str | None:
        source = entry.get("source")
        if isinstance(source, dict):
            href = source.get("href")
            if isinstance(href, str) and href.strip():
                return href.strip()

        return None

    @staticmethod
    def _normalize_source_id(source_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", source_name.lower()).strip("_")
        return normalized or "google_news"


class GoogleNewsFundingPlugin(GoogleNewsSearchPlugin):
    source_id = "google_news_funding"
    display_name = "Google News Funding"
    default_queries = (
        "india startup funding",
        "indian startup raises funding",
        "series a funding india",
        "seed funding india",
    )


class GoogleNewsVentureCapitalPlugin(GoogleNewsSearchPlugin):
    source_id = "google_news_venture_capital"
    display_name = "Google News Venture Capital"
    default_queries = (
        "india startup venture funding",
        "seed fund india",
        "venture fund india",
        "venture capital india",
    )
