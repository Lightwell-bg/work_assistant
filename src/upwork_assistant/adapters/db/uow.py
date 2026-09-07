"""UnitOfWork: одна транзакция на вакансию.

Пайплайн (`services/pipeline.py`, будет добавлен позже) обрабатывает каждую
вакансию в своей транзакции — сбой на одной вакансии откатывает только её,
не роняя весь батч опроса.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.repositories import (
    SqlAlchemyDraftRepository,
    SqlAlchemyFilterSetRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyLLMUsageRepository,
    SqlAlchemySearchQueryRepository,
    SqlAlchemyUpworkJobFactsRepository,
)


class UnitOfWork:
    """Набор репозиториев, разделяющих одну сессию/транзакцию."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.jobs = SqlAlchemyJobRepository(session)
        self.filter_sets = SqlAlchemyFilterSetRepository(session)
        self.drafts = SqlAlchemyDraftRepository(session)
        self.llm_usage = SqlAlchemyLLMUsageRepository(session)
        self.upwork_facts = SqlAlchemyUpworkJobFactsRepository(session)
        self.searches = SqlAlchemySearchQueryRepository(session)


@asynccontextmanager
async def unit_of_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[UnitOfWork]:
    """Открыть сессию на время блока: коммит при успехе, откат при исключении.

    Сессия закрывается в любом случае — иначе соединение утечёт при ошибке.
    """
    session = session_factory()
    try:
        yield UnitOfWork(session)
    except Exception:
        await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        await session.close()
