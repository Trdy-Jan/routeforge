import pytest
from fastapi.testclient import TestClient

from routeforge.app import create_app
from routeforge.auth import ConfigError, LoginLimiter
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD


def test_login_me_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json() == {"admin": True}
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_session_cookie_flags(client):
    resp = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    cookie = resp.headers["set-cookie"].lower()
    assert "routeforge_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_lockout_after_five_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 429


def test_limiter_unlocks_after_lockout_window():
    now = [0.0]
    limiter = LoginLimiter(max_failures=2, window=60, lockout=100, clock=lambda: now[0])
    limiter.record_failure("ip")
    now[0] = 61  # 第一次失败已滑出窗口
    limiter.record_failure("ip")
    assert not limiter.is_locked("ip")
    limiter.record_failure("ip")
    assert limiter.is_locked("ip")
    now[0] = 162
    assert not limiter.is_locked("ip")


def test_non_json_post_rejected(client):
    resp = client.post("/api/auth/login", data={"password": ADMIN_PASSWORD})
    assert resp.status_code == 415


def test_first_start_requires_admin_password(tmp_path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{(tmp_path / 'r.db').as_posix()}",
                        admin_password=None, cookie_secure=False)
    with pytest.raises(ConfigError):
        create_app(settings, start_scheduler=False)


def test_password_only_needed_on_first_start(tmp_path):
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    create_app(Settings(data_dir=tmp_path, database_url=url, admin_password="first", cookie_secure=False),
               start_scheduler=False)
    app = create_app(Settings(data_dir=tmp_path, database_url=url, admin_password=None, cookie_secure=False),
                     start_scheduler=False)
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"password": "first"}).status_code == 200


def test_session_invalidated_when_password_hash_recreated(tmp_path):
    from sqlmodel import Session, select
    from routeforge.db.models import Setting

    def settings(pw):
        return Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'rf.db'}",
                        admin_password=pw, cookie_secure=False)

    app1 = create_app(settings("first"), start_scheduler=False)
    with TestClient(app1) as c1:
        assert c1.post("/api/auth/login", json={"password": "first"}).status_code == 200
        cookie = c1.cookies.get("routeforge_session")
        assert c1.get("/api/auth/me").status_code == 200
    with Session(app1.state.engine) as s:
        s.delete(s.get(Setting, "admin_password_hash"))
        s.commit()
    app1.state.engine.dispose()

    app2 = create_app(settings("second"), start_scheduler=False)
    with TestClient(app2) as c2:
        c2.cookies.set("routeforge_session", cookie)
        assert c2.get("/api/auth/me").status_code == 401
        c2.cookies.clear()
        assert c2.post("/api/auth/login", json={"password": "second"}).status_code == 200


def test_oversized_password_is_422(client):
    assert client.post("/api/auth/login", json={"password": "x" * 1025}).status_code == 422


def test_docs_and_openapi_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
