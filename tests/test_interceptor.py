"""Тесты `ResponseCapture` и `search_response_predicate` на фейковом Patchright.

Реальный браузер не запускается — фейковые классы имитируют только те
атрибуты/методы `Response`/`Request`/`Page`, которые трогает `interceptor.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from upwork_assistant.adapters.upwork.interceptor import ResponseCapture, search_response_predicate


class FakeRequest:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type


class FakeResponse:
    """Фейковый ответ. `json_result`/`json_exception` управляют поведением `.json()`."""

    def __init__(
        self,
        *,
        resource_type: str = "xhr",
        url: str = "https://www.upwork.com/api/search",
        content_type: str = "application/json",
        json_result: Any = None,
        json_exception: Exception | None = None,
    ) -> None:
        self.request = FakeRequest(resource_type)
        self.url = url
        self.headers = {"content-type": content_type} if content_type is not None else {}
        self._json_result = json_result
        self._json_exception = json_exception
        self.json_call_count = 0

    async def json(self) -> Any:
        self.json_call_count += 1
        if self._json_exception is not None:
            raise self._json_exception
        return self._json_result


class FakePage:
    """Фейковая страница: `on()` просто запоминает обработчик для прямого вызова тестом."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def on(self, event_name: str, handler: Any) -> None:
        self.handlers[event_name] = handler


# --- search_response_predicate ---


def test_predicate_true_for_matching_xhr_json_response() -> None:
    response = FakeResponse(resource_type="xhr", url="https://www.upwork.com/api/search")
    assert search_response_predicate(response) is True  # type: ignore[arg-type]


def test_predicate_true_for_matching_fetch_json_response() -> None:
    response = FakeResponse(resource_type="fetch", url="https://www.upwork.com/api/search")
    assert search_response_predicate(response) is True  # type: ignore[arg-type]


def test_predicate_false_for_wrong_resource_type() -> None:
    response = FakeResponse(resource_type="document", url="https://www.upwork.com/api/search")
    assert search_response_predicate(response) is False  # type: ignore[arg-type]


def test_predicate_false_for_wrong_domain() -> None:
    response = FakeResponse(resource_type="xhr", url="https://example.com/api/search")
    assert search_response_predicate(response) is False  # type: ignore[arg-type]


def test_predicate_false_for_wrong_content_type() -> None:
    response = FakeResponse(
        resource_type="xhr",
        url="https://www.upwork.com/api/search",
        content_type="text/html",
    )
    assert search_response_predicate(response) is False  # type: ignore[arg-type]


# --- ResponseCapture ---


async def test_capture_appends_dict_json_body_when_predicate_true() -> None:
    capture = ResponseCapture(lambda response: True)
    response = FakeResponse(json_result={"jobs": []})

    await capture._on_response(response)  # type: ignore[arg-type]

    assert capture.captured == [{"jobs": []}]


async def test_capture_swallows_json_parse_error() -> None:
    capture = ResponseCapture(lambda response: True)
    response = FakeResponse(json_exception=ValueError("not valid json"))

    await capture._on_response(response)  # type: ignore[arg-type]

    assert capture.captured == []


async def test_capture_ignores_non_dict_json_body() -> None:
    capture = ResponseCapture(lambda response: True)
    response = FakeResponse(json_result=["not", "a", "dict"])

    await capture._on_response(response)  # type: ignore[arg-type]

    assert capture.captured == []


async def test_capture_never_parses_json_when_predicate_false() -> None:
    capture = ResponseCapture(lambda response: False)
    response = FakeResponse(json_result={"jobs": []})

    await capture._on_response(response)  # type: ignore[arg-type]

    assert capture.captured == []
    assert response.json_call_count == 0


async def test_attach_registers_handler_invokable_directly() -> None:
    capture = ResponseCapture(lambda response: True)
    page = FakePage()

    capture.attach(page)  # type: ignore[arg-type]
    response = FakeResponse(json_result={"ok": True})
    await page.handlers["response"](response)

    assert capture.captured == [{"ok": True}]


def test_clear_empties_captured() -> None:
    capture = ResponseCapture(lambda response: True)
    capture._captured.append({"a": 1})

    capture.clear()

    assert capture.captured == []


async def test_dump_fixtures_writes_numbered_json_files(tmp_path: Path) -> None:
    capture = ResponseCapture(lambda response: True)
    payloads = [
        {"id": 1, "title": "Обычная вакансия"},
        {"id": 2, "note": "Тест не-ASCII: мама мыла раму"},
    ]
    for payload in payloads:
        await capture._on_response(FakeResponse(json_result=payload))  # type: ignore[arg-type]

    paths = capture.dump_fixtures(tmp_path, prefix="x")

    assert [p.name for p in paths] == ["x_000.json", "x_001.json"]
    for path, expected in zip(paths, payloads, strict=True):
        assert json.loads(path.read_text(encoding="utf-8")) == expected
