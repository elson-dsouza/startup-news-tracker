from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class ArticleSourceRead(BaseModel):
    id: str
    display_name: str
    enabled: bool
    latest_article_at: datetime | None = None
