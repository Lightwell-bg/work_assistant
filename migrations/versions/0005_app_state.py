"""app state table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08

Написана руками (не автогенерацией), как и 0001-0004 — таблица должна точно
соответствовать `adapters/db/tables.py`.

Общая key/value таблица под устойчивые системные отметки процесса (например,
«поиски уже перенесены из .env» — находка 2), а не отдельная таблица/колонка
под каждый новый такой факт.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_state",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
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
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("app_state")
