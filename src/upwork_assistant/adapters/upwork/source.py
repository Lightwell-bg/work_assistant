"""`ports.JobSource` для Upwork.

Один `poll()` = один заход на каждый сохранённый поиск из
`settings.upwork_search_urls`, с пагинацией до `upwork_max_pages_per_search`
страниц: страница загружается, embedded Nuxt state разрешается
(`ssr_state.py`), сырые вакансии валидируются `RawJob` и маппятся в домен
(`mapper.py`). DOM-фолбэк подключается, только если извлечение embedded
state не удалось — то же самое разделение "основной путь / план Б", что и
было задумано для сетевого перехвата, просто реализованное на извлечении
embedded state, а не отдельного JSON-эндпоинта (эндпоинта под список
вакансий на первой загрузке не оказалось — см. `ssr_state.py`). Пагинация
DOM-фолбэка не касается: он используется только как аварийный путь для
одной уже открытой страницы, без перехода по номерам страниц.
"""

from __future__ import annotations

import asyncio
import logging

from patchright.async_api import BrowserContext
from pydantic import ValidationError

from upwork_assistant.adapters.upwork.auth import ensure_logged_in
from upwork_assistant.adapters.upwork.browser import BrowserSession
from upwork_assistant.adapters.upwork.dom_fallback import parse_dom_fallback
from upwork_assistant.adapters.upwork.mapper import map_job
from upwork_assistant.adapters.upwork.payload_models import RawJob
from upwork_assistant.adapters.upwork.polling import PollingPolicy
from upwork_assistant.adapters.upwork.ssr_state import (
    extract_jobs_search,
    extract_nuxt_expression,
    resolve_nuxt_state,
)
from upwork_assistant.config import Settings
from upwork_assistant.domain.errors import PermanentError, TransientError
from upwork_assistant.ports.job_source import PolledJob

logger = logging.getLogger(__name__)

# Сколько ждать после networkidle перед чтением HTML. Найдено эмпирически
# 2026-09-07: Cloudflare иногда отдаёт промежуточную challenge-страницу
# (redirect с `__cf_chl_rt_tk=` в URL) и сам молча редиректит на реальную
# после проверки в браузере — на это нужно время сверх networkidle,
# иначе `page.content()` возвращает HTML челленджа, а не страницы поиска.
_CLOUDFLARE_SETTLE_SECONDS = 5.0


class UpworkJobSource:
    """Реализация `ports.job_source.JobSource` поверх Patchright + SSR-извлечения.

    `policy` — тот же экземпляр `PollingPolicy`, что и у планировщика: часовой
    лимит загрузок страниц должен считаться из одного места, иначе настройка
    `max_page_loads_per_hour` ничего не ограничивает на практике.
    """

    def __init__(self, settings: Settings, policy: PollingPolicy) -> None:
        self._settings = settings
        self._policy = policy

    async def poll(self) -> list[PolledJob]:
        jobs: list[PolledJob] = []
        async with BrowserSession(
            profile_dir=self._settings.upwork_profile_dir,
            headless=self._settings.upwork_headless,
            proxy=self._settings.upwork_proxy,
        ) as context:
            page = context.pages[0] if context.pages else await context.new_page()
            if not self._policy.can_load_page():
                logger.warning("Часовой лимит загрузок страниц исчерпан — пропускаю цикл")
                return []
            self._policy.record_page_load()
            await ensure_logged_in(page)

            for url in self._settings.search_urls:
                if not self._policy.can_load_page():
                    logger.warning(
                        "Часовой лимит загрузок страниц исчерпан — прерываю опрос на %s", url
                    )
                    break
                jobs.extend(await self._poll_search(context, url))

        return jobs

    async def _poll_search(self, context: BrowserContext, base_url: str) -> list[PolledJob]:
        """Пройти по страницам одного сохранённого поиска до лимита или конца выдачи."""
        collected: list[PolledJob] = []
        for page_number in range(1, self._settings.upwork_max_pages_per_search + 1):
            if page_number > 1 and not self._policy.can_load_page():
                logger.warning(
                    "Часовой лимит загрузок страниц исчерпан — прерываю пагинацию %s", base_url
                )
                break
            url = base_url if page_number == 1 else f"{base_url}&page={page_number}"
            page_jobs, has_more = await self._poll_one(context, url)
            collected.extend(page_jobs)
            if not has_more:
                break
        return collected

    async def _poll_one(self, context: BrowserContext, url: str) -> tuple[list[PolledJob], bool]:
        """Один заход на одну страницу выдачи. Возвращает вакансии и признак "есть ещё"."""
        page = context.pages[0]
        self._policy.record_page_load()
        response = await page.goto(url, wait_until="networkidle")
        if response is None:
            raise TransientError(f"Не удалось загрузить {url}")
        await asyncio.sleep(_CLOUDFLARE_SETTLE_SECONDS)
        # Не response.text(): если был challenge-редирект, нужен HTML уже
        # осевшей страницы, а не тела самого первого ответа.
        html = await page.content()

        raw_jobs: list[object]
        has_more = False
        try:
            expression = extract_nuxt_expression(html)
            nuxt_state = await resolve_nuxt_state(context, expression)
            raw_jobs, paging = extract_jobs_search(nuxt_state)
            has_more = _has_more_pages(paging, len(raw_jobs))
        except PermanentError:
            logger.warning("Извлечение embedded state не удалось для %s — пробую DOM-фолбэк", url)
            raw_jobs = list(await parse_dom_fallback(context.pages[0]))

        if not raw_jobs:
            logger.warning("Ни одной вакансии не найдено на %s (перехват дал 0)", url)
            return [], False

        jobs: list[PolledJob] = []
        for raw in raw_jobs:
            try:
                parsed = RawJob.model_validate(raw)
            except ValidationError as exc:
                logger.error("Вакансия не прошла схему RawJob, пропускаю: %s", exc)
                continue
            job, facts = map_job(parsed)
            jobs.append(PolledJob(job=job, raw_payload=facts.raw_payload))
        return jobs, has_more


def _has_more_pages(paging: dict[str, object], returned_count: int) -> bool:
    """`paging` — как в `state.jobsSearch.paging`: `{"total", "offset", "count"}`."""
    try:
        offset = int(str(paging.get("offset", 0)))
        total = int(str(paging.get("total", 0)))
    except (TypeError, ValueError):
        return False
    return bool(offset + returned_count < total)
