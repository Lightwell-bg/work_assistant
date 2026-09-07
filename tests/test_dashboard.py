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
