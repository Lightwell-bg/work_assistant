"""Извлечение состояния Nuxt, встроенного в HTML страницы поиска.

Открытие, сделанное на реальном прогоне (headful, залогиненный профиль):
у страницы поиска Upwork нет отдельного JSON-эндпоинта со списком вакансий
для первой загрузки — список приходит внутри `window.__NUXT__`,
отрисованным на сервере (SSR) и сериализованным как самовызывающаяся
функция с вынесенными в параметры повторяющимися значениями:

    window.__NUXT__=(function(a,b,c,...){ return {...} })(v1,v2,v3,...)

Это не JSON — распознавать его регэкспами по позиционным параметрам
(их сотни) хрупко и совершенно point-in-time. Надёжнее исполнить выражение
как есть в настоящем движке JS. Свой JS-движок как зависимость не нужен:
Patchright уже даёт настоящий Chromium — выражение самодостаточно (только
литералы и локальные параметры замыкания, без обращений к window/document
живой SPA), поэтому его можно выполнить на отдельной чистой `about:blank`
вкладке того же браузера, не трогая вкладку с реальной страницей.

`interceptor.py` (перехват через `page.on("response")`) остаётся рабочим
путём для будущей пагинации/фильтров, если они дотягиваются до бирж через
отдельные XHR/fetch-запросы — на первой загрузке списка это не так.
"""

from __future__ import annotations

import logging

from patchright.async_api import BrowserContext

from upwork_assistant.domain.errors import PermanentError

logger = logging.getLogger(__name__)

NUXT_MARKER = "window.__NUXT__="


def extract_nuxt_expression(html: str) -> str:
    """Достать JS-выражение, присваиваемое `window.__NUXT__`, из сырого HTML."""
    start = html.find(NUXT_MARKER)
    if start == -1:
        raise PermanentError(
            "В HTML не найден window.__NUXT__ — вёрстка страницы поиска изменилась"
        )
    start += len(NUXT_MARKER)
    end = html.find("</script>", start)
    if end == -1:
        raise PermanentError("Не найден конец script-тега с window.__NUXT__")
    return html[start:end]


async def resolve_nuxt_state(context: BrowserContext, expression: str) -> dict[str, object]:
    """Выполнить выражение на чистой вкладке того же браузера и вернуть результат."""
    page = await context.new_page()
    try:
        result = await page.evaluate(expression)
    finally:
        await page.close()
    if not isinstance(result, dict):
        raise PermanentError("window.__NUXT__ разрешился не в объект — формат ответа изменился")
    return result


def extract_jobs_search(nuxt_state: dict[str, object]) -> tuple[list[object], dict[str, object]]:
    """Достать сырой список вакансий и paging-блок из состояния Nuxt.

    Путь `state.jobsSearch.{jobs,paging}` — как обнаружено на реальном
    прогоне 2026-09-07 по запросу `q=python`. Если Upwork поменяет разметку
    состояния, это должно упасть здесь явно, а не молча вернуть пустой список.
    """
    try:
        job_search = nuxt_state["state"]["jobsSearch"]  # type: ignore[index]
        jobs = job_search["jobs"]
        paging = job_search.get("paging", {})
    except (KeyError, TypeError) as exc:
        raise PermanentError(f"Неожиданная форма состояния Nuxt: {exc}") from exc
    if not isinstance(jobs, list):
        raise PermanentError("state.jobsSearch.jobs — не список")
    return jobs, paging
