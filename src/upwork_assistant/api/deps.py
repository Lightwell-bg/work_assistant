"""Зависимости FastAPI.

Контейнер лежит в `app.state`, а не в глобальной переменной модуля,
поэтому обработчики получают его через `Depends`, а не импортом внутри функции.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from upwork_assistant.adapters.db.uow import UnitOfWork, unit_of_work
from upwork_assistant.container import Container


def get_container(request: Request) -> Container:
    """Контейнер зависимостей текущего приложения."""
    container: Container | None = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Приложение ещё не инициализировано",
        )
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_uow(container: ContainerDep) -> AsyncIterator[UnitOfWork]:
    """Открыть `UnitOfWork` на время запроса — обработчики CRUD-эндпоинтов
    иначе повторяли бы `async with unit_of_work(...)` в каждом из них."""
    async with unit_of_work(container.session_factory) as uow:
        yield uow


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
