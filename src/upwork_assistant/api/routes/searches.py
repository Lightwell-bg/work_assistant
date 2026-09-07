"""Управление сохранёнными поисками.

Источник и имя адресуют поиск в пути (`/searches/{source}/{name}`), поэтому
`PUT` — это идемпотентное «создать или заменить», как и у пресетов фильтров.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from upwork_assistant.adapters.db.repositories import UnknownSearchQueryError
from upwork_assistant.api.deps import UowDep
from upwork_assistant.api.schemas import (
    SearchQueryIn,
    SearchQueryOut,
    search_query_out_from_domain,
)
from upwork_assistant.domain.models import JobSourceName, SearchQuery

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("", response_model=list[SearchQueryOut])
async def list_searches(
    uow: UowDep,
    source: JobSourceName | None = Query(default=None),
) -> list[SearchQueryOut]:
    """Все поиски, опционально только одного источника (включая выключенные)."""
    searches = await uow.searches.list_all()
    if source is not None:
        searches = [search for search in searches if search.source is source]
    return [search_query_out_from_domain(search) for search in searches]


@router.put("/{source}/{name}", response_model=SearchQueryOut)
async def put_search(
    source: JobSourceName, name: str, body: SearchQueryIn, uow: UowDep
) -> SearchQueryOut:
    """Создать поиск или полностью заменить существующий."""
    search = SearchQuery(
        source=source, name=name, query=body.query, is_active=body.is_active
    )
    await uow.searches.save(search)
    return search_query_out_from_domain(search)


@router.delete("/{source}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(source: JobSourceName, name: str, uow: UowDep) -> None:
    try:
        await uow.searches.delete(source, name)
    except UnknownSearchQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
