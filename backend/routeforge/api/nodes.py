import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from routeforge.api.deps import CacheDep, SessionDep, require_admin
from routeforge.db.models import NodeRow, Source
from routeforge.ir.profile import Filter
from routeforge.resolver import match_filter
from routeforge.services.library import load_library

router = APIRouter(prefix="/api/nodes", tags=["nodes"], dependencies=[Depends(require_admin)])


class NodeOut(BaseModel):
    id: int
    source_id: int
    name: str
    type: str
    server: str
    port: int
    enabled: bool
    position: int
    data: dict


class NodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None


class BulkIn(BaseModel):
    ids: list[int] = Field(max_length=5000)
    enabled: bool


class BulkOut(BaseModel):
    updated: int


def _out(row: NodeRow) -> NodeOut:
    return NodeOut(id=row.id, source_id=row.source_id, name=row.name, type=row.data["type"],
                   server=row.data["server"], port=row.data["port"], enabled=row.enabled,
                   position=row.position, data=row.data)


def _get(session: Session, node_id: int) -> NodeRow:
    row = session.get(NodeRow, node_id)
    if row is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return row


def _require_manual(session: Session, row: NodeRow, action: str) -> None:
    source = session.get(Source, row.source_id)
    if source is None or source.kind != "manual":
        raise HTTPException(status_code=400, detail=f"订阅节点会在刷新时被覆盖，不能{action}")


@router.get("")
def list_nodes(session: SessionDep, source_id: int | None = None, q: str | None = None) -> list[NodeOut]:
    stmt = select(NodeRow).order_by(NodeRow.source_id, NodeRow.position, NodeRow.id)
    if source_id is not None:
        stmt = stmt.where(NodeRow.source_id == source_id)
    rows = session.exec(stmt).all()
    if q:
        rows = [r for r in rows if q.lower() in r.name.lower()]
    return [_out(r) for r in rows]


@router.patch("/{node_id}")
def update_node(node_id: int, body: NodePatch, session: SessionDep, cache: CacheDep) -> NodeOut:
    row = _get(session, node_id)
    if body.name is not None and body.name != row.name:
        _require_manual(session, row, "改名")
        row.set_node(row.to_node().model_copy(update={"name": body.name}))
    if body.enabled is not None:
        row.enabled = body.enabled
    session.add(row)
    session.commit()
    session.refresh(row)
    cache.invalidate()
    return _out(row)


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: int, session: SessionDep, cache: CacheDep) -> Response:
    row = _get(session, node_id)
    _require_manual(session, row, "删除（可以改为禁用）")
    session.delete(row)
    session.commit()
    cache.invalidate()
    return Response(status_code=204)


@router.post("/bulk")
def bulk_update(body: BulkIn, session: SessionDep, cache: CacheDep) -> BulkOut:
    rows = session.exec(select(NodeRow).where(col(NodeRow.id).in_(body.ids))).all()
    for row in rows:
        row.enabled = body.enabled
        session.add(row)
    session.commit()
    cache.invalidate()
    return BulkOut(updated=len(rows))


@router.post("/match")
def match_nodes(body: Filter, session: SessionDep) -> list[NodeOut]:
    try:
        matched = match_filter(load_library(session), body)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"正则无效：{e}") from e
    ids = [ln.id for ln in matched]
    rows = {r.id: r for r in session.exec(select(NodeRow).where(col(NodeRow.id).in_(ids))).all()}
    return [_out(rows[i]) for i in ids]
