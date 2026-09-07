"""Round-trip тест `SqlAlchemyLLMUsageRepository` на файловой SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.repositories import SqlAlchemyLLMUsageRepository
from upwork_assistant.adapters.db.tables import Base, LLMUsageRow
from upwork_assistant.ports.llm import LLMUsageRecord


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Файловая SQLite, изолированная на каждый тест, со свежей схемой."""
    db_path = tmp_path / "llm_usage_test.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_add_persists_usage_row_with_price(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    record = LLMUsageRecord(
        purpose="scoring",
        job_external_id="job-1",
        model="openai/gpt-5-mini",
        prompt_tokens=1000,
        completion_tokens=200,
        cost_usd=0.00065,
    )

    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        await repo.add(record)
        await session.commit()

    async with session_factory() as session:
        result = await session.execute(select(LLMUsageRow))
        rows = result.scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.purpose == record.purpose
    assert row.job_external_id == record.job_external_id
    assert row.model == record.model
    assert row.prompt_tokens == record.prompt_tokens
    assert row.completion_tokens == record.completion_tokens
    assert row.cost_usd == pytest.approx(record.cost_usd)
    assert row.created_at is not None


async def test_total_cost_since_sums_only_recent_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)

    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        await repo.add(
            LLMUsageRecord(
                purpose="scoring",
                job_external_id="job-1",
                model="openai/gpt-5-mini",
                prompt_tokens=1000,
                completion_tokens=200,
                cost_usd=0.5,
            )
        )
        await repo.add(
            LLMUsageRecord(
                purpose="proposal",
                job_external_id="job-2",
                model="openai/gpt-5",
                prompt_tokens=1000,
                completion_tokens=200,
                cost_usd=1.5,
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        total = await repo.total_cost_since(now - timedelta(minutes=1))

    assert total == pytest.approx(2.0)


async def test_total_cost_since_excludes_old_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        await repo.add(
            LLMUsageRecord(
                purpose="scoring",
                job_external_id="job-1",
                model="openai/gpt-5-mini",
                prompt_tokens=1000,
                completion_tokens=200,
                cost_usd=0.5,
            )
        )
        await session.commit()

    future = datetime.now(UTC) + timedelta(days=1)
    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        total = await repo.total_cost_since(future)

    assert total == 0.0


async def test_total_cost_since_returns_zero_with_no_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyLLMUsageRepository(session)
        total = await repo.total_cost_since(datetime.now(UTC) - timedelta(days=1))

    assert total == 0.0
