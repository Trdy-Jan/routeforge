"""节点库读写：手动导入、订阅同步、加载为 resolver 输入。"""

from dataclasses import dataclass

from sqlmodel import Session, func, select

from routeforge.db.models import NodeRow, Source
from routeforge.ir.node import Node
from routeforge.resolver import LibraryNode


@dataclass
class SyncResult:
    added: int
    updated: int
    removed: int


def load_library(session: Session) -> list[LibraryNode]:
    rows = session.exec(select(NodeRow).order_by(NodeRow.source_id, NodeRow.position, NodeRow.id)).all()
    return [LibraryNode(id=r.id, source_id=r.source_id, enabled=r.enabled, node=r.to_node()) for r in rows]


def existing_names(session: Session, source_id: int) -> list[str]:
    return list(session.exec(select(NodeRow.name).where(NodeRow.source_id == source_id)).all())


def append_nodes(session: Session, source_id: int, nodes: list[Node]) -> int:
    """把节点按顺序追加到节点源末尾，返回追加数量。"""
    current = session.exec(select(func.max(NodeRow.position)).where(NodeRow.source_id == source_id)).one()
    start = 0 if current is None else current + 1
    for i, node in enumerate(nodes):
        session.add(NodeRow.from_node(source_id, node, start + i))
    session.commit()
    return len(nodes)


def sync_nodes(session: Session, source_id: int, nodes: list[Node]) -> SyncResult:
    rows = session.exec(
        select(NodeRow).where(NodeRow.source_id == source_id).order_by(NodeRow.position, NodeRow.id)
    ).all()
    by_name: dict[str, list[NodeRow]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)

    added = updated = 0
    for position, node in enumerate(nodes):
        bucket = by_name.get(node.name)
        if bucket:
            row = bucket.pop(0)
            row.set_node(node)
            row.position = position
            session.add(row)
            updated += 1
        else:
            session.add(NodeRow.from_node(source_id, node, position))
            added += 1

    leftovers = [row for bucket in by_name.values() for row in bucket]
    for row in leftovers:
        session.delete(row)
    session.commit()
    return SyncResult(added=added, updated=updated, removed=len(leftovers))


def delete_source(session: Session, source: Source) -> None:
    for row in session.exec(select(NodeRow).where(NodeRow.source_id == source.id)).all():
        session.delete(row)
    session.delete(source)
    session.commit()
