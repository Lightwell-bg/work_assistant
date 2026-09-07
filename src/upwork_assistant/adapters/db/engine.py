"""Создание асинхронного движка и фабрики сессий SQLAlchemy.

Вынесено в отдельный модуль, чтобы `container.py` и `migrations/env.py`
собирали движок одинаково, не дублируя параметры подключения.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    """Создать асинхронный движок по URL из настроек."""
    return create_async_engine(database_url)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий. `expire_on_commit=False` — доменные объекты собираются
    из строки до коммита и не должны протухать сразу после него."""
    return async_sessionmaker(engine, expire_on_commit=False)
