"""Тесты таблицы цен OpenRouter."""

from __future__ import annotations

import pytest

from upwork_assistant.adapters.llm.pricing import ModelPrice, calculate_cost_usd, get_price
from upwork_assistant.domain.errors import PermanentError


def test_get_price_known_model_returns_expected_price() -> None:
    price = get_price("openai/gpt-5-mini")
    assert price == ModelPrice(input_per_million=0.25, output_per_million=2.0)


def test_get_price_unknown_model_raises_permanent_error() -> None:
    with pytest.raises(PermanentError):
        get_price("openai/unknown-model")


def test_calculate_cost_usd_gpt5_mini() -> None:
    # 1000 промпт-токенов + 500 токенов ответа по цене gpt-5-mini.
    cost = calculate_cost_usd("openai/gpt-5-mini", prompt_tokens=1000, completion_tokens=500)
    expected = 1000 * 0.25 / 1_000_000 + 500 * 2.0 / 1_000_000
    assert cost == pytest.approx(expected)


def test_calculate_cost_usd_gpt5_nano_zero_tokens() -> None:
    cost = calculate_cost_usd("openai/gpt-5-nano", prompt_tokens=0, completion_tokens=0)
    assert cost == 0.0


def test_calculate_cost_usd_unknown_model_raises() -> None:
    with pytest.raises(PermanentError):
        calculate_cost_usd("openai/unknown-model", prompt_tokens=10, completion_tokens=10)
