import httpx
import pytest

from app.ingestion.plugins.public_feeds import (
    EntrackrFundingPlugin,
    Inc42IndiaFundingPlugin,
    PublicListingParser,
    VCCircleStartupFundingPlugin,
    YourStoryStartupFundingPlugin,
)


def test_public_listing_parser_extracts_absolute_links() -> None:
    parser = PublicListingParser("https://example.com/funding")

    parser.feed(
        """
        <a href="/article-one">Startup raises seed funding</a>
        <a href="https://other.example/story">Unrelated story</a>
        """
    )

    assert parser.links == [
        ("Startup raises seed funding", "https://example.com/article-one"),
        ("Unrelated story", "https://other.example/story"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin_class",
    [
        EntrackrFundingPlugin,
        Inc42IndiaFundingPlugin,
        YourStoryStartupFundingPlugin,
        VCCircleStartupFundingPlugin,
    ],
)
async def test_public_feed_plugins_parse_funding_entries(plugin_class) -> None:
    feed = """
    <rss><channel>
      <item>
        <title>Acme raises Series A funding</title>
        <link>https://example.com/acme</link>
        <guid>acme-guid</guid>
        <description>Funding summary</description>
        <pubDate>Mon, 08 Jun 2026 10:30:00 GMT</pubDate>
      </item>
      <item>
        <title>Founder profile</title>
        <link>https://example.com/profile</link>
      </item>
    </channel></rss>
    """

    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=feed))
    async with httpx.AsyncClient(transport=transport) as client:
        articles = await plugin_class()._fetch_feed(client, "https://example.com/feed")

    assert len(articles) == 1
    assert articles[0].source == plugin_class.source_id
    assert articles[0].title == "Acme raises Series A funding"
    assert articles[0].url == "https://example.com/acme"
    assert articles[0].external_id == "acme-guid"
