import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    enrichment: Mapped["ArticleEnrichment | None"] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    entities: Mapped[list["ArticleEntity"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ArticleEnrichment(Base):
    __tablename__ = "article_enrichments"
    __table_args__ = (
        Index("ix_article_enrichments_status", "enrichment_status"),
        Index("ix_article_enrichments_startup_country", "startup_country"),
        Index("ix_article_enrichments_publisher_country", "publisher_country"),
        Index("ix_article_enrichments_funding_amount_usd", "funding_amount_usd"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    extraction_status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="pending"
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="pending"
    )
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    startup_country: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True
    )
    publisher_country: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True
    )
    mentioned_countries: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    funding_amount_original: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True
    )
    funding_currency_original: Mapped[str | None] = mapped_column(
        String(length=16), nullable=True
    )
    funding_amount_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    funding_round: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    article: Mapped[Article] = relationship(back_populates="enrichment")


class ArticleEntity(Base):
    __tablename__ = "article_entities"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "entity_type",
            "normalized_name",
            name="uq_article_entities_article_type_name",
        ),
        Index("ix_article_entities_type_name", "entity_type", "normalized_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(length=255), nullable=False)

    article: Mapped[Article] = relationship(back_populates="entities")


class ArticleEnrichmentJob(Base):
    __tablename__ = "article_enrichment_jobs"
    __table_args__ = (
        UniqueConstraint("article_id", name="uq_article_enrichment_jobs_article_id"),
        Index("ix_article_enrichment_jobs_status", "status"),
        Index("ix_article_enrichment_jobs_next_attempt_at", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
