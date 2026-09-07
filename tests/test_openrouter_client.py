"""Тесты `OpenRouterClient` на `httpx.MockTransport` — без реальной сети."""

from __future__ import annotations

import json

import httpx
import pytest

from upwork_assistant.adapters.llm.openrouter import OpenRouterClient
from upwork_assistant.adapters.llm.schemas import ScoreResponse
from upwork_assistant.domain.errors import PermanentError, TransientError

MODEL = "openai/gpt-5-mini"


def _make_client(transport: httpx.MockTransport) -> OpenRouterClient:
    http_client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1", transport=transport
    )
    return OpenRouterClient(http_client)


def _success_response(
    content: dict[str, object], usage: dict[str, int] | None = None
) -> httpx.Response:
    body: dict[str, object] = {"choices": [{"message": {"content": json.dumps(content)}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


async def test_success_parses_response_and_computes_cost() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response(
            {"value": 8.0, "reasoning": "Хороший заказ"},
            usage={"prompt_tokens": 1000, "completion_tokens": 500},
        )

    client = _make_client(httpx.MockTransport(handler))
    result, usage = await client.complete_structured(
        model=MODEL,
        system_prompt="system",
        user_prompt="user",
        response_model=ScoreResponse,
        schema_name="job_score",
    )

    assert result == ScoreResponse(value=8.0, reasoning="Хороший заказ")
    assert usage.model == MODEL
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    expected_cost = 1000 * 0.25 / 1_000_000 + 500 * 2.0 / 1_000_000
    assert usage.cost_usd == pytest.approx(expected_cost)


async def test_retry_then_success_calls_handler_twice() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, text="rate limited")
        return _success_response({"value": 5.0, "reasoning": "ok"})

    client = _make_client(httpx.MockTransport(handler))
    result, _ = await client.complete_structured(
        model=MODEL,
        system_prompt="system",
        user_prompt="user",
        response_model=ScoreResponse,
        schema_name="job_score",
    )

    assert result == ScoreResponse(value=5.0, reasoning="ok")
    assert calls["count"] == 2


async def test_exhausted_retries_raises_transient_error_after_three_attempts() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, text="server error")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(TransientError):
        await client.complete_structured(
            model=MODEL,
            system_prompt="system",
            user_prompt="user",
            response_model=ScoreResponse,
            schema_name="job_score",
        )

    assert calls["count"] == 3


async def test_immediate_permanent_failure_does_not_retry() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, text="bad request")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(PermanentError):
        await client.complete_structured(
            model=MODEL,
            system_prompt="system",
            user_prompt="user",
            response_model=ScoreResponse,
            schema_name="job_score",
        )

    assert calls["count"] == 1


async def test_malformed_content_not_json_raises_permanent_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(PermanentError):
        await client.complete_structured(
            model=MODEL,
            system_prompt="system",
            user_prompt="user",
            response_model=ScoreResponse,
            schema_name="job_score",
        )


async def test_malformed_content_fails_schema_validation_raises_permanent_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Валидный JSON, но без обязательного поля reasoning.
        return _success_response({"value": 5.0})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(PermanentError):
        await client.complete_structured(
            model=MODEL,
            system_prompt="system",
            user_prompt="user",
            response_model=ScoreResponse,
            schema_name="job_score",
        )


async def test_missing_usage_block_defaults_tokens_to_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response({"value": 3.0, "reasoning": "ok"}, usage=None)

    client = _make_client(httpx.MockTransport(handler))
    _, usage = await client.complete_structured(
        model=MODEL,
        system_prompt="system",
        user_prompt="user",
        response_model=ScoreResponse,
        schema_name="job_score",
    )

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.cost_usd == 0.0
