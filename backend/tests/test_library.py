from sqlmodel import Session, select

from routeforge.db.models import NodeRow, Source
from routeforge.ir.node import SSNode
from routeforge.services.library import append_nodes, delete_source, existing_names, load_library, sync_nodes

def ss(name: str, port: int = 1) -> SSNode:
    return SSNode(name=name, server="1.1.1.1", port=port, cipher="aes-128-gcm", password="p")


def make_source(s: Session, kind: str = "manual") -> Source:
    src = Source(kind=kind, name=kind, url="https://x" if kind == "subscription" else None)
    s.add(src)
    s.commit()
    s.refresh(src)
    return src


def test_append_nodes_appends_to_end_and_existing_names(engine):
    with Session(engine) as s:
        src, other = make_source(s), make_source(s)
        assert append_nodes(s, src.id, [ss("A")]) == 1
        assert append_nodes(s, src.id, [ss("B"), ss("C")]) == 2
        append_nodes(s, other.id, [ss("Z")])
        rows = s.exec(select(NodeRow).where(NodeRow.source_id == src.id).order_by(NodeRow.position)).all()
        assert [(r.name, r.position) for r in rows] == [("A", 0), ("B", 1), ("C", 2)]
        assert sorted(existing_names(s, src.id)) == ["A", "B", "C"]


def test_sync_preserves_identity_and_enabled_and_handles_duplicates(engine):
    with Session(engine) as s:
        src = make_source(s, "subscription")
        sync_nodes(s, src.id, [ss("HK"), ss("HK"), ss("JP"), ss("US")])
        rows = {(r.name, r.position): r for r in s.exec(select(NodeRow)).all()}
        hk2_id = rows[("HK", 1)].id
        jp = rows[("JP", 2)]
        jp.enabled = False
        s.add(jp)
        s.commit()
        jp_id = jp.id

        result = sync_nodes(s, src.id, [ss("JP", port=2), ss("HK"), ss("HK"), ss("SG")])
        assert (result.added, result.updated, result.removed) == (1, 3, 1)

        after = s.exec(select(NodeRow).order_by(NodeRow.position)).all()
        assert [r.name for r in after] == ["JP", "HK", "HK", "SG"]
        assert after[0].id == jp_id and after[0].enabled is False and after[0].to_node().port == 2
        assert after[2].id == hk2_id
        assert "US" not in [r.name for r in after]


def test_sync_only_touches_its_own_source(engine):
    with Session(engine) as s:
        a, b = make_source(s, "subscription"), make_source(s, "subscription")
        sync_nodes(s, a.id, [ss("X")])
        sync_nodes(s, b.id, [ss("Y")])
        sync_nodes(s, a.id, [])
        assert [r.name for r in s.exec(select(NodeRow)).all()] == ["Y"]


def test_load_library_order_and_fields(engine):
    with Session(engine) as s:
        a, b = make_source(s), make_source(s)
        append_nodes(s, b.id, [ss("B")])
        append_nodes(s, a.id, [ss("A")])
        library = load_library(s)
        assert [(ln.source_id, ln.node.name) for ln in library] == [(a.id, "A"), (b.id, "B")]
        assert all(ln.enabled for ln in library)


def test_delete_source_removes_its_nodes(engine):
    with Session(engine) as s:
        src = make_source(s)
        src_id = src.id
        append_nodes(s, src_id, [ss("A")])
        delete_source(s, src)
        assert s.exec(select(NodeRow)).all() == []
        assert s.get(Source, src_id) is None
