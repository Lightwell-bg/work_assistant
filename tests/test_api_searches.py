"""Тесты REST-эндпоинтов сохранённых поисков."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upwork_assistant.adapters.db.tables import SearchQueryRow
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


def test_put_with_non_http_query_returns_422(
    settings: Settings, api_container: Container
) -> None:
    """Находка 3: query без http(s)-схемы (например, javascript:) не должен
    доходить до репозитория и залогиненного браузера."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/searches/upwork/x", json={"query": "javascript:alert(1)"}
        )

    assert response.status_code == 422


async def test_get_searches_with_corrupted_row_does_not_return_422(
    settings: Settings, api_container: Container
) -> None:
    """Регрессия находки 1: строка без http(s)-схемы — например, оставшаяся
    в БД с тех пор, когда валидатор `SearchQuery.query` ещё не существовал, —
    это порча данных на сервере, а не невалидный запрос клиента. Строка
    вставлена напрямую через ORM-таблицу в обход `SearchQuery`, поэтому
    `ValidationError` возникает только при чтении в `_search_to_domain`.
    Раньше общий обработчик в `app.py` превращал это в 422, маскируя
    серверную неисправность под ошибку клиента; после переноса перевода
    ошибки в локальный `try/except` PUT-обработчика такое чтение должно
    остаться 500, а не стать 422."""
    async with api_container.session_factory() as session:
        session.add(
            SearchQueryRow(source="upwork", name="corrupted", query="javascript:alert(1)")
        )
        await session.commit()

    app = create_app(settings, container=api_container)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/searches")

    assert response.status_code != 422
    assert response.status_code == 500
