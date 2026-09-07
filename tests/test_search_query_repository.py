"""Round-trip тесты репозитория сохранённых поисков на файловой SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.repositories import UnknownSearchQueryError
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'searches_test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_save_and_list_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    search = SearchQuery(
        source=JobSourceName.UPWORK,
        name="python",
        query="https://www.upwork.com/nx/search/jobs/?q=python",
    )

    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(search)

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert stored == [search]


async def test_save_twice_with_same_name_replaces_not_duplicates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://old")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://new")
        )

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert len(stored) == 1
    assert stored[0].query == "https://new"


async def test_same_name_under_different_sources_coexist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://upwork")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.LINKEDIN, name="python", query="https://linkedin")
        )

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert len(stored) == 2


async def test_list_active_filters_by_source_and_flag(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="on", query="https://a")
        )
        await uow.searches.save(
            SearchQuery(
                source=JobSourceName.UPWORK, name="off", query="https://b", is_active=False
            )
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.LINKEDIN, name="other", query="https://c")
        )

    async with unit_of_work(session_factory) as uow:
        active = await uow.searches.list_active(JobSourceName.UPWORK)

    assert [search.name for search in active] == ["on"]


async def test_delete_removes_only_that_search(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="a", query="https://a")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="b", query="https://b")
        )

    async with unit_of_work(session_factory) as uow:
        await uow.searches.delete(JobSourceName.UPWORK, "a")

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert [search.name for search in stored] == ["b"]


async def test_delete_unknown_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(UnknownSearchQueryError):
        async with unit_of_work(session_factory) as uow:
            await uow.searches.delete(JobSourceName.UPWORK, "missing")


async def test_count_reflects_saved_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="a", query="https://a")
        )

    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 1
