"""Сводная статистика: распределение вакансий по статусам, расходы на LLM."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter

from upwork_assistant.api.deps import UowDep
from upwork_assistant.api.schemas import StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats(uow: UowDep) -> StatsOut:
    """Посчитать статистику в Python, а не SQL-агрегатом — при личном
    масштабе использования вакансий мало, а отдельный метод репозитория
    ради одного эндпоинта не окупается.
    """
    jobs = await uow.jobs.list_all()
    jobs_by_status = dict(Counter(job.status.value for job in jobs))

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = await uow.llm_usage.total_cost_since(today_start)
    cost_total = await uow.llm_usage.total_cost_since(datetime.min.replace(tzinfo=UTC))

    return StatsOut(
        jobs_by_status=jobs_by_status,
        llm_cost_today_usd=cost_today,
        llm_cost_total_usd=cost_total,
    )
