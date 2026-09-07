"""Тесты `ProposalService` на фейковом `LLMClient`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from upwork_assistant.adapters.llm.schemas import ProposalResponse
from upwork_assistant.domain.errors import PermanentError
from upwork_assistant.domain.models import ClientProfile, JobPosting, JobType, ProposalTier, Score
from upwork_assistant.ports.llm import ResponseModelT, TokenUsage
from upwork_assistant.services.proposal_service import ProposalService


class FakeLLMClient:
    """Простая реализация `LLMClient`: возвращает заранее заданный ответ и
    запоминает промпты, с которыми её вызвали."""

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


async def test_generate_builds_draft_and_usage_record(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("Опытный Python-разработчик", encoding="utf-8")

    response = ProposalResponse(content="Здравствуйте! Готов взяться за проект.")
    usage = TokenUsage(
        model="openai/gpt-5", prompt_tokens=200, completion_tokens=80, cost_usd=0.001
    )
    fake = FakeLLMClient(response, usage)
    service = ProposalService(llm_client=fake, model="openai/gpt-5", profile_path=profile_path)

    job = _make_job()
    score = Score(value=8.0, reasoning="Хороший заказ")
    draft, record = await service.generate(job, score)

    assert draft.job_external_id == job.external_id
    assert draft.content == "Здравствуйте! Готов взяться за проект."

    assert record.purpose == "proposal"
    assert record.job_external_id == job.external_id
    assert record.model == usage.model
    assert record.prompt_tokens == usage.prompt_tokens
    assert record.completion_tokens == usage.completion_tokens
    assert record.cost_usd == usage.cost_usd


async def test_generate_missing_profile_raises_permanent_error(tmp_path: Path) -> None:
    profile_path = tmp_path / "missing_profile.md"
    response = ProposalResponse(content="text")
    usage = TokenUsage(model="openai/gpt-5", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)
    fake = FakeLLMClient(response, usage)
    service = ProposalService(llm_client=fake, model="openai/gpt-5", profile_path=profile_path)

    with pytest.raises(PermanentError):
        await service.generate(_make_job(), Score(value=5.0, reasoning="ok"))


async def test_generate_empty_profile_raises_permanent_error(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("   \n  ", encoding="utf-8")
    response = ProposalResponse(content="text")
    usage = TokenUsage(model="openai/gpt-5", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)
    fake = FakeLLMClient(response, usage)
    service = ProposalService(llm_client=fake, model="openai/gpt-5", profile_path=profile_path)

    with pytest.raises(PermanentError):
        await service.generate(_make_job(), Score(value=5.0, reasoning="ok"))


async def test_generate_profile_content_ends_up_in_prompt(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_text = "Специализация: FastAPI, PostgreSQL, 5 лет опыта"
    profile_path.write_text(profile_text, encoding="utf-8")

    response = ProposalResponse(content="text")
    usage = TokenUsage(model="openai/gpt-5", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)
    fake = FakeLLMClient(response, usage)
    service = ProposalService(llm_client=fake, model="openai/gpt-5", profile_path=profile_path)

    await service.generate(_make_job(), Score(value=5.0, reasoning="ok"))

    assert len(fake.calls) == 1
    assert profile_text in fake.calls[0]["system_prompt"]  # type: ignore[operator]
