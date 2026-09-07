"""Дымовой тест реального OpenRouter API. Требует `OPENROUTER_API_KEY` в окружении.

Помечен `live` — не запускается в обычном `pytest -q` (см. `addopts` в
`pyproject.toml`), только явно через `pytest -q -m live`.
"""

from __future__ import annotations

import os

import httpx
import pytest

from upwork_assistant.adapters.llm.openrouter import OpenRouterClient
from upwork_assistant.adapters.llm.schemas import ScoreResponse

pytestmark = pytest.mark.live


async def test_complete_structured_against_real_openrouter() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.startswith("sk-or-test") or "placeholder" in api_key.lower():
        pytest.skip("OPENROUTER_API_KEY не задан в окружении или похож на плейсхолдер")

    http_client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(30.0),
    )
    try:
        client = OpenRouterClient(http_client)
        response, usage = await client.complete_structured(
            model="openai/gpt-5-nano",
            system_prompt=(
                "Ты — ассистент фрилансера на Upwork. Оцени вакансию по шкале от 0 до 10."
            ),
            user_prompt="Вакансия: 'Нужен Python-разработчик для простого скрипта'.",
            response_model=ScoreResponse,
            schema_name="job_score",
        )
    finally:
        await http_client.aclose()

    assert isinstance(response, ScoreResponse)
    assert 0 <= response.value <= 10
    assert usage.model == "openai/gpt-5-nano"
