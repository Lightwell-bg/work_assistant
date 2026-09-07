"""APScheduler: самопланирующийся цикл опроса с джиттером и circuit breaker.

Обычный IntervalTrigger не подходит: интервал должен джиттериться на каждый
раз (`PollingPolicy.next_delay_seconds()`), а при открытом circuit breaker
опрос должен насовсем остановиться и позвать на помощь, а не долбить биржу
вхолостую по фиксированному расписанию.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from upwork_assistant.adapters.upwork.polling import CircuitOpenError, PollingPolicy
from upwork_assistant.ports.notifier import Notifier
from upwork_assistant.services.ingest_service import IngestService

logger = logging.getLogger(__name__)

_JOB_ID = "upwork_poll_cycle"


class PollingRunner:
    """Владеет самопланированием цикла опроса. `start()` не блокирует —
    только ставит первый запуск в очередь `scheduler` (который должен
    быть уже запущен вызывающим кодом)."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        ingest_service: IngestService,
        policy: PollingPolicy,
        notifier: Notifier,
    ) -> None:
        self._scheduler = scheduler
        self._ingest_service = ingest_service
        self._policy = policy
        self._notifier = notifier

    def start(self) -> None:
        """Поставить первый цикл опроса на выполнение немедленно."""
        self._schedule_next(delay_seconds=0)

    def stop(self) -> None:
        """Снять запланированный цикл, если он есть. Безопасно вызывать повторно."""
        with contextlib.suppress(JobLookupError):
            self._scheduler.remove_job(_JOB_ID)

    def is_scheduled(self) -> bool:
        """Есть ли сейчас запланированный следующий цикл — для kill switch по API."""
        return self._scheduler.get_job(_JOB_ID) is not None

    @property
    def policy(self) -> PollingPolicy:
        return self._policy

    def _schedule_next(self, delay_seconds: float) -> None:
        run_date = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        self._scheduler.add_job(
            self._run_cycle,
            trigger=DateTrigger(run_date=run_date),
            id=_JOB_ID,
            replace_existing=True,
        )

    async def _run_cycle(self) -> None:
        try:
            self._policy.check_circuit()
        except CircuitOpenError as exc:
            logger.error("Опрос остановлен: %s", exc)
            await self._notifier.notify_alert(str(exc))
            return  # не перепланируем — нужно вмешательство человека

        try:
            count = await self._ingest_service.run_once()
            logger.info("Цикл опроса обработал %d вакансий", count)
            self._policy.record_success()
        except Exception as exc:
            logger.exception("Цикл опроса упал")
            self._policy.record_failure()
            await self._notifier.notify_alert(f"Цикл опроса упал: {exc}")

        self._schedule_next(self._policy.next_delay_seconds())
