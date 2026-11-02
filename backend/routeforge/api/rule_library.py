from dataclasses import asdict
from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from routeforge.api.deps import require_admin
from routeforge.rule_library import (
    MAX_PAGE_SIZE,
    MAX_QUERY_LENGTH,
    PAGE_SIZE,
    LibraryIndex,
    LibraryUnavailable,
    RuleLibrary,
)

router = APIRouter(prefix="/api/rule-library", tags=["rule-library"], dependencies=[Depends(require_admin)])


class LibraryItemOut(BaseModel):
    category: str
    name: str
    behavior: str
    url: str


class LibraryIndexOut(BaseModel):
    updated_at: datetime | None
    error: str | None
    items: list[LibraryItemOut]


class RuleContentOut(BaseModel):
    total: int
    matched: int
    offset: int
    lines: list[str]


def _library(request: Request) -> RuleLibrary:
    return request.app.state.rule_library


def _index_out(lib: RuleLibrary, force: bool) -> LibraryIndexOut:
    try:
        idx: LibraryIndex = lib.index(force=force)
    except LibraryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return LibraryIndexOut(updated_at=idx.updated_at, error=idx.error,
                           items=[LibraryItemOut(**asdict(i)) for i in idx.items])


@router.get("")
def get_index(lib: RuleLibrary = Depends(_library)) -> LibraryIndexOut:
    return _index_out(lib, force=False)


@router.post("/refresh")
def refresh_index(lib: RuleLibrary = Depends(_library)) -> LibraryIndexOut:
    return _index_out(lib, force=True)


@router.get("/{category}/{name}/content")
def get_content(
    category: str,
    name: str,
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = PAGE_SIZE,
    lib: RuleLibrary = Depends(_library),
) -> RuleContentOut:
    """分页返回规则内容；q 为服务端检索（不区分大小写的子串匹配）。"""
    try:
        content = lib.content(category, name, q=q, offset=offset, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="规则不存在") from exc
    except LibraryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RuleContentOut(**asdict(content))
