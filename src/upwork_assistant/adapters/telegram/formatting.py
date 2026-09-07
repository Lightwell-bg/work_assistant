"""Форматирование сообщений в Telegram: только plain-text.

Без Markdown/HTML `parse_mode` намеренно: заголовок и описание вакансии —
произвольный пользовательский контент с биржи, который может содержать
символы, ломающие разметку (`_`, `*`, `<`, `&` и т.п.). Экранировать их
ради форматирования не стоит — простой текст безопаснее и достаточен.
"""

from __future__ import annotations

from upwork_assistant.domain.models import Draft, JobPosting, JobType, Score

_DRAFT_HARD_LIMIT = 4000
_TRUNCATION_NOTE = "\n\n[обрезано, полный текст в БД]"


def format_job_summary(job: JobPosting, score: Score) -> str:
    """Сводка вакансии для уведомления: без полного описания (см. `job.url`)."""
    lines = [job.title, job.url, f"Тип: {job.job_type.value}"]

    if job.job_type is JobType.FIXED and job.budget is not None:
        lines.append(f"Бюджет: {job.budget.amount} {job.budget.currency}")
    elif job.job_type is JobType.HOURLY and job.rate_range is not None:
        min_rate = job.rate_range.min_rate
        max_rate = job.rate_range.max_rate
        lines.append(f"Ставка: {min_rate}-{max_rate} {job.rate_range.currency}/ч")

    if job.duration is not None:
        lines.append(f"Длительность: {job.duration}")
    if job.experience_level is not None:
        lines.append(f"Уровень опыта: {job.experience_level.value}")
    if job.skills:
        lines.append(f"Навыки: {', '.join(job.skills)}")

    client = job.client
    client_parts = []
    if client.country is not None:
        client_parts.append(client.country)
    payment_status = "оплата подтверждена" if client.payment_verified else "оплата не подтверждена"
    client_parts.append(payment_status)
    client_parts.append(f"потрачено {client.total_spend}")
    if client.avg_rating is not None:
        client_parts.append(f"рейтинг {client.avg_rating}")
    client_parts.append(f"отзывов: {client.reviews_count}")
    lines.append("Клиент: " + ", ".join(client_parts))

    lines.append(f"Оценка: {score.value}/10")
    lines.append(f"Обоснование: {score.reasoning}")

    return "\n".join(lines)


def format_draft_message(draft: Draft) -> str:
    """Текст черновика как есть — с усечением на пределе Telegram (4096 символов).

    Известное упрощение: длинный черновик режется одним сообщением с пометкой,
    а не разбивается на несколько — правильная разбивка вынесена за рамки фазы.
    """
    content = draft.content
    if len(content) > _DRAFT_HARD_LIMIT:
        return content[:_DRAFT_HARD_LIMIT] + _TRUNCATION_NOTE
    return content
