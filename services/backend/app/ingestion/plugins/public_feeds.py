from html.parser import HTMLParser
from typing import ClassVar, Iterable, List
from urllib.parse import urljoin

import feedparser
import httpx

from app.core.config import settings
from app.domain.raw_article import RawArticle
from app.ingestion.plugins.google_news import GoogleNewsSearchPlugin
from app.ingestion.plugins.source_plugin import SourcePlugin


class PublicListingParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._current_href = urljoin(self.base_url, href)
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current_href:
            return

        title = " ".join(" ".join(self._current_text).split())
        if title:
            self.links.append((title, self._current_href))
        self._current_href = None
        self._current_text = []


class PublicFeedPlugin(SourcePlugin):
    source_id: ClassVar[str]
    display_name: ClassVar[str]
    feed_urls: ClassVar[tuple[str, ...]] = ()
    listing_urls: ClassVar[tuple[str, ...]] = ()
    include_terms: ClassVar[tuple[str, ...]] = (
        "funding",
        "raises",
        "raised",
        "venture",
        "seed",
        "series",
        "investment",
        "investor",
        "capital",
    )

    async def fetch(self) -> List[RawArticle]:
        articles: list[RawArticle] = []
        headers = {"User-Agent": settings.source_user_agent}
        async with httpx.AsyncClient(
            timeout=settings.source_timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for feed_url in self.feed_urls:
                articles.extend(await self._fetch_feed(client, feed_url))
            for listing_url in self.listing_urls:
                articles.extend(await self._fetch_listing(client, listing_url))

        return self._deduplicate(articles)

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed_url: str
    ) -> list[RawArticle]:
        response = await client.get(feed_url)
        response.raise_for_status()
        feed = feedparser.parse(response.text)

        articles: list[RawArticle] = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            if not title or not url or not self._matches_focus(title):
                continue

            articles.append(
                RawArticle(
                    source=self.source_id,
                    title=title,
                    url=url,
                    published_at=GoogleNewsSearchPlugin._parse_published(entry),
                    content=GoogleNewsSearchPlugin._extract_content(entry),
                    external_id=entry.get("id") or entry.get("guid"),
                    source_url=feed_url,
                )
            )
        return articles

    async def _fetch_listing(
        self, client: httpx.AsyncClient, listing_url: str
    ) -> list[RawArticle]:
        response = await client.get(listing_url)
        response.raise_for_status()
        parser = PublicListingParser(listing_url)
        parser.feed(response.text)

        return [
            RawArticle(
                source=self.source_id,
                title=title,
                url=url,
                published_at=None,
                content=None,
                external_id=url,
                source_url=listing_url,
            )
            for title, url in parser.links
            if self._matches_focus(title)
        ]

    def _matches_focus(self, title: str) -> bool:
        normalized = title.lower()
        return any(term in normalized for term in self.include_terms)

    @staticmethod
    def _deduplicate(articles: Iterable[RawArticle]) -> list[RawArticle]:
        seen: set[str] = set()
        unique: list[RawArticle] = []
        for article in articles:
            if article.url in seen:
                continue
            seen.add(article.url)
            unique.append(article)
        return unique


class EntrackrFundingPlugin(PublicFeedPlugin):
    source_id = "entrackr_funding"
    display_name = "Entrackr Funding"
    feed_urls = (
        "https://entrackr.com/feed",
        "https://entrackr.com/tags/funding/feed",
    )
    listing_urls = (
        "https://entrackr.com/tags/funding",
        "https://entrackr.com/report",
    )


class Inc42IndiaFundingPlugin(PublicFeedPlugin):
    source_id = "inc42_india_funding"
    display_name = "Inc42 India Funding"
    feed_urls = (
        "https://inc42.com/feed/",
        "https://inc42.com/location/india/feed/",
    )
    listing_urls = (
        "https://inc42.com/location/india/",
        "https://inc42.com/buzz/",
    )


class YourStoryStartupFundingPlugin(PublicFeedPlugin):
    source_id = "yourstory_startup_funding"
    display_name = "YourStory Startup Funding"
    feed_urls = (
        "https://yourstory.com/feed",
        "https://yourstory.com/category/startup-funding/feed",
    )
    listing_urls = ("https://yourstory.com/category/startup-funding",)


class VCCircleStartupFundingPlugin(PublicFeedPlugin):
    source_id = "vccircle_startup_funding"
    display_name = "VCCircle Startup Funding"
    feed_urls = (
        "https://www.vccircle.com/rss",
        "https://www.vccircle.com/rss/startups",
    )
    listing_urls = ("https://www.vccircle.com/startups",)
