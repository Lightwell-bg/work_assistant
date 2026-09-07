"""Цикл опроса: `JobSource.poll()` -> дедуп -> фильтр -> `pipeline.process_job`.

Зависимости — только порты и другие сервисы, не `Container`: сборка
конкретных адаптеров (реальный `JobSource`, `Notifier` и т.д.) — забота
композиции в `container.py`/`scheduler/runner.py`, а не этого модуля.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, JobStatus
from upwork_assistant.ports.job_source import JobSource
from upwork_assistant.ports.notifier import Notifier
from upwork_assistant.services import filter_service, pipeline
from upwork_assistant.services.proposal_service import ProposalService
from upwork_assistant.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


class IngestService:
    """Один цикл опроса от источника вакансий до уведомления человека."""

    def __init__(
        self,
        job_source: JobSource,
        session_factory: async_sessionmaker[AsyncSession],
        scoring_service: ScoringService,
        proposal_service: ProposalService,
        notifier: Notifier,
        min_score_to_notify: float,
        daily_budget_usd: float,
    ) -> None:
        self._job_source = job_source
        self._session_factory = session_factory
        self._scoring_service = scoring_service
        self._proposal_service = proposal_service
        self._notifier = notifier
        self._min_score_to_notify = min_score_to_notify
        self._daily_budget_usd = daily_budget_usd

    async def run_once(self) -> int:
        """Выполнить один цикл. Возвращает число новых вакансий, дошедших до пайплайна."""
        async with unit_of_work(self._session_factory) as uow:
            searches = await uow.searches.list_active(JobSourceName.UPWORK)
            active_filter_sets = await uow.filter_sets.list_active()

        if not searches:
            logger.warning("Нет активных поисков — цикл пропущен")
            return 0

        jobs = await self._job_source.poll([search.query for search in searches])
        logger.info("Опрос вернул %d вакансий", len(jobs))

        processed = 0
        for polled in jobs:
            job = polled.job
            async with unit_of_work(self._session_factory) as uow:
                if await uow.jobs.exists(job.external_id):
                    continue
                await uow.jobs.upsert(job)
                if polled.raw_payload is not None:
                    await uow.upwork_facts.add(job.external_id, polled.raw_payload)

                if not filter_service.matches_any(job, active_filter_sets):
                    await uow.jobs.set_status(job.external_id, JobStatus.FILTERED_OUT)
                    continue

                outcome = await pipeline.process_job(
                    job,
                    uow,
                    self._scoring_service,
                    self._proposal_service,
                    self._min_score_to_notify,
                    self._daily_budget_usd,
                )

            if outcome.alert is not None:
                await self._notifier.notify_alert(outcome.alert)
            elif outcome.draft is not None and outcome.score is not None:
                await self._notifier.notify_new_draft(outcome.job, outcome.score, outcome.draft)
            processed += 1

        return processed
