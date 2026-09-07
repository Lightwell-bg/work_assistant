"""Генерация черновика отклика.

Профиль фрилансера читается из `data/profile.md` (см. `Settings.freelancer_profile_path`)
и подмешивается в системный промпт — этого не было в Kwork-версии, из-за
чего отклики выходили безликими. Отсутствующий или пустой файл — явная
`PermanentError`, а не безликий отклик по умолчанию.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from upwork_assistant.adapters.llm.prompts import (
    build_proposal_system_prompt,
    build_proposal_user_prompt,
)
from upwork_assistant.adapters.llm.schemas import ProposalResponse
from upwork_assistant.domain.errors import PermanentError
from upwork_assistant.domain.models import Draft, DraftStatus, JobPosting, Score
from upwork_assistant.ports.llm import LLMClient, LLMUsageRecord

SCHEMA_NAME = "job_proposal"
PURPOSE = "proposal"


class ProposalService:
    """Генерирует черновик отклика на основе вакансии, оценки и профиля фрилансера."""

    def __init__(self, llm_client: LLMClient, model: str, profile_path: Path) -> None:
        self._llm_client = llm_client
        self._model = model
        self._profile_path = profile_path

    async def generate(self, job: JobPosting, score: Score) -> tuple[Draft, LLMUsageRecord]:
        """Сгенерировать черновик. Поднимает `PermanentError`, если профиль не заполнен."""
        profile_markdown = self._read_profile()
        response, usage = await self._llm_client.complete_structured(
            model=self._model,
            system_prompt=build_proposal_system_prompt(profile_markdown),
            user_prompt=build_proposal_user_prompt(job, score),
            response_model=ProposalResponse,
            schema_name=SCHEMA_NAME,
        )
        draft = Draft(
            job_external_id=job.external_id,
            content=response.content,
            status=DraftStatus.READY,
            created_at=datetime.now(UTC),
        )
        record = LLMUsageRecord(
            purpose=PURPOSE,
            job_external_id=job.external_id,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )
        return draft, record

    def _read_profile(self) -> str:
        if not self._profile_path.is_file():
            raise PermanentError(
                f"Файл профиля {self._profile_path} не найден. Заполните его "
                "описанием опыта, стека и тона — без него отклики будут безликими."
            )
        text = self._profile_path.read_text(encoding="utf-8").strip()
        if not text:
            raise PermanentError(f"Файл профиля {self._profile_path} пуст")
        return text
