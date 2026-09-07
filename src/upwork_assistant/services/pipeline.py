"""Обработка одной вакансии: скоринг -> (если порог пройден) генерация черновика.

Вызывается внутри одной открытой `UnitOfWork` на вакансию (владелец —
`ingest_service.py`): сбой на одной вакансии откатывает только её правки,
не роняя весь цикл опроса. Сбой скоринга/генерации — это явный
`JobStatus.SCORING_FAILED`/алерт, а не тихий откат на эвристику, как было
в Kwork-версии.

Уведомления сюда намеренно не переданы: пока транзакция не закоммичена,
рассказывать человеку не о чем — `ingest_service.py` уведомляет уже после
успешного выхода из `unit_of_work`, по возвращённому отсюда `PipelineOutcome`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from upwork_assistant.adapters.db.uow import UnitOfWork
from upwork_assistant.domain.errors import AssistantError, BudgetExceededError
from upwork_assistant.domain.models import Draft, JobPosting, JobStatus, Score
from upwork_assistant.services.proposal_service import ProposalService
from upwork_assistant.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


def _today_start_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(slots=True, frozen=True)
class PipelineOutcome:
    """Результат обработки одной вакансии — для уведомления после коммита."""

    job: JobPosting
    score: Score | None = None
    draft: Draft | None = None
    alert: str | None = None


async def process_job(
    job: JobPosting,
    uow: UnitOfWork,
    scoring_service: ScoringService,
    proposal_service: ProposalService,
    min_score_to_notify: float,
    daily_budget_usd: float,
) -> PipelineOutcome:
    """Оценить вакансию и, если релевантна, сгенерировать черновик отклика."""
    try:
        score, usage = await scoring_service.score(job)
    except AssistantError as exc:
        logger.exception("Скоринг вакансии %s упал", job.external_id)
        await uow.jobs.set_status(job.external_id, JobStatus.SCORING_FAILED)
        return PipelineOutcome(job=job, alert=f"Скоринг вакансии {job.external_id} упал: {exc}")

    await uow.llm_usage.add(usage)
    await uow.jobs.save_score(job.external_id, score)
    await uow.jobs.set_status(job.external_id, JobStatus.SCORED)

    if score.value < min_score_to_notify:
        return PipelineOutcome(job=job, score=score)

    try:
        spent_today = await uow.llm_usage.total_cost_since(_today_start_utc())
        if spent_today >= daily_budget_usd:
            raise BudgetExceededError(
                f"Дневной бюджет ${daily_budget_usd:.2f} исчерпан "
                f"(потрачено ${spent_today:.4f}) — генерация отклика пропущена"
            )
        draft, draft_usage = await proposal_service.generate(job, score)
    except AssistantError as exc:
        logger.exception("Генерация отклика для %s упала", job.external_id)
        return PipelineOutcome(
            job=job,
            score=score,
            alert=f"Генерация отклика для {job.external_id} упала: {exc}",
        )

    await uow.llm_usage.add(draft_usage)
    await uow.drafts.add(job.external_id, draft)
    await uow.jobs.set_status(job.external_id, JobStatus.DRAFTED)
    return PipelineOutcome(job=job, score=score, draft=draft)
