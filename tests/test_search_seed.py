"""Тесты разового засева поисков из `.env` в БД."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery
from upwork_assistant.services.search_seed import seed_searches_from_env


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed_test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_seeds_urls_into_empty_table(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await seed_searches_from_env(
        session_factory, ["https://www.upwork.com/a", "https://www.upwork.com/b"]
    )

    assert created == 2
    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_active(JobSourceName.UPWORK)
    assert [search.query for search in stored] == [
        "https://www.upwork.com/a",
        "https://www.upwork.com/b",
    ]


async def test_does_nothing_when_table_not_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="mine", query="https://mine")
        )

    created = await seed_searches_from_env(session_factory, ["https://www.upwork.com/a"])

    assert created == 0
    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()
    assert [search.name for search in stored] == ["mine"]


async def test_does_nothing_when_env_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await seed_searches_from_env(session_factory, [])

    assert created == 0
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0
