"""add article source metadata

Revision ID: 20260609_0002
Revises: 20260608_0001
Create Date: 2026-06-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260609_0002"
down_revision = "20260608_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("external_id", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.create_index("ix_articles_source", "articles", ["source"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_source", table_name="articles")
    op.drop_column("articles", "source_url")
    op.drop_column("articles", "external_id")
