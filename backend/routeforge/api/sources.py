from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, func, select

from routeforge.api.deps import CacheDep, HttpDep, SessionDep, require_admin
from routeforge.db.models import NodeRow, Source
from routeforge.parsers.clash_proxy import from_clash, to_clash
from routeforge.parsers.errors import ParseError, UnsupportedNode
from routeforge.parsers.manual import parse_manual_input
from routeforge.parsers.uri import LineError
from routeforge.services.library import append_nodes, delete_source, existing_names
from routeforge.sources.refresh import refresh_source

router = APIRouter(prefix="/api/sources", tags=["sources"], dependencies=[Depends(require_admin)])


def _valid_url(url: str | None) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        return bool(httpx.URL(url).host)
    except httpx.InvalidURL:
        return False


class SourceIn(BaseModel):
    kind: Literal["manual", "subscription"]
    name: str = Field(min_length=1, max_length=100)
    url: str | None = None
    refresh_interval: int = Field(default=360, ge=10, le=10080)
    user_agent: str = Field(default="clash.meta", min_length=1)

    @model_validator(mode="after")
    def _check_url(self) -> "SourceIn":
        if self.kind == "subscription" and not _valid_url(self.url):
            raise ValueError("订阅源需要 http(s) 链接")
        if self.kind == "manual":
            self.url = None
        return self


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = None
    refresh_interval: int | None = Field(default=None, ge=10, le=10080)
    user_agent: str | None = Field(default=None, min_length=1)


class SourceOut(BaseModel):
    id: int
    kind: str
    name: str
    url: str | None
    refresh_interval: int
    user_agent: str
    last_fetched_at: datetime | None
    last_error: str | None
    userinfo: dict | None
    node_count: int


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)


class ParsedNode(BaseModel):
    name: str
    type: str
    server: str
    port: int
    port_range: str | None = None
    config: dict


class ParseOut(BaseModel):
    nodes: list[ParsedNode]
    errors: list[LineError]
    existing_names: list[str]


class ImportItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    config: dict


class ImportIn(BaseModel):
    nodes: list[ImportItem] = Field(min_length=1, max_length=5000)


class ImportOut(BaseModel):
    added: int


class RefreshOut(BaseModel):
    ok: bool
    error: str | None = None
    added: int = 0
    updated: int = 0
    removed: int = 0
    parse_errors: list[LineError] = []


def _get(session: Session, source_id: int) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="节点源不存在")
    return source


def _out(session: Session, source: Source) -> SourceOut:
    count = session.exec(select(func.count()).select_from(NodeRow).where(NodeRow.source_id == source.id)).one()
    return SourceOut(**source.model_dump(), node_count=count)


@router.get("")
def list_sources(session: SessionDep) -> list[SourceOut]:
    return [_out(session, s) for s in session.exec(select(Source).order_by(Source.id)).all()]


@router.post("", status_code=201)
def create_source(body: SourceIn, session: SessionDep, http: HttpDep, cache: CacheDep) -> SourceOut:
    source = Source(**body.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    if source.kind == "subscription":
        refresh_source(session, source, http)
    cache.invalidate()
    return _out(session, source)


@router.patch("/{source_id}")
def update_source(source_id: int, body: SourcePatch, session: SessionDep, cache: CacheDep) -> SourceOut:
    source = _get(session, source_id)
    changes = body.model_dump(exclude_none=True)
    if "url" in changes:
        if source.kind != "subscription":
            raise HTTPException(status_code=400, detail="手动节点源没有订阅链接")
        if not _valid_url(changes["url"]):
            raise HTTPException(status_code=400, detail="订阅源需要 http(s) 链接")
        if changes["url"] != source.url:
            source.last_fetched_at = None
    for key, value in changes.items():
        setattr(source, key, value)
    session.add(source)
    session.commit()
    session.refresh(source)
    cache.invalidate()
    return _out(session, source)


@router.delete("/{source_id}", status_code=204)
def remove_source(source_id: int, session: SessionDep, cache: CacheDep) -> Response:
    delete_source(session, _get(session, source_id))
    cache.invalidate()
    return Response(status_code=204)


@router.post("/{source_id}/refresh")
def refresh(source_id: int, session: SessionDep, http: HttpDep, cache: CacheDep) -> RefreshOut:
    source = _get(session, source_id)
    if source.kind != "subscription":
        raise HTTPException(status_code=400, detail="手动节点源无需刷新")
    outcome = refresh_source(session, source, http)
    cache.invalidate()
    sync = outcome.sync
    return RefreshOut(
        ok=outcome.ok,
        error=outcome.error,
        added=sync.added if sync else 0,
        updated=sync.updated if sync else 0,
        removed=sync.removed if sync else 0,
        parse_errors=outcome.parse_errors,
    )


def _require_manual_source(session: Session, source_id: int) -> Source:
    source = _get(session, source_id)
    if source.kind != "manual":
        raise HTTPException(status_code=400, detail="订阅源的节点由订阅内容决定，不能手动导入")
    return source


@router.post("/{source_id}/nodes/parse")
def parse_nodes(source_id: int, body: ParseIn, session: SessionDep) -> ParseOut:
    """只解析、不写库：返回可勾选的节点、解析错误和该节点源已有的节点名。"""
    source = _require_manual_source(session, source_id)
    outcome = parse_manual_input(body.text)
    nodes: list[ParsedNode] = []
    errors = list(outcome.errors)
    for node in outcome.nodes:
        try:
            config = to_clash(node)
        except UnsupportedNode as e:
            errors.append(LineError(line=node.name, message=str(e)))
            continue
        nodes.append(ParsedNode(name=node.name, type=node.type, server=node.server, port=node.port,
                                port_range=getattr(node, "port_range", None), config=config))
    return ParseOut(nodes=nodes, errors=errors, existing_names=existing_names(session, source.id))


@router.post("/{source_id}/nodes/import")
def import_nodes(source_id: int, body: ImportIn, session: SessionDep, cache: CacheDep) -> ImportOut:
    """导入勾选的节点：逐个重新校验，任一无效则整批拒绝。"""
    source = _require_manual_source(session, source_id)
    nodes = []
    for i, item in enumerate(body.nodes, start=1):
        name = item.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail=f"第 {i} 个节点名称不能为空")
        try:
            nodes.append(from_clash({**item.config, "name": name}))
        except ParseError as e:
            raise HTTPException(status_code=400, detail=f"第 {i} 个节点「{name}」无效：{e}") from e
    added = append_nodes(session, source.id, nodes)
    cache.invalidate()
    return ImportOut(added=added)
