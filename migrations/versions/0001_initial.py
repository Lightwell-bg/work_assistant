"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-07

Первая миграция написана руками (не автогенерацией) — таблицы должны точно
соответствовать `adapters/db/tables.py`, а не тому, что alembic выведет из
подключения к пустой БД.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("budget_amount", sa.Numeric(), nullable=True),
        sa.Column("budget_currency", sa.String(), nullable=True),
        sa.Column("rate_min", sa.Numeric(), nullable=True),
        sa.Column("rate_max", sa.Numeric(), nullable=True),
        sa.Column("rate_currency", sa.String(), nullable=True),
        sa.Column("duration", sa.String(), nullable=True),
        sa.Column("experience_level", sa.String(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_country", sa.String(), nullable=True),
        sa.Column("client_payment_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("client_total_spend", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("client_hire_rate", sa.Float(), nullable=True),
        sa.Column("client_avg_rating", sa.Float(), nullable=True),
        sa.Column("client_reviews_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("competition", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("entry_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("score_value", sa.Float(), nullable=True),
        sa.Column("score_reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_job_postings_external_id", "job_postings", ["external_id"], unique=True)

    op.create_table(
        "filter_sets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("match_mode", sa.String(), nullable=False, server_default="all"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "filter_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "filter_set_id",
            sa.Integer(),
            sa.ForeignKey("filter_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_index("ix_filter_rules_filter_set_id", "filter_rules", ["filter_set_id"])

    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_posting_id",
            sa.Integer(),
            sa.ForeignKey("job_postings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("drafts")
    op.drop_table("filter_rules")
    op.drop_table("filter_sets")
    op.drop_table("job_postings")
