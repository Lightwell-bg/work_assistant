"""Тесты `IngestService.run_once()` на реальной БД (SQLite, tmp_path) и
фейковых `JobSource`/`ScoringService`/`ProposalService`/`Notifier`.

`run_once()` объединяет опрос, дедуп, фильтрацию и `pipeline.process_job` —
здесь проверяется именно эта склейка (реальные репозитории/UoW), а не
логика скоринга/генерации самого пайплайна (та уже покрыта `test_pipeline.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.errors import TransientError
from upwork_assistant.domain.filters import (
    FilterField,
    FilterMatchMode,
    FilterOperator,
    FilterRule,
    FilterSet,
)
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    JobPosting,
    JobStatus,
    JobType,
    Score,
)
from upwork_assistant.ports.job_source import PolledJob
from upwork_assistant.ports.llm import LLMUsageRecord
from upwork_assistant.services.ingest_service import IngestService

MIN_SCORE = 7.0
DAILY_BUDGET = 5.0


def _make_job(external_id: str, title: str = "Python backend developer") -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title=title,
        description="Нужен бэкенд-разработчик на FastAPI",
        skills=("python", "fastapi"),
        job_type=JobType.HOURLY,
        posted_at=datetime(2026, 9, 1, tzinfo=UTC),
        client=ClientProfile(
            country="Germany",
            payment_verified=True,
            total_spend=Decimal("1000"),
            hire_rate=None,
            avg_rating=None,
            reviews_count=0,
        ),
    )


def _usage(purpose: str, job_external_id: str) -> LLMUsageRecord:
    return LLMUsageRecord(
        purpose=purpose,
        job_external_id=job_external_id,
        model="openai/gpt-5-mini",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.001,
    )


class FakeJobSource:
    """Возвращает заранее заданный список вакансий на каждый `poll()`."""

    def __init__(self, jobs: list[JobPosting]) -> None:
        self._jobs = jobs
        self.poll_calls = 0

    async def poll(self) -> list[PolledJob]:
        self.poll_calls += 1
        return [PolledJob(job=job, raw_payload=None) for job in self._jobs]


class FakeNotifier:
    def __init__(self) -> None:
        self.new_draft_calls: list[tuple[JobPosting, Score, Draft]] = []
        self.alert_calls: list[str] = []

    async def notify_new_draft(self, job: JobPosting, score: Score, draft: Draft) -> None:
        self.new_draft_calls.append((job, score, draft))

    async def notify_alert(self, message: str) -> None:
        self.alert_calls.append(message)


class FakeScoringService:
    """Оценка по правилу: заголовок содержит "good" -> высокий скор,
    "bad" -> низкий, "fail" -> исключение. Позволяет управлять исходом
    из заголовка вакансии без дополнительных параметров конструктора."""

    async def score(self, job: JobPosting) -> tuple[Score, LLMUsageRecord]:
        if "fail" in job.title:
            raise TransientError(f"скоринг {job.external_id} упал")
        value = 9.0 if "good" in job.title else 2.0
        return Score(value=value, reasoning="фейковая оценка"), _usage(
            "scoring", job.external_id
        )


class FakeProposalService:
    async def generate(self, job: JobPosting, score: Score) -> tuple[Draft, LLMUsageRecord]:
        draft = Draft(
            job_external_id=job.external_id,
            content="Здравствуйте!",
            status=DraftStatus.PENDING,
            created_at=datetime(2026, 9, 2, tzinfo=UTC),
        )
        return draft, _usage("proposal", job.external_id)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "ingest_test.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _make_service(
    job_source: FakeJobSource,
    notifier: FakeNotifier,
    session_factory: async_sessionmaker[AsyncSession],
) -> IngestService:
    return IngestService(
        job_source,
        session_factory,
        FakeScoringService(),  # type: ignore[arg-type]
        FakeProposalService(),  # type: ignore[arg-type]
        notifier,
        MIN_SCORE,
        DAILY_BUDGET,
    )


async def test_run_once_scores_and_drafts_new_jobs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jobs = [_make_job("job-good", title="good python job"), _make_job("job-bad", title="bad job")]
    source = FakeJobSource(jobs)
    notifier = FakeNotifier()
    service = _make_service(source, notifier, session_factory)

    processed = await service.run_once()

    # Обе вакансии дошли до пайплайна (ни одна не задедуплена и не отфильтрована).
    assert processed == 2
    assert len(notifier.new_draft_calls) == 1
    assert notifier.new_draft_calls[0][0].external_id == "job-good"
    assert notifier.alert_calls == []

    async with unit_of_work(session_factory) as uow:
        good = await uow.jobs.get_by_external_id("job-good")
        bad = await uow.jobs.get_by_external_id("job-bad")
    assert good is not None and good.status == JobStatus.DRAFTED
    assert bad is not None and bad.status == JobStatus.SCORED


async def test_run_once_second_call_dedups_same_external_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jobs = [_make_job("job-good", title="good python job")]
    source = FakeJobSource(jobs)
    notifier = FakeNotifier()
    service = _make_service(source, notifier, session_factory)

    first = await service.run_once()
    assert first == 1
    assert len(notifier.new_draft_calls) == 1

    second = await service.run_once()

    assert second == 0
    # Никаких новых уведомлений и новых записей LLM usage.
    assert len(notifier.new_draft_calls) == 1
    async with unit_of_work(session_factory) as uow:
        total_cost = await uow.llm_usage.total_cost_since(datetime(2020, 1, 1, tzinfo=UTC))
    # Одна оценка + одна генерация = 2 записи по 0.001 = 0.002.
    assert total_cost == pytest.approx(0.002)


async def test_run_once_job_not_matching_filter_is_filtered_out_before_scoring(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    restrictive_filter = FilterSet(
        name="only-django",
        rules=(
            FilterRule(
                field=FilterField.SKILLS, operator=FilterOperator.CONTAINS, value="django"
            ),
        ),
        match_mode=FilterMatchMode.ALL,
        is_active=True,
    )
    async with unit_of_work(session_factory) as uow:
        await uow.filter_sets.save(restrictive_filter)

    jobs = [_make_job("job-good", title="good python job")]  # skills содержат только fastapi
    source = FakeJobSource(jobs)
    notifier = FakeNotifier()
    service = _make_service(source, notifier, session_factory)

    await service.run_once()

    async with unit_of_work(session_factory) as uow:
        job = await uow.jobs.get_by_external_id("job-good")
    assert job is not None
    assert job.status == JobStatus.FILTERED_OUT
    assert notifier.new_draft_calls == []
    assert notifier.alert_calls == []


async def test_run_once_scoring_failure_notifies_alert_and_marks_scoring_failed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jobs = [_make_job("job-fail", title="fail job")]
    source = FakeJobSource(jobs)
    notifier = FakeNotifier()
    service = _make_service(source, notifier, session_factory)

    await service.run_once()

    assert len(notifier.alert_calls) == 1
    async with unit_of_work(session_factory) as uow:
        job = await uow.jobs.get_by_external_id("job-fail")
    assert job is not None
    assert job.status == JobStatus.SCORING_FAILED
