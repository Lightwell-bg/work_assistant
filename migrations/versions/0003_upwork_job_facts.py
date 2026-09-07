"""upwork job facts table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07

Написана руками (не автогенерацией), как и 0001/0002 — таблица должна точно
соответствовать `adapters/db/tables.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upwork_job_facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_external_id", sa.String(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
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
    )
    op.create_index(
        "ix_upwork_job_facts_job_external_id",
        "upwork_job_facts",
        ["job_external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("upwork_job_facts")
