from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    title: str
    url: str
    published_at: datetime | None
    content: str | None
    created_at: datetime
