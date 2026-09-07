"""Тесты каркаса приложения: контейнер и /health."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from upwork_assistant import __version__
from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import build_container


async def test_container_yields_settings(settings: Settings) -> None:
    async with build_container(settings) as container:
        assert container.settings is settings


async def test_health_endpoint(settings: Settings) -> None:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": __version__}


def test_lifespan_publishes_container_to_app_state(settings: Settings) -> None:
    """Обработчики берут контейнер из app.state, а не из глобала модуля.

    TestClient как контекстный менеджер прогоняет lifespan целиком —
    в отличие от ASGITransport, который события жизненного цикла не шлёт.
    """
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.container.settings is settings

    assert app.state.container is None


async def test_create_app_with_prebuilt_container_uses_it_as_is(settings: Settings) -> None:
    """`__main__.py` строит Container сам и передаёт его — lifespan не должен
    строить ещё один (что запустило бы второй движок БД/HTTP-клиент)."""
    async with build_container(settings) as container:
        app = create_app(settings, container=container)

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert app.state.container is container

        assert app.state.container is None
