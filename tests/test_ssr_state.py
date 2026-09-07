"""Тесты извлечения embedded Nuxt state из HTML страницы поиска Upwork.

`resolve_nuxt_state` не тестируется здесь — она исполняет выражение на
реальной странице браузера, что этому модулю недоступно.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from upwork_assistant.adapters.upwork.ssr_state import (
    extract_jobs_search,
    extract_nuxt_expression,
)
from upwork_assistant.domain.errors import PermanentError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "upwork" / "nuxt_state_search_python.json"


def _load_fixture() -> dict[str, object]:
    data: dict[str, object] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


# --- extract_nuxt_expression ---


def test_extract_nuxt_expression_returns_text_between_marker_and_script_close() -> None:
    html = "<html><body><script>window.__NUXT__=({state:{foo:1}});</script></body></html>"

    expression = extract_nuxt_expression(html)

    assert expression == "({state:{foo:1}});"


def test_extract_nuxt_expression_raises_permanent_error_when_marker_missing() -> None:
    html = "<html><body><script>no nuxt state here</script></body></html>"

    with pytest.raises(PermanentError):
        extract_nuxt_expression(html)


def test_extract_nuxt_expression_raises_permanent_error_when_script_close_missing() -> None:
    html = "<html><body><script>window.__NUXT__=({state:{foo:1}});"

    with pytest.raises(PermanentError):
        extract_nuxt_expression(html)


# --- extract_jobs_search ---


def test_extract_jobs_search_returns_ten_jobs_and_real_paging_from_fixture() -> None:
    nuxt_state = _load_fixture()

    jobs, paging = extract_jobs_search(nuxt_state)

    assert len(jobs) == 10
    assert paging["total"] == 2465
    assert paging["offset"] == 0
    assert paging["count"] == 10


def test_extract_jobs_search_raises_permanent_error_when_state_key_missing() -> None:
    with pytest.raises(PermanentError):
        extract_jobs_search({"no_state_here": {}})


def test_extract_jobs_search_raises_permanent_error_when_jobs_is_not_a_list() -> None:
    nuxt_state: dict[str, object] = {
        "state": {"jobsSearch": {"jobs": "not-a-list", "paging": {}}}
    }

    with pytest.raises(PermanentError):
        extract_jobs_search(nuxt_state)
