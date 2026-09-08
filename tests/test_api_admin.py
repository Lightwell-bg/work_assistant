"""Тесты kill switch (`/admin/status`, `/admin/pause`, `/admin/resume`,
`/admin/polling-interval`)."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container
from upwork_assistant.services.polling_settings import (
    POLL_INTERVAL_MINUTES_KEY,
    POLL_JITTER_PCT_KEY,
)


def test_status_on_fresh_app_is_not_scheduled(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/admin/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "scheduled": False,
        "circuit_open": False,
        "consecutive_failures": 0,
        "interval_minutes": settings.poll_interval_minutes,
        "jitter_pct": settings.poll_jitter_pct,
    }


def test_resume_then_status_shows_scheduled(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        resume_response = client.post("/admin/resume")
        assert resume_response.status_code == 200
        assert resume_response.json()["scheduled"] is True

        status_response = client.get("/admin/status")
        assert status_response.json()["scheduled"] is True


def test_pause_after_resume_unschedules(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.post("/admin/resume")

        pause_response = client.post("/admin/pause")

        assert pause_response.status_code == 200
        assert pause_response.json()["scheduled"] is False

        status_response = client.get("/admin/status")
        assert status_response.json()["scheduled"] is False


def test_pause_with_nothing_scheduled_does_not_error(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.post("/admin/pause")

    assert response.status_code == 200
    assert response.json()["scheduled"] is False


def test_put_polling_interval_updates_live_status(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/admin/polling-interval", json={"interval_minutes": 25, "jitter_pct": 15}
        )

        assert response.status_code == 200
        assert response.json()["interval_minutes"] == 25
        assert response.json()["jitter_pct"] == 15

        status_response = client.get("/admin/status")
        assert status_response.json()["interval_minutes"] == 25
        assert status_response.json()["jitter_pct"] == 15


def test_put_polling_interval_persists_to_app_state(
    settings: Settings, api_container: Container
) -> None:
    """Пережить рестарт процесса — не только жить в памяти текущего Container."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/admin/polling-interval", json={"interval_minutes": 25, "jitter_pct": 15})

    async def _read_app_state() -> tuple[str | None, str | None]:
        async with unit_of_work(api_container.session_factory) as uow:
            return (
                await uow.app_state.get(POLL_INTERVAL_MINUTES_KEY),
                await uow.app_state.get(POLL_JITTER_PCT_KEY),
            )

    interval_raw, jitter_raw = asyncio.run(_read_app_state())
    assert interval_raw == "25"
    assert jitter_raw == "15"


def test_put_polling_interval_rejects_zero_minutes(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/admin/polling-interval", json={"interval_minutes": 0, "jitter_pct": 15}
        )

    assert response.status_code == 422


def test_put_polling_interval_rejects_jitter_above_100(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/admin/polling-interval", json={"interval_minutes": 10, "jitter_pct": 101}
        )

    assert response.status_code == 422
