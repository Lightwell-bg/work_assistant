"""Управление пресетами фильтров.

Пресет создаётся/полностью заменяется через `PUT /filters/{name}` (upsert
по имени) — частичного PATCH намеренно нет: `FilterSetRepository.save`
заменяет правила целиком, отдельного метода для точечного изменения нет.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from upwork_assistant.adapters.db.repositories import UnknownFilterSetError
from upwork_assistant.api.deps import UowDep
from upwork_assistant.api.schemas import (
    FilterSetIn,
    FilterSetOut,
    filter_rule_in_to_domain,
    filter_set_out_from_domain,
)
from upwork_assistant.domain.filters import FilterSet

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("", response_model=list[FilterSetOut])
async def list_filters(uow: UowDep) -> list[FilterSetOut]:
    """Список пресетов.

    Известный пробел: `FilterSetRepository` умеет отдавать только активные
    пресеты (`list_active`) — отключённые через этот эндпоинт не видны.
    """
    filter_sets = await uow.filter_sets.list_active()
    return [filter_set_out_from_domain(fs) for fs in filter_sets]


@router.put("/{name}", response_model=FilterSetOut)
async def upsert_filter(name: str, body: FilterSetIn, uow: UowDep) -> FilterSetOut:
    """Создать пресет или полностью заменить его правила (по имени)."""
    filter_set = FilterSet(
        name=name,
        match_mode=body.match_mode,
        is_active=body.is_active,
        rules=tuple(filter_rule_in_to_domain(rule) for rule in body.rules),
    )
    await uow.filter_sets.save(filter_set)
    return filter_set_out_from_domain(filter_set)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_filter(name: str, uow: UowDep) -> None:
    """Удалить пресет по имени."""
    try:
        await uow.filter_sets.delete(name)
    except UnknownFilterSetError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Пресет {name!r} не найден"
        ) from error
