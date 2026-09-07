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
