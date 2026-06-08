from typing import Iterable, List, Set

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.plugins import load_plugins
from app.ingestion.plugins.source_plugin import SourcePlugin
from app.models.article import Article
from app.domain.raw_article import RawArticle


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self) -> tuple[int, int]:
        load_plugins()
        plugin_classes = SourcePlugin.get_plugins()
        raw_articles: List[RawArticle] = []

        for plugin_class in plugin_classes:
            plugin = plugin_class()
            raw_articles.extend(await plugin.fetch())

        unique_articles = self._deduplicate_by_url(raw_articles)
        existing_urls = await self._fetch_existing_urls(unique_articles)
        new_articles = [
            article for article in unique_articles if article.url not in existing_urls
        ]

        created_count = await self._store_articles(new_articles)
        return created_count, len(raw_articles)

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
