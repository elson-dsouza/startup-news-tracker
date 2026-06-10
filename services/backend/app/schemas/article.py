from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ArticleEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    name: str
    normalized_name: str


class ArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    title: str
    url: str
    external_id: str | None
    source_url: str | None
    published_at: datetime | None
    content: str | None
    created_at: datetime
    summary: str | None = None
    entities: list[ArticleEntityRead] = []
    startup_country: str | None = None
    publisher_country: str | None = None
    mentioned_countries: list[str] = []
    funding_amount_usd: Decimal | None = None
    funding_amount_original: str | None = None
    funding_currency_original: str | None = None
    funding_round: str | None = None
    enrichment_status: str = "pending"


class ArticleSourceRead(BaseModel):
    id: str
    display_name: str
    enabled: bool
    latest_article_at: datetime | None = None


class ArticleEntityFacet(BaseModel):
    entity_type: str
    name: str
    normalized_name: str
    count: int


class ArticleCountryFacets(BaseModel):
    startup: list[str]
    publisher: list[str]
    mentioned: list[str]


class ArticleFundingFacet(BaseModel):
    min_usd: Decimal | None = None
    max_usd: Decimal | None = None


class ArticleFacetsRead(BaseModel):
    entities: list[ArticleEntityFacet]
    countries: ArticleCountryFacets
    funding: ArticleFundingFacet
