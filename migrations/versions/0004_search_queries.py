"""search queries table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08

Написана руками (не автогенерацией), как и 0001-0003 — таблица должна точно
соответствовать `adapters/db/tables.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "name", name="uq_search_queries_source_name"),
    )
    op.create_index("ix_search_queries_source", "search_queries", ["source"])


def downgrade() -> None:
    op.drop_table("search_queries")
