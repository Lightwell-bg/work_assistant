"""Таблица цен на модели OpenRouter.

Ответ OpenRouter на chat completion не всегда содержит стоимость запроса,
поэтому считаем её сами по `usage.prompt_tokens`/`usage.completion_tokens`
и этой таблице. Неизвестная модель — `PermanentError`, а не молчаливый
нулевой расход: таблицу нужно обновлять вручную вслед за `.env`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from upwork_assistant.domain.errors import PermanentError


class ModelPrice(BaseModel):
    """Цена модели в USD за 1 миллион токенов."""

    model_config = ConfigDict(frozen=True)

    input_per_million: float
    output_per_million: float


_PRICES: dict[str, ModelPrice] = {
    "openai/gpt-5-mini": ModelPrice(input_per_million=0.25, output_per_million=2.0),
    "openai/gpt-5": ModelPrice(input_per_million=1.25, output_per_million=10.0),
    "openai/gpt-5-nano": ModelPrice(input_per_million=0.05, output_per_million=0.40),
}


def get_price(model: str) -> ModelPrice:
    """Цена модели. Поднимает `PermanentError`, если модель не в таблице."""
    price = _PRICES.get(model)
    if price is None:
        raise PermanentError(
            f"Модель {model!r} отсутствует в таблице цен pricing.py — расход по ней "
            "не может быть посчитан. Добавьте цену в таблицу перед использованием модели."
        )
    return price


def calculate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Стоимость запроса в USD по числу токенов и таблице цен."""
    price = get_price(model)
    return (
        prompt_tokens * price.input_per_million / 1_000_000
        + completion_tokens * price.output_per_million / 1_000_000
    )
