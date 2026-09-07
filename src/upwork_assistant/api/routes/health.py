"""Проверка живости.

Намеренно не требует контейнера: эндпоинт должен отвечать даже тогда,
когда инициализация зависимостей ещё не завершилась или уже упала.
"""

from __future__ import annotations

from fastapi import APIRouter

from upwork_assistant import __version__
from upwork_assistant.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Приложение отвечает на запросы."""
    return HealthResponse(status="healthy", version=__version__)
