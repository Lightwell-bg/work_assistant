"""Тесты `PollingRunner`: не полагаемся на реальный тайминг APScheduler.

Циклы вызываются напрямую через `_run_cycle()` — единственный детерминированный
способ проверить поведение без ожидания реального времени.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from upwork_assistant.adapters.upwork.polling import PollingPolicy
from upwork_assistant.scheduler.runner import _JOB_ID, PollingRunner


@dataclass
class FakeIngestService:
    run_once_results: list[object]
    calls: int = 0

    async def run_once(self) -> int:
        self.calls += 1
        result = self.run_once_results[min(self.calls, len(self.run_once_results)) - 1]
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]


@dataclass
class FakeNotifier:
    alerts: list[str] = field(default_factory=list)

    async def notify_new_draft(self, job: object, score: object, draft: object) -> None:
        raise NotImplementedError

    async def notify_alert(self, message: str) -> None:
        self.alerts.append(message)


@pytest.fixture
async def scheduler() -> AsyncIterator[AsyncIOScheduler]:
    sched = AsyncIOScheduler()
    try:
        yield sched
    finally:
        if sched.running:
            sched.shutdown(wait=False)


def _make_policy(circuit_breaker_threshold: int = 3) -> PollingPolicy:
    return PollingPolicy(
        interval_minutes=1,
        jitter_pct=0,
        max_page_loads_per_hour=100,
        circuit_breaker_threshold=circuit_breaker_threshold,
        clock=lambda: datetime.now(UTC),
    )


async def test_successful_cycle_resets_failures_and_reschedules(
    scheduler: AsyncIOScheduler,
) -> None:
    policy = _make_policy()
    policy.record_failure()
    ingest = FakeIngestService(run_once_results=[5])
    notifier = FakeNotifier()
    runner = PollingRunner(scheduler, ingest, policy, notifier)  # type: ignore[arg-type]
    scheduler.start()

    await runner._run_cycle()

    assert policy.consecutive_failures == 0
    assert notifier.alerts == []
    assert scheduler.get_job(_JOB_ID) is not None


async def test_failing_cycle_notifies_alert_and_still_reschedules(
    scheduler: AsyncIOScheduler,
) -> None:
    policy = _make_policy(circuit_breaker_threshold=3)
    ingest = FakeIngestService(run_once_results=[RuntimeError("boom")])
    notifier = FakeNotifier()
    runner = PollingRunner(scheduler, ingest, policy, notifier)  # type: ignore[arg-type]
    scheduler.start()

    await runner._run_cycle()

    assert policy.consecutive_failures == 1
    assert len(notifier.alerts) == 1
    assert "Цикл опроса упал" in notifier.alerts[0]
    assert scheduler.get_job(_JOB_ID) is not None


async def test_circuit_opens_after_threshold_and_stops_rescheduling(
    scheduler: AsyncIOScheduler,
) -> None:
    # Порог уже достигнут до первого вызова `_run_cycle()` — так единственный
    # вызов проверяет именно ветку "circuit открыт", без побочного job'а,
    # оставшегося от предыдущего (успешно перепланированного) сбойного цикла.
    policy = _make_policy(circuit_breaker_threshold=2)
    policy.record_failure()
    policy.record_failure()
    assert policy.is_circuit_open is True

    ingest = FakeIngestService(run_once_results=[0])
    notifier = FakeNotifier()
    runner = PollingRunner(scheduler, ingest, policy, notifier)  # type: ignore[arg-type]
    scheduler.start()

    await runner._run_cycle()

    assert ingest.calls == 0  # до run_once дело не дошло — цикл остановлен раньше
    assert len(notifier.alerts) == 1
    assert "остановлено" in notifier.alerts[0]
    assert scheduler.get_job(_JOB_ID) is None


async def test_stop_is_safe_when_no_job_scheduled(scheduler: AsyncIOScheduler) -> None:
    policy = _make_policy()
    ingest = FakeIngestService(run_once_results=[0])
    notifier = FakeNotifier()
    runner = PollingRunner(scheduler, ingest, policy, notifier)  # type: ignore[arg-type]
    scheduler.start()

    runner.stop()  # не должно бросать, даже если задача не была поставлена
