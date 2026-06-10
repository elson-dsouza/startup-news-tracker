import pytest
import httpx

from app.enrichment.countries import normalize_country
from app.enrichment.llama_cpp import LlamaCppClient


def test_llama_cpp_client_parses_structured_payload() -> None:
    payload = LlamaCppClient._parse_payload(
        """
{
  "summary": "Acme raised a seed round.",
  "entities": [
    {"entity_type": "startup", "name": "Acme"},
    {"entity_type": "investor", "name": "First Fund"},
    {"entity_type": "sector", "name": "Fintech"}
  ],
  "startup_country": "IND",
  "publisher_country": "U.S.",
  "mentioned_countries": ["India", "United States", "India", "Asia", "EU", "Indiana"],
  "funding_amount_original": "$5 million",
  "funding_currency_original": "USD",
  "funding_amount_usd": "5000000",
  "funding_round": "Seed"
}
"""
    )

    assert payload.summary == "Acme raised a seed round."
    assert [entity.entity_type for entity in payload.entities] == [
        "startup",
        "investor",
    ]
    assert payload.startup_country == "India"
    assert payload.publisher_country == "United States"
    assert payload.mentioned_countries == ["India", "United States"]
    assert payload.funding_amount_usd == "5000000"


def test_country_normalizer_rejects_regions_and_subnational_places() -> None:
    assert normalize_country("Asia") is None
    assert normalize_country("EU") is None
    assert normalize_country("Indiana") is None
    assert normalize_country("California") is None
    assert normalize_country("UAE") == "United Arab Emirates"
    assert normalize_country("UK") == "United Kingdom"


def test_llama_cpp_client_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        LlamaCppClient._parse_payload("[]")


def test_llama_cpp_prompt_targets_healthcare_funding_ecosystem() -> None:
    messages = LlamaCppClient._build_messages(
        title="Hospital launches AI innovation grant program",
        source="google_news_funding",
        url="https://example.com/story",
        published_at=None,
        rss_content=None,
        full_text="A hospital and government agency launched a healthcare grant.",
    )

    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "healthcare innovation and funding intelligence" in system_prompt
    assert "government healthcare" in user_prompt
    assert "grants" in user_prompt
    assert "public-private partnerships" in user_prompt
    assert "regulatory announcements" in user_prompt
    assert "startup funding" in user_prompt


@pytest.mark.asyncio
async def test_llama_cpp_client_falls_back_to_json_object(monkeypatch) -> None:
    calls: list[bool] = []

    async def fake_request(self, messages, *, use_schema: bool) -> str:
        calls.append(use_schema)
        if use_schema:
            import httpx

            request = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError(
                "bad schema", request=request, response=response
            )
        return """
{
  "summary": "Fallback worked.",
  "entities": [],
  "startup_country": null,
  "publisher_country": null,
  "mentioned_countries": [],
  "funding_amount_original": null,
  "funding_currency_original": null,
  "funding_amount_usd": null,
  "funding_round": null
}
"""

    monkeypatch.setattr(LlamaCppClient, "_request_completion", fake_request)

    result = await LlamaCppClient().enrich_article(
        title="Story",
        source="source",
        url="https://example.com",
        published_at=None,
        rss_content=None,
        full_text="Article text",
    )

    assert result.status == "enriched"
    assert result.payload is not None
    assert result.payload.summary == "Fallback worked."
    assert calls == [True, False]


@pytest.mark.asyncio
async def test_llama_cpp_client_disables_prompt_cache_per_request(monkeypatch) -> None:
    captured_payloads: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {"message": {"content": "{}"}},
                ]
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, json: dict) -> FakeResponse:
            captured_payloads.append(json)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    result = await LlamaCppClient()._request_completion(
        [{"role": "user", "content": "test"}],
        use_schema=False,
    )

    assert result == "{}"
    assert captured_payloads[0]["cache_prompt"] is False
