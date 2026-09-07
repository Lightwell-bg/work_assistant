"""Разовый перенос поисков из `.env` в БД.

Поиски переехали из `UPWORK_SEARCH_URLS` в таблицу, чтобы правиться через
веб-панель. Чтобы старые установки не остались без поисков после обновления,
при старте пустая таблица один раз наполняется значениями из `.env`. Условие
«таблица пуста» намеренно грубое: как только пользователь завёл хоть один
поиск сам, `.env` больше не вмешивается и не воскрешает удалённое.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery

logger = logging.getLogger(__name__)


async def seed_searches_from_env(
    session_factory: async_sessionmaker[AsyncSession],
    search_urls: Sequence[str],
) -> int:
    """Засеять поиски Upwork из `.env`. Возвращает число созданных записей."""
    if not search_urls:
        return 0

    async with unit_of_work(session_factory) as uow:
        if await uow.searches.count() > 0:
            return 0

        for index, url in enumerate(search_urls, start=1):
            await uow.searches.save(
                SearchQuery(
                    source=JobSourceName.UPWORK,
                    name=f"upwork_{index}",
                    query=url,
                    is_active=True,
                )
            )

    logger.info("Перенесено поисков из .env в БД: %d", len(search_urls))
    return len(search_urls)
