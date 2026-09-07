"""Порт LLM: контракт для сервисов скоринга и генерации откликов.

`LLMClient` знает только про structured outputs (модель ответа задаётся
Pydantic-схемой) — сервисы не работают с сырым JSON и не парсят ответ сами.
Ошибка валидации схемы — это `PermanentError`, а не повод откатиться на
эвристику (в отличие от Kwork-версии, где голый `json.loads()` без схемы
проглатывал сбои ИИ молча).
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class TokenUsage(BaseModel):
    """Токены и стоимость одного вызова LLM, посчитанные клиентом."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class LLMClient(Protocol):
    """Один вызов LLM со structured output."""

    async def complete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> tuple[ResponseModelT, TokenUsage]:
        """Выполнить запрос и вернуть ответ, провалидированный `response_model`.

        Поднимает `TransientError` на 429/5xx/таймаут (стоит повторить) и
        `PermanentError` на 4xx или ответ, не прошедший схему (повторять
        бессмысленно — нужно вмешательство человека).
        """
        ...


class LLMUsageRecord(BaseModel):
    """Строка учёта расходов на LLM — то, что сохраняется в `llm_usage`."""

    purpose: str
    job_external_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
