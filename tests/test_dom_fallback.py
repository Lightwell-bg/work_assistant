"""Тесты DOM-фолбэка (`adapters/upwork/dom_fallback.py`) на реальном фикстурном HTML.

`parse_dom_fallback` читает через Playwright/Patchright локаторы
(`page.locator(...)`), поэтому его нельзя протестировать фейковым объектом —
нужна настоящая `Page`. Профиль/стелс не нужны (контент статичный,
уже отрендеренный сервером), поэтому используется голый
`patchright.async_api.async_playwright()`, а не `BrowserSession`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
from patchright.async_api import Page, async_playwright

from upwork_assistant.adapters.upwork.dom_fallback import parse_dom_fallback
from upwork_assistant.adapters.upwork.mapper import map_job
from upwork_assistant.adapters.upwork.payload_models import RawJob
from upwork_assistant.domain.models import ExperienceLevel, JobType

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "upwork" / "search_page_dom.html"


@pytest.fixture
async def page() -> AsyncIterator[Page]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            browser_page = await browser.new_page()
            yield browser_page
        finally:
            await browser.close()


async def test_parses_all_ten_tiles(page: Page) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    await page.set_content(html, wait_until="domcontentloaded")

    raw_jobs = await parse_dom_fallback(page)

    assert len(raw_jobs) == 10


async def test_every_tile_validates_against_raw_job_schema(page: Page) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    await page.set_content(html, wait_until="domcontentloaded")

    raw_jobs = await parse_dom_fallback(page)

    for raw in raw_jobs:
        RawJob.model_validate(raw)


async def test_first_tile_fields_match_hand_inspected_ground_truth(page: Page) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    await page.set_content(html, wait_until="domcontentloaded")

    raw_jobs = await parse_dom_fallback(page)
    first = raw_jobs[0]

    title = first["title"]
    client = first["client"]
    attrs = first["attrs"]
    assert isinstance(title, str)
    assert isinstance(client, dict)
    assert isinstance(attrs, list)

    assert first["uid"] == "2096999665946940758"
    assert first["ciphertext"] == "~022096999665946940758"
    assert "Machine Learning" in title
    assert first["type"] == 2
    assert first["hourlyBudget"] == {"min": 30.0, "max": 60.0}
    assert first["amount"] == {"amount": 0}
    # В этом конкретном тайле бейдж `payment-verified` присутствует в
    # разметке (проверено по фикстуре вручную) — клиент верифицирован.
    assert client["isPaymentVerified"] is True
    assert first["tierText"] == "jsn_Expert_0"
    assert attrs
    assert {"prefLabel": "Python"} in attrs


async def test_empty_page_returns_empty_list_without_raising(page: Page) -> None:
    await page.set_content("<html><body></body></html>", wait_until="domcontentloaded")

    raw_jobs = await parse_dom_fallback(page)

    assert raw_jobs == []


async def test_first_tile_maps_end_to_end_to_correct_domain_job(page: Page) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    await page.set_content(html, wait_until="domcontentloaded")

    raw_jobs = await parse_dom_fallback(page)
    parsed = RawJob.model_validate(raw_jobs[0])
    job, _facts = map_job(parsed)

    assert job.job_type == JobType.HOURLY
    assert job.rate_range is not None
    assert job.rate_range.min_rate == Decimal("30")
    assert job.rate_range.max_rate == Decimal("60")
    assert job.experience_level == ExperienceLevel.EXPERT
