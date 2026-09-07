"""Пресеты фильтров: матчинг вакансии против набора активных пресетов.

Пресеты перечитываются из БД заново на каждый цикл опроса (см.
`ingest_service.py`) — не кешируются между циклами, поэтому правка пресета
через REST API применяется со следующего же цикла, без перезапуска процесса
(в Kwork-версии пресеты жили только в RAM-синглтоне и терялись при рестарте).
"""

from __future__ import annotations

from collections.abc import Sequence

from upwork_assistant.domain.filters import FilterSet, evaluate
from upwork_assistant.domain.models import JobPosting


def matches_any(job: JobPosting, active_filter_sets: Sequence[FilterSet]) -> bool:
    """Вакансия проходит, если нет активных пресетов или подходит хотя бы под один.

    Пустой список активных пресетов ничего не отфильтровывает: пользователь
    без единого настроенного пресета получает все вакансии, а не молча
    теряет их из-за отсутствия правил.
    """
    if not active_filter_sets:
        return True
    return any(evaluate(job, filter_set) for filter_set in active_filter_sets)
