"""Тесты REST-эндпоинтов сохранённых поисков."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container


def test_list_is_empty_initially(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/searches")

    assert response.status_code == 200
    assert response.json() == []


def test_put_creates_and_get_returns_it(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/searches/upwork/python",
            json={
                "query": "https://www.upwork.com/nx/search/jobs/?q=python",
                "is_active": True,
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "source": "upwork",
            "name": "python",
            "query": "https://www.upwork.com/nx/search/jobs/?q=python",
            "is_active": True,
        }

        listed = client.get("/searches").json()

    assert [item["name"] for item in listed] == ["python"]


def test_put_twice_replaces_not_duplicates(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/python", json={"query": "https://old"})
        client.put("/searches/upwork/python", json={"query": "https://new"})

        listed = client.get("/searches").json()

    assert len(listed) == 1
    assert listed[0]["query"] == "https://new"


def test_list_filters_by_source(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/a", json={"query": "https://a"})
        client.put("/searches/linkedin/b", json={"query": "https://b"})

        listed = client.get("/searches", params={"source": "linkedin"}).json()

    assert [item["name"] for item in listed] == ["b"]


def test_delete_removes_it(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/python", json={"query": "https://a"})

        response = client.delete("/searches/upwork/python")

        assert response.status_code == 204
        assert client.get("/searches").json() == []


def test_delete_unknown_returns_404(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.delete("/searches/upwork/missing")

    assert response.status_code == 404


def test_put_with_unknown_source_returns_422(
    settings: Settings, api_container: Container
) -> None:
    """`JobSourceName` в пути — enum, поэтому чужая площадка отсекается
    валидацией FastAPI, а не долетает строкой до репозитория."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put("/searches/hh/python", json={"query": "https://a"})

    assert response.status_code == 422
