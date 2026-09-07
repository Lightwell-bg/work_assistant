"""Тесты `ScoringService` на фейковом `LLMClient`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel

from upwork_assistant.adapters.llm.schemas import ScoreResponse
from upwork_assistant.domain.models import ClientProfile, JobPosting, JobType, ProposalTier
from upwork_assistant.ports.llm import LLMClient, ResponseModelT, TokenUsage
from upwork_assistant.services.scoring_service import ScoringService


class FakeLLMClient:
    """Простая реализация `LLMClient`: возвращает заранее заданный ответ."""

    def __init__(self, response: BaseModel, usage: TokenUsage) -> None:
        self._response = response
        self._usage = usage
        self.calls: list[dict[str, object]] = []

    async def complete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> tuple[ResponseModelT, TokenUsage]:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_model": response_model,
                "schema_name": schema_name,
            }
        )
        return self._response, self._usage  # type: ignore[return-value]


def _make_job(external_id: str = "job-1") -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Python backend developer",
        description="Нужен бэкенд-разработчик на FastAPI",
        skills=("python", "fastapi"),
        job_type=JobType.HOURLY,
        budget=None,
        rate_range=None,
        duration=None,
        experience_level=None,
        posted_at=datetime(2026, 9, 1, tzinfo=UTC),
        client=ClientProfile(
            country="Germany",
            payment_verified=True,
            total_spend=Decimal("1000"),
            hire_rate=None,
            avg_rating=None,
            reviews_count=0,
        ),
        competition=ProposalTier.UNKNOWN,
        entry_cost=0,
    )


async def test_score_builds_domain_score_and_usage_record() -> None:
    job = _make_job()
    response = ScoreResponse(value=8.5, reasoning="Хороший бюджет")
    usage = TokenUsage(
        model="openai/gpt-5-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.0001
    )
    llm_client: LLMClient = FakeLLMClient(response, usage)

    service = ScoringService(llm_client=llm_client, model="openai/gpt-5-mini")
    score, record = await service.score(job)

    assert score.value == 8.5
    assert score.reasoning == "Хороший бюджет"

    assert record.purpose == "scoring"
    assert record.job_external_id == job.external_id
    assert record.model == usage.model
    assert record.prompt_tokens == usage.prompt_tokens
    assert record.completion_tokens == usage.completion_tokens
    assert record.cost_usd == usage.cost_usd
