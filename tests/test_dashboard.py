"""Тест веб-панели: `GET /` отдаёт HTML-страницу."""

from __future__ import annotations

import httpx

from upwork_assistant.app import create_app
from upwork_assistant.config import Settings


async def test_dashboard_returns_html_page(settings: Settings) -> None:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Upwork Assistant</title>" in response.text


async def test_dashboard_contains_searches_section(settings: Settings) -> None:
    """Смоук: раздел «Поиски» реально отдаётся страницей.

    Разметка и JS панели лежат в одном статическом файле без сборки, поэтому
    единственное, что здесь можно проверить автоматически, — что секция не
    потерялась при правке. Поведение раздела проверяется руками (Step 6).
    """
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert 'id="searches-section"' in response.text
    assert 'id="searches-tbody"' in response.text
