"""Перехват сетевых ответов SPA — основной способ получить данные о вакансиях.

Страница поиска Upwork — SPA, которая сама тянет структурный JSON с
внутренних эндпоинтов. Перехват через `page.on("response")` устойчивее к
вёрстке, чем CSS-селекторы (это была главная хрупкость Kwork-версии).
`dom_fallback.py` — план Б, только если перехват за цикл дал 0 вакансий.

До того как известна точная структура эндпоинтов поиска, `dump_fixtures()`
позволяет сохранить всё перехваченное на реальном прогоне и по этим файлам
уже писать `payload_models.py`/`mapper.py`, а не гадать заранее.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from patchright.async_api import Page, Response

logger = logging.getLogger(__name__)

ResponsePredicate = Callable[[Response], bool]


class ResponseCapture:
    """Копит JSON-тела ответов, прошедших предикат, пока прикреплена к странице."""

    def __init__(self, predicate: ResponsePredicate) -> None:
        self._predicate = predicate
        self._captured: list[dict[str, object]] = []

    def attach(self, page: Page) -> None:
        page.on("response", self._on_response)

    @property
    def captured(self) -> list[dict[str, object]]:
        return list(self._captured)

    def clear(self) -> None:
        self._captured.clear()

    def dump_fixtures(self, directory: Path, prefix: str = "capture") -> list[Path]:
        """Сохранить перехваченные тела как файлы фикстур для офлайн-тестов маппера."""
        directory.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index, body in enumerate(self._captured):
            path = directory / f"{prefix}_{index:03d}.json"
            path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
            paths.append(path)
        return paths

    async def _on_response(self, response: Response) -> None:
        if not self._predicate(response):
            return
        try:
            body = await response.json()
        except Exception:
            logger.debug("Ответ %s не является JSON — пропускаю", response.url, exc_info=True)
            return
        if isinstance(body, dict):
            self._captured.append(body)
        else:
            logger.debug("Ответ %s — не JSON-объект верхнего уровня, пропускаю", response.url)


def search_response_predicate(response: Response) -> bool:
    """Эвристика для ответов поиска вакансий: JSON, XHR/fetch, домен Upwork.

    Уточняется по реальным перехваченным URL после первого ассистированного
    прогона — сейчас это широкий фильтр, а не список конкретных эндпоинтов.
    """
    if response.request.resource_type not in ("xhr", "fetch"):
        return False
    if "upwork.com" not in response.url:
        return False
    content_type = response.headers.get("content-type", "")
    return "application/json" in content_type
