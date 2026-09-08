"""Разовый перенос поисков из `.env` в БД.

Поиски переехали из `UPWORK_SEARCH_URLS` в таблицу, чтобы правиться через
веб-панель. Чтобы старые установки не остались без поисков после обновления,
самый первый запуск процесса после обновления один раз наполняет таблицу
значениями из `.env`.

Находка 2: раньше условием засева было «таблица поисков пуста» — ловушка,
которая срабатывает снова, стоит пользователю удалить последний оставшийся
поиск (например, чтобы завести другой). Гейт — отдельная отметка в таблице
`app_state` (`SEARCH_SEED_MARKER_KEY`), а не пустота таблицы поисков. Отметка
проставляется на первом же вызове независимо от того, был ли список `.env`
пустым: иначе `.env`, которому поиск дописали месяцы спустя, ожил бы на
следующем перезапуске, хотя пользователь никогда не просил его засевать.
Как только отметка стоит, `.env` больше никогда не вмешивается и не
воскрешает то, что пользователь удалил в панели — даже удалив все поиски
до единого.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery

logger = logging.getLogger(__name__)

# Ключ отметки в app_state: разовый перенос поисков из .env уже состоялся,
# независимо от того, что именно (и сколько) было перенесено.
SEARCH_SEED_MARKER_KEY = "search_seed_done"


async def seed_searches_from_env(
    session_factory: async_sessionmaker[AsyncSession],
    search_urls: Sequence[str],
) -> int:
    """Засеять поиски Upwork из `.env`. Возвращает число созданных записей.

    Выполняется не более одного раза за всё время жизни БД — см. докстринг
    модуля про отметку в `app_state`.
    """
    async with unit_of_work(session_factory) as uow:
        if await uow.app_state.get(SEARCH_SEED_MARKER_KEY) is not None:
            return 0

        created = 0
        for index, url in enumerate(search_urls, start=1):
            await uow.searches.save(
                SearchQuery(
                    source=JobSourceName.UPWORK,
                    name=f"upwork_{index}",
                    query=url,
                    is_active=True,
                )
            )
            created += 1
        # Ставится и при пустом search_urls — см. докстринг модуля.
        await uow.app_state.set(SEARCH_SEED_MARKER_KEY, "done")

    if created:
        logger.info("Перенесено поисков из .env в БД: %d", created)
    return created
