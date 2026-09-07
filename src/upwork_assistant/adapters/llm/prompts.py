"""Сборка промптов. Чистые функции — никакого сетевого кода и I/O.

Чтение `data/profile.md` — забота `services.proposal_service`, сюда текст
профиля попадает уже прочитанным, поэтому промпты тестируются без файловой
системы.
"""

from __future__ import annotations

from upwork_assistant.domain.models import JobPosting, Score

SCORING_SYSTEM_PROMPT = (
    "Ты — ассистент фрилансера на Upwork. Оцени вакансию по шкале от 0 до 10: "
    "насколько она подходит фрилансеру по описанию, бюджету, требованиям и "
    "надёжности заказчика. 10 — идеальный заказ, стоит откликаться немедленно. "
    "0 — совершенно не подходит или похоже на мошенничество. Дай короткое "
    "обоснование оценки на русском языке."
)

PROPOSAL_SYSTEM_PROMPT_TEMPLATE = (
    "Ты помогаешь фрилансеру писать отклики на вакансии Upwork. Пиши от первого "
    "лица, на английском языке (Upwork — англоязычная площадка), кратко и по "
    "делу: без общих фраз, с конкретной привязкой к описанию вакансии. Не "
    "придумывай опыт, которого нет в профиле ниже.\n\n"
    "Профиль фрилансера:\n{profile}"
)


def build_scoring_system_prompt() -> str:
    """Системный промпт скоринга — не зависит от конкретной вакансии."""
    return SCORING_SYSTEM_PROMPT


def build_scoring_user_prompt(job: JobPosting) -> str:
    """Описание вакансии для скоринга."""
    return _describe_job(job)


def build_proposal_system_prompt(profile_markdown: str) -> str:
    """Системный промпт генерации, с вклеенным профилем фрилансера."""
    return PROPOSAL_SYSTEM_PROMPT_TEMPLATE.format(profile=profile_markdown)


def build_proposal_user_prompt(job: JobPosting, score: Score) -> str:
    """Описание вакансии для генерации отклика, с результатом скоринга."""
    return (
        f"{_describe_job(job)}\n\n"
        f"Оценка релевантности: {score.value}/10. {score.reasoning}\n\n"
        "Напиши черновик отклика на эту вакансию."
    )


def _describe_job(job: JobPosting) -> str:
    lines = [
        f"Заголовок: {job.title}",
        f"Тип оплаты: {job.job_type.value}",
    ]
    if job.budget is not None:
        lines.append(f"Бюджет: {job.budget.amount} {job.budget.currency}")
    if job.rate_range is not None:
        lines.append(
            f"Почасовая ставка: {job.rate_range.min_rate}-{job.rate_range.max_rate} "
            f"{job.rate_range.currency}"
        )
    if job.experience_level is not None:
        lines.append(f"Уровень опыта: {job.experience_level.value}")
    if job.duration is not None:
        lines.append(f"Длительность: {job.duration}")
    if job.skills:
        lines.append(f"Навыки: {', '.join(job.skills)}")
    lines.append(
        "Заказчик: "
        f"страна {job.client.country or 'не указана'}, "
        f"платёж {'подтверждён' if job.client.payment_verified else 'не подтверждён'}, "
        f"потрачено {job.client.total_spend} $, "
        f"рейтинг {job.client.avg_rating if job.client.avg_rating is not None else 'нет отзывов'}, "
        f"отзывов {job.client.reviews_count}"
    )
    lines.append(f"\nОписание:\n{job.description}")
    return "\n".join(lines)
