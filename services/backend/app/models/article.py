import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
        Index("ix_articles_source", "source"),
        Index("ix_articles_published_at", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(length=255), nullable=False)
    title: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    url: Mapped[str] = mapped_column(String(length=2048), nullable=False, unique=True)
    external_id: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(length=2048), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
