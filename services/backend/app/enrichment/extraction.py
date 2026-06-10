import logging
import re
from dataclasses import dataclass

import httpx

try:
    import trafilatura  # type: ignore[import-not-found]
except ImportError:
    trafilatura = None  # type: ignore[assignment]

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    final_url: str
    text: str | None = None
    error: str | None = None


class ArticleExtractor:
    async def extract(self, url: str) -> ExtractionResult:
        headers = {"User-Agent": settings.source_user_agent}
        try:
            async with httpx.AsyncClient(
                timeout=settings.source_timeout_seconds,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("Article extraction fetch failed for %s: %s", url, exc)
            return ExtractionResult(
                status="failed",
                final_url=url,
                error=str(exc)[:1000],
            )

        extracted_text = _extract_readable_text(response.text, str(response.url))
        if not extracted_text or not extracted_text.strip():
            return ExtractionResult(
                status="failed",
                final_url=str(response.url),
                error="No readable article text extracted.",
            )

        return ExtractionResult(
            status="extracted",
            final_url=str(response.url),
            text=extracted_text.strip(),
        )


def _extract_readable_text(html: str, url: str) -> str | None:
    if trafilatura is not None:
        return trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            url=url,
        )

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
