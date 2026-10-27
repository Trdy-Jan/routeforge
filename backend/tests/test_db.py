import pytest
from sqlmodel import Session, select

from routeforge.config import Settings
from routeforge.db.models import NodeRow, ProfileRow, Source
from routeforge.ir.node import Reality, TLSOptions, VlessNode
from routeforge.ir.profile import Profile


def test_node_row_stores_ir_as_json(engine):
    node = VlessNode(name="落地", server="ex.com", port=443, uuid="u",
                     tls=TLSOptions(reality=Reality(public_key="PK")))
    with Session(engine) as s:
        src = Source(kind="manual", name="手动")
        s.add(src)
        s.commit()
        s.refresh(src)
        s.add(NodeRow.from_node(src.id, node, position=0))
        s.commit()
    with Session(engine) as s:
        row = s.exec(select(NodeRow)).one()
        assert row.name == "落地"
        assert row.enabled is True
        assert row.to_node() == node
        row.set_node(node.model_copy(update={"name": "改名"}))
        assert row.name == "改名" and row.data["name"] == "改名"


def test_profile_row_new_has_token_and_empty_profile(engine):
    with Session(engine) as s:
        row = ProfileRow.new("我的方案")
        s.add(row)
        s.commit()
        s.refresh(row)
        assert len(row.token) >= 40
        assert row.to_profile() == Profile(name="我的方案")
        assert row.last_good is None
        row.set_profile(Profile(name="新名字"))
        assert row.name == "新名字"
        assert ProfileRow.new("x").token != row.token


def test_settings_from_env(tmp_path):
    s = Settings.from_env({"ROUTEFORGE_DATA_DIR": str(tmp_path), "ROUTEFORGE_COOKIE_SECURE": "false"})
    assert s.data_dir == tmp_path
    assert s.database_url == f"sqlite:///{(tmp_path / 'routeforge.db').as_posix()}"
    assert s.cookie_secure is False
    assert s.admin_password is None and s.static_dir is None

    d = Settings.from_env({"ROUTEFORGE_ADMIN_PASSWORD": "pw", "ROUTEFORGE_STATIC_DIR": "/srv/web"})
    assert d.cookie_secure is None and d.admin_password == "pw" and d.static_dir.as_posix() == "/srv/web"


@pytest.mark.parametrize("raw, expected", [
    ("true", True), ("1", True), ("YES", True), ("false", False), ("off", False),
    ("auto", None), (" Auto ", None), ("", None),
])
def test_settings_cookie_secure_modes(raw, expected):
    assert Settings.from_env({"ROUTEFORGE_COOKIE_SECURE": raw}).cookie_secure is expected
