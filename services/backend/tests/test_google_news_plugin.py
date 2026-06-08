from datetime import datetime
from time import struct_time

from app.ingestion.plugins.google_news import GoogleNewsFundingPlugin


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
