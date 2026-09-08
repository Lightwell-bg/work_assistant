"""Тесты доменной модели поискового запроса."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from upwork_assistant.domain.models import JobSourceName, SearchQuery


def test_search_query_holds_source_name_and_query() -> None:
    search = SearchQuery(
        source=JobSourceName.UPWORK,
        name="python_recency",
        query="https://www.upwork.com/nx/search/jobs/?q=python&sort=recency",
    )

    assert search.source is JobSourceName.UPWORK
    assert search.name == "python_recency"
    assert search.is_active is True


def test_search_query_is_frozen() -> None:
    search = SearchQuery(source=JobSourceName.LINKEDIN, name="ml", query="https://x")

    with pytest.raises(ValidationError):
        search.name = "other"  # type: ignore[misc]


def test_job_source_name_values_are_stable_strings() -> None:
    # Значения уходят в БД и в URL API — менять их нельзя без миграции.
    assert JobSourceName.UPWORK.value == "upwork"
    assert JobSourceName.LINKEDIN.value == "linkedin"


@pytest.mark.parametrize(
    "query",
    [
        "http://www.upwork.com/nx/search/jobs/?q=python",
        "https://www.upwork.com/nx/search/jobs/?q=python&sort=recency",
    ],
)
def test_search_query_accepts_http_and_https_urls(query: str) -> None:
    search = SearchQuery(source=JobSourceName.UPWORK, name="ok", query=query)

    assert search.query == query


def test_search_query_rejects_javascript_scheme() -> None:
    """Находка 3: значение уходит в page.goto() залогиненного браузера и
    рендерится как href в панели — javascript: там была бы живой ссылкой."""
    with pytest.raises(ValidationError):
        SearchQuery(source=JobSourceName.UPWORK, name="xss", query="javascript:alert(1)")


def test_search_query_rejects_non_url_string() -> None:
    with pytest.raises(ValidationError):
        SearchQuery(source=JobSourceName.UPWORK, name="bad", query="not-a-url")
