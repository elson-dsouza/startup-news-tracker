from datetime import datetime
from decimal import Decimal
from uuid import UUID
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.deps import get_session
from app.ingestion.services.ingestion_service import IngestionService
from app.models.article import Article, ArticleEnrichment, ArticleEntity
from app.schemas.article import (
    ArticleCountryFacets,
    ArticleEntityFacet,
    ArticleEntityRead,
    ArticleFacetsRead,
    ArticleFundingFacet,
    ArticleRead,
    ArticleSourceRead,
)

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=list[ArticleRead])
async def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    entity: list[str] | None = Query(default=None),
    entity_type: list[str] | None = Query(default=None),
    funding_min_usd: Decimal | None = Query(default=None, ge=0),
    funding_max_usd: Decimal | None = Query(default=None, ge=0),
    startup_country: list[str] | None = Query(default=None),
    publisher_country: list[str] | None = Query(default=None),
    mentioned_country: list[str] | None = Query(default=None),
    published_after: datetime | None = Query(default=None),
    published_before: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[ArticleRead]:
    statement = select(Article).options(
        selectinload(Article.enrichment),
        selectinload(Article.entities),
    )
    if _needs_enrichment_join(
        q=q,
        funding_min_usd=funding_min_usd,
        funding_max_usd=funding_max_usd,
        startup_country=startup_country,
        publisher_country=publisher_country,
        mentioned_country=mentioned_country,
    ):
        statement = statement.outerjoin(ArticleEnrichment)
    if entity or entity_type:
        statement = statement.join(ArticleEntity)

    if source:
        statement = statement.where(Article.source.in_(source))
    if q:
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Article.title.ilike(term),
                Article.content.ilike(term),
                ArticleEnrichment.summary.ilike(term),
                ArticleEnrichment.full_text.ilike(term),
            )
        )
    if entity:
        normalized_entities = [_normalize_filter_value(value) for value in entity]
        statement = statement.where(
            ArticleEntity.normalized_name.in_(normalized_entities)
        )
    if entity_type:
        normalized_types = [
            value.strip().lower() for value in entity_type if value.strip()
        ]
        statement = statement.where(ArticleEntity.entity_type.in_(normalized_types))
    if funding_min_usd is not None:
        statement = statement.where(
            ArticleEnrichment.funding_amount_usd >= funding_min_usd
        )
    if funding_max_usd is not None:
        statement = statement.where(
            ArticleEnrichment.funding_amount_usd <= funding_max_usd
        )
    if startup_country:
        statement = statement.where(
            func.lower(ArticleEnrichment.startup_country).in_(
                [_normalize_country_filter(value) for value in startup_country]
            )
        )
    if publisher_country:
        statement = statement.where(
            func.lower(ArticleEnrichment.publisher_country).in_(
                [_normalize_country_filter(value) for value in publisher_country]
            )
        )
    if mentioned_country:
        mentioned_filters = [
            ArticleEnrichment.mentioned_countries.contains([value.strip()])
            for value in mentioned_country
            if value.strip()
        ]
        if mentioned_filters:
            statement = statement.where(or_(*mentioned_filters))
    if published_after:
        statement = statement.where(Article.published_at >= published_after)
    if published_before:
        statement = statement.where(Article.published_at <= published_before)

    result = await session.execute(
        statement.order_by(Article.published_at.desc(), Article.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    articles = result.scalars().unique().all()
    return [_serialize_article(article) for article in articles]


@router.get("/sources", response_model=list[ArticleSourceRead])
async def list_article_sources(
    session: AsyncSession = Depends(get_session),
) -> list[ArticleSourceRead]:
    result = await session.execute(
        select(Article.source, func.max(Article.published_at)).group_by(Article.source)
    )
    latest_by_source = {row[0]: row[1] for row in result.fetchall()}

    source_metadata = {
        str(source["id"]): {
            "display_name": str(source["display_name"]),
            "enabled": bool(source["enabled"]),
        }
        for source in IngestionService.source_metadata()
    }
    for source_id in latest_by_source:
        source_metadata.setdefault(
            source_id,
            {
                "display_name": _source_display_name(source_id),
                "enabled": True,
            },
        )

    return [
        ArticleSourceRead(
            id=source_id,
            display_name=str(metadata["display_name"]),
            enabled=bool(metadata["enabled"]),
            latest_article_at=latest_by_source.get(source_id),
        )
        for source_id, metadata in sorted(
            source_metadata.items(), key=lambda item: str(item[1]["display_name"])
        )
    ]


@router.get("/facets", response_model=ArticleFacetsRead)
async def list_article_facets(
    session: AsyncSession = Depends(get_session),
) -> ArticleFacetsRead:
    entity_result = await session.execute(
        select(
            ArticleEntity.entity_type,
            ArticleEntity.name,
            ArticleEntity.normalized_name,
            func.count(ArticleEntity.id),
        )
        .group_by(
            ArticleEntity.entity_type,
            ArticleEntity.name,
            ArticleEntity.normalized_name,
        )
        .order_by(ArticleEntity.entity_type.asc(), func.count(ArticleEntity.id).desc())
    )
    entities = [
        ArticleEntityFacet(
            entity_type=row[0],
            name=row[1],
            normalized_name=row[2],
            count=row[3],
        )
        for row in entity_result.fetchall()
    ]

    country_result = await session.execute(
        select(
            ArticleEnrichment.startup_country,
            ArticleEnrichment.publisher_country,
            ArticleEnrichment.mentioned_countries,
        )
    )
    startup_countries: set[str] = set()
    publisher_countries: set[str] = set()
    mentioned_countries: set[str] = set()
    for startup, publisher, mentioned in country_result.fetchall():
        if startup:
            startup_countries.add(startup)
        if publisher:
            publisher_countries.add(publisher)
        if isinstance(mentioned, list):
            mentioned_countries.update(
                country for country in mentioned if isinstance(country, str) and country
            )

    funding_result = await session.execute(
        select(
            func.min(ArticleEnrichment.funding_amount_usd),
            func.max(ArticleEnrichment.funding_amount_usd),
        )
    )
    min_usd, max_usd = funding_result.one()

    return ArticleFacetsRead(
        entities=entities,
        countries=ArticleCountryFacets(
            startup=sorted(startup_countries),
            publisher=sorted(publisher_countries),
            mentioned=sorted(mentioned_countries),
        ),
        funding=ArticleFundingFacet(min_usd=min_usd, max_usd=max_usd),
    )


@router.get("/{article_id}", response_model=ArticleRead)
async def get_article(
    article_id: UUID, session: AsyncSession = Depends(get_session)
) -> ArticleRead:
    result = await session.execute(
        select(Article)
        .options(selectinload(Article.enrichment), selectinload(Article.entities))
        .where(Article.id == article_id)
    )
    article = result.scalars().first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _serialize_article(article)


def _needs_enrichment_join(
    *,
    q: str | None,
    funding_min_usd: Decimal | None,
    funding_max_usd: Decimal | None,
    startup_country: list[str] | None,
    publisher_country: list[str] | None,
    mentioned_country: list[str] | None,
) -> bool:
    return any(
        [
            q,
            funding_min_usd is not None,
            funding_max_usd is not None,
            startup_country,
            publisher_country,
            mentioned_country,
        ]
    )


def _source_display_name(source_id: str) -> str:
    return " ".join(
        part.capitalize() for part in re.split(r"[_\s]+", source_id) if part
    )


def _serialize_article(article: Article) -> ArticleRead:
    enrichment = article.enrichment
    return ArticleRead(
        id=article.id,
        source=article.source,
        title=article.title,
        url=article.url,
        external_id=article.external_id,
        source_url=article.source_url,
        published_at=article.published_at,
        content=article.content,
        created_at=article.created_at,
        summary=enrichment.summary if enrichment else None,
        entities=[
            ArticleEntityRead(
                entity_type=entity.entity_type,
                name=entity.name,
                normalized_name=entity.normalized_name,
            )
            for entity in sorted(
                article.entities,
                key=lambda item: (item.entity_type, item.name),
            )
        ],
        startup_country=enrichment.startup_country if enrichment else None,
        publisher_country=enrichment.publisher_country if enrichment else None,
        mentioned_countries=(
            enrichment.mentioned_countries
            if enrichment and enrichment.mentioned_countries
            else []
        ),
        funding_amount_usd=enrichment.funding_amount_usd if enrichment else None,
        funding_amount_original=(
            enrichment.funding_amount_original if enrichment else None
        ),
        funding_currency_original=(
            enrichment.funding_currency_original if enrichment else None
        ),
        funding_round=enrichment.funding_round if enrichment else None,
        enrichment_status=enrichment.enrichment_status if enrichment else "pending",
    )


def _normalize_filter_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_country_filter(value: str) -> str:
    return value.strip().lower()
