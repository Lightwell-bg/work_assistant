"""Kill switch: остановить/возобновить опрос вручную через API.

Нужен на случай, когда автоматика (circuit breaker) ещё не сработала, но
человек уже видит проблему — например, заметил рост подозрительной
активности в аккаунте Upwork и хочет остановить опрос немедленно, не дожидаясь
трёх подряд неудачных циклов.
"""

from __future__ import annotations

from fastapi import APIRouter

from upwork_assistant.api.deps import ContainerDep
from upwork_assistant.api.schemas import AdminStatusOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _status(container: ContainerDep) -> AdminStatusOut:
    runner = container.polling_runner
    return AdminStatusOut(
        scheduled=runner.is_scheduled(),
        circuit_open=runner.policy.is_circuit_open,
        consecutive_failures=runner.policy.consecutive_failures,
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
