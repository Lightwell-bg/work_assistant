"""Kill switch: остановить/возобновить опрос вручную через API.

Нужен на случай, когда автоматика (circuit breaker) ещё не сработала, но
человек уже видит проблему — например, заметил рост подозрительной
активности в аккаунте Upwork и хочет остановить опрос немедленно, не дожидаясь
трёх подряд неудачных циклов.
"""

from __future__ import annotations

from fastapi import APIRouter

from upwork_assistant.api.deps import ContainerDep, UowDep
from upwork_assistant.api.schemas import AdminStatusOut, PollingIntervalIn
from upwork_assistant.services.polling_settings import save_polling_settings

router = APIRouter(prefix="/admin", tags=["admin"])


def _status(container: ContainerDep) -> AdminStatusOut:
    runner = container.polling_runner
    return AdminStatusOut(
        scheduled=runner.is_scheduled(),
        circuit_open=runner.policy.is_circuit_open,
        consecutive_failures=runner.policy.consecutive_failures,
        interval_minutes=runner.policy.interval_minutes,
        jitter_pct=runner.policy.jitter_pct,
    )


@router.get("/status", response_model=AdminStatusOut)
async def get_status(container: ContainerDep) -> AdminStatusOut:
    """Текущее состояние опроса: запланирован ли цикл, открыт ли circuit breaker."""
    return _status(container)


@router.post("/pause", response_model=AdminStatusOut)
async def pause(container: ContainerDep) -> AdminStatusOut:
    """Снять запланированный цикл опроса. Не трогает уже выполняющийся цикл."""
    container.polling_runner.stop()
    return _status(container)


@router.post("/resume", response_model=AdminStatusOut)
async def resume(container: ContainerDep) -> AdminStatusOut:
    """Поставить цикл опроса на выполнение немедленно."""
    container.polling_runner.start()
    return _status(container)


@router.put("/polling-interval", response_model=AdminStatusOut)
async def set_polling_interval(
    body: PollingIntervalIn, container: ContainerDep, uow: UowDep
) -> AdminStatusOut:
    """Сменить интервал/разброс опроса без перезапуска.

    Сохраняем в `app_state` первым шагом: если запись в БД упадёт, живой
    `PollingPolicy` не должен разойтись с тем, что переживёт следующий
    рестарт — иначе пользователь увидит новое поведение только до
    ближайшего перезапуска, а потом оно тихо откатится.
    """
    await save_polling_settings(
        uow, interval_minutes=body.interval_minutes, jitter_pct=body.jitter_pct
    )
    container.polling_runner.policy.set_interval_minutes(body.interval_minutes)
    container.polling_runner.policy.set_jitter_pct(body.jitter_pct)
    return _status(container)
