"""Тесты kill switch (`/admin/status`, `/admin/pause`, `/admin/resume`)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container


def test_status_on_fresh_app_is_not_scheduled(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/admin/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {"scheduled": False, "circuit_open": False, "consecutive_failures": 0}


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
