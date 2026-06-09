import logging
from dataclasses import replace
from typing import Iterable, List, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.raw_article import RawArticle
from app.ingestion.plugins import load_plugins
from app.ingestion.plugins.source_plugin import SourcePlugin
from app.models.article import Article

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self) -> tuple[int, int]:
        load_plugins()
        enabled_sources = settings.enabled_source_ids
        plugin_classes = [
            plugin_class
            for plugin_class in SourcePlugin.get_plugins()
            if plugin_class.is_enabled(enabled_sources)
        ]
        raw_articles: List[RawArticle] = []

        for plugin_class in plugin_classes:
            plugin = plugin_class()
            try:
                plugin_articles = await plugin.fetch()
            except Exception:
                logger.exception("Source %s failed during ingestion", plugin.source_id)
                continue

            logger.info(
                "Source %s fetched %s articles",
                plugin.source_id,
                len(plugin_articles),
            )
            raw_articles.extend(plugin_articles)

        prepared_articles = self._prepare_articles(raw_articles)
        unique_articles = self._deduplicate_by_url(prepared_articles)
        existing_urls = await self._fetch_existing_urls(unique_articles)
        new_articles = [
            article for article in unique_articles if article.url not in existing_urls
        ]

        created_count = await self._store_articles(new_articles)
        return created_count, len(raw_articles)

    @staticmethod
    def source_metadata() -> list[dict[str, object]]:
        load_plugins()
        enabled_sources = settings.enabled_source_ids
        return [
            {
                "id": plugin_class.source_id,
                "display_name": plugin_class.display_name,
                "enabled": plugin_class.is_enabled(enabled_sources),
            }
            for plugin_class in SourcePlugin.get_plugins()
        ]

    @classmethod
    def _prepare_articles(cls, raw_articles: Iterable[RawArticle]) -> List[RawArticle]:
        prepared: List[RawArticle] = []
        for article in raw_articles:
            title = article.title.strip()
            url = cls._normalize_url(article.url)
            if not title or not url:
                continue

            source_url = article.source_url
            if article.url and article.url != url and not source_url:
                source_url = article.url

            prepared.append(
                replace(
                    article,
                    title=title,
                    url=url,
                    source_url=source_url,
                )
            )
        return prepared

    @staticmethod
    def _deduplicate_by_url(raw_articles: Iterable[RawArticle]) -> List[RawArticle]:
        seen: Set[str] = set()
        unique: List[RawArticle] = []
        for article in raw_articles:
            if article.url in seen:
                continue
            seen.add(article.url)
            unique.append(article)
        return unique

    async def _fetch_existing_urls(self, raw_articles: List[RawArticle]) -> Set[str]:
        urls = [article.url for article in raw_articles]
        if not urls:
            return set()

        result = await self.session.execute(
            select(Article.url).where(Article.url.in_(urls))
        )
        return {row[0] for row in result.fetchall()}

    async def _store_articles(self, raw_articles: List[RawArticle]) -> int:
        if not raw_articles:
            return 0

        articles = [
            Article(
                source=raw.source,
                title=raw.title,
                url=raw.url,
                external_id=raw.external_id,
                source_url=raw.source_url,
                published_at=raw.published_at,
                content=raw.content,
            )
            for raw in raw_articles
        ]
        self.session.add_all(articles)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return 0

        return len(articles)

    @staticmethod
    def _normalize_url(url: str) -> str:
        cleaned = url.strip()
        if not cleaned:
            return ""

        parsed = urlsplit(cleaned)
        if not parsed.scheme or not parsed.netloc:
            return cleaned

        dropped_prefixes = ("utm_",)
        dropped_keys = {
            "fbclid",
            "gclid",
            "igshid",
            "mc_cid",
            "mc_eid",
            "ref",
        }
        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in dropped_keys
            and not any(key.startswith(prefix) for prefix in dropped_prefixes)
        ]
        normalized_query = urlencode(query_pairs, doseq=True)
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/") or "/",
                normalized_query,
                "",
            )
        )
