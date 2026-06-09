from datetime import datetime
from time import struct_time

from app.ingestion.plugins.google_news import (
    GoogleNewsFundingPlugin,
    GoogleNewsVentureCapitalPlugin,
    load_google_news_queries,
)


def test_parse_published_uses_feedparser_time() -> None:
    entry = {
        "published_parsed": struct_time((2026, 6, 8, 10, 30, 0, 0, 0, 0)),
    }

    result = GoogleNewsFundingPlugin._parse_published(entry)

    assert result == datetime(2026, 6, 8, 10, 30, 0)


def test_extract_content_prefers_summary() -> None:
    entry = {
        "summary": "Summary text",
        "content": [{"value": "Content text"}],
    }

    result = GoogleNewsFundingPlugin._extract_content(entry)

    assert result == "Summary text"


def test_google_news_plugin_extracts_publisher_source() -> None:
    entry = {
        "source": {
            "title": "The Economic Times",
            "href": "https://economictimes.indiatimes.com",
        }
    }
    plugin = GoogleNewsFundingPlugin()

    assert plugin._extract_source_id(entry) == "the_economic_times"
    assert plugin._extract_source_url(entry) == "https://economictimes.indiatimes.com"


def test_google_news_plugins_fall_back_to_code_defaults(monkeypatch, tmp_path) -> None:
    missing_config = tmp_path / "missing_google_news.yaml"
    monkeypatch.setattr(
        "app.ingestion.plugins.google_news.settings.google_news_queries_path",
        str(missing_config),
    )
    load_google_news_queries.cache_clear()

    try:
        assert GoogleNewsFundingPlugin().queries == (
            "india startup funding",
            "indian startup raises funding",
            "series a funding india",
            "seed funding india",
        )
        assert GoogleNewsVentureCapitalPlugin().queries == (
            "india startup venture funding",
            "seed fund india",
            "venture fund india",
            "venture capital india",
        )
        assert (
            GoogleNewsFundingPlugin().feed_urls
            != GoogleNewsVentureCapitalPlugin().feed_urls
        )
        assert GoogleNewsFundingPlugin.source_id == "google_news_funding"
        assert GoogleNewsVentureCapitalPlugin.source_id == "google_news_venture_capital"
    finally:
        load_google_news_queries.cache_clear()


def test_google_news_plugin_reads_default_yaml() -> None:
    load_google_news_queries.cache_clear()

    try:
        queries = load_google_news_queries()

        assert queries["google_news_funding"]
        assert queries["google_news_venture_capital"]
    finally:
        load_google_news_queries.cache_clear()


def test_google_news_plugin_reads_queries_from_yaml(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "google_news.yaml"
    config_path.write_text(
        """
sources:
  google_news_funding:
    queries:
      - fintech funding india
      - climate startup funding india
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.ingestion.plugins.google_news.settings.google_news_queries_path",
        str(config_path),
    )
    load_google_news_queries.cache_clear()

    try:
        plugin = GoogleNewsFundingPlugin()

        assert plugin.queries == (
            "fintech funding india",
            "climate startup funding india",
        )
        assert plugin.feed_urls == (
            "https://news.google.com/rss/search?q=fintech+funding+india&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=climate+startup+funding+india&hl=en-IN&gl=IN&ceid=IN:en",
        )
        assert GoogleNewsVentureCapitalPlugin().queries == (
            "india startup venture funding",
            "seed fund india",
            "venture fund india",
            "venture capital india",
        )
    finally:
        load_google_news_queries.cache_clear()


def test_google_news_plugins_have_distinct_source_ids() -> None:
    assert GoogleNewsFundingPlugin.default_queries == (
        "india startup funding",
        "indian startup raises funding",
        "series a funding india",
        "seed funding india",
    )
    assert GoogleNewsFundingPlugin.source_id == "google_news_funding"
    assert GoogleNewsVentureCapitalPlugin.source_id == "google_news_venture_capital"
