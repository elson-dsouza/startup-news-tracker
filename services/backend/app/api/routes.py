from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models.article import Article
from app.schemas.article import ArticleRead

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=list[ArticleRead])
async def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ArticleRead]:
    result = await session.execute(
        select(Article)
        .order_by(Article.published_at.desc(), Article.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    articles = result.scalars().all()
    return articles


@router.get("/{article_id}", response_model=ArticleRead)
async def get_article(
    article_id: UUID, session: AsyncSession = Depends(get_session)
) -> ArticleRead:
    result = await session.execute(select(Article).where(Article.id == article_id))
    article = result.scalars().first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
