"""Сборка `Bot`/`Dispatcher`. Не запускает long-polling — это забота `__main__.py`.

Конструирование `Bot` не делает сетевых вызовов (сама проверка токена —
`getMe` — происходит только при первом реальном запросе), поэтому этот
модуль безопасно вызывать из `container.py` при сборке зависимостей.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.telegram.handlers import build_router


def build_bot(token: str) -> Bot:
    """Собрать `Bot`. Никакого `parse_mode` — уведомления идут plain-текстом."""
    return Bot(token=token)


def build_dispatcher(session_factory: async_sessionmaker[AsyncSession]) -> Dispatcher:
    """Собрать `Dispatcher` с зарегистрированным роутером. Polling не запускает."""
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(session_factory))
    return dispatcher
