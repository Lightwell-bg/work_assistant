"""Просмотр вакансий и их черновиков.

Вакансии и черновики создаёт пайплайн ингеста, а не API — здесь нет
`POST`/`PUT` для их создания. Исключение — пометка черновика отправленным:
это то же самое действие, что и кнопка «✅ Отклик отправлен» в Telegram
(`adapters/telegram/handlers.py`), просто доступное и из веб-панели — сам
черновик через API не меняется.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from upwork_assistant.api.deps import UowDep
from upwork_assistant.api.schemas import (
    DraftOut,
    JobOut,
    draft_out_from_domain,
    job_out_from_domain,
)
from upwork_assistant.domain.models import DraftStatus, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(
    uow: UowDep,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
) -> list[JobOut]:
    """Список вакансий, опционально отфильтрованный по статусу.

    Оценка подтягивается отдельным запросом на вакансию (N+1) — при
    личном масштабе использования это не проблема, батч-выборка бы
    только усложнила код без заметной пользы.
    """
    jobs = (
        await uow.jobs.list_by_status(status_filter)
        if status_filter is not None
        else await uow.jobs.list_all()
    )
    result = []
    for job in jobs:
        score = await uow.jobs.get_score(job.external_id)
        result.append(job_out_from_domain(job, score))
    return result


@router.get("/{external_id}", response_model=JobOut)
async def get_job(external_id: str, uow: UowDep) -> JobOut:
    """Одна вакансия по внешнему идентификатору."""
    job = await uow.jobs.get_by_external_id(external_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Вакансия {external_id!r} не найдена"
        )
    score = await uow.jobs.get_score(external_id)
    return job_out_from_domain(job, score)


@router.get("/{external_id}/draft", response_model=DraftOut)
async def get_job_draft(external_id: str, uow: UowDep) -> DraftOut:
    """Черновик отклика на вакансию, если он уже сгенерирован."""
    draft = await uow.drafts.get_by_job(external_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Черновик для вакансии {external_id!r} не найден",
        )
    return draft_out_from_domain(draft)


@router.post("/{external_id}/draft/sent", response_model=DraftOut)
async def mark_draft_sent(external_id: str, uow: UowDep) -> DraftOut:
    """Пометить черновик отправленным — то же действие, что кнопка в Telegram."""
    draft = await uow.drafts.get_by_job(external_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Черновик для вакансии {external_id!r} не найден",
        )
    await uow.drafts.set_status(external_id, DraftStatus.SENT)
    updated = await uow.drafts.get_by_job(external_id)
    assert updated is not None
    return draft_out_from_domain(updated)
