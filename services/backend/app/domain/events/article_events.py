from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.raw_article import RawArticle


@dataclass(frozen=True)
class ArticleDiscovered:
    article: RawArticle
    occurred_at: datetime


@dataclass(frozen=True)
class ArticleStored:
    article_id: UUID
    url: str
    occurred_at: datetime
