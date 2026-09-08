"""Тесты разового засева поисков из `.env` в БД.

Находка 2: старая версия гейтила засев признаком «таблица поисков пуста» —
после удаления пользователем последнего поиска признак снова становился
истинным, и `.env` воскрешал удалённое на следующем рестарте. Новая версия
гейтит засев отдельной отметкой в `app_state`, которая после первого
успешного вызова (даже с пустым `.env`) больше никогда не снимается.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery
from upwork_assistant.services.search_seed import SEARCH_SEED_MARKER_KEY, seed_searches_from_env


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


async def test_seeds_urls_on_fresh_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Совсем новая БД (отметки ещё нет) засевается как обычно."""
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


async def test_does_nothing_when_already_seeded(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Если отметка уже стоит, повторный вызов не трогает существующие поиски —
    гейт теперь именно отметка, а не «таблица не пуста»."""
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="mine", query="https://mine")
        )
        await uow.app_state.set(SEARCH_SEED_MARKER_KEY, "done")

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


async def test_marker_set_even_with_empty_env_blocks_later_seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Пустой `.env` на первом (и единственном) старте всё равно ставит
    отметку — иначе поиск, дописанный в `.env` месяцы спустя, ожил бы на
    следующем перезапуске, хотя пользователь никогда не просил его засевать."""
    first = await seed_searches_from_env(session_factory, [])
    assert first == 0

    second = await seed_searches_from_env(session_factory, ["https://www.upwork.com/a"])

    assert second == 0
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0


async def test_deleting_all_searches_does_not_resurrect_them_on_next_seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Регрессия находки 2: пользователь удаляет последний поиск в панели —
    следующий вызов (например, на рестарте процесса) не должен его вернуть."""
    await seed_searches_from_env(session_factory, ["https://www.upwork.com/a"])

    async with unit_of_work(session_factory) as uow:
        await uow.searches.delete(JobSourceName.UPWORK, "upwork_1")

    created = await seed_searches_from_env(session_factory, ["https://www.upwork.com/a"])

    assert created == 0
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0
