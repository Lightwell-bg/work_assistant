"""Pydantic-схемы structured-output ответов LLM.

Каждая схема — это одновременно JSON Schema, которую OpenRouter принуждает
модель соблюдать (`response_format.json_schema`), и валидатор ответа на
стороне клиента. Несовпадение — `PermanentError`, а не тихий фолбэк.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScoreResponse(BaseModel):
    """Ответ модели-скорера."""

    model_config = ConfigDict(extra="forbid")

    value: float = Field(ge=0, le=10, description="Релевантность вакансии профилю, от 0 до 10")
    reasoning: str = Field(description="Короткое обоснование оценки на русском")


class ProposalResponse(BaseModel):
    """Ответ модели-генератора отклика."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Текст черновика отклика, готовый к отправке заказчику")
