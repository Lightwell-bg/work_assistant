"""Тесты REST-эндпоинта сводной статистики."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container
from upwork_assistant.domain.models import ClientProfile, JobPosting, JobStatus, JobType
from upwork_assistant.ports.llm import LLMUsageRecord


def _make_job(external_id: str, status: JobStatus) -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Job",
        description="Описание",
        job_type=JobType.FIXED,
        posted_at=datetime(2026, 9, 1, tzinfo=UTC),
        client=ClientProfile(),
        status=status,
    )


async def test_stats_reflect_seeded_jobs_and_llm_usage(
    settings: Settings, api_container: Container
) -> None:
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(_make_job("job-1", JobStatus.NEW))
        await uow.jobs.upsert(_make_job("job-2", JobStatus.SCORED))
        await uow.jobs.upsert(_make_job("job-3", JobStatus.SCORED))
        await uow.llm_usage.add(
            LLMUsageRecord(
                purpose="scoring",
                job_external_id="job-2",
                model="openai/gpt-5-mini",
                prompt_tokens=1000,
                completion_tokens=200,
                cost_usd=0.5,
            )
        )
        await uow.llm_usage.add(
            LLMUsageRecord(
                purpose="proposal",
                job_external_id="job-3",
                model="openai/gpt-5",
                prompt_tokens=1000,
                completion_tokens=200,
                cost_usd=1.5,
            )
        )

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["jobs_by_status"] == {"new": 1, "scored": 2}
        assert body["llm_cost_today_usd"] == 2.0
        assert body["llm_cost_total_usd"] == 2.0


async def test_stats_with_no_data_returns_zero_costs_and_empty_status_map(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["jobs_by_status"] == {}
        assert body["llm_cost_today_usd"] == 0.0
        assert body["llm_cost_total_usd"] == 0.0
