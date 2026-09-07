"""DOM-фолбэк парсинга вакансий.

Основной путь — извлечение embedded Nuxt state (`ssr_state.py`). Этот
модуль включается, только если оно не удалось (например, Upwork
переименовал `window.__NUXT__` или сменил формат сериализации) — тогда
дрейф схемы виден по алерту, а не тихо теряет вакансии, как было в
Kwork-версии.

Селекторы (`data-test="JobTile"` и вложенные) сняты вручную с реального
DOM страницы поиска 2026-09-07 — Upwork их не документирует, они могут
измениться без предупреждения. Результат парсинга собирается в те же
ключи, что и `payload_models.RawJob`, и проходит ту же валидацию и маппинг
(`mapper.map_job`), что и основной путь — единая точка преобразования в
домен, а не отдельная параллельная логика.

Из DOM недоступно то, что есть в embedded state: `uid` (используем
ciphertext как external_id — он тоже стабилен и уникален), точная дата
публикации (только относительная фраза вида "Posted 2 hours ago" —
переводим в приблизительный UTC-момент), полное описание (только
обрезанный сниппет) и весь список навыков (видны первые ~6, дальше Upwork
прячет их за "+N").
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from patchright.async_api import Locator, Page

logger = logging.getLogger(__name__)

_CIPHERTEXT_PATTERN = re.compile(r"(~\d+)/?(?:\?|$)")

_EXPERIENCE_TEXT_MAP = {
    "entry level": "EntryLevel",
    "intermediate": "Intermediate",
    "expert": "Expert",
}

# Известные формулировки Upwork для конкуренции по откликам. Порядок важен:
# более специфичные шаблоны — раньше общих.
_PROPOSAL_TIER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"fewer than 5", re.IGNORECASE), "lessThan5"),
    (re.compile(r"50\s*\+", re.IGNORECASE), "50Plus"),
    (re.compile(r"(\d+)\s*to\s*(\d+)", re.IGNORECASE), r"\1to\2"),
)

_RELATIVE_TIME_PATTERN = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", re.IGNORECASE
)
_RELATIVE_TIME_UNITS = {
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "week": "weeks",
    "month": "days",  # timedelta не умеет в месяцы — грубое приближение (×30)
}


async def parse_dom_fallback(page: Page) -> list[dict[str, object]]:
    """Собрать сырые вакансии из DOM уже загруженной страницы поиска."""
    tiles = page.locator('[data-test="JobTile"]')
    count = await tiles.count()
    if count == 0:
        logger.warning(
            "DOM-фолбэк не нашёл ни одного [data-test=\"JobTile\"] на %s — "
            "разметка страницы, вероятно, тоже изменилась",
            page.url,
        )
        return []

    logger.warning("DOM-фолбэк разбирает %d вакансий на %s (аварийный путь)", count, page.url)

    raw_jobs: list[dict[str, object]] = []
    for index in range(count):
        try:
            raw = await _parse_tile(tiles.nth(index))
        except Exception:
            logger.exception("DOM-фолбэк не смог разобрать вакансию #%d", index)
            continue
        if raw is not None:
            raw_jobs.append(raw)
    return raw_jobs


async def _parse_tile(tile: Locator) -> dict[str, object] | None:
    title_link = tile.locator('[data-test~="job-tile-title-link"]')
    href = await title_link.get_attribute("href")
    if href is None:
        return None
    match = _CIPHERTEXT_PATTERN.search(href)
    if match is None:
        logger.warning("Не удалось достать ciphertext из href %r", href)
        return None
    ciphertext = match.group(1)

    title = (await title_link.inner_text()).strip()
    description = await _text_or_empty(tile.locator(".JobDescription p"))

    job_type_text = await _text_or_empty(tile.locator('[data-test="job-type-label"] strong'))
    is_hourly = job_type_text.lower().startswith("hourly")

    amount: dict[str, object] = {"amount": 0}
    hourly_budget: dict[str, object] = {"min": 0, "max": 0}
    if is_hourly:
        min_rate, max_rate = _parse_hourly_range(job_type_text)
        hourly_budget = {"min": min_rate, "max": max_rate}
    else:
        budget_text = await _text_or_empty(
            tile.locator('[data-test="is-fixed-price"] strong.rr-mask')
        )
        amount = {"amount": _parse_money(budget_text)}

    experience_text = await _text_or_empty(tile.locator('[data-test="experience-level"] strong'))
    tier_key = _EXPERIENCE_TEXT_MAP.get(experience_text.strip().lower())
    tier_text = f"jsn_{tier_key}_0" if tier_key is not None else None
    if tier_text is None and experience_text:
        logger.warning("Неизвестный текст уровня опыта в DOM: %r", experience_text)

    proposals_text = await _text_or_empty(tile.locator('[data-test="proposals-tier"]'))
    proposals_tier = _parse_proposals_tier(proposals_text)

    duration_label = await _text_or_empty(
        tile.locator('[data-test="duration-label"] strong').last
    )

    country_text = await _text_or_empty(tile.locator('[data-test="location"] span.rr-mask'))
    country: str | None = re.sub(r"^Location\s*", "", country_text).strip() or None

    is_payment_verified = await tile.locator('[data-test="payment-verified"]').count() > 0
    total_spent_text = await _text_or_empty(tile.locator('[data-test="total-spent"] strong'))
    total_spent = _parse_money(total_spent_text)

    posted_text = await _text_or_empty(tile.locator('[data-test="job-pubilshed-date"] span').first)
    published_on = _parse_relative_time(posted_text)

    skills = await tile.locator('[data-test="token"] span').all_inner_texts()

    return {
        "uid": _ciphertext_to_uid(ciphertext),
        "ciphertext": ciphertext,
        "title": title,
        "description": description,
        "publishedOn": published_on.isoformat(),
        "type": 2 if is_hourly else 1,
        "durationLabel": duration_label or None,
        "amount": amount,
        "hourlyBudget": hourly_budget,
        "client": {
            "location": {"country": country},
            "isPaymentVerified": is_payment_verified,
            "totalSpent": str(total_spent),
            "totalReviews": 0,
            "totalFeedback": None,
        },
        "tierText": tier_text,
        "proposalsTier": proposals_tier,
        "attrs": [{"prefLabel": skill.strip()} for skill in skills if skill.strip()],
    }


def _ciphertext_to_uid(ciphertext: str) -> str:
    """Достать числовой `uid` из `ciphertext` вида `~02<uid>` (снято с реальных данных).

    Совпадает с `uid` из embedded state — важно для дедупа: если бы DOM-путь
    порождал другой external_id для той же вакансии, при следующем удачном
    цикле через основной путь она завелась бы в БД повторно. Если префикс
    когда-нибудь окажется другим, деградируем до всего `ciphertext` без "~" —
    самосогласованно внутри DOM-пути, но может разойтись с основным путём.
    """
    if ciphertext.startswith("~02"):
        return ciphertext[3:]
    return ciphertext.lstrip("~")


async def _text_or_empty(locator: Locator) -> str:
    if await locator.count() == 0:
        return ""
    text = await locator.inner_text()
    return text.strip()


def _parse_money(text: str) -> float:
    digits = re.sub(r"[^\d.]", "", text)
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def _parse_hourly_range(text: str) -> tuple[float, float]:
    numbers = re.findall(r"[\d.]+", text)
    if len(numbers) >= 2:
        return float(numbers[0]), float(numbers[1])
    if len(numbers) == 1:
        return float(numbers[0]), float(numbers[0])
    return 0.0, 0.0


def _parse_proposals_tier(text: str) -> str | None:
    for pattern, suffix_template in _PROPOSAL_TIER_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            suffix = match.expand(suffix_template) if match.groups() else suffix_template
            return f"usnuxt_JobProposalTier_418.{suffix}"
    if text:
        logger.warning("Неизвестная формулировка конкуренции в DOM: %r", text)
    return None


def _parse_relative_time(text: str) -> datetime:
    """`"Posted 2 hours ago"` -> приблизительный момент в UTC. Пусто -> сейчас."""
    now = datetime.now(UTC)
    match = _RELATIVE_TIME_PATTERN.search(text)
    if match is None:
        return now
    amount = int(match.group(1))
    unit = match.group(2).lower()
    kwarg = _RELATIVE_TIME_UNITS.get(unit)
    if kwarg is None:
        return now
    multiplier = 30 if unit == "month" else 1
    return now - timedelta(**{kwarg: amount * multiplier})
