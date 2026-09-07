"""llm usage table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07

Написана руками (не автогенерацией), как и 0001 — таблица должна точно
соответствовать `adapters/db/tables.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("job_external_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_usage_job_external_id", "llm_usage", ["job_external_id"])


def downgrade() -> None:
    op.drop_table("llm_usage")
