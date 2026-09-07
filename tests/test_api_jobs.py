"""Тесты REST-эндпоинтов просмотра вакансий и их черновиков."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    ExperienceLevel,
    JobPosting,
    JobStatus,
    JobType,
    ProposalTier,
    RateRange,
    Score,
)


def _make_job(external_id: str = "job-1", status: JobStatus = JobStatus.NEW) -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Python backend developer",
        description="Нужен бэкенд-разработчик на FastAPI",
        skills=("python", "fastapi"),
        job_type=JobType.HOURLY,
        rate_range=RateRange(min_rate=Decimal("30"), max_rate=Decimal("60"), currency="USD"),
        duration="1 to 3 months",
        experience_level=ExperienceLevel.EXPERT,
        posted_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        client=ClientProfile(
            country="Germany",
            payment_verified=True,
            total_spend=Decimal("15000.50"),
            hire_rate=0.75,
            avg_rating=4.9,
            reviews_count=32,
        ),
        competition=ProposalTier.FIVE_TO_TEN,
        entry_cost=2,
        status=status,
    )


async def test_list_jobs_is_empty_initially(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/jobs")
        assert response.status_code == 200
        assert response.json() == []


async def test_list_jobs_returns_seeded_job_with_correct_fields(
    settings: Settings, api_container: Container
) -> None:
    job = _make_job()
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(job)

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/jobs")
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        body = jobs[0]
        assert body["external_id"] == "job-1"
        assert body["title"] == job.title
        assert body["skills"] == ["python", "fastapi"]
        assert body["client"]["country"] == "Germany"
        assert body["score_value"] is None
        assert body["score_reasoning"] is None


async def test_list_jobs_includes_score_once_saved(
    settings: Settings, api_container: Container
) -> None:
    job = _make_job()
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(job)
        await uow.jobs.save_score(job.external_id, Score(value=8.5, reasoning="Хороший фит"))

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.external_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["score_value"] == 8.5
        assert body["score_reasoning"] == "Хороший фит"


async def test_list_jobs_filters_by_status(settings: Settings, api_container: Container) -> None:
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(_make_job("job-new", JobStatus.NEW))
        await uow.jobs.upsert(_make_job("job-scored", JobStatus.SCORED))

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/jobs", params={"status": "scored"})
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["external_id"] == "job-scored"


async def test_get_job_returns_404_for_unknown_external_id(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/jobs/does-not-exist")
        assert response.status_code == 404


async def test_get_job_draft_returns_404_when_none_exists(
    settings: Settings, api_container: Container
) -> None:
    job = _make_job()
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(job)

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.external_id}/draft")
        assert response.status_code == 404


async def test_get_job_draft_returns_seeded_draft_fields(
    settings: Settings, api_container: Container
) -> None:
    job = _make_job()
    draft = Draft(
        job_external_id=job.external_id,
        content="Здравствуйте! Готов взяться за проект.",
        status=DraftStatus.READY,
        created_at=datetime(2026, 9, 2, 8, 30, tzinfo=UTC),
    )
    async with unit_of_work(api_container.session_factory) as uow:
        await uow.jobs.upsert(job)
        await uow.drafts.add(job.external_id, draft)

    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.external_id}/draft")
        assert response.status_code == 200
        body = response.json()
        assert body["job_external_id"] == job.external_id
        assert body["content"] == draft.content
        assert body["status"] == "ready"
