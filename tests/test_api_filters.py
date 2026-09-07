"""Тесты REST-эндпоинтов управления пресетами фильтров."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container


def test_upsert_then_list_shows_filter_with_tuple_value_as_json_list(
    settings: Settings, api_container: Container
) -> None:
    """PUT создаёт пресет; GET возвращает его, значение-кортеж round-trip'ится
    как JSON-список (contains_any ожидает список ключевых слов)."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        body = {
            "match_mode": "any",
            "is_active": True,
            "rules": [
                {"field": "skills", "operator": "contains_any", "value": ["python", "django"]},
                {"field": "entry_cost", "operator": "lte", "value": 4},
            ],
        }
        put_response = client.put("/filters/my-preset", json=body)
        assert put_response.status_code == 200
        assert put_response.json()["name"] == "my-preset"

        list_response = client.get("/filters")
        assert list_response.status_code == 200
        presets = list_response.json()
        assert len(presets) == 1
        preset = presets[0]
        assert preset["name"] == "my-preset"
        assert preset["match_mode"] == "any"
        assert preset["is_active"] is True
        rules = {rule["field"]: rule for rule in preset["rules"]}
        assert rules["skills"]["value"] == ["python", "django"]
        assert rules["entry_cost"]["value"] == 4


def test_put_replaces_rules_entirely_on_second_call(
    settings: Settings, api_container: Container
) -> None:
    """Второй `PUT` с тем же именем полностью заменяет правила, а не добавляет."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put(
            "/filters/preset",
            json={"rules": [{"field": "title", "operator": "contains", "value": "python"}]},
        )
        client.put(
            "/filters/preset",
            json={"rules": [{"field": "title", "operator": "contains", "value": "django"}]},
        )

        response = client.get("/filters")
        preset = response.json()[0]
        assert len(preset["rules"]) == 1
        assert preset["rules"][0]["value"] == "django"


def test_delete_removes_filter_from_list(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/filters/to-delete", json={})

        delete_response = client.delete("/filters/to-delete")
        assert delete_response.status_code == 204

        list_response = client.get("/filters")
        assert list_response.json() == []


def test_delete_unknown_filter_returns_404(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.delete("/filters/never-existed")
        assert response.status_code == 404
