from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.ingestion.services.ingestion_service import IngestionService
from app.models.article import Article
from app.schemas.article import ArticleRead, ArticleSourceRead

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=list[ArticleRead])
async def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    published_after: datetime | None = Query(default=None),
    published_before: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[ArticleRead]:
    statement = select(Article)
    if source:
        statement = statement.where(Article.source == source)
    if q:
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(Article.title.ilike(term), Article.content.ilike(term))
        )
    if published_after:
        statement = statement.where(Article.published_at >= published_after)
    if published_before:
        statement = statement.where(Article.published_at <= published_before)

    result = await session.execute(
        statement.order_by(Article.published_at.desc(), Article.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    articles = result.scalars().all()
    return articles


@router.get("/sources", response_model=list[ArticleSourceRead])
async def list_article_sources(
    session: AsyncSession = Depends(get_session),
) -> list[ArticleSourceRead]:
    result = await session.execute(
        select(Article.source, func.max(Article.published_at)).group_by(Article.source)
    )
    latest_by_source = {row[0]: row[1] for row in result.fetchall()}

    return [
        ArticleSourceRead(
            id=str(source["id"]),
            display_name=str(source["display_name"]),
            enabled=bool(source["enabled"]),
            latest_article_at=latest_by_source.get(str(source["id"])),
        )
        for source in IngestionService.source_metadata()
    ]


@router.get("/{article_id}", response_model=ArticleRead)
async def get_article(
    article_id: UUID, session: AsyncSession = Depends(get_session)
) -> ArticleRead:
    result = await session.execute(select(Article).where(Article.id == article_id))
    article = result.scalars().first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
