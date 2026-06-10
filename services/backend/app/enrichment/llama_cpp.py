import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.enrichment.countries import normalize_countries, normalize_country

logger = logging.getLogger(__name__)


ALLOWED_ENTITY_TYPES = {"startup", "investor", "person"}


@dataclass(frozen=True)
class EnrichedEntity:
    entity_type: str
    name: str


@dataclass(frozen=True)
class EnrichmentPayload:
    summary: str | None
    entities: list[EnrichedEntity]
    startup_country: str | None
    publisher_country: str | None
    mentioned_countries: list[str]
    funding_amount_original: str | None
    funding_currency_original: str | None
    funding_amount_usd: str | None
    funding_round: str | None


@dataclass(frozen=True)
class LlamaCppResult:
    status: str
    model_name: str
    payload: EnrichmentPayload | None = None
    error: str | None = None


class LlamaCppClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llama_cpp_base_url).rstrip("/")
        self.model = model or settings.llama_cpp_model

    async def enrich_article(
        self,
        *,
        title: str,
        source: str,
        url: str,
        published_at: str | None,
        rss_content: str | None,
        full_text: str,
    ) -> LlamaCppResult:
        messages = self._build_messages(
            title=title,
            source=source,
            url=url,
            published_at=published_at,
            rss_content=rss_content,
            full_text=full_text,
        )
        try:
            generated_text = await self._request_completion(messages, use_schema=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {400, 422}:
                return self._http_failure(exc)
            try:
                generated_text = await self._request_completion(
                    messages, use_schema=False
                )
            except httpx.HTTPError as fallback_exc:
                return self._http_failure(fallback_exc)
        except httpx.HTTPError as exc:
            return self._http_failure(exc)

        try:
            parsed = self._parse_payload(generated_text)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return LlamaCppResult(
                status="failed",
                model_name=self.model,
                error=f"Invalid llama.cpp JSON response: {exc}"[:1000],
            )

        return LlamaCppResult(
            status="enriched",
            model_name=self.model,
            payload=parsed,
        )

    async def _request_completion(
        self, messages: list[dict[str, str]], *, use_schema: bool
    ) -> str:
        response_format = (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "article_enrichment",
                    "schema": self._schema(),
                    "strict": True,
                },
            }
            if use_schema
            else {"type": "json_object"}
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                    "cache_prompt": False,
                    "response_format": response_format,
                },
            )
            response.raise_for_status()

        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Missing chat completion choices")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ValueError("Missing chat completion message")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Missing chat completion content")

        return content

    def _http_failure(self, exc: httpx.HTTPError) -> LlamaCppResult:
        logger.info("llama.cpp enrichment failed: %s", exc)
        return LlamaCppResult(
            status="failed",
            model_name=self.model,
            error=str(exc)[:1000],
        )

    @classmethod
    def _build_messages(
        cls,
        *,
        title: str,
        source: str,
        url: str,
        published_at: str | None,
        rss_content: str | None,
        full_text: str,
    ) -> list[dict[str, str]]:
        bounded_text = full_text[:12000]
        schema_text = json.dumps(cls._schema(), separators=(",", ":"))
        return [
            {
                "role": "system",
                "content": (
                    "You extract healthcare innovation and funding intelligence. "
                    "Return exactly one valid JSON object and no prose. The JSON "
                    "must match this schema: "
                    f"{schema_text}"
                ),
            },
            {
                "role": "user",
                "content": f"""
Extract healthcare innovation and funding intelligence from this article.

Rules:
- summary: 2-4 concise sentences for dashboard reading.
- Capture the full healthcare funding ecosystem, not only startup rounds. Relevant
  events include startup funding rounds, VC activity, government healthcare
  funding, grants, innovation programs, accelerators, research funding,
  public-private partnerships, hospital innovation initiatives, corporate
  healthcare investments, and regulatory announcements that influence funding
  flows.
- entities: include only startup/company/organization names as startup,
  investor/fund/government grantmaker/corporate funder/accelerator names as
  investor, and named people as person.
- startup_country: country of the funded startup/company/organization or main
  healthcare innovation beneficiary when inferable.
- publisher_country: country associated with the publisher/source when inferable.
- mentioned_countries: all country names materially mentioned in the story.
- Country fields must use valid ISO 3166 country names only. Do not return
  regions, economic blocs, continents, or subnational places such as Asia, EU,
  Europe, APAC, Indiana, California, or London.
- funding_amount_original: preserve the original announced amount exactly when
  the article provides one, including grants, government allocations, program
  budgets, research awards, investment commitments, and partnership values.
- funding_currency_original: original currency code or currency name when
  inferable.
- funding_amount_usd: normalize the relevant amount to USD as a number string
  when possible. Use null when no funding value is stated or conversion is not
  reasonably inferable from common currency knowledge.
- funding_round: use the article's funding/event category, such as Seed,
  Series A, Grant, Government funding, Research funding, Accelerator,
  Public-private partnership, Hospital innovation initiative, Corporate
  investment, VC fund activity, Regulatory catalyst, or the closest concise label.
- If a field is unknown, use null or an empty list.

Title: {title}
Source: {source}
URL: {url}
Published at: {published_at or "unknown"}
RSS content: {rss_content or "none"}

Article text:
{bounded_text}
""".strip(),
            },
        ]

    @staticmethod
    def _schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": ["string", "null"]},
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity_type": {
                                "type": "string",
                                "enum": sorted(ALLOWED_ENTITY_TYPES),
                            },
                            "name": {"type": "string"},
                        },
                        "required": ["entity_type", "name"],
                    },
                },
                "startup_country": {"type": ["string", "null"]},
                "publisher_country": {"type": ["string", "null"]},
                "mentioned_countries": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "funding_amount_original": {"type": ["string", "null"]},
                "funding_currency_original": {"type": ["string", "null"]},
                "funding_amount_usd": {"type": ["string", "number", "null"]},
                "funding_round": {"type": ["string", "null"]},
            },
            "required": [
                "summary",
                "entities",
                "startup_country",
                "publisher_country",
                "mentioned_countries",
                "funding_amount_original",
                "funding_currency_original",
                "funding_amount_usd",
                "funding_round",
            ],
        }

    @classmethod
    def _parse_payload(cls, generated_text: str) -> EnrichmentPayload:
        cleaned = generated_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

        raw = json.loads(cleaned)
        if not isinstance(raw, dict):
            raise ValueError("Expected object payload")

        entities = []
        for item in raw.get("entities") or []:
            if not isinstance(item, dict):
                continue
            entity_type = str(item.get("entity_type") or "").strip().lower()
            name = str(item.get("name") or "").strip()
            if entity_type in ALLOWED_ENTITY_TYPES and name:
                entities.append(EnrichedEntity(entity_type=entity_type, name=name))

        return EnrichmentPayload(
            summary=cls._optional_string(raw.get("summary")),
            entities=entities,
            startup_country=normalize_country(
                cls._optional_string(raw.get("startup_country"))
            ),
            publisher_country=normalize_country(
                cls._optional_string(raw.get("publisher_country"))
            ),
            mentioned_countries=normalize_countries(raw.get("mentioned_countries")),
            funding_amount_original=cls._optional_string(
                raw.get("funding_amount_original")
            ),
            funding_currency_original=cls._optional_string(
                raw.get("funding_currency_original")
            ),
            funding_amount_usd=cls._optional_string(raw.get("funding_amount_usd")),
            funding_round=cls._optional_string(raw.get("funding_round")),
        )

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
