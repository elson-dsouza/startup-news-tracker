"""add article enrichment jobs

Revision ID: 20260609_0004
Revises: 20260609_0003
Create Date: 2026-06-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260609_0004"
down_revision = "20260609_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_enrichment_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", name="uq_article_enrichment_jobs_article_id"),
    )
    op.create_index(
        "ix_article_enrichment_jobs_status",
        "article_enrichment_jobs",
        ["status"],
    )
    op.create_index(
        "ix_article_enrichment_jobs_next_attempt_at",
        "article_enrichment_jobs",
        ["next_attempt_at"],
    )

    op.execute(
        """
        INSERT INTO article_enrichment_jobs (
            id,
            article_id,
            status,
            attempts,
            max_attempts,
            priority
        )
        SELECT gen_random_uuid(), articles.id, 'queued', 0, 3, 0
        FROM articles
        LEFT JOIN article_enrichments
            ON article_enrichments.article_id = articles.id
        WHERE article_enrichments.article_id IS NULL
           OR article_enrichments.enrichment_status IN ('pending', 'failed')
           OR article_enrichments.extraction_status IN ('pending', 'failed')
        ON CONFLICT (article_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_article_enrichment_jobs_next_attempt_at",
        table_name="article_enrichment_jobs",
    )
    op.drop_index(
        "ix_article_enrichment_jobs_status",
        table_name="article_enrichment_jobs",
    )
    op.drop_table("article_enrichment_jobs")
