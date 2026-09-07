"""Клиент OpenRouter, реализующий `ports.llm.LLMClient`.

Собран вокруг ОДНОГО долгоживущего `httpx.AsyncClient`, который передаётся
снаружи (контейнер владеет его созданием/закрытием). В Kwork-версии клиент
открывал `async with self.session`, который закрывался после первого же
запроса — здесь этот класс никогда не открывает и не закрывает свой клиент.
"""

from __future__ import annotations

import json
import logging

import httpx
from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from upwork_assistant.adapters.llm import pricing
from upwork_assistant.domain.errors import PermanentError, TransientError
from upwork_assistant.ports.llm import ResponseModelT, TokenUsage

logger = logging.getLogger(__name__)

_TRUNCATE_LEN = 500


class OpenRouterClient:
    """Реализация `LLMClient` поверх OpenRouter chat completions API."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def complete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> tuple[ResponseModelT, TokenUsage]:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }

        data: dict[str, object] | None = None
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(TransientError),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=10),
            reraise=True,
        ):
            with attempt:
                data = await self._post(payload)
        assert data is not None  # AsyncRetrying либо вернул данные, либо поднял исключение

        return self._parse_response(data, model, response_model)

    async def _post(self, payload: dict[str, object]) -> dict[str, object]:
        """Один HTTP-запрос со сбросом статуса в `TransientError`/`PermanentError`."""
        try:
            response = await self._http_client.post("/chat/completions", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientError(f"Сетевая ошибка запроса к OpenRouter: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(
                f"OpenRouter вернул {response.status_code}: {_truncate(response.text)}"
            )
        if 400 <= response.status_code < 500:
            raise PermanentError(
                f"OpenRouter вернул {response.status_code}: {_truncate(response.text)}"
            )

        result: dict[str, object] = response.json()
        return result

    def _parse_response(
        self,
        data: dict[str, object],
        model: str,
        response_model: type[ResponseModelT],
    ) -> tuple[ResponseModelT, TokenUsage]:
        try:
            choices = data["choices"]
            content = choices[0]["message"]["content"]  # type: ignore[index]
            parsed = response_model.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise PermanentError(
                f"Ответ OpenRouter не прошёл схему {response_model.__name__}: {exc}"
            ) from exc

        usage: dict[str, object] = data.get("usage") or {}  # type: ignore[assignment]
        prompt_tokens = int(usage.get("prompt_tokens", 0))  # type: ignore[call-overload]
        completion_tokens = int(usage.get("completion_tokens", 0))  # type: ignore[call-overload]
        cost_usd = pricing.calculate_cost_usd(model, prompt_tokens, completion_tokens)

        token_usage = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        return parsed, token_usage


def _truncate(text: str) -> str:
    return text if len(text) <= _TRUNCATE_LEN else text[:_TRUNCATE_LEN] + "…"
