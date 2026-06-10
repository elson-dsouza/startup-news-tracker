"""add article enrichment tables

Revision ID: 20260609_0003
Revises: 20260609_0002
Create Date: 2026-06-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260609_0003"
down_revision = "20260609_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_enrichments",
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "extraction_status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "enrichment_status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("startup_country", sa.String(length=128), nullable=True),
        sa.Column("publisher_country", sa.String(length=128), nullable=True),
        sa.Column(
            "mentioned_countries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("funding_amount_original", sa.String(length=128), nullable=True),
        sa.Column("funding_currency_original", sa.String(length=16), nullable=True),
        sa.Column(
            "funding_amount_usd", sa.Numeric(precision=18, scale=2), nullable=True
        ),
        sa.Column("funding_round", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("enrichment_error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id"),
    )
    op.create_index(
        "ix_article_enrichments_status",
        "article_enrichments",
        ["enrichment_status"],
    )
    op.create_index(
        "ix_article_enrichments_startup_country",
        "article_enrichments",
        ["startup_country"],
    )
    op.create_index(
        "ix_article_enrichments_publisher_country",
        "article_enrichments",
        ["publisher_country"],
    )
    op.create_index(
        "ix_article_enrichments_funding_amount_usd",
        "article_enrichments",
        ["funding_amount_usd"],
    )

    op.create_table(
        "article_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "article_id",
            "entity_type",
            "normalized_name",
            name="uq_article_entities_article_type_name",
        ),
    )
    op.create_index(
        "ix_article_entities_type_name",
        "article_entities",
        ["entity_type", "normalized_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_article_entities_type_name", table_name="article_entities")
    op.drop_table("article_entities")
    op.drop_index(
        "ix_article_enrichments_funding_amount_usd",
        table_name="article_enrichments",
    )
    op.drop_index(
        "ix_article_enrichments_publisher_country",
        table_name="article_enrichments",
    )
    op.drop_index(
        "ix_article_enrichments_startup_country",
        table_name="article_enrichments",
    )
    op.drop_index("ix_article_enrichments_status", table_name="article_enrichments")
    op.drop_table("article_enrichments")
