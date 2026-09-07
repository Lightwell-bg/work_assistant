"""Общие фикстуры тестов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.config import Settings
from upwork_assistant.container import Container, build_container


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Настройки с фиктивными секретами и путями внутри tmp_path.

    Значения передаются явно, поэтому тесты не зависят от наличия `.env`.
    """
    return Settings(
        upwork_email="test@example.com",
        upwork_password=SecretStr("upwork-password"),
        openrouter_api_key=SecretStr("sk-or-test"),
        telegram_bot_token=SecretStr("123456:test-token"),
        telegram_user_id=42,
        upwork_profile_dir=tmp_path / "browser_profile",
        freelancer_profile_path=tmp_path / "profile.md",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        log_file=tmp_path / "test.log",
    )


@pytest.fixture
async def api_container(settings: Settings) -> AsyncIterator[Container]:
    """Готовый `Container` с уже созданной схемой БД — для тестов API.

    API-тесты используют `create_app(settings, container=...)` (тот же
    приём, что и `test_create_app_with_prebuilt_container_uses_it_as_is`
    в `test_app.py`): контейнер строится в тестовом event loop, а `TestClient`
    внутри `with` просто переиспользует его, ничего не строя заново.
    Схему создаём через `Base.metadata.create_all`, а не Alembic-миграции —
    как и `test_repositories.py`, это быстрее и не требует `alembic.ini`.
    """
    async with build_container(settings) as container:
        async with container.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield container
