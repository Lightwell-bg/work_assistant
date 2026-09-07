"""Тесты `services.pipeline.process_job`: скоринг -> порог -> генерация -> бюджет.

`ScoringService`/`ProposalService`/`UnitOfWork` заменены плоскими фейками
(без библиотеки мокинга — тот же стиль, что и в `test_scoring_service.py` /
`test_proposal_service.py`), чтобы явно контролировать возвращаемые значения
и проверять порядок вызовов.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from upwork_assistant.domain.errors import PermanentError, TransientError
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    JobPosting,
    JobStatus,
    JobType,
    Score,
)
from upwork_assistant.ports.llm import LLMUsageRecord
from upwork_assistant.services import pipeline


def _make_job(external_id: str = "job-1") -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Python backend developer",
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


class FakeScoringService:
    """Фейк `ScoringService`: возвращает заданный `Score` или бросает исключение."""

    def __init__(
        self, score: Score | None = None, error: Exception | None = None
    ) -> None:
        self._score = score
        self._error = error
        self.calls: list[JobPosting] = []

    async def score(self, job: JobPosting) -> tuple[Score, LLMUsageRecord]:
        self.calls.append(job)
        if self._error is not None:
            raise self._error
        assert self._score is not None
        return self._score, _usage("scoring", job.external_id)


class FakeProposalService:
    """Фейк `ProposalService`: возвращает заданный `Draft` или бросает исключение."""

    def __init__(
        self, draft: Draft | None = None, error: Exception | None = None
    ) -> None:
        self._draft = draft
        self._error = error
        self.calls: list[tuple[JobPosting, Score]] = []

    async def generate(self, job: JobPosting, score: Score) -> tuple[Draft, LLMUsageRecord]:
        self.calls.append((job, score))
        if self._error is not None:
            raise self._error
        assert self._draft is not None
        return self._draft, _usage("proposal", job.external_id)


class FakeJobRepository:
    """Записывает вызовы `set_status`/`save_score`, не хранит настоящих данных."""

    def __init__(self) -> None:
        self.set_status_calls: list[tuple[str, JobStatus]] = []
        self.save_score_calls: list[tuple[str, Score]] = []

    async def set_status(self, external_id: str, status: JobStatus) -> None:
        self.set_status_calls.append((external_id, status))

    async def save_score(self, external_id: str, score: Score) -> None:
        self.save_score_calls.append((external_id, score))


class FakeDraftRepository:
    def __init__(self) -> None:
        self.add_calls: list[tuple[str, Draft]] = []

    async def add(self, job_external_id: str, draft: Draft) -> None:
        self.add_calls.append((job_external_id, draft))


class FakeLLMUsageRepository:
    """`total_cost_since` возвращает заранее заданное значение — так и
    моделируется дневной бюджет без реальной БД."""

    def __init__(self, total_cost_since: float = 0.0) -> None:
        self.add_calls: list[LLMUsageRecord] = []
        self._total_cost_since = total_cost_since

    async def add(self, record: LLMUsageRecord) -> None:
        self.add_calls.append(record)

    async def total_cost_since(self, since: datetime) -> float:
        return self._total_cost_since


class FakeUnitOfWork:
    def __init__(self, total_cost_since: float = 0.0) -> None:
        self.jobs = FakeJobRepository()
        self.drafts = FakeDraftRepository()
        self.llm_usage = FakeLLMUsageRepository(total_cost_since)


MIN_SCORE = 7.0
DAILY_BUDGET = 5.0


async def test_score_below_threshold_stops_before_generation() -> None:
    job = _make_job()
    score = Score(value=5.0, reasoning="Средний заказ")
    uow = FakeUnitOfWork()
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService()

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert outcome.score == score
    assert outcome.draft is None
    assert outcome.alert is None

    assert uow.jobs.save_score_calls == [(job.external_id, score)]
    assert (job.external_id, JobStatus.SCORED) in uow.jobs.set_status_calls
    assert len(uow.llm_usage.add_calls) == 1
    assert uow.llm_usage.add_calls[0].purpose == "scoring"
    assert proposal.calls == []


async def test_score_at_threshold_generates_draft() -> None:
    job = _make_job()
    score = Score(value=MIN_SCORE, reasoning="Хороший заказ")
    draft = Draft(
        job_external_id=job.external_id,
        content="Здравствуйте!",
        status=DraftStatus.PENDING,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    uow = FakeUnitOfWork(total_cost_since=0.0)
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService(draft=draft)

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert outcome.draft == draft
    assert outcome.alert is None
    assert uow.drafts.add_calls == [(job.external_id, draft)]
    assert (job.external_id, JobStatus.DRAFTED) in uow.jobs.set_status_calls
    assert len(uow.llm_usage.add_calls) == 2
    assert [r.purpose for r in uow.llm_usage.add_calls] == ["scoring", "proposal"]


async def test_scoring_failure_produces_alert_and_never_calls_proposal() -> None:
    job = _make_job()
    uow = FakeUnitOfWork()
    scoring = FakeScoringService(error=TransientError("модель недоступна"))
    proposal = FakeProposalService()

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert outcome.score is None
    assert outcome.draft is None
    assert outcome.alert is not None

    assert (job.external_id, JobStatus.SCORING_FAILED) in uow.jobs.set_status_calls
    assert proposal.calls == []
    assert uow.llm_usage.add_calls == []


async def test_generation_failure_keeps_score_but_no_draft() -> None:
    job = _make_job()
    score = Score(value=MIN_SCORE, reasoning="Хороший заказ")
    uow = FakeUnitOfWork()
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService(error=PermanentError("схема ответа не совпала"))

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert outcome.score == score
    assert outcome.draft is None
    assert outcome.alert is not None
    # Скоринг уже был сохранён до сбоя генерации.
    assert uow.jobs.save_score_calls == [(job.external_id, score)]


async def test_budget_exhausted_short_circuits_before_generate() -> None:
    job = _make_job()
    score = Score(value=MIN_SCORE, reasoning="Хороший заказ")
    uow = FakeUnitOfWork(total_cost_since=DAILY_BUDGET)
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService()

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert proposal.calls == []
    assert outcome.alert is not None
    assert "бюджет" in outcome.alert.lower()
    assert outcome.draft is None
    assert outcome.score == score


async def test_budget_boundary_exactly_equal_still_blocks() -> None:
    job = _make_job()
    score = Score(value=MIN_SCORE, reasoning="Хороший заказ")
    uow = FakeUnitOfWork(total_cost_since=DAILY_BUDGET)
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService()

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert proposal.calls == []
    assert outcome.draft is None


async def test_budget_just_under_limit_proceeds_to_generate() -> None:
    job = _make_job()
    score = Score(value=MIN_SCORE, reasoning="Хороший заказ")
    draft = Draft(
        job_external_id=job.external_id,
        content="Здравствуйте!",
        status=DraftStatus.PENDING,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    uow = FakeUnitOfWork(total_cost_since=DAILY_BUDGET - 0.01)
    scoring = FakeScoringService(score=score)
    proposal = FakeProposalService(draft=draft)

    outcome = await pipeline.process_job(
        job, uow, scoring, proposal, MIN_SCORE, DAILY_BUDGET  # type: ignore[arg-type]
    )

    assert len(proposal.calls) == 1
    assert outcome.draft == draft
    assert outcome.alert is None
