"""Скоринг вакансии моделью.

Сервис не пишет в БД — он только зовёт LLM и возвращает домен плюс запись
об использовании. Персистентность и переход `JobStatus` в `SCORING_FAILED`
при сбое — забота пайплайна (`services/pipeline.py`, следующая фаза), у
которого одна транзакция на вакансию.
"""

from __future__ import annotations

from upwork_assistant.adapters.llm.prompts import (
    build_scoring_system_prompt,
    build_scoring_user_prompt,
)
from upwork_assistant.adapters.llm.schemas import ScoreResponse
from upwork_assistant.domain.models import JobPosting, Score
from upwork_assistant.ports.llm import LLMClient, LLMUsageRecord

SCHEMA_NAME = "job_score"
PURPOSE = "scoring"


class ScoringService:
    """Оценивает релевантность вакансии профилю фрилансера."""

    def __init__(self, llm_client: LLMClient, model: str) -> None:
        self._llm_client = llm_client
        self._model = model

    async def score(self, job: JobPosting) -> tuple[Score, LLMUsageRecord]:
        """Оценить вакансию. Поднимает `TransientError`/`PermanentError` LLM-клиента как есть."""
        response, usage = await self._llm_client.complete_structured(
            model=self._model,
            system_prompt=build_scoring_system_prompt(),
            user_prompt=build_scoring_user_prompt(job),
            response_model=ScoreResponse,
            schema_name=SCHEMA_NAME,
        )
        score = Score(value=response.value, reasoning=response.reasoning)
        record = LLMUsageRecord(
            purpose=PURPOSE,
            job_external_id=job.external_id,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )
        return score, record
